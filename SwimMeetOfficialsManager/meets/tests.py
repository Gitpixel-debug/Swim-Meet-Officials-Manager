from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from meets.models import RosterEntry, RosterCertification

User = get_user_model()

class OfficialCertificationsTest(TestCase):
    def setUp(self):
        self.client = Client()
    
    def test_official_dashboard_shows_certifications(self):
        """Test that official dashboard displays certifications from roster"""
        
        # Step 1: Register as official
        resp = self.client.post('/official/register', {
            'member_id': 'C4B74D3D9829E2',
            'password': 'testpass123',
            'confirmation': 'testpass123'
        }, follow=True)
        
        self.assertEqual(resp.status_code, 200)
        
        # Step 2: Verify user was created
        user = User.objects.get(username='C4B74D3D9829E2')
        self.assertEqual(user.first_name, 'Kamal')
        self.assertEqual(user.last_name, 'Choudhary')
        
        # Step 3: Login
        self.client.logout()
        logged_in = self.client.login(
            username='C4B74D3D9829E2',
            password='testpass123'
        )
        self.assertTrue(logged_in, "Login should succeed")
        
        # Step 4: Access dashboard
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
