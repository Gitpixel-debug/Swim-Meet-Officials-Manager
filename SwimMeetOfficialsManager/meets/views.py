import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.http import HttpResponseRedirect, JsonResponse
from django.urls import reverse
from django.db import IntegrityError, transaction
from .models import *
from .forms import SessionEditForm, CSVUploadForm
import csv
from io import TextIOWrapper
from django.contrib import messages
import uuid
import os
from django.core.mail import send_mail
from django.conf import settings
from .email_utils import send_email
from django.http import HttpResponseForbidden, HttpResponse
from django.utils import timezone
from datetime import timedelta, datetime
import math
from django.db.models import Sum
import random
import string
from django.utils import dateparse
from django.views.decorators.http import require_POST
from django.db.models import Q
from .services.deck_assignment import generate_deck_assignments, finalize_and_save_assignments, CERT_ROLE_MAP, _official_cert_codes, get_allowed_roles, get_extra_roles
from django.views.decorators.csrf import csrf_exempt

# Create your views here.
def index(request):
    # If authenticated, show official dashboard; otherwise send to login page
    if request.user and request.user.is_authenticated:
        return redirect('official-dashboard')
    return redirect('login')

from django.contrib.auth.decorators import login_required
from .forms import MeetCreateForm
from .models import Meet
from django.contrib.auth import get_user_model


# ===============================
# CREATE MEET


@login_required
def meet_create(request):

    if request.method == "POST":
        form = MeetCreateForm(request.POST)

        if form.is_valid():
            meet = form.save(commit=False)
            meet.created_by = request.user
            meet.save()

            # Auto-create sessions with distribution across days
            total_sessions = meet.num_sessions or 1
            start = meet.start_date
            end = meet.end_date or meet.start_date
            days = (end - start).days + 1
            sessions_per_day = math.ceil(total_sessions / days)
            # Time slots repeat the same pattern each day (8-noon, noon-4, ...)
            daily_slots = [("08:00", "12:00"), ("12:00", "16:00"), ("16:00", "20:00"), ("20:00", "23:00")]
            for i in range(1, total_sessions + 1):
                day_index = (i - 1) // sessions_per_day
                session_date = start + timedelta(days=day_index)
                time_idx = (i - 1) % sessions_per_day  # resets for each day
                slot = daily_slots[time_idx % len(daily_slots)]
                start_time, end_time = slot
                Session.objects.create(
                    meet=meet,
                    session_number=i,
                    date=session_date,
                    start_time=start_time,
                    end_time=end_time
                )

            return redirect("meet-home", meet_id=meet.id)
    else:
        form = MeetCreateForm()

    return render(request, "meets/meet_create.html", {"form": form})


@login_required
def meet_home(request, meet_id):
    meet = get_object_or_404(Meet, id=meet_id)
    User = get_user_model()
    joined_officials = User.objects.filter(sessionassignment__session__meet=meet).distinct()
    # prepare set of session ids the current user has joined for checkbox pre-checking
    user_session_ids = set()
    if request.user and request.user.is_authenticated:
        user_session_ids = set(SessionAssignment.objects.filter(session__meet=meet, official=request.user).values_list('session__id', flat=True))
    # build per-session joined officials mapping
    # prepare sessions list and attach assignments per session for template convenience
    sessions_list = list(meet.sessions.all())
    for s in sessions_list:
        s.joined_assignments = list(SessionAssignment.objects.filter(session=s).select_related('official'))

    return render(request, "meets/meet_home.html", {
        "meet": meet,
        "sessions": sessions_list,
        "joined_officials": joined_officials,
        "user_session_ids": user_session_ids,
    })


@login_required
def add_session(request, meet_id):
    meet = get_object_or_404(Meet, id=meet_id)
    if request.user != meet.created_by:
        return HttpResponseForbidden('Not allowed')
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if request.method == 'POST':
        sn = request.POST.get('session_number', '').strip()
        date = request.POST.get('date', '').strip()
        start_time = request.POST.get('start_time', '').strip() or '08:00'
        end_time = request.POST.get('end_time', '').strip() or '12:00'
        errors = []
        if not date:
            errors.append('Date is required.')
        if not sn:
            sn = (meet.sessions.count() or 0) + 1
        else:
            try:
                sn = int(sn)
            except ValueError:
                errors.append('Session number must be a whole number.')
        if errors:
            if is_ajax:
                return JsonResponse({'success': False, 'errors': errors}, status=400)
            messages.error(request, ' '.join(errors))
            return redirect('meet-home', meet_id=meet.id)
        has_relay_starts = request.POST.get('has_relay_starts') == 'on'
        offline_mode = request.POST.get('offline_mode') == 'on'
        Session.objects.create(meet=meet, session_number=sn, date=date, start_time=start_time, end_time=end_time, has_relay_starts=has_relay_starts, offline_mode=offline_mode)
        if is_ajax:
            return JsonResponse({'success': True})
    return redirect('meet-home', meet_id=meet.id)


@login_required
def delete_session(request, session_id):
    session = get_object_or_404(Session, pk=session_id)
    if request.user != session.meet.created_by:
        return HttpResponseForbidden('Not allowed')
    meet_id = session.meet.id
    session.delete()
    return redirect('meet-home', meet_id=meet_id)


@login_required
def session_home(request, session_id):
    session = get_object_or_404(Session, id=session_id)
    try:
        load_roster_if_empty()
    except Exception:
        pass
    checked_assignments = SessionAssignment.objects.filter(session=session, checked_in=True)
    uploaded_assignments = SessionAssignment.objects.filter(session=session, created_via_csv=True, checked_in=False)

    # find if the current user has an assignment for this session
    user_assignment = None
    if request.user and request.user.is_authenticated:
        user_assignment = SessionAssignment.objects.filter(session=session, official=request.user).first()

    # all officials who have joined this session (checked-in or not)
    all_assignments = SessionAssignment.objects.filter(session=session).select_related('official')

    return render(request, "meets/session_home.html", {
        "session": session,
        "checked_assignments": checked_assignments,
        "uploaded_assignments": uploaded_assignments,
        "user_assignment": user_assignment,
        "all_assignments": all_assignments,
        "today": timezone.now().date(),
    })


@login_required
@require_POST
def referee_check_in(request, session_id, assignment_id):
    """Allow the meet referee to check in an official."""
    session = get_object_or_404(Session, pk=session_id)
    if request.user != session.meet.created_by:
        return HttpResponseForbidden('Not allowed')
    sa = get_object_or_404(SessionAssignment, pk=assignment_id, session=session)
    sa.checked_in = True
    sa.save()
    messages.success(request, f'{sa.official.get_full_name() or sa.official.username} checked in.')
    return redirect('session-home', session_id=session.id)


@login_required
@require_POST
def referee_checkout_session(request, session_id, assignment_id):
    """Remove an official from the session. Preserves volunteer hours in the log."""
    session = get_object_or_404(Session, pk=session_id)
    if request.user != session.meet.created_by:
        return HttpResponseForbidden('Not allowed')
    sa = get_object_or_404(SessionAssignment, pk=assignment_id, session=session)
    official_name = sa.official.get_full_name() or sa.official.username

    # Snapshot hours if session is running
    if session.status == 'in_progress' and session.started_at:
        now = timezone.now()
        elapsed_sec = max((now - session.started_at).total_seconds(), 0)
        da = DeckAssignment.objects.filter(session=session, official=sa.official).first()
        break_sec = 0
        if da:
            break_sec = da.break_time_total
            if da.on_break and da.break_started_at:
                break_sec += (now - da.break_started_at).total_seconds()
        hours = round(max(elapsed_sec - break_sec, 0) / 3600, 2)
        # Preserve hours in VolunteerLog
        vlog = VolunteerLog.objects.filter(session=session, official=sa.official).first()
        if vlog:
            vlog.hours_worked = hours
            vlog.save()

    # Remove deck assignments and session assignment
    DeckAssignment.objects.filter(session=session, official=sa.official).delete()
    sa.delete()

    messages.success(request, f'{official_name} removed from session.')
    return redirect('session-home', session_id=session.id)


@login_required
def deck_assignments(request, session_id):
    session = get_object_or_404(Session, pk=session_id)
    # only meet creator may manage deck (safe default)
    if request.user != session.meet.created_by:
        return HttpResponseForbidden('Not allowed')

    checked = SessionAssignment.objects.filter(session=session, checked_in=True).select_related('official')
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'generate':
            assignments = generate_deck_assignments(session)
            roles = ['Starter','Deck Referee','Chief Judge','Stroke & Turn','Admin Official']
            # attach suggested role + allowed roles + break length to checked items
            for sa in checked:
                val = assignments.get(sa.official.id) or assignments.get(str(sa.official.id)) or {}
                sa.suggested_role = val.get('role', '')
                sa.assigned_role = val.get('role', '')
                try:
                    sa.break_schedule_json = json.dumps(val.get('break_schedule', []))
                except Exception:
                    sa.break_schedule_json = '[]'
                # compute allowed roles from certification codes (includes extra roles)
                try:
                    codes = _official_cert_codes(sa.official)
                except Exception:
                    codes = set()
                sa.allowed_roles = get_allowed_roles(codes, session)
                sa.pool_number = val.get('pool_number', 1)
                # derive break length
                bl = ''
                try:
                    bs = val.get('break_schedule', [])
                    if isinstance(bs, list) and len(bs) > 0:
                        first = bs[0]
                        if isinstance(first, (int, float)):
                            bl = int(first)
                        else:
                            try:
                                bl = int(str(first))
                            except Exception:
                                bl = ''
                except Exception:
                    bl = ''
                sa.break_length_minutes = bl
            extra_roles = get_extra_roles(session)
            num_pools = session.meet.num_pools or 1
            return render(request, 'meets/session/deck_assignments.html', {
                'session': session,
                'checked': checked,
                'assignments': assignments,
                'roles': roles,
                'extra_roles': extra_roles,
                'num_pools': num_pools,
                'pool_range': list(range(1, num_pools + 1)),
            })
        elif action == 'save':
            # expected JSON payload of assignments
            data = request.POST.get('assignments')
            try:
                assignments = json.loads(data or '{}')
            except Exception:
                assignments = {}
            finalize_and_save_assignments(session, assignments)
            # Also update VolunteerLog roles if session is in progress
            if session.status == 'in_progress':
                for oid_str, info in assignments.items():
                    try:
                        oid = int(oid_str)
                    except (ValueError, TypeError):
                        continue
                    VolunteerLog.objects.filter(session=session, official_id=oid).update(role=info.get('role', ''))
            messages.success(request, 'Deck assignments saved.')
            if session.status == 'in_progress':
                return redirect('session-simulation', session_id=session.id)
            return redirect('session-home', session_id=session.id)

    # GET -> show page (prepare existing assignments mapping)
    existing = {da.official_id: {'role': da.role, 'pool_number': da.pool_number, 'break_schedule': json.loads(da.break_schedule or '[]')} for da in session.deck_assignments.all()}

    # Attach assignment info to each checked assignment for template convenience
    for sa in checked:
        val = existing.get(sa.official_id) or existing.get(str(sa.official_id)) or {}
        sa.suggested_role = val.get('role', '')
        sa.assigned_role = val.get('role', '')
        try:
            sa.break_schedule_json = json.dumps(val.get('break_schedule', []))
        except Exception:
            sa.break_schedule_json = '[]'

    # Compute allowed roles per official based on their certifications (includes extra roles)
    for sa in checked:
        try:
            codes = _official_cert_codes(sa.official)
        except Exception:
            codes = set()
        sa.allowed_roles = get_allowed_roles(codes, session)
        val2 = existing.get(sa.official_id) or {}
        sa.pool_number = val2.get('pool_number', 1)
        # derive a simple break length (minutes) from existing break_schedule if present
        bl = ''
        try:
            bs = val.get('break_schedule', [])
            if isinstance(bs, list) and len(bs) > 0:
                first = bs[0]
                if isinstance(first, (int, float)):
                    bl = int(first)
                else:
                    # try to coerce numeric string
                    try:
                        bl = int(str(first))
                    except Exception:
                        bl = ''
        except Exception:
            bl = ''
        sa.break_length_minutes = bl

    roles = ['Starter','Deck Referee','Chief Judge','Stroke & Turn','Admin Official']
    extra_roles = get_extra_roles(session)
    num_pools = session.meet.num_pools or 1
    return render(request, 'meets/session/deck_assignments.html', {
        'session': session,
        'checked': checked,
        'assignments': existing,
        'roles': roles,
        'extra_roles': extra_roles,
        'num_pools': num_pools,
        'pool_range': list(range(1, num_pools + 1)),
    })


@login_required
def join_sessions_from_meet(request, meet_id):
    meet = get_object_or_404(Meet, id=meet_id)
    if request.method != 'POST':
        return redirect('meet-home', meet_id=meet.id)
    # Support checking and unchecking sessions: `session_ids` represent sessions the user wants to remain joined.
    session_ids = set()
    for sid in request.POST.getlist('session_ids'):
        try:
            session_ids.add(int(sid))
        except Exception:
            continue

    created = 0
    removed = 0

    # Ensure assignments exist for checked sessions; remove assignments for unchecked sessions
    for s in meet.sessions.all():
        try:
            sid = int(s.id)
        except Exception:
            continue
        if sid in session_ids:
            assignment, was_created = SessionAssignment.objects.get_or_create(session=s, official=request.user, defaults={'hours_worked': 0})
            if was_created:
                created += 1
        else:
            # if user was previously assigned and now unchecked -> remove (leave)
            existing = SessionAssignment.objects.filter(session=s, official=request.user)
            if existing.exists():
                existing.delete()
                removed += 1

    if created:
        messages.success(request, f"Joined {created} session(s) for {meet.name}.")
    if removed:
        messages.success(request, f"Left {removed} session(s) for {meet.name}.")
    if not created and not removed:
        messages.info(request, "No changes to your session enrollments.")

    return redirect('official-dashboard')


def _generate_code(n=6):
    return ''.join(random.choices(string.digits, k=n))


def request_login_code(request):
    """Send a one-time code to the provided email for login/registration."""
    if request.method != 'POST':
        return JsonResponse({'status': 'bad_method'}, status=405)
    email = request.POST.get('email') or request.POST.get('email_address')
    if not email:
        return JsonResponse({'status': 'missing_email'}, status=400)

    # Ensure roster is loaded before checking
    try:
        load_roster_if_empty()
    except Exception:
        pass

    # Validate email exists in the official roster (authoritative source)
    roster_exists = RosterEntry.objects.filter(email__iexact=email).exists()
    if not roster_exists:
        return JsonResponse({'status': 'email_not_found'}, status=400)

    code = _generate_code()
    # store code and expiry in session
    key = f'login_code_{email}'
    exp_key = f'login_code_exp_{email}'
    request.session[key] = code
    request.session[exp_key] = (timezone.now() + timedelta(minutes=10)).isoformat()
    try:
        send_mail(
            'Your login code',
            f'Your login code is: {code}',
            settings.DEFAULT_FROM_EMAIL,
            [email],
            fail_silently=False,
        )
    except Exception:
        return JsonResponse({'status': 'email_failed'}, status=500)
    return JsonResponse({'status': 'sent'})


def verify_login_code(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'bad_method'}, status=405)
    email = request.POST.get('email')
    code = request.POST.get('code')
    if not email or not code:
        return JsonResponse({'status': 'missing'}, status=400)
    key = f'login_code_{email}'
    exp_key = f'login_code_exp_{email}'
    stored = request.session.get(key)
    exp = request.session.get(exp_key)
    if not stored or stored != code:
        return JsonResponse({'status': 'invalid_code'}, status=400)
    if exp and dateparse.parse_datetime(exp) < timezone.now():
        return JsonResponse({'status': 'expired'}, status=400)

    # Require a RosterEntry for the email (authoritative source)
    roster = RosterEntry.objects.filter(email__iexact=email).first()
    if not roster:
        return JsonResponse({'status': 'email_not_found'}, status=400)

    # find or create user from roster
    User = get_user_model()
    user, created = User.objects.get_or_create(
        username=roster.member_id,
        defaults={'email': email}
    )
    if created:
        user.set_unusable_password()
        user.first_name = roster.first_name or ''
        user.last_name = roster.last_name or ''
        user.save()

    # log in the user
    login(request, user)
    # cleanup
    try:
        del request.session[key]
        del request.session[exp_key]
    except Exception:
        pass
    return JsonResponse({'status': 'ok'})


@login_required
def edit_session(request, session_id):
    session = get_object_or_404(Session, pk=session_id)
    if request.user != session.meet.created_by:
        return HttpResponseForbidden('Not allowed')
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if request.method == 'POST':
        form = SessionEditForm(request.POST, instance=session)
        if form.is_valid():
            form.save()
            if is_ajax:
                return JsonResponse({'success': True})
            return redirect('meet-home', meet_id=session.meet.id)
        else:
            if is_ajax:
                errors = [f"{field.replace('_', ' ').title()}: {e}" for field, field_errs in form.errors.items() for e in field_errs]
                return JsonResponse({'success': False, 'errors': errors}, status=400)
            messages.error(request, 'Please correct the session form errors.')
    # GET or failed non-AJAX POST: redirect back to meet home instead of separate page
    return redirect('meet-home', meet_id=session.meet.id)


@login_required
@require_POST
def send_join_code_view(request, session_id, assignment_id):
    session = get_object_or_404(Session, pk=session_id)
    assignment = get_object_or_404(SessionAssignment, pk=assignment_id, session=session)

    # Only the meet creator (referee) may send join codes
    if request.user != session.meet.created_by:
        return HttpResponseForbidden('Not allowed')

    meet = session.meet
    join_code = getattr(meet, 'join_code', '')

    # prefer using the current logged-in user's email as sender
    from_email = request.user.email or settings.DEFAULT_FROM_EMAIL

    # In offline mode, display the join code on-screen instead of emailing it
    if getattr(session, 'offline_mode', False):
        messages.info(request, f"Offline mode: Join code for {meet.name} is {join_code}. Share it directly with the official.")
        return redirect('session-home', session_id=session.id)

    if getattr(assignment.official, 'email', None):
        check_in_url = request.build_absolute_uri(reverse('check-in', args=[assignment.id])) + (f'?code={join_code}' if join_code else '')
        context = {
            'subject': f"Join code for {meet.name}",
            'to_email': assignment.official.email,
            'from_email': from_email,
            'join_code': join_code,
            'check_in_url': check_in_url,
            'meet_name': meet.name,
            'sender_name': request.user.get_full_name() or request.user.username,
        }
        try:
            send_email('email/join_code.html', context)
            assignment.join_code_sent = True
            assignment.save()
            messages.success(request, f"Join code sent to {assignment.official.email}.")
        except Exception:
            messages.error(request, "Failed to send join code (check mail settings).")

    return redirect('session-home', session_id=session.id)


@login_required
@require_POST
def send_join_all(request, session_id):
    session = get_object_or_404(Session, pk=session_id)
    if request.user != session.meet.created_by:
        return HttpResponseForbidden('Not allowed')

    assignments = SessionAssignment.objects.filter(session=session, created_via_csv=True, checked_in=False)
    meet = session.meet
    join_code = meet.join_code
    from_email = request.user.email or settings.DEFAULT_FROM_EMAIL
    sent_count = 0
    for assignment in assignments:
        if not assignment.official.email:
            continue
        try:
            check_in_url = request.build_absolute_uri(reverse('check-in', args=[assignment.id])) + f'?code={join_code}'
            context = {
                'subject': f"Join code for {meet.name}",
                'to_email': assignment.official.email,
                'from_email': from_email,
                'join_code': join_code,
                'check_in_url': check_in_url,
                'meet_name': meet.name,
                'sender_name': request.user.get_full_name() or request.user.username,
            }
            send_email('email/join_code.html', context)
            assignment.join_code_sent = True
            assignment.save()
            sent_count += 1
        except Exception:
            continue
    if sent_count:
        messages.success(request, f"Sent join codes to {sent_count} officials.")
    else:
        messages.warning(request, "No join codes were sent; ensure officials have emails and mail settings are correct.")

    return redirect('session-home', session_id=session.id)


def check_in(request, assignment_id):
    code = request.GET.get('code', '')
    assignment = get_object_or_404(SessionAssignment, pk=assignment_id)
    meet = assignment.session.meet
    # Offline mode: only the referee device handles check-in directly
    if getattr(assignment.session, 'offline_mode', False):
        return render(request, 'meets/check_in_fail.html', {'offline': True})
    if code and code == meet.join_code:
        assignment.checked_in = True
        assignment.save()
        return render(request, 'meets/check_in_success.html', {'assignment': assignment})
    return render(request, 'meets/check_in_fail.html', {})


@login_required
@require_POST
def self_check_in(request, session_id):
    session = get_object_or_404(Session, pk=session_id)
    # Offline mode: self check-in disabled
    if getattr(session, 'offline_mode', False):
        messages.error(request, 'This session is in offline mode. The referee will check you in directly.')
        return redirect('session-home', session_id=session.id)
    # must be assigned
    assignment = SessionAssignment.objects.filter(session=session, official=request.user).first()
    if not assignment:
        return HttpResponseForbidden('Not assigned to this session')

    # only allow on the day of the session
    today = timezone.now().date()
    if getattr(session, 'date', None) != today:
        messages.error(request, 'Check-in is allowed only on the day of the session.')
        return redirect('session-home', session_id=session.id)

    assignment.checked_in = True
    assignment.save()
    messages.success(request, 'You are checked in for this session.')
    return redirect('session-home', session_id=session.id)


@login_required
@require_POST
def delete_session_csv(request, session_id):
    session = get_object_or_404(Session, pk=session_id)
    if request.user != session.meet.created_by:
        return HttpResponseForbidden('Not allowed')

    # delete assignments created via CSV for this session and imported rows
    SessionAssignment.objects.filter(session=session, created_via_csv=True).delete()
    ImportedOfficial.objects.filter(session=session).delete()
    return redirect('session-home', session_id=session.id)


def load_roster_if_empty():
    # path to the provided CSV file (adjust if you place it elsewhere)
    csv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'Private Roster PNS Jan 2026.xlsx - 01.09.2026.csv')
    if RosterEntry.objects.exists():
        return
    if not os.path.exists(csv_path):
        return

    with open(csv_path, newline='', encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        for raw in reader:
            row = { (k or '').strip().lower(): (v or '').strip() for k, v in raw.items() }
            member_id = row.get('member id') or row.get('member_id') or ''
            first_name = row.get('first name') or ''
            last_name = row.get('last name') or ''
            email = row.get('member email') or row.get('member_email') or ''
            club = row.get('club') or ''
            if not member_id:
                continue
            try:
                with transaction.atomic():
                    entry = RosterEntry.objects.create(member_id=member_id, first_name=first_name, last_name=last_name, email=email, club=club)
            except Exception:
                continue
            # save certs
            cert_columns = ['reg','apt','bgc','cpt','ao-a','ao-c','cj-a','cj-c','dr-a','dr-c','sr-a','sr-c','st-a','st-c']
            for cert_col in cert_columns:
                val = row.get(cert_col)
                if val:
                    RosterCertification.objects.create(roster=entry, name=cert_col, value=val)

# meets/views.py

import csv
from io import TextIOWrapper
from django.contrib import messages
from .models import Official
from .forms import CSVUploadForm

def upload_officials(request):
    if request.method == 'POST':
        form = CSVUploadForm(request.POST, request.FILES)
        if form.is_valid():
            csv_file = request.FILES['file']
            csv_reader = csv.reader(TextIOWrapper(csv_file, encoding='utf-8'))
            
            for row in csv_reader:
                name, email, phone_number, certification = row
                Official.objects.create(name=name, email=email, phone_number=phone_number, certification=certification)
            
            messages.success(request, 'Officials uploaded successfully!')
            return redirect('home')  # or another page
    else:
        form = CSVUploadForm()

    return render(request, 'meets/upload_officials.html', {'form': form})

# meets/views.py

from .models import Official, Session

def home(request):
    officials = Official.objects.all()
    sessions = Session.objects.all()
    return render(request, 'meets/session_home.html', {'officials': officials, 'sessions': sessions})

from django.core.mail import send_mail
from django.conf import settings
import random
import string

def send_join_code(official_email):
    join_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    send_mail(
        'Your Join Code',
        f'Your join code is {join_code}',
        settings.DEFAULT_FROM_EMAIL,
        [official_email],
        fail_silently=False,
    )


def login_view(request):
    # ensure roster is loaded into DB before handling login
    try:
        load_roster_if_empty()
    except Exception:
        # don't block login if roster load fails
        pass
    if request.method == "POST":
        member_id = request.POST.get("member_id")
        password = request.POST.get("password")

        if not member_id:
            return render(request, "meets/login.html", {"message": "Enter your member ID."})

        # look up roster entry
        roster = None
        try:
            roster = RosterEntry.objects.get(member_id__iexact=member_id)
        except RosterEntry.DoesNotExist:
            roster = None

        # find existing user by username == member_id
        user = None
        try:
            user = User.objects.get(username=member_id)
        except User.DoesNotExist:
            user = None

        # If roster entry exists but no User, require explicit registration
        if roster and not user:
            return render(request, "meets/login.html", {
                "message": "Member ID found but not registered. Please register first.",
                "member_id": member_id
            })

        if user:
            # if user has no usable password, treat provided password as initial creation
            if not user.has_usable_password():
                user.set_password(password)
                user.save()
                auth_user = authenticate(request, username=user.username, password=password)
                if auth_user is not None:
                    login(request, auth_user)
                    return HttpResponseRedirect(reverse("index"))

            # authenticate normally
            auth_user = authenticate(request, username=user.username, password=password)
            if auth_user is not None:
                login(request, auth_user)
                return HttpResponseRedirect(reverse("index"))

        return render(request, "meets/login.html", {
            "message": "Invalid member ID and/or password."
        })
    else:
        return render(request, "meets/login.html")


def logout_view(request):
    logout(request)
    return HttpResponseRedirect(reverse("index"))


def register(request):
    """Registration removed — users are created automatically from the roster on login."""
    return redirect('login')


# ===============================
# OFFICIALS LOGIN / DASHBOARD
# Official-specific login/register removed; use main `login`/`register` views above.

@login_required
def official_dashboard(request):
    """Dashboard for officials: shows enrollments, certs, and available meets.

    Supports searching meets via `?q=term` which will show matching meets
    with their sessions and a Join button for each session.
    """
    user = request.user

    # Get user's certifications from roster
    roster_entry = RosterEntry.objects.filter(member_id__iexact=user.username).first()
    certifications = RosterCertification.objects.filter(roster=roster_entry) if roster_entry else []

    # Get meets/sessions the user is enrolled in via SessionAssignment
    enrollments = SessionAssignment.objects.filter(official=user).select_related('session__meet', 'session')

    # Volunteer hours: sum of hours_worked from past sessions where checked_in or hours > 0
    today = timezone.now().date()
    past_sessions = enrollments.filter(session__date__lt=today).filter(Q(hours_worked__gt=0) | Q(checked_in=True))
    volunteer_hours = round(past_sessions.aggregate(total=Sum('hours_worked'))['total'] or 0)

    # categorize enrollments for summary (keeps previous behavior for stats)
    past_enrollments = []
    present_enrollments = []
    future_enrollments = []
    for e in enrollments:
        sess_date = getattr(e.session, 'date', None)
        did_something = bool(getattr(e, 'hours_worked', 0) or getattr(e, 'checked_in', False))
        if not sess_date:
            continue
        if sess_date < today and did_something:
            past_enrollments.append(e)
        elif sess_date == today and did_something:
            present_enrollments.append(e)
        elif sess_date > today and did_something:
            future_enrollments.append(e)

    # Filters apply to the user's enrollments only (not available meets)
    filter_mode = request.GET.get('filter', 'future')
    q = request.GET.get('q', '').strip()

    if filter_mode == 'past':
        enrollments = enrollments.filter(session__date__lt=today)
    elif filter_mode == 'present':
        enrollments = enrollments.filter(session__date=today)
    else:
        enrollments = enrollments.filter(session__date__gt=today)

    # Available meets — show all meets
    available_meets = Meet.objects.all().order_by('-start_date')

    # apply search term to available meets only
    if q:
        available_meets = available_meets.filter(Q(name__icontains=q) | Q(location__icontains=q)).distinct()

    # meets created by this user (My Meets)
    my_meets = Meet.objects.filter(created_by=user).order_by('-start_date')

    return render(request, "meets/official_dashboard.html", {
        "user": user,
        "certifications": certifications,
        "enrollments": enrollments,
        "volunteer_hours": volunteer_hours,
        "past_enrollments": past_enrollments,
        "present_enrollments": present_enrollments,
        "future_enrollments": future_enrollments,
        "available_meets": available_meets,
        "my_meets": my_meets,
        "q": q,
        "filter_mode": filter_mode,
        "today": timezone.now().date(),
    })


@login_required
def join_meet(request):
    """Officials can join a session via session join code."""
    if request.method == "POST":
        join_code = request.POST.get("join_code", "").strip().upper()
        
        if not join_code:
            return render(request, "meets/join_meet.html", {
                "message": "Enter a join code."
            })
        
        # Find session by join code
        try:
            session = Session.objects.get(join_code=join_code)
        except Session.DoesNotExist:
            return render(request, "meets/join_meet.html", {
                "message": "Invalid join code."
            })
        
        # Create enrollment in this specific session
        assignment, created = SessionAssignment.objects.get_or_create(
            session=session,
            official=request.user,
            defaults={'hours_worked': 0}
        )
        if created:
            messages.success(request, f"You have joined {session.meet.name} - Session {session.session_number}!")
        else:
            messages.info(request, f"You are already enrolled in {session.meet.name} - Session {session.session_number}.")
        
        return HttpResponseRedirect(reverse("official-dashboard"))
    else:
        return render(request, "meets/join_meet.html")


@login_required
def join_session(request, session_id):
    """Directly join a session (no join code required).

    This is used by officials searching for a meet and clicking Join on a session.
    """
    try:
        session = Session.objects.get(pk=session_id)
    except Session.DoesNotExist:
        messages.error(request, "Session not found.")
        return HttpResponseRedirect(reverse("official-dashboard"))

    assignment, created = SessionAssignment.objects.get_or_create(
        session=session,
        official=request.user,
        defaults={'hours_worked': 0}
    )
    if created:
        messages.success(request, f"You have joined {session.meet.name} - Session {session.session_number}!")
    else:
        messages.info(request, f"You are already enrolled in {session.meet.name} - Session {session.session_number}.")

    return HttpResponseRedirect(reverse("official-dashboard"))


@login_required
@require_POST
def leave_session(request, assignment_id):
    """Allow an official to leave a session they are enrolled in."""
    assignment = get_object_or_404(SessionAssignment, pk=assignment_id)
    if assignment.official != request.user:
        return HttpResponseForbidden('Not allowed')
    assignment.delete()
    messages.success(request, f"You have left {assignment.session.meet.name} - Session {assignment.session.session_number}.")
    return HttpResponseRedirect(reverse("official-dashboard"))


@login_required
def referee_dashboard(request):
    """Dashboard for referees showing meets they created."""
    user = request.user
    my_meets = Meet.objects.filter(created_by=user).order_by('-start_date')
    return render(request, 'meets/referee_dashboard.html', {
        'meets': my_meets,
    })


# ===============================
# SESSION LIFECYCLE: START / SIMULATION / END / RESULTS
# ===============================

@login_required
@require_POST
def start_session(request, session_id):
    """Start a session: begin volunteer hours for all checked-in officials."""
    session = get_object_or_404(Session, pk=session_id)
    if request.user != session.meet.created_by:
        return HttpResponseForbidden('Not allowed')
    if session.status != 'not_started':
        messages.warning(request, 'Session has already been started.')
        return redirect('session-simulation', session_id=session.id)

    # Validate that the session date is today
    today = timezone.now().date()
    if session.date != today:
        messages.error(request, 'Session can only be started on its scheduled date.')
        return redirect('session-home', session_id=session.id)

    now = timezone.now()
    session.status = 'in_progress'
    session.started_at = now
    session.save()

    # Create VolunteerLog entries for every checked-in official based on deck assignments
    checked = SessionAssignment.objects.filter(session=session, checked_in=True).select_related('official')
    deck_map = {da.official_id: da.role for da in DeckAssignment.objects.filter(session=session)}

    for sa in checked:
        role = deck_map.get(sa.official_id, '')
        VolunteerLog.objects.get_or_create(
            session=session,
            official=sa.official,
            defaults={'role': role, 'hours_worked': 0},
        )

    messages.success(request, 'Session started! Volunteer hours are now being tracked.')
    return redirect('session-simulation', session_id=session.id)


@login_required
def session_simulation(request, session_id):
    """Live simulation view of the session in progress."""
    session = get_object_or_404(Session, pk=session_id)

    # Build simulation data from deck assignments
    deck_assignments = DeckAssignment.objects.filter(session=session).select_related('official')

    now = timezone.now()
    # Compute session time boundaries using actual started_at if available
    session_start = session.started_at or timezone.make_aware(
        datetime.combine(session.date, session.start_time)
    )
    session_end_dt = timezone.make_aware(
        datetime.combine(session.date, session.end_time)
    )
    total_duration_sec = max((session_end_dt - session_start).total_seconds(), 1)
    elapsed_sec = max((now - session_start).total_seconds(), 0)
    progress_pct = min(elapsed_sec / total_duration_sec * 100, 100)
    remaining_sec = max(total_duration_sec - elapsed_sec, 0)

    officials_data = []
    for da in deck_assignments:
        # Calculate hours worked so far, subtracting break time
        total_break_sec = da.break_time_total
        if da.on_break and da.break_started_at:
            total_break_sec += (now - da.break_started_at).total_seconds()
        active_sec = max(min(elapsed_sec, total_duration_sec) - total_break_sec, 0)
        hours_so_far = round(active_sec / 3600, 2)

        officials_data.append({
            'official': da.official,
            'role': da.role,
            'on_break': da.on_break,
            'hours_so_far': hours_so_far,
            'pool_number': da.pool_number,
        })

    num_pools = session.meet.num_pools or 1
    return render(request, 'meets/session/simulation.html', {
        'session': session,
        'officials_data': officials_data,
        'progress_pct': round(progress_pct, 1),
        'elapsed_minutes': int(elapsed_sec // 60),
        'remaining_minutes': int(remaining_sec // 60),
        'is_running': session.status == 'in_progress',
        'num_pools': num_pools,
        'pool_range': list(range(1, num_pools + 1)),
    })


@login_required
def session_simulation_data(request, session_id):
    """JSON endpoint for live simulation updates (polled by the simulation page)."""
    session = get_object_or_404(Session, pk=session_id)
    deck_assignments = DeckAssignment.objects.filter(session=session).select_related('official')

    now = timezone.now()
    session_start = session.started_at or timezone.make_aware(
        datetime.combine(session.date, session.start_time)
    )
    session_end_dt = timezone.make_aware(
        datetime.combine(session.date, session.end_time)
    )
    total_duration_sec = max((session_end_dt - session_start).total_seconds(), 1)
    elapsed_sec = max((now - session_start).total_seconds(), 0)
    progress_pct = min(elapsed_sec / total_duration_sec * 100, 100)
    remaining_sec = max(total_duration_sec - elapsed_sec, 0)

    officials = []
    for da in deck_assignments:
        # Subtract break time from hours
        total_break_sec = da.break_time_total
        if da.on_break and da.break_started_at:
            total_break_sec += (now - da.break_started_at).total_seconds()
        active_sec = max(min(elapsed_sec, total_duration_sec) - total_break_sec, 0)
        hours_so_far = round(active_sec / 3600, 2)
        officials.append({
            'id': da.official.id,
            'name': da.official.get_full_name() or da.official.username,
            'role': da.role,
            'on_break': da.on_break,
            'hours_so_far': hours_so_far,
        })

    return JsonResponse({
        'status': session.status,
        'progress_pct': round(progress_pct, 1),
        'elapsed_minutes': int(elapsed_sec // 60),
        'remaining_minutes': int(remaining_sec // 60),
        'officials': officials,
    })


@login_required
@require_POST
def end_session(request, session_id):
    """End a session: finalize volunteer hours."""
    session = get_object_or_404(Session, pk=session_id)
    if request.user != session.meet.created_by:
        return HttpResponseForbidden('Not allowed')
    if session.status != 'in_progress':
        messages.warning(request, 'Session is not currently running.')
        return redirect('session-home', session_id=session.id)

    now = timezone.now()
    session.status = 'ended'
    session.ended_at = now
    session.save()

    # Calculate actual hours worked for each volunteer log
    started = session.started_at or timezone.make_aware(
        datetime.combine(session.date, session.start_time)
    )
    total_elapsed_sec = max((now - started).total_seconds(), 0)

    # Build a map of break time per official from DeckAssignments
    break_time_map = {}
    for da in DeckAssignment.objects.filter(session=session):
        total_break = da.break_time_total
        if da.on_break and da.break_started_at:
            total_break += (now - da.break_started_at).total_seconds()
        break_time_map[da.official_id] = total_break

    for vlog in VolunteerLog.objects.filter(session=session):
        break_sec = break_time_map.get(vlog.official_id, 0)
        active_sec = max(total_elapsed_sec - break_sec, 0)
        vlog.hours_worked = round(active_sec / 3600, 2)
        vlog.save()

    # Also update SessionAssignment hours
    for sa in SessionAssignment.objects.filter(session=session, checked_in=True):
        break_sec = break_time_map.get(sa.official_id, 0)
        active_sec = max(total_elapsed_sec - break_sec, 0)
        sa.hours_worked = round(active_sec / 3600, 2)
        sa.save()

    messages.success(request, 'Session ended. You can now review and edit the results.')
    return redirect('session-results', session_id=session.id)


@login_required
@require_POST
def toggle_break(request, session_id, official_id):
    """Toggle break status for an official during the session."""
    session = get_object_or_404(Session, pk=session_id)
    if request.user != session.meet.created_by:
        return JsonResponse({'error': 'Not allowed'}, status=403)
    if session.status != 'in_progress':
        return JsonResponse({'error': 'Session not in progress'}, status=400)

    da = get_object_or_404(DeckAssignment, session=session, official_id=official_id)
    now = timezone.now()
    if da.on_break:
        # Coming back from break — accumulate break time
        if da.break_started_at:
            da.break_time_total += (now - da.break_started_at).total_seconds()
        da.on_break = False
        da.break_started_at = None
    else:
        # Going on break — record start time
        da.on_break = True
        da.break_started_at = now
    da.save()
    return JsonResponse({'on_break': da.on_break})


@login_required
def search_officials(request, session_id):
    """Search for officials by name and return qualified roles."""
    session = get_object_or_404(Session, pk=session_id)
    if request.user != session.meet.created_by:
        return JsonResponse({'error': 'Not allowed'}, status=403)

    query = request.GET.get('q', '').strip()
    if len(query) < 2:
        return JsonResponse({'results': []})

    # Search roster entries by first or last name
    roster_entries = RosterEntry.objects.filter(
        Q(first_name__icontains=query) | Q(last_name__icontains=query)
    )[:20]  # Limit to 20 results

    results = []
    for roster in roster_entries:
        # Get qualified roles for this official
        user = User.objects.filter(username__iexact=roster.member_id).first()
        if user:
            qualified_roles = list(_official_cert_codes(user))
            # Convert cert codes to role names
            role_names = []
            for code in qualified_roles:
                if code in CERT_ROLE_MAP:
                    role_name = CERT_ROLE_MAP[code]
                    if role_name not in role_names:
                        role_names.append(role_name)
            qualified_roles = role_names
        else:
            # If user doesn't exist yet, look at the roster directly
            certs = roster.certifications.all()
            qualified_roles = []
            for cert in certs:
                cert_upper = (cert.name or '').upper().strip()
                if cert_upper in CERT_ROLE_MAP:
                    role_name = CERT_ROLE_MAP[cert_upper]
                    if role_name not in qualified_roles:
                        qualified_roles.append(role_name)

        results.append({
            'id': roster.id,
            'member_id': roster.member_id,
            'name': f"{roster.first_name} {roster.last_name}".strip() or roster.member_id,
            'qualified_roles': qualified_roles
        })

    return JsonResponse({'results': results})


@login_required
@require_POST
def add_official(request, session_id):
    """Add and check in a new official during the session."""
    session = get_object_or_404(Session, pk=session_id)
    if request.user != session.meet.created_by:
        return JsonResponse({'error': 'Not allowed'}, status=403)
    if session.status != 'in_progress':
        return JsonResponse({'error': 'Session not in progress'}, status=400)

    member_id = request.POST.get('member_id', '').strip()
    role = request.POST.get('role', '').strip()

    if not member_id or not role:
        return JsonResponse({'error': 'Member ID and role required'}, status=400)

    # Find roster entry
    roster = RosterEntry.objects.filter(member_id__iexact=member_id).first()
    if not roster:
        return JsonResponse({'error': 'Official not found in roster'}, status=404)

    # Find or create user
    user = User.objects.filter(username__iexact=member_id).first()
    if not user:
        user = User.objects.create_user(username=member_id, email=roster.email or '')
        user.first_name = roster.first_name or ''
        user.last_name = roster.last_name or ''
        user.save()

    # Check if already assigned
    if SessionAssignment.objects.filter(session=session, official=user, checked_in=True).exists():
        return JsonResponse({'error': 'Already assigned'}, status=400)
    # Create new session assignment (or recreate if previously checked out)
    SessionAssignment.objects.create(session=session, official=user, hours_worked=0, checked_in=True)

    # Create deck assignment (may have been deleted on checkout)
    da, _ = DeckAssignment.objects.get_or_create(
        session=session, official=user,
        defaults={'role': role, 'on_break': False}
    )
    if not _:  # already existed, update role
        da.role = role
        da.on_break = False
        da.break_started_at = None
        da.save()

    # Create or update volunteer log
    vlog, _ = VolunteerLog.objects.get_or_create(
        session=session, official=user,
        defaults={'role': role, 'hours_worked': 0}
    )
    if not _:
        vlog.role = role
        vlog.save()

    return JsonResponse({'success': True, 'official': {'id': user.id, 'name': user.get_full_name() or user.username, 'role': role}})


@login_required
def session_results(request, session_id):
    """Post-session page where the referee can edit what each official actually did."""
    session = get_object_or_404(Session, pk=session_id)
    if request.user != session.meet.created_by:
        return HttpResponseForbidden('Not allowed')

    logs = VolunteerLog.objects.filter(session=session).select_related('official')
    roles = ['Starter', 'Deck Referee', 'Chief Judge', 'Stroke & Turn', 'Admin Official']

    if request.method == 'POST':
        # Process edits from the form
        for vlog in logs:
            role_key = f'role_{vlog.id}'
            hours_key = f'hours_{vlog.id}'
            notes_key = f'notes_{vlog.id}'

            if role_key in request.POST:
                vlog.role = request.POST[role_key]
            if hours_key in request.POST:
                try:
                    vlog.hours_worked = round(float(request.POST[hours_key]), 2)
                except (ValueError, TypeError):
                    pass
            if notes_key in request.POST:
                vlog.notes = request.POST[notes_key]
            vlog.save()

            # Sync hours back to SessionAssignment
            sa = SessionAssignment.objects.filter(session=session, official=vlog.official).first()
            if sa:
                sa.hours_worked = vlog.hours_worked
                sa.save()

        messages.success(request, 'Session results saved.')
        return redirect('session-results', session_id=session.id)

    return render(request, 'meets/session/results.html', {
        'session': session,
        'logs': logs,
        'roles': roles,
    })


@login_required
@require_POST
def checkout_official(request, session_id, official_id):
    """Remove an official from the session during simulation. Preserves volunteer hours."""
    session = get_object_or_404(Session, pk=session_id)
    if request.user != session.meet.created_by:
        return JsonResponse({'error': 'Not allowed'}, status=403)
    if session.status != 'in_progress':
        return JsonResponse({'error': 'Session not in progress'}, status=400)

    sa = SessionAssignment.objects.filter(session=session, official_id=official_id).first()
    if not sa:
        return JsonResponse({'error': 'Not found'}, status=404)

    # Snapshot hours into VolunteerLog before removing
    now = timezone.now()
    session_start = session.started_at or timezone.make_aware(datetime.combine(session.date, session.start_time))
    elapsed_sec = max((now - session_start).total_seconds(), 0)
    da = DeckAssignment.objects.filter(session=session, official_id=official_id).first()
    break_sec = 0
    if da:
        break_sec = da.break_time_total
        if da.on_break and da.break_started_at:
            break_sec += (now - da.break_started_at).total_seconds()
    hours = round(max(elapsed_sec - break_sec, 0) / 3600, 2)
    vlog = VolunteerLog.objects.filter(session=session, official_id=official_id).first()
    if vlog:
        vlog.hours_worked = hours
        vlog.save()

    # Remove deck assignment and session assignment (keeps VolunteerLog)
    DeckAssignment.objects.filter(session=session, official_id=official_id).delete()
    sa.delete()

    return JsonResponse({'success': True})
