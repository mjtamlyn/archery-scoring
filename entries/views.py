from itertools import groupby
import json
import math

from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import HttpResponse, HttpResponseBadRequest
from django.utils.datastructures import SortedDict
from django.views.generic import View, DetailView, ListView
from django.shortcuts import render, get_object_or_404

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, PageBreak, TableStyle, KeepTogether, Image
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.rl_config import defaultPageSize
from reportlab.lib import colors
from reportlab.lib.units import inch

from entries.forms import new_entry_form_for_competition
from entries.models import *

from scoring.utils import class_view_decorator


@class_view_decorator(login_required)
class CompetitionList(ListView):
    model = Competition

    def get_queryset(self):
        return self.model.objects.all().select_related('tournament')


@class_view_decorator(login_required)
class CompetitionDetail(DetailView):
    model = Competition
    object_name = 'competition'


@class_view_decorator(login_required)
class EntryList(ListView):
    model = SessionEntry
    template_name = 'entries/entry_list.html'

    def get_queryset(self):
        return self.model.objects.filter(competition_entry__competition__slug=self.kwargs['slug']).select_related('competition_entry__competition', 'competition_entry__club', 'competition_entry__bowstyle', 'competition_entry__archer', 'session_round__session', 'session_round__shot_round').order_by('-competition_entry')

    def get_context_data(self, **kwargs):
        context = super(EntryList, self).get_context_data(**kwargs)
        self.entries = context['object_list']
        if self.entries:
            self.competition = self.entries[0].competition_entry.competition
        else:
            self.competition = Competition.objects.get(slug=self.kwargs['slug'])
        context.update({
            'competition': self.competition,
            'stats': self.get_stats(),
            'form': self.get_form_class()(),
        })
        return context

    def get_form_class(self):
        return new_entry_form_for_competition(self.competition)

    def get_stats(self):
        competition = self.competition
        entries = self.entries
        stats = []
        stats.append(
            ('Total Entries', len(entries)),
        )
        # TODO: Make all the stats much better. These ones are rubbish.
        #sessions = competition.sessions_with_rounds()
        #for session in sessions:
        #    stats.append((
        #        'Entries for {0}'.format(session.start.strftime('%A')),
        #        competition.competitionentry_set.filter(sessionentry__session_round__session=session).count(),
        #    ))
        #    for session_round in session.sessionround_set.all():
        #        stats.append((
        #            'Entries for {0}'.format(session_round.shot_round),
        #            competition.competitionentry_set.filter(sessionentry__session_round=session_round).count(),
        #        ))
        #for session in sessions:
        #    for session_round in session.sessionround_set.all():
        #        for gender_code, gender in GENDER_CHOICES:
        #            stats.append((
        #                '{0} entries for {1}'.format(gender, session_round.shot_round),
        #                entries.filter(sessionentry__session_round=session_round, archer__gender=gender_code).count(),
        #            ))
        return stats

    def post(self, request, slug):
        if '_method' in request.POST and request.POST['_method'] == 'delete':
            return self.delete(request, slug)
        self.competition = Competition.objects.get(slug=slug)
        instance = CompetitionEntry(competition=self.competition)
        form = self.get_form_class()(request.POST, instance=instance)
        if form.is_valid():
            entry = form.save()
            return render(request, 'includes/entry_row.html', locals())
        else:
            errors = json.dumps(form.errors)
        return HttpResponseBadRequest(errors)

    def delete(self, request, slug):
        entry = get_object_or_404(CompetitionEntry, pk=request.POST['pk'])
        entry.delete()
        return HttpResponse('deleted')


@class_view_decorator(login_required)
class BetterTargetList(ListView):
    template_name = 'entries/target_list.html'
    model = TargetAllocation

    def get_queryset(self):
        return self.model.objects.filter(session_entry__competition_entry__competition__slug=self.kwargs['slug']).select_related('session_entry__competition_entry__competition__tournament', 'session_entry__session_round__session', 'session_entry__session_round__shot_round', 'session_entry__competition_entry__bowstyle', 'session_entry__competition_entry__club', 'session_entry__competition_entry__archer', 'session_entry__competition_entry__archer__club')

    def get_empty_target_list(self):
        target_list = SortedDict()
        session_rounds = SessionRound.objects.filter(session__competition__slug=self.kwargs['slug']).select_related('session')
        for session_round in session_rounds:
            session = session_round.session
            if session not in target_list:
                target_list[session] = {'rounds': [session_round], 'targets': [], 'entries': []}
            else:
                target_list[session]['rounds'].append(session_round)
        return target_list

    def get_target_list(self):
        target_list = self.get_empty_target_list()
        for allocation in self.allocations:
            session_round = allocation.session_entry.session_round
            session = session_round.session
            target_list[session]['targets'].append(allocation)

        # Turn the targets into an actual target list
        for session, options in target_list.iteritems():
            details = session.details
            # Work out which bosses and details we need
            archers_per_target = session.archers_per_target
            allocations = options['targets']
            num_entries = SessionEntry.objects.filter(session_round__session=session).count()
            current_bosses = [allocation.boss for allocation in allocations]
            min_boss = min(current_bosses) if current_bosses else 1
            needed_bosses = int(math.ceil(num_entries / float(archers_per_target)))
            current_max_boss = max(current_bosses) if current_bosses else 1
            bosses = range(min_boss, max(needed_bosses, current_max_boss) + 1)

            # Make a lookup dictionary from the current allocations
            allocations_lookup = dict([('{0}{1}'.format(allocation.boss, allocation.target), allocation) for allocation in allocations])

            session_target_list = options['target_list'] = []

            for boss in bosses:
                allocations = []
                for detail in details:
                    target = '{0}{1}'.format(boss, detail)
                    allocations.append((detail, allocations_lookup.get(target, None)))
                session_target_list.append((boss, allocations))
        return target_list

    def add_unallocated_entries(self, target_list):
        entries = SessionEntry.objects.filter(competition_entry__competition=self.competition).exclude(targetallocation__isnull=False).select_related('session_round__session', 'competition_entry__club', 'competition_entry__archer', 'competition_entry__bowstyle')

        for entry in entries:
            session = entry.session_round.session
            session_round = entry.session_round
            target_list[session]['entries'].append(entry)

        for details in target_list.values():
            details['entries'] = sorted(details['entries'], key=lambda e: e.competition_entry.archer.name)
            data = [{'pk': e.pk, 'label': e.competition_entry.archer.name} for e in details['entries']]
            details['entries_json'] = json.dumps(data)

    def get_context_data(self, **kwargs):
        context = super(BetterTargetList, self).get_context_data(**kwargs)
        self.allocations  = context['object_list']

        if self.allocations:
            self.competition = self.allocations[0].session_entry.competition_entry.competition
        else:
            self.competition = Competition.objects.get(slug=self.kwargs['slug'])

        target_list = self.get_target_list()
        self.add_unallocated_entries(target_list)

        context.update({
            'competition': self.competition,
            'target_list': target_list
        })
        return context

    def post(self, request, slug):
        data = json.loads(request.raw_post_data)
        if data['method'] == 'create':
            allocation = TargetAllocation.objects.create(session_entry_id=data['entry'], boss=data['location'][:-1], target=data['location'][-1])
            return HttpResponse(allocation.pk)
        elif data['method'] == 'delete':
            TargetAllocation.objects.get(pk=data['entry']).delete()
            return HttpResponse('ok')
        return HttpResponseBadRequest()


class Registration(BetterTargetList):
    template_name = 'entries/registration.html'

    def add_unallocated_entries(self, target_list):
        pass

    def post(self, request, slug):
        entry = get_object_or_404(SessionEntry, pk=request.POST['pk'])
        entry.present = json.loads(request.POST['present'])
        entry.save()
        return HttpResponse('ok')


@class_view_decorator(login_required)
class TargetList(View):
    template = 'target_list.html'

    def get_target_list(self, session_round):
        return session_round.target_list()

    def get(self, request, slug):
        competition = get_object_or_404(Competition, slug=slug)
        session_rounds = SessionRound.objects.filter(session__competition=competition).order_by('session__start')
        target_list = [(
            session_round.session, # session
            session_round, # round
            self.get_target_list(session_round),
            session_round.sessionentry_set.annotate(entered=Count('targetallocation')).filter(entered=0), # entries
            ) for session_round in session_rounds]
        sessions = []
        for key, values in groupby(target_list, lambda x: x[0]):
            sessions.append((key, [value[1] for value in values]))
        return render(request, self.template, locals())

    def post(self, request, slug):
        targets = json.loads(request.POST['targets'])
        for target in targets:
            TargetAllocation.objects.filter(session_entry__pk=target['entry']).delete()
            entry = SessionEntry.objects.get(pk=target['entry'])
            new_allocation = TargetAllocation(session_entry=entry, boss=target['target'][:-1], target=target['target'][-1])
            new_allocation.save()
        return HttpResponse()


@class_view_decorator(login_required)
class ScoreSheets(ListView):
    template_name = 'entries/score_sheets.html'

    def get_queryset(self):
        return SessionRound.objects.filter(session__competition__slug=self.kwargs['slug']).select_related('session', 'shot_round', 'session__competition__tournament')

    def get_context_data(self, **kwargs):
        context = super(ScoreSheets, self).get_context_data(**kwargs)
        rounds = context['object_list']
        if rounds:
            context['competition'] = rounds[0].session.competition
        else:
            context['competition'] = Competition.objects.get(slug=self.kwargs['slug'])
        return context


# PDF views

class PdfView(View):

    styles = getSampleStyleSheet()
    PAGE_HEIGHT=defaultPageSize[1]
    PAGE_WIDTH=defaultPageSize[0]

    def set_options(self, slug=None, round_id=None):
        if slug:
            self.competition = get_object_or_404(Competition, slug=slug)
        if round_id:
            self.session_round = get_object_or_404(SessionRound, pk=round_id)

    def get(self, request, **kwargs):
        self.set_options(**kwargs)
        self.update_style()
        elements = self.get_elements()
        return self.response(elements)

    def update_style(self):
        """Subclasses can customise to amend self.style"""
        pass

    def setMargins(self, doc):
        pass

    def response(self, elements):
        response = HttpResponse(mimetype='application/pdf')
        doc = self.get_doc(response)
        self.setMargins(doc)
        doc.build(elements)
        return response

    def get_doc(self, response):
        doc = SimpleDocTemplate(response, pagesize=(self.PAGE_WIDTH, self.PAGE_HEIGHT))
        return doc

    def Para(self, string, style='Normal'):
        return Paragraph(unicode(string), self.styles[style])

    def get_elements(self):
        return [self.Para('This is not done yet')]

class HeadedPdfView(PdfView):
    title = ''

    def draw_title(self, canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica-Bold', 18)
        canvas.drawCentredString(self.PAGE_WIDTH/2.0, self.PAGE_HEIGHT-70, u'{0}: {1}'.format(self.competition, self.title))

        sponsors = self.competition.sponsors.all()

        positions = (
            (30, self.PAGE_HEIGHT-240),
            (self.PAGE_WIDTH-140, self.PAGE_HEIGHT-120),
        )
        for i, sponsor in enumerate(sponsors):
            canvas.drawImage(sponsors[i].logo.path, positions[i][0], positions[i][1], width=100, preserveAspectRatio=True, anchor='nw')
            pass

        canvas.restoreState()

    def response(self, elements):
        response = HttpResponse(mimetype='application/pdf')
        doc = self.get_doc(response)
        self.setMargins(doc)
        doc.build(elements, onFirstPage=self.draw_title, onLaterPages=self.draw_title)
        return response

class TargetListPdf(HeadedPdfView):
    title = 'Target List'
    lunch = False

    def setMargins(self, doc):
        doc.topMargin = 1.1*inch
        doc.bottomMargin = 0.5*inch

    def update_style(self):
        self.styles['h2'].alignment = 1

    def get_elements(self):
        session_rounds = SessionRound.objects.filter(session__competition=self.competition).order_by('session', 'session__start')

        elements = []
        for session_round in session_rounds:
            target_list = session_round.target_list_pdf(lunch=self.lunch)
            if not target_list:
                continue

            title = "Target List for {0} - {1}".format(session_round.shot_round, session_round.session.start.strftime('%A, %d %B %Y, %X'))
            header = self.Para(title, 'h2')
            table = Table(target_list)
            spacer = Spacer(self.PAGE_WIDTH, 0.25*inch)

            elements = [header, spacer, table, spacer, PageBreak()] + elements
        return elements

target_list_pdf = login_required(TargetListPdf.as_view())

class TargetListLunch(TargetListPdf):
    lunch = True
target_list_lunch = login_required(TargetListLunch.as_view())

class ScoreSheetsPdf(HeadedPdfView):

    box_size = 0.32*inch
    wide_box = box_size*1.35
    total_cols = 12 + 2 + 4
    col_widths = 6*[box_size] + [wide_box] + 6*[box_size] + 6*[wide_box]

    def setMargins(self, doc):
        doc.topMargin = 1.1*inch

    def update_style(self):
        self.title = self.session_round.shot_round
        self.spacer = Spacer(self.PAGE_WIDTH, self.box_size*0.5)

    def get_elements(self):

        score_sheet_elements = self.get_score_sheet_elements()

        elements = []
        for boss, entries in groupby(self.session_round.target_list(), lambda x: x[0][:-1]):
            entries = list(entries)
            if not reduce(lambda e, f: e or f, map(lambda e: e[1], entries)):
                continue
            for target, entry in entries:
                if entry:
                    entry = entry.session_entry.competition_entry
                    table_data = [
                            [self.Para(target, 'h2'), self.Para(entry.archer, 'h2'), self.Para(entry.club.name, 'h2')],
                            #[None, self.Para(u'{0} {1}'.format(entry.archer.get_gender_display(), entry.bowstyle), 'h2'), self.Para(entry.get_age_display(), 'h2')],
                            [None, self.Para(u'{0} {1}'.format(entry.archer.get_gender_display(), entry.bowstyle), 'h2'), self.Para(entry.get_novice_display(), 'h2')],
                    ]
                else:
                    table_data = [
                            [self.Para(target, 'h2'), None, None],
                            [],
                    ]
                header_table = Table(table_data, [0.4*inch, 2.5*inch, 4*inch])
                elements.append(KeepTogether([self.spacer, header_table, self.spacer] + score_sheet_elements))
            elements.append(PageBreak())

        return elements


    def get_score_sheet_elements(self):
        subrounds = self.session_round.shot_round.subrounds.order_by('-distance')
        score_sheet_elements = []

        for subround in subrounds:
            subround_title = self.Para(u'{0}{1}'.format(subround.distance, subround.unit), 'h3')
            dozens = subround.arrows / 12
            extra = subround.arrows % 12
            total_rows = dozens + 2
            scoring_labels = ['ET', 'S', '10+X', 'X', 'RT'] if self.session_round.shot_round.scoring_type == 'X' else ['ET', 'S', 'H', 'G', 'RT']
            table_data = [[subround_title] + [None] * 5 + ['ET'] + [None] * 6 + scoring_labels]
            table_data += [[None for i in range(self.total_cols)] for j in range(total_rows - 1)]
            if extra is 6:
                total_rows += 1
                table_data += [[None for i in range(self.total_cols)]]
                self.scores_table_style._cmds.append(('BOX', (7, 1), (12, -3), 2, colors.black))
                self.scores_table_style._cmds.append(('INNERGRID', (0, -2), (6, -2), 0, colors.black))
                self.scores_table_style._cmds.append(('LINEABOVE', (0, -2), (6, -2), 0.25, colors.black))
                self.scores_table_style._cmds[3][2] = (-1, -3)
                self.scores_table_style._cmds[4][2] = (-1, -3)
                self.scores_table_style._cmds[6][2] = (-1, -3)

            table = Table(table_data, self.col_widths, total_rows*[self.box_size])
            table.setStyle(self.scores_table_style)

            score_sheet_elements += [table, self.spacer]

        compound_round = bool(subrounds.count() - 1)
        if compound_round:
            totals_table = Table([[None]*self.total_cols], self.col_widths, [self.box_size])
            totals_table.setStyle(self.totals_table_style)

            score_sheet_elements += [totals_table, self.spacer]

        signing_table_widths = [0.7*inch, 2*inch]
        signing_table = Table([[self.Para('Archer', 'h3'), None, None, self.Para('Scorer', 'h3'), '']], signing_table_widths + [0.5*inch] + signing_table_widths)
        signing_table.setStyle(self.signing_table_style)
        score_sheet_elements += [self.spacer, signing_table]

        return score_sheet_elements

    scores_table_style = TableStyle([
        # alignment
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),

        # arrows grid
        ('BOX', (0, 1), (6, -2), 2, colors.black),
        ['BOX', (7, 1), (-1, -2), 2, colors.black],
        ['INNERGRID', (0, 1), (-1, -2), 0.25, colors.black],

        # end totals columns
        ('BOX', (6, 0), (6, -2), 2, colors.black),
        ['BOX', (13, 0), (13, -2), 2, colors.black],

        # totals grid
        ('BOX', (14, 0), (-1, -2), 2, colors.black),
        ('BOX', (14, -1), (-2, -1), 2, colors.black),
        ('LINEBEFORE', (15, 0), (-1, -1), 1.5, colors.black),
    ])

    totals_table_style = TableStyle([
        ('BOX', (14, 0), (-2, 0), 2, colors.black),
        ('LINEBEFORE', (15, 0), (-1, -1), 1.5, colors.black),
    ])

    signing_table_style = TableStyle([
        ('LINEBELOW', (1, 0), (1, 0), 1, colors.black),
        ('LINEBELOW', (4, 0), (4, 0), 1, colors.black),
    ])

score_sheets_pdf = login_required(ScoreSheetsPdf.as_view())

class RunningSlipsPdf(ScoreSheetsPdf):
    def draw_title(self, canvas, doc):
        pass

    def setMargins(self, doc):
        doc.topMargin = doc.bottomMargin = 0.3*inch

    def get_elements(self):
        elements = []
        for boss, entries in groupby(self.session_round.target_list(), lambda x: x[0][:-1]):
            entries = list(entries)
            if not reduce(lambda e, f: e or f, entries):
                continue
            elements += self.get_running_slip_elements(boss, list(entries))
        return elements

    def get_running_slip_elements(self, target, entries):
        dozens = self.session_round.shot_round.arrows / 12
        elements = []
        for dozen in range(1, dozens + 1):
            table_data = [['Dozen {0}'.format(dozen)] + [None] * 6 + ['ET'] + [None] * 6 + ['ET', 'S', '10+X', 'X', 'RT' if dozen > 1 else 'Inits.']]
            for entry in entries:
                table_data.append([entry[0]] + [None for i in range(self.total_cols)])
            table = Table(table_data, [self.box_size] + self.col_widths, (len(entries) + 1)*[self.box_size])
            table.setStyle(self.scores_table_style)
            elements.append(KeepTogether(table))
            elements += [self.spacer] * 3
        return elements

    scores_table_style = TableStyle([
        # alignment
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),

        # arrows grid
        ('BOX', (0, 1), (-1, -1), 2, colors.black),
        ('INNERGRID', (0, 1), (-1, -1), 0.25, colors.black),

        # end totals columns
        ('BOX', (7, 0), (7, -1), 2, colors.black),
        ('BOX', (14, 0), (14, -1), 2, colors.black),

        # details column
        ('BOX', (0, 1), (0, -1), 2, colors.black),

        # totals grid
        ('BOX', (15, 0), (-1, -1), 2, colors.black),
        ('LINEBEFORE', (15, 0), (-1, -1), 1.5, colors.black),

        # title
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
    ])


running_slips_pdf = login_required(RunningSlipsPdf.as_view())