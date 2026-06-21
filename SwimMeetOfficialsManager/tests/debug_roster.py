import os
import sys
import csv
from pathlib import Path

proj_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(proj_root))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SwimMeetOfficialsManager.settings')
import django
django.setup()

from django.core.management import call_command
from meets.models import RosterEntry

# Run migrations
call_command('migrate', verbosity=0)

# Debug CSV loading
csv_path = r"c:\Users\zorro\Programming\Private Roster PNS Jan 2026.xlsx - 09.06.2025.csv"
print(f"CSV Path: {csv_path}")
print(f"File exists: {os.path.exists(csv_path)}")

# Manual CSV reading
print("\n=== Manual CSV Reading ===")
count = 0
target_found = False
with open(csv_path, newline='', encoding='utf-8') as fh:
    reader = csv.DictReader(fh)
    print(f"Headers: {reader.fieldnames}")
    for raw in reader:
        count += 1
        row = { (k or '').strip().lower(): (v or '').strip() for k, v in raw.items() }
        member_id = row.get('member id') or row.get('member_id') or ''
        if member_id == 'C4B74D3D9829E2':
            target_found = True
            print(f"\nTarget found at row {count}")
            print(f"  member_id (from 'member id'): {row.get('member id')}")
            print(f"  member_id (from 'member_id'): {row.get('member_id')}")
            print(f"  first_name: {row.get('first name')}")
            print(f"  last_name: {row.get('last name')}")
            print(f"  email: {row.get('member email')}")
            break
        if count <= 3:
            print(f"\nRow {count}: member_id={member_id}")

print(f"\nTotal rows in CSV: {count}")
print(f"Target member_id found: {target_found}")

# Check loaded roster
print("\n=== Database Roster Entries ===")
from meets.views import load_roster_if_empty
load_roster_if_empty()
entries = RosterEntry.objects.all()
print(f"Total roster entries in DB: {entries.count()}")
for entry in entries[:5]:
    print(f"  {entry.member_id}: {entry.first_name} {entry.last_name}")

# Check if target is there
target_in_db = RosterEntry.objects.filter(member_id__iexact='C4B74D3D9829E2').exists()
print(f"\nTarget member_id in DB: {target_in_db}")
