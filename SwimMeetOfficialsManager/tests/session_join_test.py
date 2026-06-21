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

from django.core.management import call_command
from django.contrib.auth import get_user_model
from meets.models import Meet, Session, SessionAssignment, User, Certification
from django.test import Client

# Run migrations first
call_command('migrate', verbosity=0)

User = get_user_model()

# Create users
referee, created = User.objects.get_or_create(username='test_referee', defaults={'email':'referee@example.com'})
if created or not referee.has_usable_password():
    referee.set_password('refpass')
    referee.save()

official, created = User.objects.get_or_create(username='test_official', defaults={'email':'official@example.com'})
if created or not official.has_usable_password():
    official.set_password('offpass')
    official.save()

# Add certification
cert, _ = Certification.objects.get_or_create(name='REG', defaults={'level': 'Level 1'})
official.certifications.add(cert)

# Create meet with multiple sessions
meet = Meet.objects.create(
    name='Multi-Session Meet',
    location='Local Pool',
    start_date='2026-04-01',
    end_date='2026-04-03',
    created_by=referee
)
print(f"✓ Created meet: {meet.name}")

# Create 3 sessions
sessions = []
for i in range(1, 4):
    session = Session.objects.create(
        meet=meet,
        session_number=i,
        date='2026-04-0' + str(i),
        start_time='08:00',
        end_time='12:00'
    )
    sessions.append(session)
    print(f"  ✓ Session {i}: join_code = {session.join_code}")

# Test client
client = Client()

# TEST 1: Verify session join codes exist
print("\n--- TEST 1: Session Join Codes ---")
for session in sessions:
    assert session.join_code, f"Session {session.session_number} should have join_code"
    assert len(session.join_code) == 8, "Join code should be 8 chars"
    print(f"✓ Session {session.session_number}: {session.join_code}")

# TEST 2: Official joins Session 1
print("\n--- TEST 2: Official Joins Session 1 ---")
client.login(username='test_official', password='offpass')
resp = client.post('/official/join', {'join_code': sessions[0].join_code}, follow=True)
assert resp.status_code == 200
assignment1 = SessionAssignment.objects.filter(official=official, session=sessions[0]).first()
assert assignment1 is not None, "Should be enrolled in Session 1"
print(f"✓ Official enrolled in Session 1")

# TEST 3: Verify enrollment shows on dashboard
print("\n--- TEST 3: Dashboard Shows Enrollment ---")
resp = client.get('/official/dashboard')
content = resp.content.decode()
assert sessions[0].join_code not in content, "Join code should NOT be visible on dashboard"
assert 'Multi-Session Meet' in content
assert 'Session 1' in content
print(f"✓ Dashboard shows enrollment (join code hidden)")

# TEST 4: Accordion shows all sessions
print("\n--- TEST 4: Accordion Shows All Sessions ---")
assert 'Available Meets' in content, "Should have 'Available Meets' section"
assert 'accordion' in content.lower() or 'collapse' in content.lower(), "Should have accordion/collapse elements"
print(f"✓ Dashboard accordion structure present")

# TEST 5: Official joins Session 2
print("\n--- TEST 5: Official Joins Session 2 ---")
resp = client.post('/official/join', {'join_code': sessions[1].join_code}, follow=True)
assignment2 = SessionAssignment.objects.filter(official=official, session=sessions[1]).first()
assert assignment2 is not None
print(f"✓ Official now enrolled in 2 sessions")

# TEST 6: Verify both enrollments on dashboard
print("\n--- TEST 6: Both Enrollments Visible ---")
resp = client.get('/official/dashboard')
content = resp.content.decode()
# Count "Session" occurrences (should be >3 because of headers, accordion, and table)
session_count = content.count('Session ')
assert session_count >= 4, f"Should mention sessions multiple times, got {session_count}"
print(f"✓ Dashboard shows both enrollments")

# TEST 7: Test invalid join code
print("\n--- TEST 7: Invalid Session Join Code ---")
resp = client.post('/official/join', {'join_code': 'BADCODE1'}, follow=False)
content = resp.content.decode()
assert 'Invalid join code' in content
print(f"✓ Invalid code properly rejected")

# TEST 8: Verify session_home shows join code
print("\n--- TEST 8: Session Home Shows Join Code ---")
client.login(username='test_referee', password='refpass')
resp = client.get(f'/session/{sessions[0].id}')
content = resp.content.decode()
assert sessions[0].join_code in content, "Session home should display the join code"
assert 'Join Code for Officials' in content
print(f"✓ Session home displays join code: {sessions[0].join_code}")

print("\n" + "="*50)
print("ALL SESSION-LEVEL JOIN TESTS PASSED! ✓")
print("="*50)
