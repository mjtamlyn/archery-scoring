# -*- coding: utf-8 -*-
# Generated by Django 1.9.2 on 2017-03-18 00:05
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('olympic', '0010_extra_entries_on_seedings'),
    ]

    operations = [
        migrations.AddField(
            model_name='olympicsessionround',
            name='cut',
            field=models.IntegerField(blank=True, null=True),
        ),
    ]
