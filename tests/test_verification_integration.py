"""
Integration Tests for Document Verification Feature
Run these to verify all components work together correctly.
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'loan_system.settings')
sys.path.insert(0, '/home/nick/ACCT.f')
django.setup()

from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
import json
import base64

User = get_user_model()


class DocumentVerificationIntegrationTest(TestCase):
    """Complete integration test suite"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testclient',
            email='test@example.com',
            password='testpass123'
        )
        self.client.login(username='testclient', password='testpass123')
    
    def test_01_profile_page_renders(self):
        """Verify the profile page loads correctly with React embedded"""
        response = self.client.get('/client/profile/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'verification-root')
        self.assertContains(response, 'VERIFICATION_CONTEXT')
        self.assertContains(response, 'csrf-token')
    
    def test_02_document_upload_api(self):
        """Test document upload endpoint works"""
        # Create test image
        image_content = base64.b64decode(
            'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
        )
        
        test_file = SimpleUploadedFile(
            'test_id.jpg',
            image_content,
            content_type='image/jpeg'
        )
        
        response = self.client.post(
            '/api/client/documents/upload/',
            {'id_front': test_file},
            format='multipart'
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn('files', data)
    
    def test_03_profile_update_api(self):
        """Test profile update with extracted data"""
        payload = {
            'extracted_data': {
                'personalInfo': {
                    'idNumber': '12345678',
                    'fullName': 'John Doe',
                    'dateOfBirth': '1990-01-15',
                    'gender': 'male'
                },
                'employmentInfo': {
                    'employer': 'ABC Company',
                    'monthlyIncome': 45000
                }
            },
            'verification_results': {
                'idCard': {'verified': True, 'confidence': 95},
                'payslips': {'verified': True, 'count': 2}
            }
        }
        
        response = self.client.post(
            '/api/client/profile/update/',
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')
    
    def test_04_verification_status_api(self):
        """Test verification status endpoint"""
        response = self.client.get('/api/client/verification-status/')
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.content)
        self.assertIn('status', data)
        self.assertIn('id_front_url', data)
        self.assertIn('payslip_urls', data)
    
    def test_05_csrf_token_present(self):
        """Verify CSRF token is available in template"""
        response = self.client.get('/client/profile/')
        self.assertContains(response, 'csrftoken')
    
    def test_06_static_files_configured(self):
        """Verify static files configuration"""
        from django.conf import settings
        self.assertTrue(hasattr(settings, 'STATICFILES_DIRS'))
        self.assertTrue(any('verification' in str(d) for d in settings.STATICFILES_DIRS))


class URLIntegrationTest(TestCase):
    """Test all URLs resolve correctly"""
    
    def test_url_resolution(self):
        """Verify all URLs are properly configured"""
        urls_to_test = [
            '/client/profile/',
            '/api/client/documents/upload/',
            '/api/client/profile/update/',
            '/api/client/verification-status/',
        ]
        
        for url in urls_to_test:
            response = self.client.get(url)
            # Should not return 404
            self.assertNotEqual(response.status_code, 404, f"URL {url} not found")


class ModelIntegrationTest(TestCase):
    """Test model fields exist for verification"""
    
    def test_client_model_fields(self):
        """Verify Client model has required verification fields"""
        from loan_system.models import Client  # Adjust import as needed
        
        required_fields = [
            'id_number',
            'id_front_url',
            'id_back_url',
            'payslip_urls',
            'selfie_url',
            'verification_status',
            'verification_results',
            'monthly_income',
            'employer',
        ]
        
        for field in required_fields:
            self.assertTrue(
                hasattr(Client, field),
                f"Client model missing field: {field}"
            )


def run_integration_tests():
    """Run all integration tests"""
    import unittest
    
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test classes
    suite.addTests(loader.loadTestsFromTestCase(DocumentVerificationIntegrationTest))
    suite.addTests(loader.loadTestsFromTestCase(URLIntegrationTest))
    suite.addTests(loader.loadTestsFromTestCase(ModelIntegrationTest))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_integration_tests()
    sys.exit(0 if success else 1)
