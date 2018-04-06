from __future__ import unicode_literals

from django.db import models

from silo.models import Silo, Read

# Create your models here.


class CommCareCache(models.Model):
    project = models.CharField(max_length=255)
    form_name = models.CharField(max_length=1000)
    form_id = models.CharField(max_length=255)
    silo = models.OneToOneField(Silo)
    read = models.OneToOneField(Read, blank=True, null=True)
    last_updated = models.DateTimeField()

    def __str__(self):
        return '%s %s' % (self.project, self.form_name)
