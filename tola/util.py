import unicodedata
import datetime
import urllib2
import json
import base64
from django.utils import timezone
from django.conf import settings
from django.contrib.auth.models import User

from silo.models import Read, Silo, LabelValueStore

import pymongo
from bson.objectid import ObjectId
from pymongo import MongoClient

def combineColumns(silo_id):
    client = MongoClient(settings.MONGODB_HOST)
    db = client.tola
    lvs = json.loads(LabelValueStore.objects(silo_id = silo_id).to_json())
    cols = []
    for l in lvs:
        cols.extend([k for k in l.keys() if k not in cols])

    for l in lvs:
        for c in cols:
            if c not in l.keys():
                db.label_value_store.update_one(
                    {"_id": ObjectId(l['_id']['$oid'])},
                    {"$set": {c: ''}},
                    False
                )
    return True

#CREATE NEW DATA DICTIONARY OBJECT
def siloToDict(silo):
    parsed_data = {}
    key_value = 1
    for d in silo:
        label = unicodedata.normalize('NFKD', d.field.name).encode('ascii','ignore')
        value = unicodedata.normalize('NFKD', d.char_store).encode('ascii','ignore')
        row = unicodedata.normalize('NFKD', d.row_number).encode('ascii','ignore')
        parsed_data[key_value] = {label : value}

        key_value += 1

    return parsed_data


#IMPORT JSON DATA
def importJSON(read_obj, user, remote_user = None, password = None, silo_id = None, silo_name = None):
    # set date time stamp
    today = datetime.date.today()
    today.strftime('%Y-%m-%d')
    today = str(today)
    try:
        request2 = urllib2.Request(read_obj.read_url)
        #if they passed in a usernmae get auth info from form post then encode and add to the request header

        if remote_user and password:
            base64string = base64.encodestring('%s:%s' % (remote_user, password))[:-1]
            request2.add_header("Authorization", "Basic %s" % base64string)
        #retrieve JSON data from formhub via auth info
        json_file = urllib2.urlopen(request2)
        silo = None

        if silo_name:
            silo = Silo(name=silo_name, owner=user, public=False, create_date=today)
            silo.save()
        else:
            silo = Silo.objects.get(id = silo_id)

        silo.reads.add(read_obj)
        silo_id = silo.id

        #create object from JSON String
        data = json.load(json_file)
        json_file.close()

        #loop over data and insert create and edit dates and append to dict
        for row in data:
            lvs = LabelValueStore()
            lvs.silo_id = silo_id
            for new_label, new_value in row.iteritems():
                if new_label is not "" and new_label is not None and new_label is not "edit_date" and new_label is not "create_date":
                    if new_label == "id" or new_label == "_id": new_label="user_assigned_id"
                    setattr(lvs, new_label, new_value)
            lvs.create_date = timezone.now()
            lvs.save()
        combineColumns(silo_id)
        return ("success", "Data imported successfully.", str(silo_id))
    except Exception as e:
        return ("error", "An error has occured: %s" % e, str(silo_id))

def getSiloColumnNames(id):
    lvs = LabelValueStore.objects(silo_id=id).to_json()
    data = {}
    jsonlvs = json.loads(lvs)
    for item in jsonlvs:
        for k, v in item.iteritems():
            #print("The key and value are ({}) = ({})".format(k, v))
            if k == "_id" or k == "edit_date" or k == "create_date" or k == "silo_id":
                continue
            else:
                data[k] = v
    return data
