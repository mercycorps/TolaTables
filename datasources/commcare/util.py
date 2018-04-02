
from silo.models import Read, ReadType
from django.contrib import messages
import json
import requests

from celery import group

from .tasks import fetchCommCareData, requestCommCareData, storeCommCareData

from silo.models import LabelValueStore
from tola.util import saveDataToSilo, addColsToSilo, hideSiloColumns
from pymongo import MongoClient
from django.conf import settings

client  = MongoClient(settings.MONGODB_URI)
db = client.get_database(settings.TOLATABLES_MONGODB_NAME)


#this gets a list of projects that users have used in the past to import data from commcare
#used in commcare/forms.py
def getProjects(user_id):
    reads = Read.objects.filter(type__read_type='CommCare', owner_id=user_id)
    projects = []
    for read in reads:
        projects.append(read.read_url.split('/')[4])
    return list(set(projects))


# get a list of reports available to the user
def getCommCareReportIDs(project_name, header):
    url = 'https://www.commcarehq.org/a/%s/api/v0.5/simplereportconfiguration/?format=JSON' % project_name
    response = requests.get(url, headers=header)
    response_data = json.loads(response.content)
    report_ids = {}
    try:
        for rpt_info in response_data['objects']:
            report_ids[rpt_info['id']] = rpt_info['title']
    except KeyError:
        pass
    return report_ids

# Rectrieve record counts for commcare download.
def getCommCareRecordCount(base_url, auth_header, project=None, extra_data=None):
    # If 'configurablereportdata' is in the url, reports are being downloaded
    if 'configurablereportdata' in base_url:
        url = 'https://www.commcarehq.org/a/%s/api/v0.5/configurablereportdata/%s/?format=JSON&limit=1' % (project, extra_data)
        response = requests.get(url, headers=auth_header)
        response_data = json.loads(response.content)
        return response_data['total_records']
    # Counts for forms and cases can be retrieved in the same way
    else:
        response = requests.get(base_url, headers=auth_header)
        response_data = json.loads(response.content)
        return response_data['meta']['total_count']



def getCommCareDataHelper(url, auth, auth_header, total_cases, silo, read, download_type, extra_data, update=False):
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
    if download_type == 'commcare_report':
        record_limit = 50
    else:
        record_limit = 100

    # replace the record limit
    base_url = url.replace('limit=1', 'limit=' + str(record_limit))

    data_raw = fetchCommCareData(base_url, auth, auth_header,\
                    0, total_cases, record_limit, silo.id, read.id, \
                    download_type, extra_data, update)
    data_collects = data_raw.apply_async()
    data_retrieval = [v.get() for v in data_collects]
    columns = set()
    for data in data_retrieval:
        columns = columns.union(data)

    #add new columns to the list of current columns this is slower because
    #order has to be maintained (2n instead of n)
    addColsToSilo(silo, columns)
    hideSiloColumns(silo, ["case_id"])
    return (messages.SUCCESS, "CommCare data imported successfully", columns)

from silo.models import ThirdPartyTokens
class CommCareImportConfig(object):
    def __init__(self, *args, **kwargs):
        self.download_type = kwargs.get('download_type', None)
        self.url = kwargs.get('url', None)
        self.silo = kwargs.get('silo', None)
        self.read = kwargs.get('read', None)
        self.project = kwargs.get('project', None)
        self.report_name = kwargs.get('report_name', None)
        self.tables_user = kwargs.get('user', None)
        self.tpt_username = kwargs.get('tpt_username', None) #ThirdPartyTokens
        self.token = kwargs.get('token', None) # dict includes username, token
        self.auth_header = kwargs.get('auth_header', None)


    def set_token(self):
        print 'in set token', self.__str__()
        self.token = ThirdPartyTokens.objects.get(
            username=self.tpt_username, name="CommCare"
        ).token

    def set_auth_header(self):
        if not self.token:
            self.set_token()
        self.auth_header = {'Authorization': 'ApiKey %(u)s:%(a)s' % \
            {'u' : self.tpt_username, 'a' : self.token}}

    def parseURL(url):
        url_parts = url.split('/')
        print url_parts[3], url_parts[6]

    def __str__(self):
        return "\n".join("%s: %s" % (k, v) for k, v in vars(self).iteritems())

