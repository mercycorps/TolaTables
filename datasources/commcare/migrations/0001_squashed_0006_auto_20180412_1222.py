# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2018-04-16 04:03
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    replaces = [('commcare', '0001_initial'), ('commcare', '0002_commcarecache_read'), ('commcare', '0003_auto_20180406_1329'), ('commcare', '0004_commcarecache_xmlns_id'), ('commcare', '0005_auto_20180407_0902'), ('commcare', '0006_auto_20180412_1222')]

    initial = True

    dependencies = [
        ('silo', '0035_auto_20180404_1035'),
    ]

    operations = [
        migrations.CreateModel(
            name='CommCareCache',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('project', models.CharField(max_length=255)),
                ('form_name', models.CharField(max_length=1000)),
                ('form_id', models.CharField(max_length=255, unique=True)),
                ('last_updated', models.DateTimeField()),
                ('silo', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to='silo.Silo')),
                ('read', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='silo.Read')),
                ('app_id', models.CharField(default='', max_length=255)),
                ('app_name', models.CharField(default='', max_length=255)),
                ('xmlns', models.CharField(default='', max_length=255)),
            ],
        ),
    ]