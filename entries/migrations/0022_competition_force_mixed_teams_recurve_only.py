# -*- coding: utf-8 -*-
# Generated by Django 1.9.2 on 2017-02-18 19:10
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('entries', '0021_custom_team_names'),
    ]

    operations = [
        migrations.AddField(
            model_name='competition',
            name='force_mixed_teams_recurve_only',
            field=models.BooleanField(default=False),
        ),
    ]
