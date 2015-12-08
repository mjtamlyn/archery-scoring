from django.core.urlresolvers import reverse
from django.db import models

from scores.result_modes import get_result_modes


class League(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField()

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('name',)

    def get_absolute_url(self):
        return reverse('league-detail', kwargs={'league_slug': self.slug})


class Season(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField()
    league = models.ForeignKey('League')
    clubs = models.ManyToManyField('core.Club')
    start_date = models.DateField()
    end_date = models.DateField()

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('-start_date',)

    def get_absolute_url(self):
        return reverse('season-detail', kwargs={'league_slug': self.league.slug, 'season_slug': self.slug})


class Leg(models.Model):
    season = models.ForeignKey('Season')
    competitions = models.ManyToManyField('entries.Competition')
    clubs = models.ManyToManyField('core.Club')
    index = models.PositiveIntegerField()

    def __str__(self):
        return '%s Leg %s' % (self.season, self.index)


class ResultsMode(models.Model):
    leg = models.ForeignKey('Leg', related_name='result_modes')
    mode = models.CharField(max_length=31, choices=tuple(get_result_modes()))
    leaderboard_only = models.BooleanField(default=False)

    class Meta:
        unique_together = ('leg', 'mode')

    def __str__(self):
        return str(self.get_mode_display())