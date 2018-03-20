
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


def getCommCareDataHelper(url, auth, auth_header, total_cases, silo, read, commcare_report_name):
    """
    Use fetch and request CommCareData to store all of the case data

    domain -- the domain name used for a commcare project
    auth -- the authorization required
    auth_header -- True = use Header, False = use Digest authorization
    total_cases -- total cases to get
    silo - silo to put the data into
    read -- read that the data is apart of
    """

    if commcare_report_name:
        record_limit = 50
    else:
        record_limit = 100
    # check if there are already parameters on the url
    if '?' in url:
        base_url = url + "&limit=" + str(record_limit)
    else:
        base_url = url + "?limit=" + str(record_limit)

    data_raw = fetchCommCareData(base_url, auth, auth_header,\
                    0, total_cases, record_limit, silo.id, read.id, commcare_report_name)
    data_collects = data_raw.apply_async()
    data_retrieval = [v.get() for v in data_collects]
    columns = set()
    for data in data_retrieval:
        columns = columns.union(data)

    #add new columns to the list of current columns this is slower because
    #order has to be maintained (2n instead of n)
    addColsToSilo(silo, columns)
    hideSiloColumns(silo, ["case_id"])
    return (messages.SUCCESS, "CommCare cases imported successfully", columns)
