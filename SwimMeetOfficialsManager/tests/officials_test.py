import os
import sys
import time
from pathlib import Path

# Ensure project root is on sys.path
proj_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(proj_root))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SwimMeetOfficialsManager.settings')
import django
django.setup()

from django.contrib.auth import get_user_model
from meets.models import Meet, Session, SessionAssignment, User, Certification
from django.test import Client
from django.utils import timezone

# Create or get users
User = get_user_model()

# Create referee (meet creator)
referee, created = User.objects.get_or_create(username='referee1', defaults={'email':'referee@example.com'})
if created or not referee.has_usable_password():
    referee.set_password('refereepass')
    referee.save()
    print(f"✓ Created/updated referee user")

# Create official
official, created = User.objects.get_or_create(username='official1', defaults={'email':'official@example.com'})
if created or not official.has_usable_password():
    official.set_password('officialpass')
    official.save()
    print(f"✓ Created/updated official user")

# Add a certification to the official
cert, _ = Certification.objects.get_or_create(name='REG', defaults={'level': 'Level 1'})
official.certifications.add(cert)

# Create a meet as referee
meet = Meet.objects.create(
    name='Test Swim Meet',
    location='Local Pool',
    start_date='2026-03-01',
    end_date='2026-03-02',
    created_by=referee
)
print(f"✓ Created meet: {meet.name} (join code: {meet.join_code})")

# Create a session
session = Session.objects.create(
    meet=meet,
    session_number=1,
    date='2026-03-01',
    start_time='08:00',
    end_time='12:00'
)
print(f"✓ Created session: {session}")

# Test client
client = Client()

# TEST 1: Official login
print("\n--- TEST 1: Official Login ---")
# Double-check official has usable password
print(f"Official usable password: {official.has_usable_password()}")
print(f"Official username: {official.username}")
logged_in = client.login(username='official1', password='officialpass')
print(f"✓ Official login successful: {logged_in}")
if not logged_in:
    # Try to re-verify user exists and password works
    from django.contrib.auth import authenticate
    user = authenticate(username='official1', password='officialpass')
    print(f"  Direct authenticate result: {user}")
    if not user:
        print("  Re-setting password and retrying...")
        official.set_password('officialpass')
        official.save()
        user = authenticate(username='official1', password='officialpass')
        logged_in = client.login(username='official1', password='officialpass')
        print(f"  After reset, login: {logged_in}")

# TEST 2: Visit official dashboard
print("\n--- TEST 2: Official Dashboard (before join) ---")
resp = client.get('/official/dashboard')
print(f"✓ Dashboard status: {resp.status_code}")
assert resp.status_code == 200, "Dashboard should be accessible"
content = resp.content.decode()
assert 'official1' in content or 'Official' in content, "Should show official name/page"
print("✓ Dashboard page loaded")

# TEST 3: Join meet with join code
print("\n--- TEST 3: Official Joins Meet via Join Code ---")
resp = client.post('/official/join', {'join_code': meet.join_code}, follow=True)
print(f"✓ Join response status: {resp.status_code}")
# Check if assignment was created
assignment = SessionAssignment.objects.filter(official=official, session=session).first()
assert assignment is not None, "Official should have a session assignment"
print(f"✓ Official is now enrolled in {meet.name}")

# TEST 4: Verify dashboard shows enrollment
print("\n--- TEST 4: Verify Enrollment on Dashboard ---")
resp = client.get('/official/dashboard')
content = resp.content.decode()
assert meet.name in content, "Meet name should appear on dashboard"
assert 'Your Enrollments' in content, "Enrollments section should exist"
print(f"✓ Dashboard shows enrollment in {meet.name}")

# TEST 5: Verify certifications show on dashboard
print("\n--- TEST 5: Verify Certifications on Dashboard ---")
assert cert.name in content, "Certification should appear on dashboard"
print(f"✓ Dashboard shows certification: {cert.name}")

# TEST 6: Test invalid join code
print("\n--- TEST 6: Invalid Join Code ---")
client.logout()
client.login(username='official1', password='officialpass')
resp = client.post('/official/join', {'join_code': 'INVALID'}, follow=False)
assert resp.status_code == 200, "Should re-render join form"
content = resp.content.decode()
assert 'Invalid join code' in content, "Should show error message"
print("✓ Invalid join code properly rejected")

print("\n" + "="*50)
print("ALL TESTS PASSED! ✓")
print("="*50)
