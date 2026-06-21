import os
import time
import sys
from pathlib import Path
# ensure project root is on sys.path so Django can import the project package
proj_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(proj_root))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SwimMeetOfficialsManager.settings')
import django
django.setup()

from django.contrib.auth import get_user_model
from meets.models import Meet, Session, SessionAssignment
from django.test import Client
from django.utils import timezone

User = get_user_model()

# Create users
creator, created = User.objects.get_or_create(username='creator', defaults={'email':'creator@example.com'})
if created:
    creator.set_password('pass')
    creator.save()

official, created = User.objects.get_or_create(username='official', defaults={'email':'official@example.com'})
if created:
    official.set_password('pass2')
    official.save()

# Create meet
meet = Meet.objects.create(name='Test Meet', location='Test Pool', start_date='2026-02-01', end_date='2026-02-02', created_by=creator)

# Create session
session = Session.objects.create(meet=meet, session_number=1, date='2026-02-01', start_time='08:00', end_time='12:00')

# Create assignment
assignment, created = SessionAssignment.objects.get_or_create(session=session, official=official, defaults={'hours_worked': 0, 'created_via_csv': True})

print('Created test data:')
print('Meet:', meet.id, meet.name)
print('Session:', session.id)
print('Assignment:', assignment.id, 'official email:', official.email)

# Use test client to login and post to send_join_code
c = Client()
logged_in = c.login(username='creator', password='pass')
print('Logged in as creator:', logged_in)

url = f'/session/{session.id}/send_join/{assignment.id}/'
print('POSTing to', url)
resp = c.post(url, follow=True)
print('Response status:', resp.status_code)
print('Response redirects:', [r[0] for r in resp.redirect_chain])

# allow background thread to finish
print('Waiting for email thread to finish...')
time.sleep(2)
print('Done.')
