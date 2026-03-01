"""
Custom User Model Test Script
==============================

Run this script to verify your custom User model implementation:
    python manage.py shell < tests/test_user_model.py

Or in Django shell:
    python manage.py shell
    >>> exec(open('tests/test_user_model.py').read())
"""

import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import authenticate
from django.utils import timezone
from datetime import timedelta
from apps.core.models import User


def print_section(title):
    """Print formatted section header"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def test_user_creation():
    """Test basic user creation"""
    print_section("TEST 1: User Creation")
    
    try:
        # Delete test users if they exist
        User.objects.filter(email__in=[
            'test_customer@example.com',
            'test_admin@example.com',
            'test_officer@example.com'
        ]).delete()
        
        # Create customer
        customer = User.objects.create_user(
            email='test_customer@example.com',
            password='TestPass123!',
            first_name='John',
            last_name='Doe',
            role=User.CUSTOMER
        )
        print(f"✅ Created customer: {customer}")
        print(f"   - Email: {customer.email}")
        print(f"   - Role: {customer.role}")
        print(f"   - Is Active: {customer.is_active}")
        print(f"   - Is Verified: {customer.is_verified}")
        
        # Create admin
        admin = User.objects.create_user(
            email='test_admin@example.com',
            password='TestPass123!',
            first_name='Admin',
            last_name='User',
            role=User.ADMIN,
            is_staff=True,
            is_verified=True
        )
        print(f"✅ Created admin: {admin}")
        
        # Create credit officer
        officer = User.objects.create_user(
            email='test_officer@example.com',
            password='TestPass123!',
            first_name='Jane',
            last_name='Smith',
            role=User.CREDIT_OFFICER,
            employee_id='EMP001',
            department='Credit',
            is_verified=True
        )
        print(f"✅ Created credit officer: {officer}")
        print(f"   - Employee ID: {officer.employee_id}")
        print(f"   - Department: {officer.department}")
        
        print("\n✅ TEST PASSED: User creation works correctly")
        return True
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {str(e)}")
        return False


def test_authentication():
    """Test email-based authentication"""
    print_section("TEST 2: Authentication")
    
    try:
        # Test valid credentials
        user = authenticate(
            email='test_customer@example.com',
            password='TestPass123!'
        )
        
        if user:
            print(f"✅ Authentication successful: {user.email}")
        else:
            print("❌ Authentication failed with valid credentials")
            return False
        
        # Test invalid password
        user = authenticate(
            email='test_customer@example.com',
            password='WrongPassword'
        )
        
        if user is None:
            print("✅ Authentication correctly rejected invalid password")
        else:
            print("❌ Authentication should reject invalid password")
            return False
        
        # Test non-existent user
        user = authenticate(
            email='nonexistent@example.com',
            password='TestPass123!'
        )
        
        if user is None:
            print("✅ Authentication correctly rejected non-existent user")
        else:
            print("❌ Authentication should reject non-existent user")
            return False
        
        print("\n✅ TEST PASSED: Authentication works correctly")
        return True
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {str(e)}")
        return False


def test_role_permissions():
    """Test role-based permissions"""
    print_section("TEST 3: Role-Based Permissions")
    
    try:
        # Get test users
        admin = User.objects.get(email='test_admin@example.com')
        officer = User.objects.get(email='test_officer@example.com')
        customer = User.objects.get(email='test_customer@example.com')
        
        # Test admin permissions
        print("Admin permissions:")
        print(f"  - is_admin(): {admin.is_admin()}")
        print(f"  - can_approve_loans(): {admin.can_approve_loans()}")
        print(f"  - can_manage_finances(): {admin.can_manage_finances()}")
        print(f"  - has_permission('loans', 'approve'): {admin.has_permission('loans', 'approve')}")
        
        if not admin.is_admin():
            print("❌ Admin should have is_admin() = True")
            return False
        
        # Test credit officer permissions
        print("\nCredit Officer permissions:")
        print(f"  - is_admin(): {officer.is_admin()}")
        print(f"  - can_approve_loans(): {officer.can_approve_loans()}")
        print(f"  - can_manage_finances(): {officer.can_manage_finances()}")
        
        if not officer.can_approve_loans():
            print("❌ Credit Officer should be able to approve loans")
            return False
        
        if officer.can_manage_finances():
            print("❌ Credit Officer should NOT manage finances")
            return False
        
        # Test customer permissions
        print("\nCustomer permissions:")
        print(f"  - is_admin(): {customer.is_admin()}")
        print(f"  - can_approve_loans(): {customer.can_approve_loans()}")
        print(f"  - can_manage_finances(): {customer.can_manage_finances()}")
        
        if customer.is_admin():
            print("❌ Customer should NOT be admin")
            return False
        
        if customer.can_approve_loans():
            print("❌ Customer should NOT approve loans")
            return False
        
        print("\n✅ TEST PASSED: Role permissions work correctly")
        return True
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {str(e)}")
        return False


def test_account_locking():
    """Test account lockout mechanism"""
    print_section("TEST 4: Account Lockout")
    
    try:
        user = User.objects.get(email='test_customer@example.com')
        
        # Test unlocked account
        print(f"Initial lock status: {user.is_account_locked()}")
        if user.is_account_locked():
            print("❌ Account should not be locked initially")
            return False
        
        # Lock account
        user.account_locked_until = timezone.now() + timedelta(hours=1)
        user.save()
        
        # Test locked account
        print(f"After locking: {user.is_account_locked()}")
        if not user.is_account_locked():
            print("❌ Account should be locked")
            return False
        
        # Expire lock
        user.account_locked_until = timezone.now() - timedelta(hours=1)
        user.save()
        
        # Test expired lock
        print(f"After expiry: {user.is_account_locked()}")
        if user.is_account_locked():
            print("❌ Account should be unlocked after expiry")
            return False
        
        # Reset
        user.account_locked_until = None
        user.save()
        
        print("\n✅ TEST PASSED: Account lockout works correctly")
        return True
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {str(e)}")
        return False


def test_queries():
    """Test database queries and indexes"""
    print_section("TEST 5: Database Queries")
    
    try:
        # Test role filter (uses index)
        officers = User.objects.filter(role=User.CREDIT_OFFICER)
        print(f"✅ Role filter: Found {officers.count()} credit officers")
        
        # Test compound filter (uses compound index)
        active_verified = User.objects.filter(is_active=True, is_verified=True)
        print(f"✅ Compound filter: Found {active_verified.count()} active verified users")
        
        # Test ordering (uses index)
        recent = User.objects.order_by('-created_at')[:5]
        print(f"✅ Ordering: Retrieved {recent.count()} most recent users")
        
        # Test unique fields
        emp_users = User.objects.filter(employee_id__isnull=False)
        print(f"✅ Unique field filter: Found {emp_users.count()} employees")
        
        # Test get_full_name
        user = User.objects.first()
        print(f"✅ get_full_name(): {user.get_full_name()}")
        
        print("\n✅ TEST PASSED: Queries execute correctly")
        return True
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {str(e)}")
        return False


def test_field_validation():
    """Test field validation and constraints"""
    print_section("TEST 6: Field Validation")
    
    try:
        # Test unique email constraint
        try:
            User.objects.create_user(
                email='test_customer@example.com',  # Duplicate
                password='TestPass123!'
            )
            print("❌ Should not allow duplicate email")
            return False
        except Exception:
            print("✅ Duplicate email correctly rejected")
        
        # Test email requirement
        try:
            User.objects.create_user(
                email='',
                password='TestPass123!'
            )
            print("❌ Should require email")
            return False
        except ValueError:
            print("✅ Empty email correctly rejected")
        
        # Test role choices
        user = User.objects.get(email='test_customer@example.com')
        valid_roles = [choice[0] for choice in User.ROLE_CHOICES]
        print(f"✅ Valid roles: {', '.join(valid_roles)}")
        
        if user.role not in valid_roles:
            print("❌ User has invalid role")
            return False
        
        print("\n✅ TEST PASSED: Field validation works correctly")
        return True
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {str(e)}")
        return False


def test_timestamps():
    """Test created_at and updated_at timestamps"""
    print_section("TEST 7: Timestamps")
    
    try:
        user = User.objects.get(email='test_customer@example.com')
        
        # Check created_at
        if not user.created_at:
            print("❌ created_at should be set automatically")
            return False
        print(f"✅ created_at: {user.created_at}")
        
        # Check updated_at
        if not user.updated_at:
            print("❌ updated_at should be set automatically")
            return False
        print(f"✅ updated_at: {user.updated_at}")
        
        # Test auto-update
        import time
        old_updated = user.updated_at
        time.sleep(1)
        user.first_name = "Updated"
        user.save()
        
        if user.updated_at <= old_updated:
            print("❌ updated_at should change on save")
            return False
        print(f"✅ updated_at changed on save: {user.updated_at}")
        
        # created_at should not change
        if user.created_at != User.objects.get(email='test_customer@example.com').created_at:
            print("❌ created_at should not change on update")
            return False
        print("✅ created_at remains unchanged")
        
        print("\n✅ TEST PASSED: Timestamps work correctly")
        return True
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {str(e)}")
        return False


def cleanup():
    """Clean up test data"""
    print_section("Cleanup")
    
    try:
        deleted = User.objects.filter(email__in=[
            'test_customer@example.com',
            'test_admin@example.com',
            'test_officer@example.com'
        ]).delete()
        
        print(f"✅ Cleaned up {deleted[0]} test users")
        return True
        
    except Exception as e:
        print(f"❌ Cleanup failed: {str(e)}")
        return False


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("  CUSTOM USER MODEL TEST SUITE")
    print("="*60)
    
    tests = [
        ("User Creation", test_user_creation),
        ("Authentication", test_authentication),
        ("Role Permissions", test_role_permissions),
        ("Account Locking", test_account_locking),
        ("Database Queries", test_queries),
        ("Field Validation", test_field_validation),
        ("Timestamps", test_timestamps),
    ]
    
    results = []
    for name, test_func in tests:
        result = test_func()
        results.append((name, result))
    
    # Summary
    print_section("TEST SUMMARY")
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{status}: {name}")
    
    print(f"\n{'='*60}")
    print(f"  Results: {passed}/{total} tests passed")
    print(f"{'='*60}\n")
    
    # Cleanup
    cleanup()
    
    if passed == total:
        print("🎉 ALL TESTS PASSED! Your User model is production-ready.\n")
        return True
    else:
        print("⚠️  SOME TESTS FAILED. Please review the errors above.\n")
        return False


if __name__ == '__main__':
    main()
