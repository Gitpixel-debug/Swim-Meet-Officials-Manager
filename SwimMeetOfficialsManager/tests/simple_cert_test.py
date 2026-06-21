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

# Fresh database
call_command('migrate', verbosity=0)

client = Client()

# Step 1: Register official
print("=== Step 1: Register Official ===")
resp = client.post('/official/register', {
    'member_id': 'C4B74D3D9829E2',
    'password': 'testpass123',
    'confirmation': 'testpass123'
}, follow=True)

if resp.status_code == 200:
    print("✓ Registration returned 200")
else:
    print(f"✗ Registration returned {resp.status_code}")

# Step 2: Login as official
print("\n=== Step 2: Login as Official ===")
client.logout()

# Use client.login() directly instead of POST
success = client.login(username='C4B74D3D9829E2', password='testpass123')
if success:
    print("✓ client.login() succeeded")
else:
    print("✗ client.login() failed")

# Step 3: Access dashboard
print("\n=== Step 3: Access Official Dashboard ===")
resp = client.get('/official/dashboard', follow=True)

if resp.status_code == 200:
    print("✓ Dashboard accessible")
    content = resp.content.decode()
    
    if "Your Certifications" in content:
        print("✓ 'Your Certifications' section found")
    else:
        print("✗ 'Your Certifications' section not found")
    
    if "No certifications on record" in content:
        print("✗ ERROR: Shows 'No certifications on record'")
    else:
        print("✓ Certifications are showing")
    
    # Count how many cert names appear
    certs_to_check = ['REG', 'APT', 'BGC', 'CPT', 'AO-C', 'DR-A', 'SR-C', 'ST-C']
    found = [c for c in certs_to_check if c in content]
    print(f"\n✓ Found {len(found)} out of {len(certs_to_check)} expected certifications")
    for cert in found:
        print(f"  ✓ {cert}")
    
else:
    print(f"✗ Dashboard returned {resp.status_code}")

print("\n" + "="*50)
