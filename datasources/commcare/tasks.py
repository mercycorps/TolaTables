# Create your tasks here
from __future__ import absolute_import, unicode_literals
from celery import shared_task, group, chain
from django.utils import timezone

from requests.auth import HTTPDigestAuth

from django.conf import settings
from pymongo import MongoClient
from pymongo.operations import UpdateMany

from tola.util import getColToTypeDict
from silo.models import Silo

import requests
import json
import time

@shared_task(trail=True)
def fetchCommCareData(url, auth, auth_header, start, end, step, silo_id, read_id, report_name, update=False) :
    """
    This function will call the appointed functions to retrieve the commcare data

    url -- the base url
    auth -- the authorization required
    auth_header -- True = use Header, False = use Digest authorization
    start -- What record to start at
    end -- what record to end at
    step -- # of records to get in one request
    update -- if true use the update functioality instead of the regular store furnctionality
    form -- if None download case data, otherwise download form data and save only specified form
    """
    print 'hey look url, auth, auth_header start, end, step, form', url, auth, auth_header, start, end, step, silo_id, read_id, report_name, update
    return group(requestCommCareData.s(url, offset, auth, auth_header, silo_id, read_id, report_name, update, 0) \
            for offset in xrange(start,end,step))


@shared_task(trail=True)
def requestCommCareData(base_url, offset, auth, auth_header, silo_id, read_id, report_name, update, req_count):
    """
    This function will retrieve the appointed page of commcare data and return the data in an array

    url -- the base url
    offset -- to get the records starting at n
    auth -- the authorization required
    auth_header -- True = use Header, False = use Digest authorization
    """

    MAX_RETRIES = 4
    print 'oh my gosh'
    url = base_url + "&offset=" + str(offset)
    print 'built url', url

    if auth_header:
        response = requests.get(url, headers=auth)
    else:
        response = requests.get(url, auth=HTTPDigestAuth(auth['u'],auth['p']))
    if response.status_code == 200:
        data = json.loads(response.content)
    elif response.status_code == 429:
        if req_count > MAX_RETRIES:
            raise ConnectionRefusedError
        else:
            time.sleep(1)
            req_count += 1
            return requestCommCareData(url, offset, auth, auth_header, silo_id, read_id, report_name, update, req_count)
    elif response.status_code == 404:
        raise URLNotFoundError(url)
    else:
        if req_count > MAX_RETRIES:
            raise ConnectionRefusedError
        else:
            #add something to this future error code stopping everything with throw exception
            time.sleep(1)
            print 'sleepytime'
            req_count += 1
            print "comeonnnn"
            return requestCommCareData(url, offset, auth, auth_header, silo_id, read_id, report_name, update)

    # Now get the properties of each data. Process form data and case data differently.
    if report_name:
        print 'just checkoung', data
        return parseCommCareReportData(data, silo_id, read_id, update, report_name)
    else:
        return parseCommCareCaseData(data['objects'], silo_id, read_id, update)



@shared_task()
def parseCommCareCaseData(data, silo_id, read_id, update):
    data_properties = []
    data_columns = set()
    for entry in data:
        data_properties.append(entry['properties'])
        try: data_properties[-1]["user_case_id"] = data_properties[-1].pop('case_id')
        except KeyError as e: pass
        data_properties[-1]["case_id"] = entry['case_id']
        data_columns.update(entry['properties'].keys())
    storeCommCareData(data_properties, silo_id, read_id, update)
    return list(data_columns)

@shared_task()
def parseCommCareFormData(data, silo_id, read_id, update, form):
    exclude_tags = ['case', 'meta']
    data_properties = []
    data_columns = set()
    for entry in data:
        filtered_data = {}
        for form_key in entry['objects']['form'].keys():
            if form_key in exclude_tags or form_key[:1] in ['#', '@']:
                continue
            filtered_data.update(entry['objects']['form'][form_key])
        data_properties.append(filtered_data)
        data_columns.update(filtered_data.keys())
        print 'data columns', data_columns
    storeCommCareData(data_properties, silo_id, read_id, update)
    return list(data_columns)

@shared_task()
def parseCommCareReportData(data, silo_id, read_id, update, report_name):
    print 'in report data'
    data_properties = []
    data_columns = set()
    column_mapper = {}
    for c in data['columns']:
        column_mapper[c['slug']] = c['header']
    print 'colmapper', column_mapper

    for row in data['data']:
        renamed_row = dict((column_mapper[col], row[col]) for col in row)
        print 'renameeed data', renamed_row
        data_properties.append(renamed_row)

    data_columns = column_mapper.values()
    storeCommCareData(data_properties, silo_id, read_id, update)
    return data_columns


@shared_task()
def storeCommCareData(data, silo_id, read_id, update):

    data_refined = []
    try:
        fieldToType = getColToTypeDict(Silo.objects.get(pk=silo_id))
    except Silo.DoesNotExist as e:
        fieldToType = {}
    for row in data:
        for column in row:
            if fieldToType.get(column, 'string') == 'int':
                try:
                    row[column] = int(row[column])
                except ValueError as e:
                    # skip this one
                    # add message that this is skipped
                    continue
            if fieldToType.get(column, 'string') == 'double':
                try:
                    row[column] = float(row[column])
                except ValueError as e:
                    # skip this one
                    # add message that this is skipped
                    continue
            row[column.replace(".", "_").replace("$", "USD")] = row.pop(column)
        try: row.pop("")
        except KeyError as e: pass
        try: row.pop("silo_id")
        except KeyError as e: pass
        try: row.pop("read_id")
        except KeyError as e: pass
        try: row["user_assigned_id"] = row.pop("id")
        except KeyError as e: pass
        try: row["user_assigned_id"] = row.pop("_id")
        except KeyError as e: pass
        try: row["editted_date"] = row.pop("edit_date")
        except KeyError as e: pass
        try: row["created_date"] = row.pop("create_date")
        except KeyError as e: pass
        row["silo_id"] = silo_id
        row["read_id"] = read_id


        data_refined.append(row)

    db = getattr(MongoClient(settings.MONGODB_URI), settings.TOLATABLES_MONGODB_NAME)
    if not update:
        for row in data_refined:
            row["create_date"] = timezone.now()
        db.label_value_store.insert(data_refined)
    else:
        for row in data_refined:
            row['edit_date'] = timezone.now()
            db.label_value_store.update(
                {'silo_id' : silo_id,
                'case_id' : row['case_id']},
                {"$set" : row},
                upsert=True
            )

# @shared_task()
# def addExtraFields(columns, silo_id):
#     """
#     This function makes sure all mongodb entries of a particular silo share a columns
#     This function is no longer in use, but might be useful in the future and as an example
#     """
#     db = MongoClient(settings.MONGODB_HOST).tola
#     mongo_request = []
#     db.label_value_store.create_index('silo_id')
#     for column in columns:
#         db.label_value_store.create_index('column')
#         mongo_request.append(UpdateMany(
#             {
#                 "silo_id" : silo_id,
#                 column : {"$not" : {"$exists" : "true"}}\
#             }, #filter
#             {"$set" : {column : ""}} #update
#         ))
#     db.label_value_store.bulk_write(mongo_request)
