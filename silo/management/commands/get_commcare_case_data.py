import requests, json
from requests.auth import HTTPDigestAuth

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.contrib.auth.models import User

from silo.models import LabelValueStore, Read, Silo, ThirdPartyTokens, ReadType
from tola.util import getNewestDataDate, cleanKey, addColsToSilo

from commcare.tasks import fetchCommCareData
from commcare.util import get_commcare_record_count

class Command(BaseCommand):
    """
    python manage.py get_commcare_case_data --f weekly
    """
    help = 'Fetches a specific form data from ONA'

    def add_arguments(self, parser):
        parser.add_argument("-f", "--frequency", type=str, required=True)

    def handle(self, *args, **options):

        frequency = options['frequency']
        if frequency != "daily" and frequency != "weekly":
            return self.stdout.write("Frequency argument can either be 'daily' or 'weekly'")

        silos = Silo.objects.filter(reads__autopull_frequency__isnull=False, reads__autopull_frequency = frequency).distinct()
        read_type = ReadType.objects.get(read_type="CommCare")

        for silo in silos:
            reads = silo.reads.filter(type=read_type.pk)
            for read in reads:
                commcare_token = None
                try:
                    commcare_token = ThirdPartyTokens.objects.get(user=silo.owner.pk, name="CommCare")
                except Exception as e:
                    self.stdout.write('No commcare api key for silo %s, read "%s"' % (silo.pk, read.pk))
                    continue
                url = read.read_url
                auth_header = {'Authorization': 'ApiKey %(u)s:%(a)s' % {'u' : commcare_token.username, 'a' : commcare_token.token}}

                # get/build metadata based on download_type
                if 'case' in url:
                    last_data_retrieved = str(getNewestDataDate(silo.id))[:10]
                    url = url + "&date_modified_start=" + last_data_retrieved
                    download_type = 'case'
                    record_count = get_commcare_record_count(url, auth_header)
                elif 'configurablereportdata' in url:
                    download_type = 'commcare_report'
                    url_parts = url.split('/')
                    project = url_parts[4]
                    report_id = url_parts[8]
                    record_count = get_commcare_record_count(url, auth_header, project, report_id)

                if record_count == 0:
                    self.stdout.write('No new commcare data for READ_ID, "%s"' % read.pk)
                    continue

                response = requests.get(url, headers=auth_header)
                if response.status_code == 401:
                    commcare_token.delete()
                    self.stdout.write('Incorrect commcare api key for silo %s, read %s' % (silo.pk, read.pk))
                elif response.status_code != 200:
                    self.stdout.write('Failure retrieving commcare data for silo %s, read %s' % (silo.pk, read.pk))

                #Now call the update data function in commcare tasks
                data_raw = fetchCommCareData(
                    url, auth_header, True, 0, record_count,
                    50, silo.id, read.id, download_type, None, True
                )
                data_collects = data_raw.apply_async()
                new_colnames = set()
                for colset in [set(v.get()) for v in data_collects]:
                    new_colnames.update(colset)
                cleaned_colnames = [cleanKey(name) for name in new_colnames]
                addColsToSilo(silo, cleaned_colnames, )

                self.stdout.write('Successfully fetched silo %s, read %s from CommCare' % (silo.pk, read.pk))
