import requests
import datetime
import pytz
from dateutil.parser import parse

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

from silo.models import Read, Silo, ThirdPartyTokens
from tola.util import cleanKey, addColsToSilo
from commcare.tasks import fetchCommCareData
from commcare.util import get_commcare_record_count, CommCareImportConfig
from commcare.models import CommCareCache


class Command(BaseCommand):
    """
    python manage.py refreshCommCareCache [-p <project_name>]
    """
    help = 'Refresh the CommCare form data cache.'

    def add_arguments(self, parser):
        parser.add_argument('-p', '--project', type=str)

    def handle(self, *args, **options):

        disabled_projects = ['prospectsmonitoring']
        # Get a list of projects to import data from
        if options['project']:
            project = [options['project']]
        else:
            read_urls = Read.objects.filter(type__read_type='CommCare') \
                .values_list('read_url', flat=True)
            projects = set()
            for read_url in read_urls:
                projects.add(read_url.split('/')[4])

        base_url = 'https://www.commcarehq.org/a/%s/api/v0.5/form/?limit=1'

        for project in projects:
            if project in disabled_projects:
                continue
            print 'Downloading ' + project

            conf = CommCareImportConfig(
                project=project,
                tables_user_id=User.objects.get(
                    email='systems@mercycorps.org',
                    username='systems'
                ).id,
                base_url=base_url % project,
                download_type='commcare_form',
                update=True,
                use_token=True,
                for_cache=True
            )

            try:
                conf.set_auth_header()
            except ThirdPartyTokens.DoesNotExist:
                self.stdout.write('CommCare Token is not in the DB')
                continue

            response = requests.get(conf.base_url, headers=conf.auth_header)
            if response.status_code == 401:
                commcare_token = ThirdPartyTokens.objects.get(token=conf.token)
                commcare_token.delete()
                self.stdout.write('Incorrect CommCare api key for project %s'
                                  % project)
                continue
            elif response.status_code != 200:
                self.stdout.write(
                    'Failure retrieving CommCare data for project %s'
                    % project)

            conf.record_count = get_commcare_record_count(conf)
            if conf.record_count == 0:
                self.stdout.write(
                    'Fetching of record counts failed. Skipping project %s'
                    % project)
                continue

            # Trigger the data retrieval and retrieve the column names
            url = conf.base_url.replace('limit=1', 'limit=100')
            data_raw = fetchCommCareData(
                conf.to_dict(), url, 0, 100)
            data_collects = data_raw.apply_async()
            data_retrieval = [v.get() for v in data_collects]

            # Add columns to the Silo and max date to Cache
            silo_ref = {}
            save_date = datetime.datetime(1980, 1, 1).replace(tzinfo=pytz.UTC)
            for column_dict, max_date in data_retrieval:
                for silo_id in column_dict:
                    cleaned_colnames = [
                        cleanKey(name) for name in column_dict[silo_id]]
                    if silo_id in silo_ref:
                        silo = silo_ref[silo_id]
                    else:
                        silo = Silo.objects.get(pk=silo_id)
                        silo_ref[silo_id] = silo
                    addColsToSilo(silo, cleaned_colnames)

                save_date = max(
                    parse(max_date).replace(tzinfo=pytz.UTC), save_date)

            for cache_obj in CommCareCache.objects.filter(project=project):
                cache_obj.last_updated = save_date
                cache_obj.save()

            self.stdout.write(
                'Successfully fetched project %s from CommCare' % conf.project)
