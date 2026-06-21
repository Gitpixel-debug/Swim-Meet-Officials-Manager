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
from meets.models import RosterEntry, User

# Run migrations fresh
print("Clearing database and running migrations...")
call_command('migrate', verbosity=0)

# Clear all existing roster and user data
RosterEntry.objects.all().delete()
User.objects.all().delete()

print(f"Roster entries after clear: {RosterEntry.objects.count()}")
print(f"Users after clear: {User.objects.count()}")

# TEST 1: Referee Registration with actual member_id from CSV
print("\n=== TEST 1: Referee Registration ===")
client = Client()
resp = client.post('/register', {
    'member_id': 'C4B74D3D9829E2',
    'password': 'testpass123',
    'confirmation': 'testpass123'
}, follow=True)

roster_count = RosterEntry.objects.count()
print(f"Roster entries loaded: {roster_count}")

if roster_count > 70:
    print("✓ Full roster loaded successfully")
else:
    print(f"⚠ Expected 75 entries, got {roster_count}")

# Check if target is in roster
target_roster = RosterEntry.objects.filter(member_id='C4B74D3D9829E2').first()
if target_roster:
    print(f"✓ Target member found: {target_roster.first_name} {target_roster.last_name}")
else:
    print("✗ Target member not found in roster")

# Check if registration succeeded
target_user = User.objects.filter(username='C4B74D3D9829E2').first()
if target_user:
    print(f"✓ User registered successfully")
    print(f"  Name: {target_user.first_name} {target_user.last_name}")
    print(f"  Email: {target_user.email}")
else:
    print("✗ User registration failed")
    content = resp.content.decode()
    if 'Invalid member ID' in content:
        print("  Error: Invalid member ID")

print("\n" + "="*50)
print("REGISTRATION FIX TEST COMPLETE")
print("="*50)
