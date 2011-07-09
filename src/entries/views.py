from django.shortcuts import render, get_object_or_404

from entries.forms import new_entry_form_for_competition
from entries.models import Tournament, Competition

def tournaments(request):
    tournaments = Tournament.objects.all()
    return render(request, 'tournaments.html', locals())

def competition_index(request, slug):
    competition = get_object_or_404(Competition, slug=slug)
    return render(request, 'competition_index.html', locals())

def entries(request, slug):
    competition = get_object_or_404(Competition, slug=slug)
    entries = competition.competitionentry_set.all()
    FormClass = new_entry_form_for_competition(competition)
    form = FormClass()
    return render(request, 'competition_entries.html', locals())
