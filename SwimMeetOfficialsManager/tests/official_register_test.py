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

# Create roster entries
roster1 = RosterEntry.objects.create(
    member_id='OFF001',
    first_name='Alice',
    last_name='Official',
    email='alice@example.com',
    club='Club A'
)
print(f"✓ Created roster entry: {roster1.member_id}")

client = Client()

# TEST 1: Invalid member ID for official register
print("\n--- TEST 1: Invalid Member ID ---")
resp = client.post('/official/register', {
    'member_id': 'BADOFF999',
    'password': 'test123',
    'confirmation': 'test123'
}, follow=False)
content = resp.content.decode()
assert 'Invalid member ID' in content, "Should reject invalid member ID"
print("✓ Invalid member ID properly rejected")

# TEST 2: Valid member ID registration for official
print("\n--- TEST 2: Valid Member ID Registration ---")
resp = client.post('/official/register', {
    'member_id': 'OFF001',
    'password': 'offpass123',
    'confirmation': 'offpass123'
}, follow=True)
assert resp.status_code == 200
from django.contrib.auth import get_user_model
User = get_user_model()
user = User.objects.get(username='OFF001')
assert user.first_name == 'Alice', "Should have first name from roster"
assert user.last_name == 'Official', "Should have last name from roster"
assert user.email == 'alice@example.com', "Should have email from roster"
print(f"✓ Registered as official with member_id OFF001")
print(f"  User created: {user.get_full_name()} <{user.email}>")

# TEST 3: Duplicate registration
print("\n--- TEST 3: Duplicate Registration ---")
resp = client.post('/official/register', {
    'member_id': 'OFF001',
    'password': 'newpass',
    'confirmation': 'newpass'
}, follow=False)
content = resp.content.decode()
assert 'already registered' in content, "Should reject duplicate registration"
print("✓ Duplicate member ID properly rejected")

# TEST 4: Login as official
print("\n--- TEST 4: Official Login ---")
client.logout()
logged_in = client.login(username='OFF001', password='offpass123')
assert logged_in, "Should login with member_id"
print("✓ Successfully logged in as official")

# TEST 5: Password mismatch
print("\n--- TEST 5: Password Mismatch ---")
client.logout()
roster2 = RosterEntry.objects.create(
    member_id='OFF002',
    first_name='Bob',
    last_name='Official',
    email='bob@example.com',
    club='Club B'
)
resp = client.post('/official/register', {
    'member_id': 'OFF002',
    'password': 'pass123',
    'confirmation': 'different'
}, follow=False)
content = resp.content.decode()
assert 'must match' in content.lower()
print("✓ Mismatched passwords properly rejected")

print("\n" + "="*50)
print("ALL OFFICIAL REGISTRATION TESTS PASSED! ✓")
print("="*50)
