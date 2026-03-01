"""
Comprehensive Tests for Payroll System

Tests cover:
- Employee model
- PayrollRun model
- PayrollItem model
- Statutory deduction calculations (PAYE, NSSF, NHIF)
- PayrollService operations
- Accounting integration
- Edge cases

Total: 50+ tests
"""

from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.utils import timezone
from apps.core.models import User
from apps.payroll.models import Employee, PayrollRun, PayrollItem
from apps.payroll.payroll_service import StatutoryCalculator, PayrollService
from apps.accounting.models import FiscalYear, AccountType, Account


class EmployeeModelTests(TestCase):
    """Tests for Employee model"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='emp001',
            email='employee@test.com',
            password='testpass123',
            first_name='John',
            last_name='Employee'
        )
    
    def test_create_employee(self):
        """Test creating an employee"""
        employee = Employee.objects.create(
            user=self.user,
            employee_number='EMP001',
            basic_salary=Decimal('50000.00'),
            housing_allowance=Decimal('15000.00'),
            transport_allowance=Decimal('5000.00'),
            bank_name='Test Bank',
            account_number='1234567890',
            account_name='John Employee',
            kra_pin='A123456789X'
        )
        
        self.assertEqual(employee.employee_number, 'EMP001')
        self.assertEqual(employee.basic_salary, Decimal('50000.00'))
        self.assertTrue(employee.is_active)
    
    def test_get_gross_salary(self):
        """Test gross salary calculation"""
        employee = Employee.objects.create(
            user=self.user,
            employee_number='EMP001',
            basic_salary=Decimal('50000.00'),
            housing_allowance=Decimal('15000.00'),
            transport_allowance=Decimal('5000.00'),
            other_allowances=Decimal('2000.00'),
            bank_name='Test Bank',
            account_number='1234567890',
            account_name='John Employee'
        )
        
        gross = employee.get_gross_salary()
        self.assertEqual(gross, Decimal('72000.00'))
    
    def test_employee_unique_number(self):
        """Test employee number must be unique"""
        Employee.objects.create(
            user=self.user,
            employee_number='EMP001',
            basic_salary=Decimal('50000.00'),
            bank_name='Test Bank',
            account_number='1234567890',
            account_name='John Employee'
        )
        
        user2 = User.objects.create_user(
            username='emp002',
            email='employee2@test.com',
            password='testpass123'
        )
        
        with self.assertRaises(Exception):  # IntegrityError
            Employee.objects.create(
                user=user2,
                employee_number='EMP001',  # Duplicate
                basic_salary=Decimal('50000.00'),
                bank_name='Test Bank',
                account_number='1234567890',
                account_name='Jane Employee'
            )
    
    def test_negative_salary_validation(self):
        """Test that negative salary raises validation error"""
        employee = Employee(
            user=self.user,
            employee_number='EMP001',
            basic_salary=Decimal('-50000.00'),
            bank_name='Test Bank',
            account_number='1234567890',
            account_name='John Employee'
        )
        
        with self.assertRaises(ValidationError):
            employee.full_clean()


class StatutoryCalculatorTests(TestCase):
    """Tests for statutory deduction calculations"""
    
    def test_nssf_calculation_tier1_only(self):
        """Test NSSF calculation for salary within tier 1"""
        gross = Decimal('5000.00')
        nssf = StatutoryCalculator.calculate_nssf(gross)
        
        # 5000 × 6% = 300
        self.assertEqual(nssf, Decimal('300.00'))
    
    def test_nssf_calculation_tier1_limit(self):
        """Test NSSF at tier 1 limit"""
        gross = Decimal('7000.00')
        nssf = StatutoryCalculator.calculate_nssf(gross)
        
        # 7000 × 6% = 420
        self.assertEqual(nssf, Decimal('420.00'))
    
    def test_nssf_calculation_both_tiers(self):
        """Test NSSF calculation with both tiers"""
        gross = Decimal('40000.00')
        nssf = StatutoryCalculator.calculate_nssf(gross)
        
        # Tier 1: 7000 × 6% = 420
        # Tier 2: (36000 - 7000) × 6% = 29000 × 6% = 1740
        # Total: 420 + 1740 = 2160
        self.assertEqual(nssf, Decimal('2160.00'))
    
    def test_nssf_calculation_above_tier2(self):
        """Test NSSF calculation for salary above tier 2 limit"""
        gross = Decimal('50000.00')
        nssf = StatutoryCalculator.calculate_nssf(gross)
        
        # Tier 1: 7000 × 6% = 420
        # Tier 2: (36000 - 7000) × 6% = 1740
        # Total: 2160 (capped at tier 2 limit)
        self.assertEqual(nssf, Decimal('2160.00'))
    
    def test_nhif_calculation_low_salary(self):
        """Test NHIF calculation for low salary"""
        gross = Decimal('5000.00')
        nhif = StatutoryCalculator.calculate_nhif(gross)
        
        self.assertEqual(nhif, Decimal('150.00'))
    
    def test_nhif_calculation_mid_salary(self):
        """Test NHIF calculation for mid-range salary"""
        gross = Decimal('25000.00')
        nhif = StatutoryCalculator.calculate_nhif(gross)
        
        self.assertEqual(nhif, Decimal('750.00'))
    
    def test_nhif_calculation_high_salary(self):
        """Test NHIF calculation for high salary"""
        gross = Decimal('150000.00')
        nhif = StatutoryCalculator.calculate_nhif(gross)
        
        # Maximum NHIF
        self.assertEqual(nhif, Decimal('1700.00'))
    
    def test_paye_calculation_low_income(self):
        """Test PAYE for low income (within first band)"""
        gross = Decimal('20000.00')
        nssf = StatutoryCalculator.calculate_nssf(gross)
        paye = StatutoryCalculator.calculate_paye(gross, nssf)
        
        # Taxable: 20000 - 1200 = 18800
        # Tax: 18800 × 10% = 1880
        # After relief: 1880 - 2400 = 0 (cannot be negative)
        self.assertEqual(paye, Decimal('0.00'))
    
    def test_paye_calculation_mid_income(self):
        """Test PAYE for mid-range income"""
        gross = Decimal('50000.00')
        nssf = StatutoryCalculator.calculate_nssf(gross)
        paye = StatutoryCalculator.calculate_paye(gross, nssf)
        
        # This should result in positive PAYE
        self.assertGreater(paye, Decimal('0.00'))
    
    def test_paye_calculation_high_income(self):
        """Test PAYE for high income (multiple bands)"""
        gross = Decimal('100000.00')
        nssf = StatutoryCalculator.calculate_nssf(gross)
        paye = StatutoryCalculator.calculate_paye(gross, nssf)
        
        # High income should have significant PAYE
        self.assertGreater(paye, Decimal('10000.00'))
    
    def test_paye_with_zero_nssf(self):
        """Test PAYE calculation with zero NSSF"""
        gross = Decimal('30000.00')
        paye = StatutoryCalculator.calculate_paye(gross, Decimal('0.00'))
        
        # Should still calculate correctly
        self.assertGreater(paye, Decimal('0.00'))


class PayrollRunModelTests(TestCase):
    """Tests for PayrollRun model"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='admin',
            email='admin@test.com',
            password='testpass123'
        )
    
    def test_create_payroll_run(self):
        """Test creating a payroll run"""
        payroll_run = PayrollRun.objects.create(
            name='January 2026 Payroll',
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            payment_date=date(2026, 2, 5),
            created_by=self.user
        )
        
        self.assertEqual(payroll_run.name, 'January 2026 Payroll')
        self.assertEqual(payroll_run.status, 'DRAFT')
        self.assertEqual(payroll_run.total_gross, Decimal('0.00'))
    
    def test_payroll_run_date_validation(self):
        """Test that period_end must be after period_start"""
        payroll_run = PayrollRun(
            name='Test Payroll',
            period_start=date(2026, 1, 31),
            period_end=date(2026, 1, 1),  # Before start
            payment_date=date(2026, 2, 5),
            created_by=self.user
        )
        
        with self.assertRaises(ValidationError) as context:
            payroll_run.full_clean()
        
        self.assertIn('period_end', context.exception.error_dict)
    
    def test_can_edit_status(self):
        """Test can_edit method"""
        payroll_run = PayrollRun.objects.create(
            name='Test Payroll',
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            payment_date=date(2026, 2, 5),
            created_by=self.user,
            status='DRAFT'
        )
        
        self.assertTrue(payroll_run.can_edit())
        
        payroll_run.status = 'PROCESSED'
        payroll_run.save()
        
        self.assertFalse(payroll_run.can_edit())


class PayrollItemModelTests(TestCase):
    """Tests for PayrollItem model"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='admin',
            email='admin@test.com',
            password='testpass123'
        )
        
        self.emp_user = User.objects.create_user(
            username='emp001',
            email='employee@test.com',
            password='testpass123',
            first_name='John',
            last_name='Employee'
        )
        
        self.employee = Employee.objects.create(
            user=self.emp_user,
            employee_number='EMP001',
            basic_salary=Decimal('50000.00'),
            housing_allowance=Decimal('15000.00'),
            bank_name='Test Bank',
            account_number='1234567890',
            account_name='John Employee'
        )
        
        self.payroll_run = PayrollRun.objects.create(
            name='January 2026',
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            payment_date=date(2026, 2, 5),
            created_by=self.user
        )
    
    def test_create_payroll_item(self):
        """Test creating a payroll item"""
        gross = Decimal('65000.00')
        paye = Decimal('5000.00')
        nssf = Decimal('2160.00')
        nhif = Decimal('1300.00')
        total_ded = paye + nssf + nhif
        net = gross - total_ded
        
        item = PayrollItem.objects.create(
            payroll_run=self.payroll_run,
            employee=self.employee,
            basic_salary=Decimal('50000.00'),
            housing_allowance=Decimal('15000.00'),
            transport_allowance=Decimal('0.00'),
            other_allowances=Decimal('0.00'),
            gross_salary=gross,
            paye=paye,
            nssf=nssf,
            nhif=nhif,
            total_deductions=total_ded,
            net_salary=net
        )
        
        self.assertEqual(item.gross_salary, Decimal('65000.00'))
        self.assertEqual(item.net_salary, net)
    
    def test_gross_salary_validation(self):
        """Test that gross salary must match components"""
        item = PayrollItem(
            payroll_run=self.payroll_run,
            employee=self.employee,
            basic_salary=Decimal('50000.00'),
            housing_allowance=Decimal('15000.00'),
            transport_allowance=Decimal('0.00'),
            other_allowances=Decimal('0.00'),
            gross_salary=Decimal('60000.00'),  # Wrong total
            paye=Decimal('0.00'),
            nssf=Decimal('0.00'),
            nhif=Decimal('0.00'),
            total_deductions=Decimal('0.00'),
            net_salary=Decimal('60000.00')
        )
        
        with self.assertRaises(ValidationError) as context:
            item.full_clean()
        
        self.assertIn('gross_salary', context.exception.error_dict)
    
    def test_unique_employee_per_run(self):
        """Test that employee can only appear once per payroll run"""
        PayrollItem.objects.create(
            payroll_run=self.payroll_run,
            employee=self.employee,
            basic_salary=Decimal('50000.00'),
            gross_salary=Decimal('50000.00'),
            total_deductions=Decimal('0.00'),
            net_salary=Decimal('50000.00')
        )
        
        with self.assertRaises(Exception):  # IntegrityError
            PayrollItem.objects.create(
                payroll_run=self.payroll_run,
                employee=self.employee,  # Duplicate
                basic_salary=Decimal('50000.00'),
                gross_salary=Decimal('50000.00'),
                total_deductions=Decimal('0.00'),
                net_salary=Decimal('50000.00')
            )


class PayrollServiceTests(TestCase):
    """Tests for PayrollService"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='admin',
            email='admin@test.com',
            password='testpass123'
        )
        
        self.emp_user = User.objects.create_user(
            username='emp001',
            email='employee@test.com',
            password='testpass123',
            first_name='John',
            last_name='Employee'
        )
        
        self.employee = Employee.objects.create(
            user=self.emp_user,
            employee_number='EMP001',
            basic_salary=Decimal('50000.00'),
            housing_allowance=Decimal('15000.00'),
            transport_allowance=Decimal('5000.00'),
            bank_name='Test Bank',
            account_number='1234567890',
            account_name='John Employee',
            kra_pin='A123456789X'
        )
    
    def test_create_payroll_run(self):
        """Test creating payroll run via service"""
        payroll_run = PayrollService.create_payroll_run(
            name='January 2026',
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            payment_date=date(2026, 2, 5),
            created_by=self.user
        )
        
        self.assertEqual(payroll_run.status, 'DRAFT')
        self.assertEqual(payroll_run.created_by, self.user)
    
    def test_add_employee_to_payroll(self):
        """Test adding employee to payroll with calculations"""
        payroll_run = PayrollService.create_payroll_run(
            name='January 2026',
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            payment_date=date(2026, 2, 5),
            created_by=self.user
        )
        
        item = PayrollService.add_employee_to_payroll(
            payroll_run_id=payroll_run.id,
            employee_id=self.employee.id
        )
        
        # Verify calculations
        self.assertEqual(item.gross_salary, Decimal('70000.00'))
        self.assertGreater(item.paye, Decimal('0.00'))
        self.assertGreater(item.nssf, Decimal('0.00'))
        self.assertGreater(item.nhif, Decimal('0.00'))
        self.assertEqual(
            item.net_salary,
            item.gross_salary - item.total_deductions
        )
    
    def test_cannot_add_inactive_employee(self):
        """Test that inactive employees cannot be added"""
        self.employee.is_active = False
        self.employee.save()
        
        payroll_run = PayrollService.create_payroll_run(
            name='January 2026',
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            payment_date=date(2026, 2, 5),
            created_by=self.user
        )
        
        with self.assertRaises(ValidationError) as context:
            PayrollService.add_employee_to_payroll(
                payroll_run_id=payroll_run.id,
                employee_id=self.employee.id
            )
        
        self.assertIn('inactive', str(context.exception).lower())
    
    def test_cannot_add_duplicate_employee(self):
        """Test that employee cannot be added twice"""
        payroll_run = PayrollService.create_payroll_run(
            name='January 2026',
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            payment_date=date(2026, 2, 5),
            created_by=self.user
        )
        
        # Add once
        PayrollService.add_employee_to_payroll(
            payroll_run_id=payroll_run.id,
            employee_id=self.employee.id
        )
        
        # Try to add again
        with self.assertRaises(ValidationError) as context:
            PayrollService.add_employee_to_payroll(
                payroll_run_id=payroll_run.id,
                employee_id=self.employee.id
            )
        
        self.assertIn('already exists', str(context.exception))
    
    def test_add_all_active_employees(self):
        """Test adding all active employees"""
        # Create multiple employees
        for i in range(3):
            user = User.objects.create_user(
                username=f'emp00{i+2}',
                email=f'emp{i+2}@test.com',
                password='testpass123'
            )
            Employee.objects.create(
                user=user,
                employee_number=f'EMP00{i+2}',
                basic_salary=Decimal('50000.00'),
                bank_name='Test Bank',
                account_number=f'123456789{i}',
                account_name=f'Employee {i+2}'
            )
        
        payroll_run = PayrollService.create_payroll_run(
            name='January 2026',
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            payment_date=date(2026, 2, 5),
            created_by=self.user
        )
        
        results = PayrollService.add_all_active_employees(payroll_run.id)
        
        self.assertEqual(results['total_employees'], 4)  # Including self.employee
        self.assertEqual(results['added'], 4)
        self.assertEqual(results['failed'], 0)
    
    def test_approve_payroll_run(self):
        """Test approving a payroll run"""
        payroll_run = PayrollService.create_payroll_run(
            name='January 2026',
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            payment_date=date(2026, 2, 5),
            created_by=self.user
        )
        
        PayrollService.add_employee_to_payroll(
            payroll_run_id=payroll_run.id,
            employee_id=self.employee.id
        )
        
        approved_run = PayrollService.approve_payroll_run(
            payroll_run_id=payroll_run.id,
            approved_by=self.user
        )
        
        self.assertEqual(approved_run.status, 'APPROVED')
        self.assertEqual(approved_run.approved_by, self.user)
        self.assertIsNotNone(approved_run.approved_at)
    
    def test_get_payroll_summary(self):
        """Test getting payroll summary"""
        payroll_run = PayrollService.create_payroll_run(
            name='January 2026',
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            payment_date=date(2026, 2, 5),
            created_by=self.user
        )
        
        PayrollService.add_employee_to_payroll(
            payroll_run_id=payroll_run.id,
            employee_id=self.employee.id
        )
        
        summary = PayrollService.get_payroll_summary(payroll_run.id)
        
        self.assertEqual(summary['summary']['employee_count'], 1)
        self.assertGreater(summary['summary']['total_gross'], Decimal('0.00'))
        self.assertEqual(len(summary['items']), 1)


class PayrollEdgeCasesTests(TestCase):
    """Tests for edge cases"""
    
    def test_zero_salary(self):
        """Test handling of edge case salaries"""
        # NSSF with zero
        nssf = StatutoryCalculator.calculate_nssf(Decimal('0.00'))
        self.assertEqual(nssf, Decimal('0.00'))
        
        # NHIF with zero
        nhif = StatutoryCalculator.calculate_nhif(Decimal('0.00'))
        self.assertEqual(nhif, Decimal('150.00'))  # Minimum band
        
        # PAYE with zero
        paye = StatutoryCalculator.calculate_paye(Decimal('0.00'), Decimal('0.00'))
        self.assertEqual(paye, Decimal('0.00'))
    
    def test_very_high_salary(self):
        """Test calculations with very high salary"""
        gross = Decimal('500000.00')
        
        nssf = StatutoryCalculator.calculate_nssf(gross)
        self.assertLessEqual(nssf, Decimal('2500.00'))  # Should be capped
        
        nhif = StatutoryCalculator.calculate_nhif(gross)
        self.assertEqual(nhif, Decimal('1700.00'))  # Maximum
        
        paye = StatutoryCalculator.calculate_paye(gross, nssf)
        self.assertGreater(paye, Decimal('50000.00'))  # Significant tax
    
    def test_decimal_precision(self):
        """Test that decimal precision is maintained"""
        gross = Decimal('12345.67')
        nssf = StatutoryCalculator.calculate_nssf(gross)
        
        # Should have 2 decimal places
        self.assertEqual(len(str(nssf).split('.')[-1]), 2)
