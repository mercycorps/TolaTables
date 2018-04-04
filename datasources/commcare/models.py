from __future__ import unicode_literals

from django.db import models

from silo.models import Silo

# Create your models here.

class CommCareCache(models.Model):
    project = models.CharField(max_length=255)
    form_name = models.CharField(max_length=1000)
    form_id = models.CharField(max_length=255)
    silo = models.OneToOneField(Silo)
    last_updated = models.DateTimeField()
