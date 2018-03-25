
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


#get a list of reports available to the user
def getCommCareReportIDs(project_name, header):
    url = 'https://www.commcarehq.org/a/%s/api/v0.5/simplereportconfiguration/?format=JSON' % project_name
    response = requests.get(url, headers=header)
    response_data = json.loads(response.content)
    report_ids = {}
    for rpt_info in response_data['objects']:
        report_ids[rpt_info['id']] = rpt_info['title']
    return report_ids

def getCommCareReportCount(project, auth_header, report_id):
    url = 'https://www.commcarehq.org/a/%s/api/v0.5/configurablereportdata/%s/?format=JSON&limit=1' % (project, report_id)
    print 'reptcout url ', url
    response = requests.get(url, headers=auth_header)
    response_data = json.loads(response.content)
    return response_data['total_records']


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
        record_limit = 3

    # replace the record limit
    base_url = url.replace('limit=1', 'limit=' + str(record_limit))

    # For reports, we need to save the current data so we can delete it after a
    # successful import
    if download_type == 'commcare_report' and update:
        # current_data = LabelValueStore.objects(silo_id=silo.id)
        # current_data = db.label_value_store.find({'silo_id':silo.id}, {'_id': 1}).to_array()
        # print 'currentdata', current_data.count(), current_data
        db.label_value_store.update({'silo_id':silo.id}, {'$set': {'silo_id':'old-'+str(silo.id)}}, multi=True)

    data_raw = fetchCommCareData(base_url, auth, auth_header,\
                    0, 10, record_limit, silo.id, read.id, \
                    download_type, extra_data)
    data_collects = data_raw.apply_async()
    data_retrieval = [v.get() for v in data_collects]
    columns = set()
    for data in data_retrieval:
        columns = columns.union(data)

    if download_type == 'commcare_report' and update:
        #delete the old data only if new data has been entered into MongoDB
        if columns:
            db.label_value_store.remove({'silo_id': 'old-'+str(silo.id)})
        else:
            db.label_value_store.update({'silo_id':'old-'+str(silo.id)}, {'$set': {'silo_id':silo.id}}, multi=True)
        # new_data = db.label_value_store.find({'silo_id':silo.id})
        # print 'new data', new_data.count, new_data
        # delete_result = db.label_value_store.delete_many(current_data)
        # print 'deleted?', delete_result.deleted_count
        # # for dat in current_data:
        #     print "deleting"
        #     del_count = dat.delete()
        #     print 'deleted this many', del_count
        # current_data.delete()

    #add new columns to the list of current columns this is slower because
    #order has to be maintained (2n instead of n)
    addColsToSilo(silo, columns)
    hideSiloColumns(silo, ["case_id"])
    return (messages.SUCCESS, "CommCare data imported successfully", columns)
