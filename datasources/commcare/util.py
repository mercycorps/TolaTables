import json
import requests
import collections
from operator import itemgetter

from pymongo import MongoClient

from django.contrib import messages
from django.conf import settings

from tola.util import addColsToSilo
from silo.models import Read, ThirdPartyTokens, Silo
from commcare.models import CommCareCache

client = MongoClient(settings.MONGODB_URI)
db = client.get_database(settings.TOLATABLES_MONGODB_NAME)


# This gets a list of projects that users have used in the past to import
# data from commcare.
def get_projects(user_id):
    reads = Read.objects.filter(type__read_type='CommCare', owner_id=user_id)
    projects = []
    for read in reads:
        projects.append(read.read_url.split('/')[4])
    return list(set(projects))


# Get a list of reports available to the user
def get_commcare_report_ids(conf):
    url = 'https://www.commcarehq.org/a/%s/api/v0.5/' \
        'simplereportconfiguration/?format=JSON' % conf.project
    response = requests.get(url, headers=conf.auth_header)
    response_data = json.loads(response.content)
    report_ids = {}
    try:
        for rpt_info in response_data['objects']:
            report_ids[rpt_info['id']] = rpt_info['title']
    except KeyError:
        pass
    return report_ids


# Get a list of reports available to the user
def get_commcare_form_ids(conf):
    db_forms = CommCareCache.objects.filter(project=conf.project).values(
        'form_id', 'form_name', 'app_name')
    form_tuples = [(f['form_id'], f['app_name'] + ' - ' + f['form_name'])
                   for f in db_forms]
    form_tuples.sort(key=itemgetter(1))
    return form_tuples


# Retrieve record counts for commcare download.
def get_commcare_record_count(conf):
    # If 'configurablereportdata' is in the url, reports are being downloaded
    if 'configurablereportdata' in conf.base_url:
        url = 'https://www.commcarehq.org/a/%s/api/v0.5/' \
            'configurablereportdata/%s/?format=JSON&limit=1'
        url = url % (conf.project, conf.report_id)
        response = requests.get(url, headers=conf.auth_header)
        response_data = json.loads(response.content)
        return response_data['total_records']
    # Counts for forms and cases can be retrieved in the same way
    else:
        response = requests.get(conf.base_url, headers=conf.auth_header)
        response_data = json.loads(response.content)
        return response_data['meta']['total_count']


def copy_from_cache(cache_silo, silo, read):
    cached_data = db.label_value_store.find({
        'silo_id': cache_silo.id})
    for record in cached_data:
        record.pop('_id')
        record['silo_id'] = silo.id
        record['read_id'] = read.id
        db.label_value_store.insert(record)

    cols = []
    col_types = {}
    for col in json.loads(cache_silo.columns):
        cols.append(col['name'])
        col_types[col['name']] = col['type']
    addColsToSilo(silo, cols, col_types)


def flatten(data, parent_key='', sep='-'):
    items = []
    for k, v in data.items():
        new_key = parent_key + sep + k if parent_key else k
        if isinstance(v, collections.MutableMapping):
            items.extend(flatten(v, new_key, sep=sep).items())
        elif isinstance(v, list) and isinstance(v[0], collections.MutableMapping):
            flat_list = []
            for list_item in v:
                h = flatten(list_item, parent_key=new_key)
                flat_list.append(h)
            items.append((new_key, flat_list))
        else:
            items.append((new_key, v))
    return dict(items)




class CommCareImportConfig(object):
    def __init__(self, *args, **kwargs):
        self.download_type = kwargs.get('download_type', None)
        self.update = kwargs.get('update', False)
        self.base_url = kwargs.get('base_url', None)
        self.silo_id = kwargs.get('silo_id', None)
        self.read_id = kwargs.get('read_id', None)
        self.project = kwargs.get('project', None)
        self.report_id = kwargs.get('report_id', None)
        self.form_id = kwargs.get('form_id', None)
        self.record_count = kwargs.get('record_count', None)
        self.tables_user_id = kwargs.get('tables_user_id', None)
        self.use_token = kwargs.get('use_token', True)
        self.for_cache = kwargs.get('for_cache', False)
        self.tpt_username = kwargs.get('tpt_username', None)  # ThirdPartyToken
        self.token = kwargs.get('token', None)  # Dict includes username, token
        self.auth_header = kwargs.get('auth_header', None)

    def set_token(self):
        token_obj = ThirdPartyTokens.objects.get(
            user_id=self.tables_user_id, name="CommCare"
        )
        self.token = token_obj.token
        self.tpt_username = token_obj.username

    def set_auth_header(self):
        if not self.token:
            self.set_token()
        self.auth_header = {
            'Authorization': 'ApiKey %(u)s:%(a)s' %
            {'u': self.tpt_username, 'a': self.token}}

    def to_dict(self):
        return dict((k, v) for k, v in vars(self).iteritems())

    def __str__(self):
        return "\n".join("%s: %s" % (k, v) for k, v in vars(self).iteritems())
