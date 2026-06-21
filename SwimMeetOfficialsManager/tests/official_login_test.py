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
from django.contrib.auth import get_user_model

User = get_user_model()

# Run migrations
call_command('migrate', verbosity=0)

# Create roster entry
roster = RosterEntry.objects.create(
    member_id='TEST_OFF',
    first_name='Test',
    last_name='Official',
    email='test@example.com',
    club='Test Club'
)
print(f"✓ Created roster entry: {roster.member_id}")

# Create user via register
client = Client()
resp = client.post('/official/register', {
    'member_id': 'TEST_OFF',
    'password': 'testpass123',
    'confirmation': 'testpass123'
}, follow=True)
print(f"✓ Registered official with member_id TEST_OFF")

# TEST 1: Login with valid member_id
print("\n--- TEST 1: Valid Official Login ---")
client.logout()
logged_in = client.login(username='TEST_OFF', password='testpass123')
assert logged_in, "Should login with member_id"
resp = client.get('/official/dashboard')
assert resp.status_code == 200, "Should access dashboard after login"
print("✓ Successfully logged in with member_id and accessed dashboard")

# TEST 2: Invalid member_id
print("\n--- TEST 2: Invalid Member ID ---")
client.logout()
resp = client.post('/official/login', {
    'member_id': 'NOTEXIST',
    'password': 'wrongpass'
}, follow=False)
content = resp.content.decode()
assert 'Invalid member ID' in content, "Should show invalid member ID message"
print("✓ Invalid member ID properly rejected")

# TEST 3: Wrong password
print("\n--- TEST 3: Wrong Password ---")
resp = client.post('/official/login', {
    'member_id': 'TEST_OFF',
    'password': 'wrongpassword'
}, follow=False)
content = resp.content.decode()
assert 'Invalid member ID and/or password' in content, "Should show auth error"
print("✓ Wrong password properly rejected")

# TEST 4: Missing member_id
print("\n--- TEST 4: Missing Member ID ---")
resp = client.post('/official/login', {
    'member_id': '',
    'password': 'testpass123'
}, follow=False)
content = resp.content.decode()
assert 'Enter your member ID' in content, "Should ask for member ID"
print("✓ Missing member ID properly rejected")

print("\n" + "="*50)
print("ALL OFFICIAL LOGIN TESTS PASSED! ✓")
print("="*50)
