# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2017-07-28 11:45
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('board', '0015_auto_20170727_0249'),
    ]

    operations = [
        migrations.AlterField(
            model_name='graphinput',
            name='graphmodel',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='graphinputs', to='board.Graphmodel'),
        ),
    ]
