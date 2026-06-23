from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from meets.models import RosterEntry, RosterCertification

User = get_user_model()

class OfficialCertificationsTest(TestCase):
    def setUp(self):
        self.client = Client()
    
    def test_official_dashboard_shows_certifications(self):
        """Test that official dashboard displays certifications from roster"""
        
        # Step 1: Register as official (Step 1 of OTP)
        resp = self.client.post('/official/register', {
            'action': 'request_code',
            'member_id': 'C4B74D3D9829E2',
            'email': 'kamal.choudhary@gmail.com'
        })
        self.assertEqual(resp.status_code, 200)
        
        token = resp.context['token']
        
        # Pull code from mail outbox
        from django.core import mail
        self.assertEqual(len(mail.outbox), 1)
        email_body = mail.outbox[0].body
        import re
        code_match = re.search(r'Your registration code is:\s+(\d+)', email_body)
        self.assertTrue(code_match, "Code not found in email!")
        code = code_match.group(1)
        
        # Step 2: Verify code (Step 2 of OTP)
        resp = self.client.post('/official/register', {
            'action': 'verify_code',
            'member_id': 'C4B74D3D9829E2',
            'email': 'kamal.choudhary@gmail.com',
            'code': code,
            'token': token
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
        
        # Step 3: Verify user was created
        user = User.objects.get(username='C4B74D3D9829E2')
        self.assertEqual(user.first_name, 'Kamal')
        self.assertEqual(user.last_name, 'Choudhary')
        
        # Step 4: Access dashboard
        self.client.force_login(user)
        resp = self.client.get('/official/dashboard', follow=True)
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        
        # Step 5: Verify certifications are displayed
        self.assertNotIn("No certifications on record", content)
        self.assertIn("Your Certifications", content)
        
        # Verify specific certifications appear
        expected_certs = ['REG', 'APT', 'BGC', 'CPT', 'AO-C', 'DR-A', 'SR-C', 'ST-C']
        for cert in expected_certs:
            self.assertIn(cert, content, f"Certification {cert} should appear on dashboard")
