import os
import sys
from pathlib import Path

proj_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(proj_root))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SwimMeetOfficialsManager.settings')
import django
django.setup()

from django.test import Client
from django.core.management import call_command
from meets.models import User

# Fresh database
call_command('migrate', verbosity=0)

client = Client()

# Register official
resp = client.post('/official/register', {
    'member_id': 'C4B74D3D9829E2',
    'password': 'testpass123',
    'confirmation': 'testpass123'
}, follow=True)

print("=== Users in Database ===")
for user in User.objects.all():
    print(f"Username: {user.username}")
    print(f"  First: {user.first_name}, Last: {user.last_name}")
    print(f"  Email: {user.email}")
    print(f"  Usable password: {user.has_usable_password()}")
    
    # Try to authenticate
    from django.contrib.auth import authenticate
    auth_result = authenticate(username=user.username, password='testpass123')
    print(f"  Auth with 'testpass123': {auth_result is not None}")
    print()
