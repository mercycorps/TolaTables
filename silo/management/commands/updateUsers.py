from django.core.management.base import BaseCommand, CommandError
from silo.models import Silo, UniqueFields, Read
from django.contrib.auth.models import User
from django.db.models import Q

import re
import sys

class Command(BaseCommand):
    """
    Usage: python manage.py update_to_0-9-2
    """

    def handle(self, *args, **options):
        #get every column for each silo
        emailList = (
            'ikasrashvili@mercycorps.org',
            'gsarukhanishvili@mercycorps.org',
            'mlomidze@mercycorps.org',
            'rnadiradze@mercycorps.org',
            'ggabedava@mercycorps.org',
            'ms.metreveli@gmail.com',
            'dmerabishvili@mercycorps.org',
            'kbegiashvili@mercycorps.org',
            'shgagnidze@mercycorps.org',
            'tchulukhadze@mercycorps.org',
            'skhelisupali@mercycorps.org',
            'ocreamer@mercycorps.org',
            'papinashvili@mercycorps.org',
        )


        # for e in emailList:
        #     emailUser, domain = e.split('@')
        #     users = User.objects.filter(username__contains=emailUser).values('username')
        #     print users
        # counter = 0
        # usernames = set([u.email.split('@')[0] for u in User.objects.all() if '@' in u.email])
        # for un in usernames:
        #
        #     # print "email=", u.email
        #     users = User.objects.filter(username__contains=un)
        #     if len(users) > 1:
        #         print un
        #         print users
        #         counter += 1
        #
        # print 'count=', counter

        silos = Silo.objects.filter(reads__type_id=3)
        newsilos = silos.filter(reads__type_id=1)
        for silo in newsilos:
            print 'silo', silo, silo.id, silo.owner
            reads = silo.reads.all()
            for read in reads:
                print 'read', read, read.id
