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
from meets.models import User, RosterEntry
from django.contrib.auth import authenticate

# Fresh database
call_command('migrate', verbosity=0)

# Register Kamal via the form
client = Client()
resp = client.post('/official/register', {
    'member_id': 'C4B74D3D9829E2',
    'password': 'Testpass123',  # Try different case
    'confirmation': 'Testpass123'
}, follow=True)

print("=== Check User After Registration ===")
user = User.objects.filter(username='C4B74D3D9829E2').first()
if user:
    print(f"✓ User created: {user.first_name} {user.last_name}")
    
    # Try auth
    result = authenticate(username='C4B74D3D9829E2', password='Testpass123')
    print(f"Auth with registered password: {result is not None}")
else:
    print("✗ User not found")

# Check roster
print("\n=== Check Roster ===")
roster = RosterEntry.objects.filter(member_id='C4B74D3D9829E2').first()
if roster:
    print(f"✓ Roster entry found: {roster.first_name} {roster.last_name}")
    from meets.models import RosterCertification
    certs = RosterCertification.objects.filter(roster=roster)
    print(f"  Certifications: {certs.count()}")
    for cert in certs[:3]:
        print(f"    - {cert.name}: {cert.value}")
else:
    print("✗ No roster entry")

# Now login and check dashboard
print("\n=== Dashboard Test ===")
client.logout()
success = client.login(username='C4B74D3D9829E2', password='Testpass123')
print(f"Login success: {success}")

if not success:
    print("Trying password without capital T...")
    success = client.login(username='C4B74D3D9829E2', password='testpass123')
    print(f"Login with lowercase: {success}")

if success:
    resp = client.get('/official/dashboard', follow=True)
    content = resp.content.decode()
    
    if "No certifications on record" in content:
        print("✗ Shows 'No certifications on record'")
        # Debug
        print("\nDebugging dashboard view...")
        from meets.views import official_dashboard
        print(f"  Request user: {resp.wsgi_request.user}")
        print(f"  Is authenticated: {resp.wsgi_request.user.is_authenticated}")
    else:
        print("✓ Certifications are showing")
        
        certs_to_check = ['REG', 'APT', 'BGC', 'CPT']
        found = [c for c in certs_to_check if c in content]
        print(f"  Found: {found}")
else:
    print("✗ Cannot login")
