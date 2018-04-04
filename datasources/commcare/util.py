
from silo.models import Read, ReadType
from django.contrib import messages
import json
import requests

from celery import group

from .tasks import fetchCommCareData, requestCommCareData, storeCommCareData

from silo.models import LabelValueStore, Silo
from tola.util import saveDataToSilo, addColsToSilo, hideSiloColumns
from pymongo import MongoClient
from django.conf import settings

client  = MongoClient(settings.MONGODB_URI)
db = client.get_database(settings.TOLATABLES_MONGODB_NAME)


#this gets a list of projects that users have used in the past to import data from commcare
#used in commcare/forms.py
def get_projects(user_id):
    reads = Read.objects.filter(type__read_type='CommCare', owner_id=user_id)
    projects = []
    for read in reads:
        projects.append(read.read_url.split('/')[4])
    return list(set(projects))


# get a list of reports available to the user
def get_commcare_report_ids(conf):
    url = 'https://www.commcarehq.org/a/%s/api/v0.5/simplereportconfiguration/?format=JSON' % conf.project
    print 'reportids conf', conf
    response = requests.get(url, headers=conf.auth_header)
    response_data = json.loads(response.content)
    report_ids = {}
    try:
        for rpt_info in response_data['objects']:
            report_ids[rpt_info['id']] = rpt_info['title']
    except KeyError:
        pass
    return report_ids

# Rectrieve record counts for commcare download.
def get_commcare_record_count(conf):
    # If 'configurablereportdata' is in the url, reports are being downloaded
    print "getcomreacordcount conf", conf
    if 'configurablereportdata' in conf.base_url:
        print 'in config report data', conf
        url = 'https://www.commcarehq.org/a/%s/api/v0.5/configurablereportdata/%s/?format=JSON&limit=1'
        url = url % (conf.project, conf.report_id)
        response = requests.get(url, headers=conf.auth_header)
        print 'response content for report', response.content
        response_data = json.loads(response.content)
        return response_data['total_records']
    # Counts for forms and cases can be retrieved in the same way
    else:
        print 'not in config report data', conf
        response = requests.get(conf.base_url, headers=conf.auth_header)
        response_data = json.loads(response.content)
        return response_data['meta']['total_count']



def getCommCareDataHelper(conf):
    """
    Use fetch and request CommCareData to store all of the case data

    domain -- the domain name used for a commcare project
    auth -- the authorization required
    auth_header -- True = use Header, False = use Digest authorization
    total_cases -- total cases to get
    silo - silo to put the data into
    read -- read that the data is apart of
    """

    # CommCare has a max limit of 50 for report downloads
    if conf.download_type == 'commcare_report':
        record_limit = 50
    else:
        record_limit = 100

    # replace the record limit
    base_url = conf.base_url.replace('limit=1', 'limit=' + str(record_limit))
    data_raw = fetchCommCareData(conf.to_dict(), base_url, 0, record_limit)
    data_collects = data_raw.apply_async()
    data_retrieval = [v.get() for v in data_collects]
    columns = set()
    for data in data_retrieval:
        columns = columns.union(data)

    #add new columns to the list of current columns this is slower because
    #order has to be maintained (2n instead of n)
    silo = Silo.objects.get(pk=conf.silo_id)
    addColsToSilo(silo, columns)
    hideSiloColumns(silo, ["case_id"])
    return (messages.SUCCESS, "CommCare data imported successfully", columns)

from silo.models import ThirdPartyTokens
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
        self.tpt_username = kwargs.get('tpt_username', None) #ThirdPartyTokens
        self.token = kwargs.get('token', None) # dict includes username, token
        self.auth_header = kwargs.get('auth_header', None)


    def set_token(self):
        print 'tuid', self.tables_user_id
        token_obj = ThirdPartyTokens.objects.get(
            user_id=self.tables_user_id, name="CommCare"
        )
        self.token = token_obj.token
        self.tpt_username = token_obj.username

    def set_auth_header(self):
        print 'inauthheader userid', self.tables_user_id
        if not self.token:
            self.set_token()
        self.auth_header = {'Authorization': 'ApiKey %(u)s:%(a)s' % \
            {'u' : self.tpt_username, 'a' : self.token}}

    def to_dict(self):
        return dict((k, v) for k, v in vars(self).iteritems())

    def __str__(self):
        return "\n".join("%s: %s" % (k, v) for k, v in vars(self).iteritems())

