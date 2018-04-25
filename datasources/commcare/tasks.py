# Create your tasks here
from __future__ import absolute_import, unicode_literals
import json
import time
import datetime
import dateutil
import re
import pytz

import requests
from requests.auth import HTTPDigestAuth
from celery import shared_task, group
from pymongo import MongoClient

from django.db import IntegrityError
from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone

from commcare.models import CommCareCache
from commcare.util import flatten
from tola.util import getColToTypeDict, cleanKey, saveDataToSilo
from silo.models import Silo, Read, ReadType


@shared_task(trail=True)
def fetchCommCareData(conf, url, start, step):
    """
    This function will call the appointed functions to fetch the commcare data

    conf -- a CommCareImportConfig dict
    url -- the base url
    start -- What record to start at
    step -- # of records to get in one request
    """
    return group(requestCommCareData.s(
        conf, url, offset, 0) for offset in xrange(
            start, conf['record_count'], step))

    # return group(requestCommCareData.s(
    #     conf, url, offset, 0) for offset in xrange(
    #         start, 1000, step))


@shared_task(trail=True)
def requestCommCareData(conf, base_url, offset, req_count):
    """
    This function will retrieve the appointed page of commcare data and
    return the data in an array.

    conf -- a CommCareImportConfig dict
    url -- the base url
    offset -- number of records to skip when calling the CommCare API
    req_count -- number of times this function has called itself
    """

    # Limits the number of times this function can call itself
    MAX_RETRIES = 4

    # Request data from CommCare and process any errors
    url = base_url + "&offset=" + str(offset)

    if conf['use_token']:
        response = requests.get(url, headers=conf['auth_header'])
    else:
        response = requests.get(
            url, auth=HTTPDigestAuth(conf['tpt_username'], conf['password']))
    if response.status_code == 200:
        data = json.loads(response.content)
    elif response.status_code == 429:
        if req_count > MAX_RETRIES:
            raise OSError("Too many requests to server")
        else:
            time.sleep(2)
            req_count += 1
            return requestCommCareData(conf, base_url, offset, req_count)
    elif response.status_code == 404:
        raise OSError("Permission to CommCare server denied")
    else:
        if req_count > MAX_RETRIES:
            raise OSError("Unspecified CommCare download error")
        else:
            time.sleep(1)
            req_count += 1
            return requestCommCareData(conf, base_url, offset, req_count)

    # Parse the data and return the results
    if conf['download_type'] == 'commcare_report':
        return parseCommCareReportData(conf, data)
    elif conf['download_type'] == 'commcare_form':
        return parseCommCareFormData(conf, data)
    else:
        return parseCommCareCaseData(conf, data['objects'])


@shared_task()
def parseCommCareCaseData(conf, data):
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
    storeCommCareData(conf, data_properties)
    return list(data_columns)


@shared_task()
def parseCommCareFormData(conf, data):
    exclude_tags = ['case', 'meta']
    exclude_chars = ['#', '@']
    default_date = datetime.datetime(1980, 1, 1).replace(tzinfo=pytz.UTC)

    # Cacheing is handled differently because each row could be from a
    # different form and needs to be processed individually.  Also need to
    # check for a pre-existing cache entry or create one.
    if conf['for_cache']:
        data_columns = {}
        max_date = default_date
        for row in data['objects']:
            # Discard any entries that aren't form entries.  Sometimes they
            # are just updates to the Case information.
            match = re.search('formdesigner\/(.*)', row['form']['@xmlns'])
            if match:
                form_id = match.group(1)
            else:
                print 'Skipped ', row['form']['@xmlns']
                continue

            # Store the date if it's a max value
            row_date = dateutil.parser.parse(row['received_on']) \
                .replace(tzinfo=pytz.UTC)
            max_date = max(row_date, max_date)

            # Use the cached data if it exists, if there is no cache
            # create an entry for the current form
            try:
                cache_obj = CommCareCache.objects.get(form_id=form_id)
                conf['form_id'] = cache_obj.form_id
                conf['form_name'] = cache_obj.form_name
                conf['silo_id'] = cache_obj.silo_id
                conf['read_id'] = cache_obj.read_id
            except CommCareCache.DoesNotExist:
                created = False
                conf['form_id'] = form_id
                conf['form_name'] = row['form']['@name']
                user = User.objects.get(pk=conf['tables_user_id'])
                silo_name = "SAVE-Cache-%s-%s" % (
                    conf['project'], conf['form_name'])
                cache_url = re.sub('&received_on.*', '', conf['base_url'])
                read = Read.objects.create(
                    owner=user,
                    type=ReadType.objects.get(read_type='CommCare'),
                    read_name=silo_name[:100],
                    description=silo_name,
                    read_url=cache_url,
                    resource_id=conf['form_id'])
                silo = Silo.objects.create(
                    name=silo_name[:60], public=0, owner=user)
                silo.reads.add(read)

                # Additional try block accomodates a race condition
                # where a different celery worker has created the cache
                # between the exists-check and the creation step in this
                # worker.
                cache_obj, created = CommCareCache.objects.get_or_create(
                    project=conf['project'],
                    form_id=conf['form_id'],
                    defaults={
                        'form_name': conf['form_name'],
                        'app_id': '',
                        'app_name': '',
                        'silo': silo,
                        'read': read,
                        'last_updated': default_date})

                # If the cache object was created, we now have to populate
                # the rest of the fields with the relevant data.
                if created:
                    conf['silo_id'] = silo.id
                    conf['read_id'] = read.id
                    # Save the xmlns id of the form, can be used for downloading
                    # form-specific data.
                    cache_obj.xmlns = row['form']['@xmlns']

                    # The CommCare application id is used to build the
                    # dropdown by which users select a form.
                    try:
                        cache_obj.app_id = row['app_id']
                    except KeyError:
                        cache_obj.app_id = ''
                    if cache_obj.app_id:
                        app_url = 'https://www.commcarehq.org/a/%s/api/v0.5/' \
                            'application/%s/?format=json' % (
                                conf['project'], cache_obj.app_id)
                        response = requests.get(
                            app_url, headers=conf['auth_header'])
                        if response.status_code == 200:
                            cache_obj.app_name = json.loads(
                                response.content)['name']
                        else:
                            print "Could not retrieve Application name for %s, %s"\
                                % (conf['project'], conf['form_name'])
                            cache_obj.app_name = ''
                    else:
                        cache_obj.app_name = ''

                    cache_obj.save()
                # If the silo was not created, it means another celery
                # process ninja'd the cache creation process (i.e. there's a
                # race condition) and the new silo and read should be deleted,
                # since they aren't being used after all.
                else:
                    conf['silo_id'] = cache_obj.silo_id
                    conf['read_id'] = cache_obj.read_id
                    read.delete()
                    silo.delete()
                    print 'Smooth run through a race condition'


            # Filter out the stuff that isn't data from the returned JSON
            # (CommCare doesn't provide a clean data object, the form
            # data is mixed in with other metadata, all in the same object)
            int(conf['silo_id'])
            filtered_data = {}
            for form_key in row['form'].keys():
                if form_key in exclude_tags or form_key[:1] in exclude_chars:
                    continue
                filtered_data[form_key] = row['form'][form_key]
                filtered_data['submission_id'] = row['id']
            flattened_data = flatten(filtered_data)
            # Each row could be a different form/silo. So we'll be storing
            # a dict of sets instead of a set.
            try:
                data_columns[conf['silo_id']].update(flattened_data.keys())
            except KeyError:
                data_columns[conf['silo_id']] = set(flattened_data.keys())
            storeCommCareData(conf, [flattened_data])

        # Sets don't serialize, need to convert to lists.
        for key in data_columns:
            data_columns[key] = list(data_columns[key])
        return (data_columns, max_date)
    # This handles regular user request, not a cache building request.
    else:
        data_properties = []
        data_columns = set()
        for row in data['objects']:
            filtered_row = {}
            for form_key in row['form'].keys():
                if form_key in exclude_tags or form_key[:1] in exclude_chars:
                    continue
                filtered_row[form_key] = row['form'][form_key]
            filtered_row['submission_id'] = row['id']
            flattened_row = flatten(filtered_row)
            data_properties.append(flattened_row)
            data_columns.update(flattened_row.keys())
        storeCommCareData(conf, data_properties)
        return list(data_columns)


@shared_task()
def parseCommCareReportData(conf, data):
    data_properties = []
    data_columns = set()
    column_mapper = {}
    for c in data['columns']:
        column_mapper[c['slug']] = c['header']

    for row in data['data']:
        renamed_row = dict((column_mapper[col], row[col]) for col in row)
        data_properties.append(renamed_row)

    data_columns = column_mapper.values()
    storeCommCareData(conf, data_properties)
    return data_columns


@shared_task()
def storeCommCareData(conf, data):
    data_refined = []
    try:
        fieldToType = getColToTypeDict(Silo.objects.get(pk=conf['silo_id']))
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

    client = MongoClient(settings.MONGODB_URI)
    db = client.get_database(settings.TOLATABLES_MONGODB_NAME)

    if conf['download_type'] == 'commcare_form':
        for row in data_refined:
            row['edit_date'] = timezone.now()
            row['silo_id'] = conf['silo_id']
            row['read_id'] = conf['read_id']
        db.label_value_store.insert_many(data_refined)
    else:
        if conf['update']:
            if conf['download_type'] == 'case':
                for row in data_refined:
                    row['edit_date'] = timezone.now()
                    db.label_value_store.update(
                        {'silo_id': conf['silo_id'], 'case_id': row['case_id']},
                        {"$set": row},
                        upsert=True)

            elif conf['download_type'] == 'commcare_report':
                silo = Silo.objects.get(pk=conf['silo_id'])
                read = Read.objects.get(pk=conf['read_id'])
                db.label_value_store.delete_many({'silo_id': conf['silo_id']})
                saveDataToSilo(silo, data_refined, read)

        else:
            for row in data_refined:
                row["create_date"] = timezone.now()
                row["silo_id"] = conf['silo_id']
                row["read_id"] = conf['read_id']
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
