import os
import sys
from pathlib import Path
proj_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(proj_root))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','SwimMeetOfficialsManager.settings')
import django
django.setup()
from django.test import Client
from django.core.management import call_command

# ensure fresh DB
call_command('migrate', verbosity=0)

from meets.views import load_roster_if_empty
from django.contrib.auth import get_user_model
User = get_user_model()

load_roster_if_empty()

client = Client()
# create a user directly and force login
user, created = User.objects.get_or_create(username='C4B74D3D9829E2')
if created:
	user.set_password('testpass123')
	# attempt to populate name/email from roster if available
	try:
		from meets.models import RosterEntry
		roster = RosterEntry.objects.filter(member_id__iexact='C4B74D3D9829E2').first()
		if roster:
			user.first_name = roster.first_name
			user.last_name = roster.last_name
			user.email = roster.email or ''
	except Exception:
		pass
	user.save()

client.force_login(user)
resp = client.get('/official/dashboard')
print('dashboard status', resp.status_code)
content = resp.content.decode()
print('has data-bs-toggle:', 'data-bs-toggle="collapse"' in content or 'data-bs-toggle=\'collapse\'' in content)
print('has data-bs-target:', 'data-bs-target' in content or 'data-bs-target=' in content)
print('has accordion-button:', 'accordion-button' in content)
print('snippet check:', 'Available Meets' in content or 'Sessions:' in content)
