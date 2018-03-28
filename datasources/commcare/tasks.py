# Create your tasks here
from __future__ import absolute_import, unicode_literals

from django.utils import timezone
from django.conf import settings

from celery import shared_task, group
from pymongo import MongoClient
from requests.auth import HTTPDigestAuth

from tola.util import getColToTypeDict, cleanKey, saveDataToSilo
from silo.models import Silo, Read

import requests
import json
import time


@shared_task(trail=True)
def fetchCommCareData(
        url, auth, auth_header, start, end, step,
        silo_id, read_id, download_type, extra_data, update=False):
    """
    This function will call the appointed functions to fetch the commcare data

    url -- the base url
    auth -- the authorization required
    auth_header -- True = use Header, False = use Digest authorization
    start -- What record to start at
    end -- what record to end at
    step -- # of records to get in one request
    silo_id -- the id of the silo being modified, may be empy
    read_id -- the id of the read being modified, may be empy
    download_type -- the type of download (commcare_form_name, etc...)
    extra_data -- the form or report that is to be downloaded, may be empty
    update -- if true use the update functionality
    """
    return group(requestCommCareData.s(
            url, offset, auth, auth_header, silo_id, read_id, download_type,
            extra_data, update, 0) for offset in xrange(start, end, step)
        )


@shared_task(trail=True)
def requestCommCareData(
            base_url, offset, auth, auth_header, silo_id, read_id,
            download_type, extra_data, update, req_count
        ):
    """
    This function will retrieve the appointed page of commcare data and
    return the data in an array.

    url -- the base url
    offset -- to get the records starting at n
    auth -- the authorization required
    auth_header -- True = use Header, False = use Digest authorization
    silo_id -- the id of the silo being modified, may be empy
    read_id -- the id of the read being modified, may be empy
    download_type -- the type of download (commcare_form_name, etc...)
    extra_data -- the form or report name that is to be fetched, may be empty
    update -- if true use the update functionality
    req_count -- number of times this function has called itself
    """

    MAX_RETRIES = 4
    url = base_url + "&offset=" + str(offset)
    if auth_header:
        response = requests.get(url, headers=auth)
    else:
        response = requests.get(url, auth=HTTPDigestAuth(auth['u'], auth['p']))
    if response.status_code == 200:
        data = json.loads(response.content)
    elif response.status_code == 429:
        if req_count > MAX_RETRIES:
            raise OSError("Too many requests to server")
        else:
            time.sleep(1)
            req_count += 1
            return requestCommCareData(
                url, offset, auth, auth_header, silo_id, read_id,
                download_type, extra_data, update, req_count
            )
    elif response.status_code == 404:
        raise OSError("Permission to CommCare server denied")
    else:
        if req_count > MAX_RETRIES:
            raise OSError("Unspecified CommCare download error")
        else:
            time.sleep(1)
            req_count += 1
            return requestCommCareData(
                url, offset, auth, auth_header, silo_id, read_id,
                download_type, extra_data, update, req_count
            )

    # Now get the properties of each dataset.
    if download_type == 'commcare_report':
        return parseCommCareReportData(
            data, silo_id, read_id, update, download_type)
    elif download_type == 'commcare_form':
        return parseCommCareFormData(
            data, silo_id, read_id, update, extra_data, download_type
        )
    else:
        return parseCommCareCaseData(
            data['objects'], silo_id, read_id, update, download_type
        )


@shared_task()
def parseCommCareCaseData(data, silo_id, read_id, update, download_type):
    data_properties = []
    data_columns = set()
    for entry in data:
        data_properties.append(entry['properties'])
        try:
            data_properties[-1]["user_case_id"] = \
                data_properties[-1].pop('case_id')
        except KeyError:
            pass
        data_properties[-1]["case_id"] = entry['case_id']
        data_columns.update(entry['properties'].keys())
    storeCommCareData(data_properties, silo_id, read_id, update, download_type)
    return list(data_columns)


@shared_task()
def parseCommCareFormData(
            data, silo_id, read_id, update, form_id, download_type
        ):
    exclude_tags = ['case', 'meta']
    data_properties = []
    data_columns = set()
    for row in data['objects']:
        filtered_data = {}
        for form_key in row['form'].keys():
            if form_key in exclude_tags or form_key[:1] in ['#', '@']:
                continue
            filtered_data[form_key] = row['form'][form_key]
        data_properties.append(filtered_data)
        data_columns.update(filtered_data.keys())
    storeCommCareData(data_properties, silo_id, read_id, update, download_type)
    return list(data_columns)


@shared_task()
def parseCommCareReportData(data, silo_id, read_id, update, download_type):
    data_properties = []
    data_columns = set()
    column_mapper = {}
    for c in data['columns']:
        column_mapper[c['slug']] = c['header']

    for row in data['data']:
        renamed_row = dict((column_mapper[col], row[col]) for col in row)
        data_properties.append(renamed_row)

    data_columns = column_mapper.values()
    storeCommCareData(data_properties, silo_id, read_id, update, download_type)
    return data_columns


@shared_task()
def storeCommCareData(data, silo_id, read_id, update, download_type):

    data_refined = []
    try:
        fieldToType = getColToTypeDict(Silo.objects.get(pk=silo_id))
    except Silo.DoesNotExist:
        fieldToType = {}
    for row in data:
        for column in row:
            if fieldToType.get(column, 'string') == 'int':
                try:
                    row[column] = int(row[column])
                except ValueError:
                    # skip this one
                    # add message that this is skipped
                    continue
            if fieldToType.get(column, 'string') == 'double':
                try:
                    row[column] = float(row[column])
                except ValueError:
                    # skip this one
                    # add message that this is skipped
                    continue
            row[cleanKey(column)] = row.pop(column)

        data_refined.append(row)

    db = getattr(
        MongoClient(settings.MONGODB_URI), settings.TOLATABLES_MONGODB_NAME
    )
    if update:
        if download_type == 'case':
            for row in data_refined:
                row['edit_date'] = timezone.now()
                db.label_value_store.update(
                    {'silo_id': silo_id, 'case_id': row['case_id']},
                    {"$set": row},
                    upsert=True
                )
        elif download_type == 'commcare_report':
            silo = Silo.objects.get(id=silo_id)
            read = Read.objects.get(id=read_id)
            db.label_value_store.delete_many({'silo_id': silo.pk})
            saveDataToSilo(silo, data_refined, read)
    else:

        for row in data_refined:
            row["create_date"] = timezone.now()
            row["silo_id"] = silo_id
            row["read_id"] = read_id
        db.label_value_store.insert(data_refined)


# @shared_task()
# def addExtraFields(columns, silo_id):
#     """
#     This function is no longer in use, but might be useful in the future
#     and as an example
#
#     This function makes sure all mongodb entries of a particular silo
#     share a columns.
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
