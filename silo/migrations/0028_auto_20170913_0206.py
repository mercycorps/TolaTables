# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2017-09-13 09:06
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('silo', '0027_auto_20170913_0140'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='workflowlevel1',
            name='activity_id',
        ),
        migrations.AlterField(
            model_name='silo',
            name='workflowlevel1',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='silo.WorkflowLevel1'),
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
