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
from meets.models import RosterEntry

# Run migrations
call_command('migrate', verbosity=0)

# TEST 1: Referee Registration with actual member_id from CSV
print("\n=== TEST 1: Referee Registration ===")
client = Client()
resp = client.post('/register', {
    'member_id': 'C4B74D3D9829E2',
    'password': 'testpass123',
    'confirmation': 'testpass123'
}, follow=True)
content = resp.content.decode()

if 'C4B74D3D9829E2' in RosterEntry.objects.values_list('member_id', flat=True):
    print("✓ Roster loaded successfully")
    print(f"  Roster entries: {RosterEntry.objects.count()}")
    roster = RosterEntry.objects.get(member_id='C4B74D3D9829E2')
    print(f"  Name: {roster.first_name} {roster.last_name}")
    print(f"  Email: {roster.email}")
else:
    print("✗ Roster not loaded")
    print(f"  Roster entries: {RosterEntry.objects.count()}")

if 'Invalid member ID' not in content and resp.status_code == 200:
    print("✓ Registration succeeded (redirected to index)")
else:
    print("✗ Registration failed")
    if 'Invalid member ID' in content:
        print("  Error: Invalid member ID")
    print(f"  Status: {resp.status_code}")

# TEST 2: Official Registration with same member_id
print("\n=== TEST 2: Official Registration ===")
client.logout()
resp = client.post('/official/register', {
    'member_id': 'C4B74D3D9829E3',  # Different member ID to avoid duplicate
    'password': 'testpass123',
    'confirmation': 'testpass123'
}, follow=True)
content = resp.content.decode()

if 'Invalid member ID' not in content and resp.status_code == 200:
    print("✓ Official registration succeeded")
else:
    print("✗ Official registration failed")
    if 'Invalid member ID' in content:
        print("  Error: Invalid member ID")

print("\n" + "="*50)
print("REGISTRATION FIX TESTS COMPLETE")
print("="*50)
