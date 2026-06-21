import os
import sys
from pathlib import Path

proj_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(proj_root))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SwimMeetOfficialsManager.settings')
import django
django.setup()

from django.test import Client

print("=== End-to-End Test: Official Registration & Dashboard ===\n")

client = Client()

# Step 1: Register
print("Step 1: Register as official")
resp = client.post('/official/register', {
    'member_id': 'C4B74D3D9829E2',
    'password': 'testpass123',
    'confirmation': 'testpass123'
}, follow=True)

if resp.status_code == 200:
    print("✓ Registration page accessed")
    
    # Check if it auto-logged in
    if resp.wsgi_request.user.is_authenticated:
        print(f"✓ Auto-logged in as {resp.wsgi_request.user.username}")
    else:
        print("⚠ Not auto-logged in after registration, need to login separately")
else:
    print(f"✗ Registration returned {resp.status_code}")

# Step 2: Login
print("\nStep 2: Login")
client.logout()
success = client.login(username='C4B74D3D9829E2', password='testpass123')
if success:
    print("✓ Login successful")
else:
    print("✗ Login failed")
    sys.exit(1)

# Step 3: Access dashboard
print("\nStep 3: Access official dashboard")
resp = client.get('/official/dashboard', follow=True)

if resp.status_code == 200:
    print("✓ Dashboard accessible (200 OK)")
    content = resp.content.decode()
    
    # Check for certifications
    if "No certifications on record" in content:
        print("✗ ERROR: Shows 'No certifications on record'")
        print("\nDEBUGGING...")
        from meets.models import RosterEntry, RosterCertification
        roster = RosterEntry.objects.filter(member_id='C4B74D3D9829E2').first()
        if roster:
            certs = RosterCertification.objects.filter(roster=roster)
            print(f"  Roster has {certs.count()} certifications in DB")
        else:
            print("  No roster entry found")
    elif "Your Certifications" in content:
        print("✓ 'Your Certifications' section found")
        
        # Count certs
        certs_to_check = ['REG', 'APT', 'BGC', 'CPT', 'AO-C', 'DR-A', 'SR-C', 'ST-C']
        found = [c for c in certs_to_check if c in content]
        print(f"✓ Found {len(found)} certifications displaying:")
        for cert in found:
            print(f"  - {cert}")
    else:
        print("⚠ 'Your Certifications' section not found")
else:
    print(f"✗ Dashboard returned {resp.status_code}")

print("\n" + "="*60)
print("TEST COMPLETE")
print("="*60)
