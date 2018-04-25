# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2018-04-04 17:35
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('silo', '0034_tolauser_tola_user_uuid'),
    ]

    operations = [
        migrations.AlterField(
            model_name='silo',
            name='workflowlevel1',
            field=models.ManyToManyField(blank=True, to='silo.WorkflowLevel1'),
        ),
        migrations.AlterField(
            model_name='tolauser',
            name='workflowlevel1',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='silo.WorkflowLevel1'),
        ),
        migrations.AlterField(
            model_name='workflowlevel2',
            name='workflowlevel1',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='silo.WorkflowLevel1'),
        ),
    ]
