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

# Fresh database
call_command('migrate', verbosity=0)

# Register Kamal
client = Client()
resp = client.post('/register', {
    'member_id': 'C4B74D3D9829E2',
    'password': 'testpass123',
    'confirmation': 'testpass123'
}, follow=True)

print("=== Registration Test ===")
user = User.objects.filter(username='C4B74D3D9829E2').first()
if user:
    print(f"✓ User registered: {user.first_name} {user.last_name}")
else:
    print("✗ User not found")
    sys.exit(1)

# Check if user is logged in after registration
print("\n=== Dashboard Access (as Referee) ===")
resp_index = client.get('/index')
if resp_index.status_code == 200:
    print(f"✓ Can access index page after registration")
else:
    print(f"✗ Cannot access index page")

# Now test official dashboard - need to login as official
print("\n=== Official Dashboard Test ===")
client.logout()

# Register as official with different member ID
resp = client.post('/official/register', {
    'member_id': 'C4B74D3D9829E2',
    'password': 'testpass123',
    'confirmation': 'testpass123'
}, follow=True)

# Check if error says already registered
content = resp.content.decode()
if 'already registered' in content.lower():
    print("✓ Member ID already in system (expected)")
    
    # Try to login as official
    client.logout()
    resp = client.post('/official/login', {
        'member_id': 'C4B74D3D9829E2',
        'password': 'testpass123'
    }, follow=True)
    
    if resp.status_code == 200 and 'Your Certifications' in resp.content.decode():
        print("✓ Official login successful")
        
        dashboard_content = resp.content.decode()
        
        # Check for certification names
        certs_to_check = ['REG', 'APT', 'BGC', 'CPT', 'AO-C', 'DR-A', 'SR-C', 'ST-C']
        found_certs = []
        missing_certs = []

        for cert in certs_to_check:
            if cert in dashboard_content:
                found_certs.append(cert)
            else:
                missing_certs.append(cert)

        print(f"\n✓ Certifications found on dashboard: {len(found_certs)}")
        for cert in found_certs:
            print(f"  ✓ {cert}")

        if missing_certs:
            print(f"\n  Missing: {missing_certs}")

        # Check for the error message
        if "No certifications on record" in dashboard_content:
            print("\n✗ ERROR: 'No certifications on record' message found!")
        else:
            print("\n✓ Certifications are displaying correctly!")
    else:
        print("✗ Official login failed or dashboard not found")
else:
    print("✗ Registration error (member should already be in system)")
    print(f"  Error: {content[:200]}")

print("\n" + "="*50)
print("CERTIFICATION DISPLAY TEST COMPLETE")
print("="*50)
