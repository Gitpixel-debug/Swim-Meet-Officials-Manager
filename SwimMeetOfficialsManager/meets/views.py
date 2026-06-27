import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.http import HttpResponseRedirect, JsonResponse
from django.urls import reverse
from django.db import IntegrityError
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
from datetime import timedelta
import math
from django.db.models import Sum
import random
import string
import logging
from django.utils import dateparse
from django.views.decorators.http import require_POST
from django.db.models import Q
from .services.deck_assignment import generate_deck_assignments, finalize_and_save_assignments, CERT_ROLE_MAP, _official_cert_codes
from django.views.decorators.csrf import csrf_exempt
from django.core import signing
from django.core.signing import BadSignature, SignatureExpired

logger = logging.getLogger(__name__)

# Create your views here.
def index(request):
    return render(request, 'meets/index.html')

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
            days_count = max(days, 1)

            if days_count == 1:
                sessions_per_day = [total_sessions]
            else:
                found = False
                for x in range(total_sessions, 0, -1):
                    y = total_sessions - (days_count - 1) * x
                    if 0 < y < x:
                        sessions_per_day = [y] + [x] * (days_count - 1)
                        found = True
                        break
                if not found:
                    for x in range(total_sessions, 0, -1):
                        y = total_sessions - (days_count - 1) * x
                        if 0 <= y <= x:
                            sessions_per_day = [y] + [x] * (days_count - 1)
                            found = True
                            break
                if not found:
                    sessions_per_day = [0] * days_count
                    rem = total_sessions
                    for d_idx in range(days_count - 1, -1, -1):
                        if d_idx == 0:
                            sessions_per_day[d_idx] = rem
                        else:
                            val = math.ceil(rem / (d_idx + 1))
                            sessions_per_day[d_idx] = val
                            rem -= val

            session_num = 1
            for day_idx, count_for_day in enumerate(sessions_per_day):
                session_date = start + timedelta(days=day_idx)
                for j in range(count_for_day):
                    start_hour = (8 + j * 4) % 24
                    end_hour = (12 + j * 4) % 24
                    start_time = f"{start_hour:02d}:00"
                    end_time = f"{end_hour:02d}:00"
                    Session.objects.create(
                        meet=meet,
                        session_number=session_num,
                        date=session_date,
                        start_time=start_time,
                        end_time=end_time
                    )
                    session_num += 1

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
    sessions_list = list(meet.sessions.all().order_by('session_number'))
    for s in sessions_list:
        s.joined_assignments = list(SessionAssignment.objects.filter(session=s).select_related('official'))

    # Prefill calculations for adding a new session
    last_day_date = (meet.end_date or meet.start_date).strftime('%Y-%m-%d') if (meet.end_date or meet.start_date) else ''
    
    last_session = meet.sessions.order_by('session_number').last()
    if last_session:
        next_session_number = last_session.session_number + 1
        
        import datetime as dt
        try:
            last_start = last_session.start_time
            dummy_datetime = dt.datetime.combine(dt.date.today(), last_start)
            next_start_dt = dummy_datetime + dt.timedelta(hours=4)
            next_session_start = next_start_dt.time().strftime('%H:%M')
            
            last_end = last_session.end_time
            dummy_end_datetime = dt.datetime.combine(dt.date.today(), last_end)
            next_end_dt = dummy_end_datetime + dt.timedelta(hours=4)
            next_session_end = next_end_dt.time().strftime('%H:%M')
        except Exception:
            next_session_start = '08:00'
            next_session_end = '12:00'
    else:
        next_session_number = 1
        next_session_start = '08:00'
        next_session_end = '12:00'

    return render(request, "meets/meet_home.html", {
        "meet": meet,
        "sessions": sessions_list,
        "joined_officials": joined_officials,
        "user_session_ids": user_session_ids,
        "next_session_number": next_session_number,
        "next_session_date": last_day_date,
        "next_session_start": next_session_start,
        "next_session_end": next_session_end,
    })


@login_required
def add_session(request, meet_id):
    meet = get_object_or_404(Meet, id=meet_id)
    if request.user != meet.created_by:
        return HttpResponseForbidden('Not allowed')
    if request.method == 'POST':
        sn = request.POST.get('session_number')
        date = request.POST.get('date')
        start_time = request.POST.get('start_time') or '08:00'
        end_time = request.POST.get('end_time') or '12:00'
        try:
            sn = int(sn)
        except Exception:
            sn = (meet.sessions.count() or 0) + 1
        Session.objects.create(meet=meet, session_number=sn, date=date, start_time=start_time, end_time=end_time)
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
    today = timezone.now().date()
    is_meet_referee = request.user.is_authenticated and request.user == session.meet.created_by
    meet_started = bool(session.meet.start_date and session.meet.start_date <= today)

    return render(request, "meets/session_home.html", {
        "session": session,
        "checked_assignments": checked_assignments,
        "uploaded_assignments": uploaded_assignments,
        "user_assignment": user_assignment,
        "all_assignments": all_assignments,
        "today": today,
        "is_meet_referee": is_meet_referee,
        "meet_started": meet_started,
    })


@login_required
def deck_assignments(request, session_id):
    session = get_object_or_404(Session, pk=session_id)
    # only meet creator may manage deck (safe default)
    if request.user != session.meet.created_by:
        return HttpResponseForbidden('Not allowed')

    checked = SessionAssignment.objects.filter(session=session).select_related('official')
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
                # compute allowed roles from certification codes
                try:
                    codes = _official_cert_codes(sa.official)
                except Exception:
                    codes = set()
                allowed = []
                for code in codes:
                    role = CERT_ROLE_MAP.get(code)
                    if role and role not in allowed:
                        allowed.append(role)
                sa.allowed_roles = allowed
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
            return render(request, 'meets/session/deck_assignments.html', {
                'session': session,
                'checked': checked,
                'assignments': assignments,
                'roles': roles,
            })
        elif action == 'save':
            # expected JSON payload of assignments
            data = request.POST.get('assignments')
            try:
                assignments = json.loads(data or '{}')
            except Exception:
                assignments = {}
            finalize_and_save_assignments(session, assignments)
            messages.success(request, 'Deck assignments saved.')
            return redirect('session-home', session_id=session.id)

    # GET -> show page (prepare existing assignments mapping)
    existing = {da.official_id: {'role': da.role, 'break_schedule': json.loads(da.break_schedule or '[]')} for da in session.deck_assignments.all()}

    # Attach assignment info to each checked assignment for template convenience
    for sa in checked:
        val = existing.get(sa.official_id) or existing.get(str(sa.official_id)) or {}
        sa.suggested_role = val.get('role', '')
        sa.assigned_role = val.get('role', '')
        try:
            sa.break_schedule_json = json.dumps(val.get('break_schedule', []))
        except Exception:
            sa.break_schedule_json = '[]'

    # Compute allowed roles per official based on their certifications
    for sa in checked:
        val = existing.get(sa.official_id) or existing.get(str(sa.official_id)) or {}
        try:
            codes = _official_cert_codes(sa.official)
        except Exception:
            codes = set()
        allowed = []
        for code in codes:
            role = CERT_ROLE_MAP.get(code)
            if role and role not in allowed:
                allowed.append(role)
        # attach ordered allowed roles; if none, leave empty list (no permissions)
        sa.allowed_roles = allowed
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
    return render(request, 'meets/session/deck_assignments.html', {
        'session': session,
        'checked': checked,
        'assignments': existing,
        'roles': roles,
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


def _wants_json_response(request):
    return request.headers.get('x-requested-with') == 'XMLHttpRequest'


def _validate_registration_identity(member_id, email):
    member_id = (member_id or '').strip()
    email = (email or '').strip()
    if not member_id or not email:
        return None, 'Enter your member ID and email.'

    try:
        roster = RosterEntry.objects.get(member_id__iexact=member_id)
    except RosterEntry.DoesNotExist:
        return None, 'Invalid member ID.'

    roster_email = (roster.email or '').strip()
    if roster_email and roster_email.lower() != email.lower():
        return None, 'Provided email does not match roster record.'

    if User.objects.filter(username=member_id).exists():
        return None, 'Member ID already registered.'

    return roster, None


def request_login_code(request):
    """Send a one-time code to the provided email for login/registration."""
    if request.method != 'POST':
        return JsonResponse({'status': 'bad_method'}, status=405)
    email = request.POST.get('email') or request.POST.get('email_address')
    if not email:
        return JsonResponse({'status': 'missing_email'}, status=400)
    code = _generate_code()
    token = signing.dumps({'email': email, 'code': code}, salt='login-code')
    try:
        send_mail(
            'Your login code',
            f'Your login code is: {code}',
            settings.DEFAULT_FROM_EMAIL,
            [email],
            fail_silently=False,
        )
    except Exception:
        if _wants_json_response(request):
            return JsonResponse({'status': 'email_failed', 'message': 'Unable to send the login code. Check email settings and try again.'}, status=500)
        return redirect(f"{reverse('login')}?message=Unable+to+send+the+login+code.+Check+email+settings+and+try+again.&email={email}")
    if _wants_json_response(request):
        return JsonResponse({'status': 'sent', 'token': token})
    return redirect(f"{reverse('login')}?message=Code+sent+to+{email}&email={email}&verify=1&token={token}")


def verify_login_code(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'bad_method'}, status=405)
    email = request.POST.get('email')
    code = request.POST.get('code')
    token = request.POST.get('token')
    if not email or not code or not token:
        return JsonResponse({'status': 'missing'}, status=400)
    try:
        payload = signing.loads(token, salt='login-code', max_age=600)
    except SignatureExpired:
        if _wants_json_response(request):
            return JsonResponse({'status': 'expired'}, status=400)
        return redirect(f"{reverse('login')}?message=That+code+has+expired.+Request+a+new+one.&email={email}")
    except BadSignature:
        if _wants_json_response(request):
            return JsonResponse({'status': 'invalid_code'}, status=400)
        return redirect(f"{reverse('login')}?message=Invalid+code.&email={email}&verify=1")

    token_email = payload.get('email')
    token_code = payload.get('code')
    if token_email != email or token_code != code:
        if _wants_json_response(request):
            return JsonResponse({'status': 'invalid_code'}, status=400)
        return redirect(f"{reverse('login')}?message=Invalid+code.&email={email}&verify=1")

    # find or create user by email or roster
    User = get_user_model()
    user = User.objects.filter(email__iexact=email).first()
    if not user:
        roster = RosterEntry.objects.filter(email__iexact=email).first()
        if roster:
            username = roster.member_id
            user, created = User.objects.get_or_create(username=username, defaults={'email': email})
            if created:
                user.set_unusable_password()
                user.first_name = roster.first_name or ''
                user.last_name = roster.last_name or ''
                user.save()
        else:
            # fallback: create user with localpart username
            local = email.split('@', 1)[0]
            user, created = User.objects.get_or_create(username=local, defaults={'email': email})
            if created:
                user.set_unusable_password()
                user.save()

    # log in the user
    login(request, user)
    if _wants_json_response(request):
        return JsonResponse({'status': 'ok'})
    return redirect('official-dashboard')


@login_required
def edit_session(request, session_id):
    session = get_object_or_404(Session, pk=session_id)

    if request.method == 'POST':
        form = SessionEditForm(request.POST, instance=session)
        if form.is_valid():
            form.save()
            return redirect('session-home', session_id=session.id)
    else:
        form = SessionEditForm(instance=session)

    return render(request, 'meets/edit_session.html', {'form': form, 'session': session})


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
    if code and code == meet.join_code:
        assignment.checked_in = True
        assignment.save()
        return render(request, 'meets/check_in_success.html', {'assignment': assignment})
    return render(request, 'meets/check_in_fail.html', {})


@login_required
@require_POST
def self_check_in(request, session_id):
    session = get_object_or_404(Session, pk=session_id)
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
def set_assignment_check_in(request, assignment_id):
    assignment = get_object_or_404(SessionAssignment, pk=assignment_id)
    session = assignment.session
    meet = session.meet

    if request.user != meet.created_by:
        return HttpResponseForbidden('Not allowed')

    today = timezone.now().date()
    if not meet.start_date or meet.start_date > today:
        messages.error(request, 'Check-in controls are available only after the meet has started.')
        return redirect('session-home', session_id=session.id)

    target = (request.POST.get('checked_in') or '').strip()
    assignment.checked_in = (target == '1')
    assignment.save(update_fields=['checked_in'])

    if assignment.checked_in:
        messages.success(request, 'Official marked as checked in.')
    else:
        messages.success(request, 'Official check-in removed.')
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
    # Path resolved relative to this file so it works on any deployment (Vercel, local, etc.)
    csv_path = os.path.join(os.path.dirname(__file__), 'data', 'roster.csv')
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
                entry, _created = RosterEntry.objects.update_or_create(
                    member_id=member_id,
                    defaults={
                        'first_name': first_name,
                        'last_name': last_name,
                        'email': email,
                        'club': club,
                    },
                )
            except Exception:
                logger.exception('Failed to upsert roster entry %s', member_id)
                continue
            # save certs
            cert_columns = ['reg','apt','bgc','cpt','ao-a','ao-c','cj-a','cj-c','dr-a','dr-c','sr-a','sr-c','st-a','st-c']
            for cert_col in cert_columns:
                val = row.get(cert_col)
                if val:
                    RosterCertification.objects.update_or_create(
                        roster=entry,
                        name=cert_col,
                        defaults={'value': val},
                    )

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
    message = request.GET.get('message') or ''
    email = request.GET.get('email') or ''
    token = request.GET.get('token') or ''
    show_verify = request.GET.get('verify') == '1' or bool(email)

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
        return render(request, "meets/login.html", {
            "message": message,
            "email": email,
            "token": token,
            "show_verify": show_verify,
        })


def logout_view(request):
    logout(request)
    return HttpResponseRedirect(reverse("index"))


def register(request):
    # ensure roster is loaded into DB before handling registration
    try:
        load_roster_if_empty()
    except Exception:
        # don't block registration if roster load fails
        pass
    
    message = request.GET.get('message') or ''
    member_id = request.GET.get('member_id') or ''
    email = request.GET.get('email') or ''
    token = request.GET.get('token') or ''
    show_verify = request.GET.get('verify') == '1' or bool(token)

    if request.method == "POST":
        action = request.POST.get('action') or 'request_code'
        member_id = (request.POST.get("member_id") or '').strip()
        email = (request.POST.get("email") or '').strip()

        if action == 'request_code':
            roster, err = _validate_registration_identity(member_id, email)
            if err:
                return render(request, "meets/register.html", {
                    "message": err,
                    "member_id": member_id,
                    "email": email,
                    "token": '',
                    "show_verify": False,
                })

            code = _generate_code()
            token = signing.dumps({'member_id': member_id, 'email': email, 'code': code}, salt='register-code')
            try:
                send_mail(
                    'Your registration code',
                    f'Your registration code is: {code}',
                    settings.DEFAULT_FROM_EMAIL,
                    [email],
                    fail_silently=False,
                )
            except Exception:
                return render(request, "meets/register.html", {
                    "message": "Unable to send verification code. Check email settings and try again.",
                    "member_id": member_id,
                    "email": email,
                    "token": '',
                    "show_verify": False,
                })

            return render(request, "meets/register.html", {
                "message": f"Code sent to {email}.",
                "member_id": member_id,
                "email": email,
                "token": token,
                "show_verify": True,
            })

        if action == 'verify_code':
            code = (request.POST.get('code') or '').strip()
            token = (request.POST.get('token') or '').strip()
            if not member_id or not email or not code or not token:
                return render(request, "meets/register.html", {
                    "message": "Enter your member ID, email, and verification code.",
                    "member_id": member_id,
                    "email": email,
                    "token": token,
                    "show_verify": True,
                })

            try:
                payload = signing.loads(token, salt='register-code', max_age=600)
            except SignatureExpired:
                return render(request, "meets/register.html", {
                    "message": "That code has expired. Request a new one.",
                    "member_id": member_id,
                    "email": email,
                    "token": '',
                    "show_verify": False,
                })
            except BadSignature:
                return render(request, "meets/register.html", {
                    "message": "Invalid verification code.",
                    "member_id": member_id,
                    "email": email,
                    "token": '',
                    "show_verify": False,
                })

            if payload.get('member_id') != member_id or payload.get('email') != email or payload.get('code') != code:
                return render(request, "meets/register.html", {
                    "message": "Invalid verification code.",
                    "member_id": member_id,
                    "email": email,
                    "token": token,
                    "show_verify": True,
                })

            roster, err = _validate_registration_identity(member_id, email)
            if err:
                return render(request, "meets/register.html", {
                    "message": err,
                    "member_id": member_id,
                    "email": email,
                    "token": '',
                    "show_verify": False,
                })

            try:
                user = User.objects.create_user(username=member_id, email=email)
                user.set_unusable_password()
                user.first_name = roster.first_name or ''
                user.last_name = roster.last_name or ''
                user.save()
            except IntegrityError:
                return render(request, "meets/register.html", {
                    "message": "Registration failed. Try again.",
                    "member_id": member_id,
                    "email": email,
                    "token": '',
                    "show_verify": False,
                })

            login(request, user)
            return HttpResponseRedirect(reverse("official-dashboard"))

        return render(request, "meets/register.html", {
            "message": "Invalid registration action.",
            "member_id": member_id,
            "email": email,
            "token": token,
            "show_verify": show_verify,
        })

    return render(request, "meets/register.html", {
        "message": message,
        "member_id": member_id,
        "email": email,
        "token": token,
        "show_verify": show_verify,
    })


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

    # Volunteer hours: count of distinct meets where the user "did something" in the past
    today = timezone.now().date()
    meets_done_qs = enrollments.filter(session__date__lt=today).filter(Q(hours_worked__gt=0) | Q(checked_in=True)).values_list('session__meet', flat=True).distinct()
    volunteer_hours = meets_done_qs.count()

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

    # Available meets remain independent (show upcoming meets)
    available_meets = Meet.objects.filter(start_date__gt=today)

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
