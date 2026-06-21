import os
import sys
from pathlib import Path
proj_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(proj_root))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','SwimMeetOfficialsManager.settings')
import django
django.setup()
from django.core.management import call_command
from django.test import Client
from django.contrib.auth import get_user_model
from meets.models import Meet, Session, SessionAssignment, RosterEntry
User = get_user_model()

# fresh DB
call_command('migrate', verbosity=0)

# ensure roster loaded
from meets.views import load_roster_if_empty
load_roster_if_empty()

# create a meet creator user and a meet with sessions
creator, _ = User.objects.get_or_create(username='creator', defaults={'email':'creator@example.com'})
if not creator.has_usable_password():
    creator.set_password('creatorpass')
    creator.save()
meet = Meet.objects.create(name='Test Meet X', location='Test Pool', start_date='2026-03-01', end_date='2026-03-02', created_by=creator, num_sessions=2)
Session.objects.filter(meet=meet).delete()
for i in range(1,3):
    Session.objects.create(meet=meet, session_number=i, date='2026-03-01', start_time='08:00', end_time='12:00')

sessions = list(meet.sessions.all())
print('Created meet and sessions:', meet.id, [s.id for s in sessions])

# register official using existing roster member
client = Client()
member = RosterEntry.objects.first()
if not member:
    print('No roster entries; abort')
    sys.exit(1)

print('Using roster member:', member.member_id)
resp = client.post('/official/register', {'member_id': member.member_id, 'password':'joinpass123', 'confirmation':'joinpass123'}, follow=True)
print('register status', resp.status_code)

# login
client.logout()
ok = client.login(username=member.member_id, password='joinpass123')
print('login ok', ok)

# search for meet
resp = client.get('/official/dashboard', {'q':'Test Meet X'})
print('dashboard search status', resp.status_code)

# join first session
session_id = sessions[0].id
resp = client.post(f'/official/join_session/{session_id}', follow=True)
print('join post status', resp.status_code)

# verify assignment
exists = SessionAssignment.objects.filter(session__id=session_id, official__username=member.member_id).exists()
print('assignment exists', exists)
if exists:
    assignment = SessionAssignment.objects.filter(session__id=session_id, official__username=member.member_id).first()
    resp = client.post(f'/official/leave/{assignment.id}', follow=True)
    print('leave post status', resp.status_code)
    exists_after = SessionAssignment.objects.filter(pk=assignment.id).exists()
    print('assignment exists after leave', exists_after)
