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
from meets.models import RosterEntry, RosterCertification

# Fresh database
call_command('migrate', verbosity=0)

# Manual debug of CSV loading
csv_path = r"c:\Users\zorro\Programming\Private Roster PNS Jan 2026.xlsx - 09.06.2025.csv"

print("=== CSV Reading Debug ===")
with open(csv_path, newline='', encoding='utf-8') as fh:
    reader = csv.DictReader(fh)
    print(f"Headers: {reader.fieldnames}\n")
    
    for raw in reader:
        row = { (k or '').strip().lower(): (v or '').strip() for k, v in raw.items() }
        member_id = row.get('member id') or row.get('member_id') or ''
        
        if member_id == 'C4B74D3D9829E2':
            print(f"Found Kamal Choudhary:")
            print(f"  member_id: {member_id}")
            
            cert_columns = ['reg','apt','bgc','cpt','ao-a','ao-c','cj-a','cj-c','dr-a','dr-c','sr-a','sr-c','st-a','st-c']
            print(f"\n  Certifications from CSV:")
            for cert_col in cert_columns:
                val = row.get(cert_col)
                print(f"    {cert_col}: {val}")
            break

# Now load roster via the function
print("\n=== Loading Roster ===")
from meets.views import load_roster_if_empty
load_roster_if_empty()

# Check what's in the database
print(f"\nRoster entries: {RosterEntry.objects.count()}")
kamal = RosterEntry.objects.filter(member_id='C4B74D3D9829E2').first()
if kamal:
    print(f"\nKamal found in database:")
    print(f"  Name: {kamal.first_name} {kamal.last_name}")
    print(f"  Email: {kamal.email}")
    
    certs = RosterCertification.objects.filter(roster=kamal)
    print(f"\n  Certifications in database: {certs.count()}")
    for cert in certs:
        print(f"    {cert.name}: {cert.value}")
else:
    print("\nKamal not found in database!")
