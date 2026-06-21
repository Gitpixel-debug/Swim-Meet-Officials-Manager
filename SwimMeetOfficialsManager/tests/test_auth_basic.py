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
from meets.models import User
from django.contrib.auth import authenticate

# Fresh database
call_command('migrate', verbosity=0)

# Manually create a user
print("=== Manual User Creation ===")
user = User.objects.create_user(
    username='testuser',
    email='test@test.com',
    password='testpass123'
)
print(f"✓ Created user: {user.username}")

# Try to authenticate
result = authenticate(username='testuser', password='testpass123')
print(f"Authentication result: {result}")
print(f"Same user? {result == user if result else 'No match'}")

# Try with client.login
print("\n=== Client Login Test ===")
client = Client()
success = client.login(username='testuser', password='testpass123')
print(f"client.login() result: {success}")

if success:
    print("✓ Can access protected page")
    resp = client.get('/official/dashboard', follow=True)
    print(f"  Status: {resp.status_code}")
