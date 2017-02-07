# -*- coding: utf-8 -*-
# Generated by Django 1.9.5 on 2017-02-07 18:45
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('silo', '0009_auto_20160811_1356'),
    ]

    operations = [
        migrations.DeleteModel(
            name='DocumentationApp',
        ),
        migrations.DeleteModel(
            name='FAQ',
        ),
        migrations.RemoveField(
            model_name='feedback',
            name='submitter',
        ),
        migrations.AddField(
            model_name='silo',
            name='country',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='silo.Country'),
        ),
        migrations.AddField(
            model_name='silo',
            name='program',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='tolasites',
            name='tola_activity_token',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='tolasites',
            name='tola_activity_user',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='tolasites',
            name='tola_report_url',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='tolauser',
            name='tables_api_token',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.DeleteModel(
            name='Feedback',
        ),
    ]
