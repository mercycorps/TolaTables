# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2017-08-25 09:28
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('board', '0019_auto_20170814_0235'),
    ]

    operations = [
        migrations.AlterField(
            model_name='graphinput',
            name='graphmodel',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='graphinputs', to='board.Graphmodel'),
        ),
    ]
