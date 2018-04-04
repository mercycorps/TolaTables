import requests, json

from requests.auth import HTTPDigestAuth

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.contrib.auth.models import User

from silo.models import LabelValueStore, Read, Silo, ThirdPartyTokens, ReadType
from tola.util import getNewestDataDate, cleanKey, addColsToSilo

from commcare.tasks import fetchCommCareData
from commcare.util import get_commcare_record_count, CommCareImportConfig

class Command(BaseCommand):
    """
    python manage.py refreshCommCareCache [-p <project_name>]
    """
    help = 'Refresh the CommCare form data cache.'

    def add_arguments(self, parser):
        parser.add_argument('-p', '--project', type=str)

    def handle(self, *args, **options):


        if options['project']:
            project_list = [options['project']]
            print 'options project', options['project']
        else:
            read_urls = Read.objects.filter(type__read_type='CommCare') \
            .values_list('read_url', flat=True)
            project_list = set()
            for read_url in read_urls:
                project_list.add(read_url.split('/')[4])

        base_url = 'https://www.commcarehq.org/a/%s/api/v0.5/form/?limit=1'

        for project in project_list:
            print 'Downloading ' + project
            conf = CommCareImportConfig()
            conf.tpt_username = 'systems@mercycorps.org'
            conf.set_auth_header()

            conf.url = base_url % project
            