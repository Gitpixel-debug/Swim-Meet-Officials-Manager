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
from django.contrib.auth import authenticate

# Fresh database
call_command('migrate', verbosity=0)

# Manually trace what the registration view does
client = Client()
print("=== Simulating registration ===")

from meets.models import RosterEntry
from django.db import IntegrityError

# Load roster
from meets.views import load_roster_if_empty
load_roster_if_empty()

member_id = 'C4B74D3D9829E2'
password = 'testpass123'

# Check roster
roster = RosterEntry.objects.get(member_id__iexact=member_id)
print(f"Roster entry: {roster.first_name} {roster.last_name}")

# Check user doesn't exist
user_exists = User.objects.filter(username=member_id).exists()
print(f"User already exists: {user_exists}")

# Create user exactly as the view does
email = roster.email or ''
print(f"Creating user with:")
print(f"  username: {member_id}")
print(f"  email: {email}")
print(f"  password: {password}")

try:
    user = User.objects.create_user(member_id, email, password)
    user.first_name = roster.first_name or ''
    user.last_name = roster.last_name or ''
    user.save()
    print(f"✓ User created successfully")
    
    # Check the password hash
    print(f"\nUser details:")
    print(f"  id: {user.id}")
    print(f"  username: {user.username}")
    print(f"  password (hashed): {user.password[:50]}...")
    print(f"  has_usable_password: {user.has_usable_password()}")
    
    # Try to authenticate
    print(f"\nAuthentication test:")
    auth_user = authenticate(username=member_id, password=password)
    print(f"  Result: {auth_user}")
    
    # Try check_password directly
    print(f"  check_password directly: {user.check_password(password)}")
    
except IntegrityError as e:
    print(f"✗ IntegrityError: {e}")
