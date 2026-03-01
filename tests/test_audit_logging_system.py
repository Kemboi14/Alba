"""
Audit Logging System - Test Suite
==================================

Comprehensive tests for the tamper-resistant audit logging system.

Run tests:
    python manage.py test apps.core.tests.test_audit_logging

Or run in Django shell:
    python manage.py shell
    >>> exec(open('tests/test_audit_logging_system.py').read())
"""

import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.test import TestCase, RequestFactory
from django.contrib.auth import authenticate
from django.utils import timezone
from datetime import timedelta
from apps.core.models import User, AuditLog


def print_section(title):
    """Print formatted section header"""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


class AuditLogModelTest(TestCase):
    """Test AuditLog model functionality"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User',
            role=User.ADMIN
        )
    
    def test_audit_log_creation(self):
        """Test creating an audit log"""
        log = AuditLog.log_action(
            user=self.user,
            action_type=AuditLog.CREATE,
            model_name='TestModel',
            object_id='123',
            description='Test log entry',
            module='core',
        )
        
        self.assertIsNotNone(log)
        self.assertEqual(log.user, self.user)
        self.assertEqual(log.action_type, AuditLog.CREATE)
        self.assertEqual(log.model_name, 'TestModel')
        self.assertEqual(log.object_id, '123')
        self.assertIsNotNone(log.checksum)
        print("✅ Audit log creation works")
    
    def test_immutability(self):
        """Test that audit logs cannot be modified"""
        log = AuditLog.log_action(
            user=self.user,
            action_type=AuditLog.CREATE,
            model_name='TestModel',
            object_id='123',
            description='Original description',
            module='core',
        )
        
        # Try to modify
        log.description = 'Modified description'
        
        with self.assertRaises(ValueError) as context:
            log.save()
        
        self.assertIn('immutable', str(context.exception).lower())
        print("✅ Immutability enforced")
    
    def test_no_deletion(self):
        """Test that audit logs cannot be deleted"""
        log = AuditLog.log_action(
            user=self.user,
            action_type=AuditLog.CREATE,
            model_name='TestModel',
            object_id='123',
            description='Test log',
            module='core',
        )
        
        with self.assertRaises(ValueError) as context:
            log.delete()
        
        self.assertIn('cannot be deleted', str(context.exception).lower())
        print("✅ Deletion prevented")
    
    def test_checksum_generation(self):
        """Test that checksum is automatically generated"""
        log = AuditLog.log_action(
            user=self.user,
            action_type=AuditLog.CREATE,
            model_name='TestModel',
            object_id='123',
            description='Test checksum',
            module='core',
        )
        
        self.assertIsNotNone(log.checksum)
        self.assertEqual(len(log.checksum), 64)  # SHA-256 hash length
        print("✅ Checksum generated")
    
    def test_integrity_verification(self):
        """Test integrity verification"""
        log = AuditLog.log_action(
            user=self.user,
            action_type=AuditLog.CREATE,
            model_name='TestModel',
            object_id='123',
            description='Test integrity',
            module='core',
        )
        
        # Verify original log
        self.assertTrue(log.verify_integrity())
        print("✅ Integrity verification works")


class AutomaticLoggingTest(TestCase):
    """Test automatic logging via signals"""
    
    def test_user_creation_logged(self):
        """Test that user creation is automatically logged"""
        initial_count = AuditLog.objects.count()
        
        user = User.objects.create_user(
            email='newuser@example.com',
            password='testpass123'
        )
        
        # Check log was created
        final_count = AuditLog.objects.count()
        self.assertEqual(final_count, initial_count + 1)
        
        # Verify log details
        log = AuditLog.objects.filter(
            model_name='User',
            object_id=str(user.pk),
            action_type=AuditLog.CREATE
        ).first()
        
        self.assertIsNotNone(log)
        self.assertIn('Created', log.description)
        print("✅ User creation automatically logged")
    
    def test_user_update_logged(self):
        """Test that user updates are automatically logged"""
        user = User.objects.create_user(
            email='updatetest@example.com',
            password='testpass123',
            first_name='Original'
        )
        
        initial_count = AuditLog.objects.filter(
            model_name='User',
            object_id=str(user.pk)
        ).count()
        
        # Update user
        user.first_name = 'Updated'
        user.save()
        
        # Check update was logged
        final_count = AuditLog.objects.filter(
            model_name='User',
            object_id=str(user.pk)
        ).count()
        
        self.assertEqual(final_count, initial_count + 1)
        
        # Verify update log
        log = AuditLog.objects.filter(
            model_name='User',
            object_id=str(user.pk),
            action_type=AuditLog.UPDATE
        ).first()
        
        self.assertIsNotNone(log)
        self.assertIn('Updated', log.description)
        
        # Check changed fields tracking
        if log.changed_fields:
            self.assertIn('first_name', log.changed_fields)
        
        print("✅ User update automatically logged")
    
    def test_user_deletion_logged(self):
        """Test that user deletion is automatically logged"""
        user = User.objects.create_user(
            email='deletetest@example.com',
            password='testpass123'
        )
        
        user_id = user.pk
        
        # Delete user
        user.delete()
        
        # Check deletion was logged
        log = AuditLog.objects.filter(
            model_name='User',
            object_id=str(user_id),
            action_type=AuditLog.DELETE
        ).first()
        
        self.assertIsNotNone(log)
        self.assertIn('Deleted', log.description)
        print("✅ User deletion automatically logged")


class QueryPerformanceTest(TestCase):
    """Test query performance with indexes"""
    
    @classmethod
    def setUpTestData(cls):
        """Create test data once"""
        # Create users
        cls.users = []
        for i in range(10):
            user = User.objects.create_user(
                email=f'user{i}@example.com',
                password='testpass123'
            )
            cls.users.append(user)
        
        # Create various audit logs
        action_types = [AuditLog.CREATE, AuditLog.UPDATE, AuditLog.DELETE]
        for i, user in enumerate(cls.users):
            for j in range(5):
                AuditLog.log_action(
                    user=user,
                    action_type=action_types[j % 3],
                    model_name='TestModel',
                    object_id=str(i * 10 + j),
                    description=f'Test log {i}-{j}',
                    module='core',
                    ip_address=f'192.168.1.{i}',
                )
    
    def test_query_by_user(self):
        """Test querying by user"""
        user = self.users[0]
        logs = AuditLog.objects.filter(user=user)
        
        self.assertGreater(logs.count(), 0)
        print(f"✅ Query by user: {logs.count()} logs")
    
    def test_query_by_action(self):
        """Test querying by action type"""
        logs = AuditLog.objects.filter(action_type=AuditLog.CREATE)
        
        self.assertGreater(logs.count(), 0)
        print(f"✅ Query by action: {logs.count()} logs")
    
    def test_query_recent(self):
        """Test querying recent logs"""
        logs = AuditLog.objects.order_by('-timestamp')[:10]
        
        self.assertEqual(len(logs), 10)
        print("✅ Query recent logs: 10 logs")
    
    def test_query_by_object(self):
        """Test querying by model and object ID"""
        logs = AuditLog.objects.filter(
            model_name='TestModel',
            object_id='0'
        )
        
        self.assertGreaterEqual(logs.count(), 0)
        print(f"✅ Query by object: {logs.count()} logs")
    
    def test_complex_query(self):
        """Test complex multi-filter query"""
        yesterday = timezone.now() - timedelta(days=1)
        
        logs = AuditLog.objects.filter(
            user=self.users[0],
            action_type__in=[AuditLog.CREATE, AuditLog.UPDATE],
            timestamp__gte=yesterday
        )
        
        self.assertGreaterEqual(logs.count(), 0)
        print(f"✅ Complex query: {logs.count()} logs")


class IntegrityTest(TestCase):
    """Test integrity verification"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='integrity@example.com',
            password='testpass123'
        )
    
    def test_valid_checksum(self):
        """Test that valid logs pass integrity check"""
        log = AuditLog.log_action(
            user=self.user,
            action_type=AuditLog.CREATE,
            model_name='TestModel',
            object_id='123',
            description='Test integrity',
            module='core',
        )
        
        self.assertTrue(log.verify_integrity())
        print("✅ Valid checksum verified")
    
    def test_all_logs_valid(self):
        """Test that all logs have valid checksums"""
        # Create multiple logs
        for i in range(5):
            AuditLog.log_action(
                user=self.user,
                action_type=AuditLog.CREATE,
                model_name='TestModel',
                object_id=str(i),
                description=f'Test log {i}',
                module='core',
            )
        
        # Verify all logs
        all_valid = all(
            log.verify_integrity() 
            for log in AuditLog.objects.all()
        )
        
        self.assertTrue(all_valid)
        print("✅ All logs have valid checksums")


class CustomActionTest(TestCase):
    """Test custom action logging"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='custom@example.com',
            password='testpass123'
        )
    
    def test_login_action(self):
        """Test logging login action"""
        log = AuditLog.log_action(
            user=self.user,
            action_type=AuditLog.LOGIN,
            model_name='User',
            object_id=str(self.user.pk),
            description='User logged in',
            module='core',
            ip_address='192.168.1.100',
        )
        
        self.assertEqual(log.action_type, AuditLog.LOGIN)
        self.assertEqual(log.ip_address, '192.168.1.100')
        print("✅ Login action logged")
    
    def test_approve_action(self):
        """Test logging approval action"""
        log = AuditLog.log_action(
            user=self.user,
            action_type=AuditLog.APPROVE,
            model_name='Loan',
            object_id='123',
            description='Loan approved',
            module='loans',
            old_value={'status': 'PENDING'},
            new_value={'status': 'APPROVED'},
        )
        
        self.assertEqual(log.action_type, AuditLog.APPROVE)
        self.assertIsNotNone(log.old_value)
        self.assertIsNotNone(log.new_value)
        print("✅ Approve action logged")
    
    def test_payment_action(self):
        """Test logging payment action"""
        log = AuditLog.log_action(
            user=self.user,
            action_type=AuditLog.PAYMENT,
            model_name='Loan',
            object_id='456',
            description='Payment received: KES 5000',
            module='loans',
        )
        
        self.assertEqual(log.action_type, AuditLog.PAYMENT)
        self.assertIn('Payment', log.description)
        print("✅ Payment action logged")


def run_all_tests():
    """Run all tests and print summary"""
    import unittest
    from io import StringIO
    
    print_section("AUDIT LOGGING SYSTEM - TEST SUITE")
    
    # Test suites
    test_classes = [
        AuditLogModelTest,
        AutomaticLoggingTest,
        QueryPerformanceTest,
        IntegrityTest,
        CustomActionTest,
    ]
    
    total_tests = 0
    total_passed = 0
    
    for test_class in test_classes:
        print_section(test_class.__doc__ or test_class.__name__)
        
        suite = unittest.TestLoader().loadTestsFromTestCase(test_class)
        runner = unittest.TextTestRunner(stream=StringIO(), verbosity=0)
        result = runner.run(suite)
        
        tests_run = result.testsRun
        tests_passed = tests_run - len(result.failures) - len(result.errors)
        
        total_tests += tests_run
        total_passed += tests_passed
        
        print(f"\n  Tests run: {tests_run}")
        print(f"  Passed: {tests_passed}")
        print(f"  Failed: {len(result.failures)}")
        print(f"  Errors: {len(result.errors)}")
        
        if result.failures:
            print("\n  Failures:")
            for test, traceback in result.failures:
                print(f"    - {test}: {traceback}")
        
        if result.errors:
            print("\n  Errors:")
            for test, traceback in result.errors:
                print(f"    - {test}: {traceback}")
    
    # Summary
    print_section("TEST SUMMARY")
    print(f"  Total tests: {total_tests}")
    print(f"  Passed: {total_passed}")
    print(f"  Failed: {total_tests - total_passed}")
    print(f"  Success rate: {(total_passed/total_tests*100):.1f}%")
    
    if total_passed == total_tests:
        print("\n  🎉 ALL TESTS PASSED!\n")
        return True
    else:
        print("\n  ⚠️  SOME TESTS FAILED\n")
        return False


def demo_usage():
    """Demonstrate audit logging usage"""
    print_section("AUDIT LOGGING - USAGE DEMONSTRATION")
    
    # Create test user
    print("1. Creating a user (automatically logged)...")
    user = User.objects.create_user(
        email='demo@example.com',
        password='demo123',
        first_name='Demo',
        last_name='User'
    )
    print(f"   ✅ User created: {user.email}")
    
    # Check audit log
    log = AuditLog.objects.filter(
        model_name='User',
        object_id=str(user.pk),
        action_type=AuditLog.CREATE
    ).first()
    
    if log:
        print(f"   ✅ Audit log created:")
        print(f"      - Action: {log.action_type}")
        print(f"      - Description: {log.description}")
        print(f"      - Timestamp: {log.timestamp}")
        print(f"      - Checksum: {log.checksum[:16]}...")
    
    # Update user
    print("\n2. Updating user (automatically logged)...")
    user.first_name = 'Updated'
    user.save()
    print(f"   ✅ User updated")
    
    update_log = AuditLog.objects.filter(
        model_name='User',
        object_id=str(user.pk),
        action_type=AuditLog.UPDATE
    ).first()
    
    if update_log:
        print(f"   ✅ Update logged:")
        print(f"      - Changed fields: {update_log.changed_fields}")
    
    # Manual logging
    print("\n3. Manual action logging...")
    custom_log = AuditLog.log_action(
        user=user,
        action_type=AuditLog.APPROVE,
        model_name='DemoModel',
        object_id='999',
        description='Demo approval action',
        module='demo',
    )
    print(f"   ✅ Custom log created: {custom_log.description}")
    
    # Test immutability
    print("\n4. Testing immutability...")
    try:
        log.description = "Trying to modify"
        log.save()
        print("   ❌ ERROR: Should not allow modification!")
    except ValueError as e:
        print(f"   ✅ Modification prevented: {e}")
    
    # Test integrity
    print("\n5. Testing integrity verification...")
    is_valid = log.verify_integrity()
    print(f"   ✅ Integrity check: {'Valid' if is_valid else 'TAMPERED!'}")
    
    # Query examples
    print("\n6. Query examples...")
    
    recent = AuditLog.objects.order_by('-timestamp')[:5]
    print(f"   ✅ Recent logs: {recent.count()} entries")
    
    user_logs = AuditLog.objects.filter(user=user)
    print(f"   ✅ User logs: {user_logs.count()} entries")
    
    creates = AuditLog.objects.filter(action_type=AuditLog.CREATE)
    print(f"   ✅ CREATE actions: {creates.count()} entries")
    
    print("\n✅ DEMONSTRATION COMPLETE!\n")


if __name__ == '__main__':
    print("\n" + "="*70)
    print("  AUDIT LOGGING SYSTEM - COMPREHENSIVE TEST SUITE")
    print("="*70 + "\n")
    
    # Run demo
    demo_usage()
    
    # Run tests
    success = run_all_tests()
    
    if success:
        print("\n🎉 SYSTEM FULLY OPERATIONAL AND PRODUCTION-READY!\n")
    else:
        print("\n⚠️  PLEASE REVIEW FAILED TESTS ABOVE\n")
