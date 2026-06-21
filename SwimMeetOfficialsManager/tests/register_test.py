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

# Create a roster entry (simulating CSV load)
roster = RosterEntry.objects.create(
    member_id='MEM001',
    first_name='John',
    last_name='Referee',
    email='john@example.com',
    club='Local Club'
)
print(f"✓ Created roster entry: {roster.member_id}")

client = Client()

# TEST 1: Try to register with invalid member_id
print("\n--- TEST 1: Invalid Member ID ---")
resp = client.post('/register', {
    'member_id': 'INVALID999',
    'password': 'test123',
    'confirmation': 'test123'
}, follow=False)
content = resp.content.decode()
assert 'Invalid member ID' in content, "Should reject invalid member ID"
print("✓ Invalid member ID properly rejected")

# TEST 2: Register with valid member_id
print("\n--- TEST 2: Valid Member ID Registration ---")
resp = client.post('/register', {
    'member_id': 'MEM001',
    'password': 'pass123',
    'confirmation': 'pass123'
}, follow=True)
assert resp.status_code == 200, "Should succeed"
# Check user was created
from django.contrib.auth import get_user_model
User = get_user_model()
user = User.objects.get(username='MEM001')
assert user.first_name == 'John', "Should have first name from roster"
assert user.last_name == 'Referee', "Should have last name from roster"
assert user.email == 'john@example.com', "Should have email from roster"
print(f"✓ Registered with member_id MEM001")
print(f"  User created: {user.get_full_name()} <{user.email}>")

# TEST 3: Try to register same member_id twice
print("\n--- TEST 3: Duplicate Registration ---")
resp = client.post('/register', {
    'member_id': 'MEM001',
    'password': 'newpass',
    'confirmation': 'newpass'
}, follow=False)
content = resp.content.decode()
assert 'already registered' in content, "Should reject duplicate registration"
print("✓ Duplicate member ID properly rejected")

# TEST 4: Login with registered member_id
print("\n--- TEST 4: Login with Member ID ---")
client.logout()
logged_in = client.login(username='MEM001', password='pass123')
assert logged_in, "Should login with member_id"
print("✓ Successfully logged in with member_id")

# TEST 5: Password mismatch
print("\n--- TEST 5: Password Mismatch ---")
client.logout()
# Create another roster entry for this test
roster2 = RosterEntry.objects.create(
    member_id='MEM002',
    first_name='Jane',
    last_name='Referee',
    email='jane@example.com',
    club='Another Club'
)
resp = client.post('/register', {
    'member_id': 'MEM002',
    'password': 'pass123',
    'confirmation': 'different'
}, follow=False)
content = resp.content.decode()
assert 'must match' in content.lower(), "Should reject mismatched passwords"
print("✓ Mismatched passwords properly rejected")

print("\n" + "="*50)
print("ALL REFEREE REGISTRATION TESTS PASSED! ✓")
print("="*50)
