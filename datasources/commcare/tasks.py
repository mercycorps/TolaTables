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

from django.utils import timezone
from django.conf import settings
from django.contrib.auth.models import User

from celery import shared_task, group
from pymongo import MongoClient

from tola.util import getColToTypeDict, cleanKey, saveDataToSilo
from silo.models import Silo, Read, ReadType
from commcare.models import CommCareCache


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
    #         start, 100, step))


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
    if conf['for_cache']:
        data_columns = {}
        max_date = datetime.datetime(1980, 1, 1).replace(tzinfo=pytz.UTC)
        for row in data['objects']:

            # Discard any entries that aren't form entries.  Sometimes they
            # are just updates to the Case information.
            match = re.search('formdesigner\/(.*)', row['form']['@xmlns'])
            if match:
                form_id = match.group(1)
            else:
                print 'skipped ', row['form']['@xmlns']
                continue

            # Store the date if it's a max value
            row_date = dateutil.parser.parse(row['received_on']) \
                .replace(tzinfo=pytz.UTC)
            max_date = max(row_date, max_date)

            # See if this form exists in the Cache. If it doesn't, create
            # the entry.
            try:
                cache_obj = CommCareCache.objects.get(form_id=form_id)
                conf['silo_id'] = cache_obj.silo_id
                conf['read_id'] = cache_obj.read_id
                conf['form_name'] = cache_obj.form_name
                conf['form_id'] = cache_obj.form_id
            except CommCareCache.DoesNotExist:
                conf['form_id'] = form_id
                conf['form_name'] = row['form']['@name']
                user = User.objects.get(pk=conf['tables_user_id'])
                silo_name = "SAVE-Cache-%s-%s" % (
                    conf['project'], conf['form_name'])
                silo = Silo.objects.create(
                    name=silo_name[:60], public=0, owner=user)
                read = Read.objects.create(
                    owner=user,
                    type=ReadType.objects.get(read_type='CommCare'),
                    read_name=silo_name[:100],
                    description=silo_name,
                    read_url=conf['base_url'],
                    resource_id=form_id)
                conf['silo_id'] = silo.id
                conf['read_id'] = read.id

                # Create a cache with a dummy last_updated date.  It will get
                # overwritten by the calling function
                cache_obj = CommCareCache.objects.create(
                    project=conf['project'],
                    form_name=conf['form_name'],
                    form_id=conf['form_id'],
                    app_id='',
                    app_name='',
                    silo=silo,
                    read=read,
                    last_updated=datetime.datetime(1980, 1, 1))

                # Store additional data in the the Cache table now.
                # Do this after the initial Cache object creation because
                # taking too long for the initial save creates a race
                # condition, with multiple entries for the same project/form
                # getting created in the MySQL DB.

                # Save the xmlns id of the form, can be used for downloading
                # form-specific data.
                cache_obj.xmlns = row['form']['@xmlns']

                # Retreive and save the application name and id.  Used for
                # displaying form names on the download page.
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

            # Filter out the stuff that isn't data from the returned JSON
            filtered_data = {}
            for form_key in row['form'].keys():
                if form_key in exclude_tags or form_key[:1] in exclude_chars:
                    continue
                filtered_data[form_key] = row['form'][form_key]
                filtered_data['submission_id'] = row['id']

            # Each row could be a different form/silo. So we'll be returning
            # a dict of sets instead of a set.
            try:
                data_columns[conf['silo_id']].update(filtered_data.keys())
            except KeyError:
                data_columns[conf['silo_id']] = set(filtered_data.keys())
            storeCommCareData(conf, [filtered_data])

        # Sets don't serialize, need to convert to lists.
        for key in data_columns:
            data_columns[key] = list(data_columns[key])

        return (data_columns, max_date)
    else:
        data_properties = []
        data_columns = set()
        for row in data['objects']:
            filtered_data = {}
            for form_key in row['form'].keys():
                if form_key in exclude_tags or form_key[:1] in exclude_chars:
                    continue
                filtered_data[form_key] = row['form'][form_key]
                filtered_data['submission_id'] = row['id']
            data_properties.append(filtered_data)
            data_columns.update(filtered_data.keys())
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

    db = getattr(
        MongoClient(settings.MONGODB_URI), settings.TOLATABLES_MONGODB_NAME)
    if conf['update']:
        if conf['download_type'] == 'case':
            for row in data_refined:
                row['edit_date'] = timezone.now()
                db.label_value_store.update(
                    {'silo_id': conf['silo_id'], 'case_id': row['case_id']},
                    {"$set": row},
                    upsert=True)
        elif conf['download_type'] == 'commcare_form':
            for row in data_refined:
                row['edit_date'] = timezone.now()
                db.label_value_store.update({
                        'silo_id': conf['silo_id'],
                        'submission_id': row['submission_id']},
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
