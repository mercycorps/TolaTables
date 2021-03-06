# -*- coding: utf-8 -*-
# Generated by Django 1.9.5 on 2017-01-31 18:34
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('board', '0005_auto_20170131_1032'),
    ]

    operations = [
        migrations.RenameField(
            model_name='graph',
            old_name='ember_component',
            new_name='embercomponent',
        ),
        migrations.RenameField(
            model_name='graphinput',
            old_name='aggregation_function',
            new_name='aggregationfunction',
        ),
        migrations.RenameField(
            model_name='graphinput',
            old_name='graph_input',
            new_name='graphinput',
        ),
        migrations.RenameField(
            model_name='graphmodel',
            old_name='input_type',
            new_name='inputtype',
        ),
        migrations.RenameField(
            model_name='graphmodel',
            old_name='is_required',
            new_name='isrequired',
        ),
        migrations.RenameField(
            model_name='item',
            old_name='widget_col',
            new_name='widgetcol',
        ),
        migrations.RenameField(
            model_name='item',
            old_name='widget_row',
            new_name='widgetrow',
        ),
        migrations.RenameField(
            model_name='item',
            old_name='widget_size_x',
            new_name='widgetsizex',
        ),
        migrations.RenameField(
            model_name='item',
            old_name='widget_size_y',
            new_name='widgetsizey',
        ),
    ]
