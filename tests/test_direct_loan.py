"""
Comprehensive Test Suite for Direct Loan Models and Services
Tests all loan functionality including FLAT and REDUCING_BALANCE interest methods
"""
from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.utils import timezone
from apps.loans.models import (
    LoanProduct,
    DirectLoan,
    DirectLoanRepaymentSchedule
)
from apps.loans.services import LoanService

User = get_user_model()


class DirectLoanModelTest(TestCase):
    """Test DirectLoan model validation and methods"""
    
    def setUp(self):
        """Set up test data"""
        # Create test user
        self.user = User.objects.create_user(
            username='borrower1',
            email='borrower@example.com',
            password='testpass123',
            first_name='John',
            last_name='Doe'
        )
        
        # Create loan officer
        self.officer = User.objects.create_user(
            username='officer1',
            email='officer@example.com',
            password='testpass123',
            role='LOAN_OFFICER'
        )
        
        # Create loan product
        self.product = LoanProduct.objects.create(
            name='Personal Loan',
            code='PL-001',
            description='Standard personal loan',
            interest_rate=Decimal('12.00'),
            interest_method='REDUCING_BALANCE',
            minimum_amount=Decimal('10000.00'),
            maximum_amount=Decimal('500000.00'),
            minimum_term_months=6,
            maximum_term_months=60,
            processing_fee_percentage=Decimal('2.00'),
            late_payment_penalty_percentage=Decimal('1.50'),
            grace_period_days=3,
            default_repayment_frequency='MONTHLY',
            created_by=self.officer
        )
    
    def test_create_direct_loan(self):
        """Test creating a direct loan"""
        loan = DirectLoan.objects.create(
            customer=self.user,
            loan_product=self.product,
            principal_amount=Decimal('50000.00'),
            interest_rate=Decimal('12.00'),
            term_months=12,
            status='PENDING',
            created_by=self.officer
        )
        
        self.assertIsNotNone(loan.pk)
        self.assertEqual(loan.customer, self.user)
        self.assertEqual(loan.principal_amount, Decimal('50000.00'))
        self.assertEqual(loan.term_months, 12)
        self.assertEqual(loan.status, 'PENDING')
        self.assertEqual(loan.outstanding_principal, Decimal('0.00'))
    
    def test_loan_str_representation(self):
        """Test loan string representation"""
        loan = DirectLoan.objects.create(
            customer=self.user,
            loan_product=self.product,
            principal_amount=Decimal('50000.00'),
            interest_rate=Decimal('12.00'),
            term_months=12,
            status='PENDING'
        )
        
        self.assertIn(str(loan.pk), str(loan))
        self.assertIn('John Doe', str(loan))
    
    def test_loan_amount_below_minimum_validation(self):
        """Test validation when amount is below product minimum"""
        with self.assertRaises(ValidationError) as context:
            loan = DirectLoan(
                customer=self.user,
                loan_product=self.product,
                principal_amount=Decimal('5000.00'),  # Below minimum
                interest_rate=Decimal('12.00'),
                term_months=12,
                status='PENDING'
            )
            loan.full_clean()
        
        self.assertIn('below product minimum', str(context.exception))
    
    def test_loan_amount_above_maximum_validation(self):
        """Test validation when amount exceeds product maximum"""
        with self.assertRaises(ValidationError) as context:
            loan = DirectLoan(
                customer=self.user,
                loan_product=self.product,
                principal_amount=Decimal('600000.00'),  # Above maximum
                interest_rate=Decimal('12.00'),
                term_months=12,
                status='PENDING'
            )
            loan.full_clean()
        
        self.assertIn('exceeds product maximum', str(context.exception))
    
    def test_loan_term_below_minimum_validation(self):
        """Test validation when term is below product minimum"""
        with self.assertRaises(ValidationError) as context:
            loan = DirectLoan(
                customer=self.user,
                loan_product=self.product,
                principal_amount=Decimal('50000.00'),
                interest_rate=Decimal('12.00'),
                term_months=3,  # Below minimum
                status='PENDING'
            )
            loan.full_clean()
        
        self.assertIn('below product minimum', str(context.exception))
    
    def test_loan_term_above_maximum_validation(self):
        """Test validation when term exceeds product maximum"""
        with self.assertRaises(ValidationError) as context:
            loan = DirectLoan(
                customer=self.user,
                loan_product=self.product,
                principal_amount=Decimal('50000.00'),
                interest_rate=Decimal('12.00'),
                term_months=72,  # Above maximum
                status='PENDING'
            )
            loan.full_clean()
        
        self.assertIn('exceeds product maximum', str(context.exception))
    
    def test_disbursement_date_required_for_disbursed_status(self):
        """Test that disbursement date is required for DISBURSED status"""
        with self.assertRaises(ValidationError) as context:
            loan = DirectLoan(
                customer=self.user,
                loan_product=self.product,
                principal_amount=Decimal('50000.00'),
                interest_rate=Decimal('12.00'),
                term_months=12,
                status='DISBURSED',
                disbursement_date=None  # Missing
            )
            loan.full_clean()
        
        self.assertIn('Disbursement date required', str(context.exception))
    
    def test_outstanding_principal_auto_set_on_disbursement(self):
        """Test that outstanding principal is auto-set when status is DISBURSED"""
        loan = DirectLoan(
            customer=self.user,
            loan_product=self.product,
            principal_amount=Decimal('50000.00'),
            interest_rate=Decimal('12.00'),
            term_months=12,
            status='DISBURSED',
            disbursement_date=date.today(),
            outstanding_principal=Decimal('0.00')  # Should be auto-set
        )
        loan.full_clean()  # This should set outstanding_principal
        
        self.assertEqual(loan.outstanding_principal, Decimal('50000.00'))
    
    def test_closed_loan_must_have_zero_outstanding(self):
        """Test that closed loans must have zero outstanding principal"""
        with self.assertRaises(ValidationError) as context:
            loan = DirectLoan(
                customer=self.user,
                loan_product=self.product,
                principal_amount=Decimal('50000.00'),
                interest_rate=Decimal('12.00'),
                term_months=12,
                status='CLOSED',
                disbursement_date=date.today(),
                outstanding_principal=Decimal('1000.00')  # Should be zero
            )
            loan.full_clean()
        
        self.assertIn('must be zero for closed loans', str(context.exception))
    
    def test_invalid_status_transition(self):
        """Test invalid status transitions are prevented"""
        # Create and save a CLOSED loan
        loan = DirectLoan.objects.create(
            customer=self.user,
            loan_product=self.product,
            principal_amount=Decimal('50000.00'),
            interest_rate=Decimal('12.00'),
            term_months=12,
            status='DISBURSED',
            disbursement_date=date.today(),
            outstanding_principal=Decimal('0.00')
        )
        loan.status = 'CLOSED'
        loan.save()
        
        # Try to change from CLOSED to PENDING (invalid)
        with self.assertRaises(ValidationError) as context:
            loan.status = 'PENDING'
            loan.full_clean()
        
        self.assertIn('Cannot change status from CLOSED', str(context.exception))
    
    def test_get_total_interest_flat(self):
        """Test calculating total interest for FLAT method"""
        # Create FLAT product
        flat_product = LoanProduct.objects.create(
            name='Flat Loan',
            code='FL-001',
            description='Flat interest loan',
            interest_rate=Decimal('10.00'),
            interest_method='FLAT',
            minimum_amount=Decimal('10000.00'),
            maximum_amount=Decimal('500000.00'),
            minimum_term_months=6,
            maximum_term_months=60,
            processing_fee_percentage=Decimal('2.00'),
            late_payment_penalty_percentage=Decimal('1.50'),
            grace_period_days=3,
            default_repayment_frequency='MONTHLY',
            created_by=self.officer
        )
        
        loan = DirectLoan.objects.create(
            customer=self.user,
            loan_product=flat_product,
            principal_amount=Decimal('100000.00'),
            interest_rate=Decimal('10.00'),
            term_months=12,
            status='PENDING'
        )
        
        # FLAT interest: 100,000 × 0.10 × (12/12) = 10,000
        total_interest = loan.get_total_interest()
        self.assertEqual(total_interest, Decimal('10000.00'))
    
    def test_get_monthly_payment(self):
        """Test calculating monthly payment"""
        loan = DirectLoan.objects.create(
            customer=self.user,
            loan_product=self.product,
            principal_amount=Decimal('100000.00'),
            interest_rate=Decimal('12.00'),
            term_months=12,
            status='PENDING'
        )
        
        monthly_payment = loan.get_monthly_payment()
        
        # Should be a positive amount
        self.assertGreater(monthly_payment, Decimal('0.00'))
        # Should be reasonable (between 8k and 10k for this loan)
        self.assertGreater(monthly_payment, Decimal('8000.00'))
        self.assertLess(monthly_payment, Decimal('10000.00'))


class DirectLoanRepaymentScheduleModelTest(TestCase):
    """Test DirectLoanRepaymentSchedule model validation and methods"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='borrower2',
            email='borrower2@example.com',
            password='testpass123',
            first_name='Jane',
            last_name='Smith'
        )
        
        self.officer = User.objects.create_user(
            username='officer2',
            email='officer2@example.com',
            password='testpass123',
            role='LOAN_OFFICER'
        )
        
        self.product = LoanProduct.objects.create(
            name='Business Loan',
            code='BL-001',
            description='Business loan',
            interest_rate=Decimal('15.00'),
            interest_method='REDUCING_BALANCE',
            minimum_amount=Decimal('50000.00'),
            maximum_amount=Decimal('1000000.00'),
            minimum_term_months=12,
            maximum_term_months=60,
            processing_fee_percentage=Decimal('3.00'),
            late_payment_penalty_percentage=Decimal('2.00'),
            grace_period_days=5,
            default_repayment_frequency='MONTHLY',
            created_by=self.officer
        )
        
        self.loan = DirectLoan.objects.create(
            customer=self.user,
            loan_product=self.product,
            principal_amount=Decimal('200000.00'),
            interest_rate=Decimal('15.00'),
            term_months=12,
            status='DISBURSED',
            disbursement_date=date.today(),
            outstanding_principal=Decimal('200000.00')
        )
    
    def test_create_repayment_schedule(self):
        """Test creating a repayment schedule entry"""
        schedule = DirectLoanRepaymentSchedule.objects.create(
            loan=self.loan,
            installment_number=1,
            due_date=date.today() + timedelta(days=30),
            principal_due=Decimal('16666.67'),
            interest_due=Decimal('2500.00'),
            penalty_due=Decimal('0.00'),
            paid_amount=Decimal('0.00'),
            is_paid=False
        )
        
        self.assertIsNotNone(schedule.pk)
        self.assertEqual(schedule.loan, self.loan)
        self.assertEqual(schedule.installment_number, 1)
        self.assertEqual(schedule.principal_due, Decimal('16666.67'))
        self.assertEqual(schedule.interest_due, Decimal('2500.00'))
        self.assertFalse(schedule.is_paid)
    
    def test_schedule_str_representation(self):
        """Test schedule string representation"""
        schedule = DirectLoanRepaymentSchedule.objects.create(
            loan=self.loan,
            installment_number=1,
            due_date=date.today() + timedelta(days=30),
            principal_due=Decimal('16666.67'),
            interest_due=Decimal('2500.00')
        )
        
        self.assertIn(str(self.loan.pk), str(schedule))
        self.assertIn('Installment 1', str(schedule))
    
    def test_paid_amount_exceeds_total_due_validation(self):
        """Test validation when paid amount exceeds total due"""
        with self.assertRaises(ValidationError) as context:
            schedule = DirectLoanRepaymentSchedule(
                loan=self.loan,
                installment_number=1,
                due_date=date.today() + timedelta(days=30),
                principal_due=Decimal('16666.67'),
                interest_due=Decimal('2500.00'),
                penalty_due=Decimal('0.00'),
                paid_amount=Decimal('20000.00'),  # Exceeds total
                is_paid=False
            )
            schedule.full_clean()
        
        self.assertIn('exceeds total due', str(context.exception))
    
    def test_is_paid_flag_inconsistency_validation(self):
        """Test validation when is_paid flag is inconsistent with paid amount"""
        with self.assertRaises(ValidationError) as context:
            schedule = DirectLoanRepaymentSchedule(
                loan=self.loan,
                installment_number=1,
                due_date=date.today() + timedelta(days=30),
                principal_due=Decimal('16666.67'),
                interest_due=Decimal('2500.00'),
                penalty_due=Decimal('0.00'),
                paid_amount=Decimal('10000.00'),  # Less than total
                is_paid=True  # But marked as paid
            )
            schedule.full_clean()
        
        self.assertIn('Cannot mark as paid', str(context.exception))
    
    def test_paid_date_required_when_paid(self):
        """Test that paid_date is required when is_paid is True"""
        with self.assertRaises(ValidationError) as context:
            schedule = DirectLoanRepaymentSchedule(
                loan=self.loan,
                installment_number=1,
                due_date=date.today() + timedelta(days=30),
                principal_due=Decimal('16666.67'),
                interest_due=Decimal('2500.00'),
                penalty_due=Decimal('0.00'),
                paid_amount=Decimal('19166.67'),
                is_paid=True,
                paid_date=None  # Missing
            )
            schedule.full_clean()
        
        self.assertIn('Paid date required', str(context.exception))
    
    def test_get_total_due(self):
        """Test calculating total due amount"""
        schedule = DirectLoanRepaymentSchedule.objects.create(
            loan=self.loan,
            installment_number=1,
            due_date=date.today() + timedelta(days=30),
            principal_due=Decimal('16666.67'),
            interest_due=Decimal('2500.00'),
            penalty_due=Decimal('100.00')
        )
        
        total = schedule.get_total_due()
        self.assertEqual(total, Decimal('19266.67'))
    
    def test_get_outstanding_amount(self):
        """Test calculating outstanding amount"""
        schedule = DirectLoanRepaymentSchedule.objects.create(
            loan=self.loan,
            installment_number=1,
            due_date=date.today() + timedelta(days=30),
            principal_due=Decimal('16666.67'),
            interest_due=Decimal('2500.00'),
            penalty_due=Decimal('0.00'),
            paid_amount=Decimal('5000.00')
        )
        
        outstanding = schedule.get_outstanding_amount()
        self.assertEqual(outstanding, Decimal('14166.67'))
    
    def test_is_overdue_false_when_paid(self):
        """Test that paid installments are not overdue"""
        schedule = DirectLoanRepaymentSchedule.objects.create(
            loan=self.loan,
            installment_number=1,
            due_date=date.today() - timedelta(days=10),  # Past due date
            principal_due=Decimal('16666.67'),
            interest_due=Decimal('2500.00'),
            paid_amount=Decimal('19166.67'),
            is_paid=True,
            paid_date=date.today()
        )
        
        self.assertFalse(schedule.is_overdue())
    
    def test_is_overdue_true_when_unpaid_and_past_due(self):
        """Test that unpaid installments past due date are overdue"""
        schedule = DirectLoanRepaymentSchedule.objects.create(
            loan=self.loan,
            installment_number=1,
            due_date=date.today() - timedelta(days=10),  # Past due date
            principal_due=Decimal('16666.67'),
            interest_due=Decimal('2500.00'),
            is_paid=False
        )
        
        self.assertTrue(schedule.is_overdue())
    
    def test_get_days_overdue(self):
        """Test calculating days overdue"""
        past_date = date.today() - timedelta(days=15)
        schedule = DirectLoanRepaymentSchedule.objects.create(
            loan=self.loan,
            installment_number=1,
            due_date=past_date,
            principal_due=Decimal('16666.67'),
            interest_due=Decimal('2500.00'),
            is_paid=False
        )
        
        days = schedule.get_days_overdue()
        self.assertEqual(days, 15)
    
    def test_record_payment_partial(self):
        """Test recording a partial payment"""
        schedule = DirectLoanRepaymentSchedule.objects.create(
            loan=self.loan,
            installment_number=1,
            due_date=date.today() + timedelta(days=30),
            principal_due=Decimal('16666.67'),
            interest_due=Decimal('2500.00'),
            penalty_due=Decimal('0.00')
        )
        
        excess = schedule.record_payment(Decimal('10000.00'))
        
        schedule.refresh_from_db()
        self.assertEqual(schedule.paid_amount, Decimal('10000.00'))
        self.assertFalse(schedule.is_paid)
        self.assertIsNone(schedule.paid_date)
        self.assertEqual(excess, Decimal('0.00'))
    
    def test_record_payment_full(self):
        """Test recording a full payment"""
        schedule = DirectLoanRepaymentSchedule.objects.create(
            loan=self.loan,
            installment_number=1,
            due_date=date.today() + timedelta(days=30),
            principal_due=Decimal('16666.67'),
            interest_due=Decimal('2500.00'),
            penalty_due=Decimal('0.00')
        )
        
        total_due = schedule.get_total_due()
        excess = schedule.record_payment(total_due, date.today())
        
        schedule.refresh_from_db()
        self.assertEqual(schedule.paid_amount, total_due)
        self.assertTrue(schedule.is_paid)
        self.assertIsNotNone(schedule.paid_date)
        self.assertEqual(excess, Decimal('0.00'))
    
    def test_record_payment_excess(self):
        """Test recording payment with excess amount"""
        schedule = DirectLoanRepaymentSchedule.objects.create(
            loan=self.loan,
            installment_number=1,
            due_date=date.today() + timedelta(days=30),
            principal_due=Decimal('16666.67'),
            interest_due=Decimal('2500.00'),
            penalty_due=Decimal('0.00')
        )
        
        total_due = schedule.get_total_due()
        excess = schedule.record_payment(total_due + Decimal('5000.00'), date.today())
        
        schedule.refresh_from_db()
        self.assertEqual(schedule.paid_amount, total_due)
        self.assertTrue(schedule.is_paid)
        self.assertEqual(excess, Decimal('5000.00'))


class LoanServiceTest(TestCase):
    """Test LoanService business logic"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='borrower3',
            email='borrower3@example.com',
            password='testpass123',
            first_name='Bob',
            last_name='Johnson'
        )
        
        self.officer = User.objects.create_user(
            username='officer3',
            email='officer3@example.com',
            password='testpass123',
            role='LOAN_OFFICER'
        )
        
        self.product_flat = LoanProduct.objects.create(
            name='Flat Loan Product',
            code='FLAT-001',
            description='Flat interest loan',
            interest_rate=Decimal('10.00'),
            interest_method='FLAT',
            minimum_amount=Decimal('10000.00'),
            maximum_amount=Decimal('500000.00'),
            minimum_term_months=6,
            maximum_term_months=60,
            processing_fee_percentage=Decimal('2.00'),
            late_payment_penalty_percentage=Decimal('1.50'),
            grace_period_days=3,
            default_repayment_frequency='MONTHLY',
            created_by=self.officer
        )
        
        self.product_reducing = LoanProduct.objects.create(
            name='Reducing Balance Loan',
            code='RED-001',
            description='Reducing balance loan',
            interest_rate=Decimal('12.00'),
            interest_method='REDUCING_BALANCE',
            minimum_amount=Decimal('10000.00'),
            maximum_amount=Decimal('500000.00'),
            minimum_term_months=6,
            maximum_term_months=60,
            processing_fee_percentage=Decimal('2.00'),
            late_payment_penalty_percentage=Decimal('1.50'),
            grace_period_days=3,
            default_repayment_frequency='MONTHLY',
            created_by=self.officer
        )
    
    def test_create_loan_with_service(self):
        """Test creating loan with LoanService"""
        loan = LoanService.create_loan(
            customer=self.user,
            loan_product=self.product_reducing,
            principal_amount=Decimal('100000.00'),
            term_months=12,
            status='PENDING',
            created_by=self.officer
        )
        
        self.assertIsNotNone(loan.pk)
        self.assertEqual(loan.customer, self.user)
        self.assertEqual(loan.principal_amount, Decimal('100000.00'))
        self.assertEqual(loan.term_months, 12)
        self.assertEqual(loan.interest_rate, Decimal('12.00'))  # From product
    
    def test_create_loan_with_custom_interest_rate(self):
        """Test creating loan with custom interest rate"""
        loan = LoanService.create_loan(
            customer=self.user,
            loan_product=self.product_reducing,
            principal_amount=Decimal('100000.00'),
            term_months=12,
            interest_rate=Decimal('15.00'),  # Override
            status='PENDING'
        )
        
        self.assertEqual(loan.interest_rate, Decimal('15.00'))
    
    def test_create_loan_validation_amount_too_low(self):
        """Test loan creation fails when amount is too low"""
        with self.assertRaises(ValidationError) as context:
            LoanService.create_loan(
                customer=self.user,
                loan_product=self.product_reducing,
                principal_amount=Decimal('5000.00'),  # Too low
                term_months=12
            )
        
        self.assertIn('outside product limits', str(context.exception))
    
    def test_create_loan_validation_term_too_long(self):
        """Test loan creation fails when term is too long"""
        with self.assertRaises(ValidationError) as context:
            LoanService.create_loan(
                customer=self.user,
                loan_product=self.product_reducing,
                principal_amount=Decimal('100000.00'),
                term_months=72  # Too long
            )
        
        self.assertIn('outside product limits', str(context.exception))
    
    def test_generate_flat_schedule(self):
        """Test generating FLAT interest repayment schedule"""
        loan = DirectLoan.objects.create(
            customer=self.user,
            loan_product=self.product_flat,
            principal_amount=Decimal('120000.00'),
            interest_rate=Decimal('10.00'),
            term_months=12,
            status='DISBURSED',
            disbursement_date=date(2024, 1, 1),
            outstanding_principal=Decimal('120000.00')
        )
        
        schedules = LoanService.generate_repayment_schedule(
            loan=loan,
            start_date=date(2024, 1, 15),
            frequency='MONTHLY'
        )
        
        self.assertEqual(len(schedules), 12)
        
        # Check first installment
        first = schedules[0]
        self.assertEqual(first.installment_number, 1)
        self.assertEqual(first.due_date, date(2024, 1, 15))
        
        # Check total interest distributed
        total_interest = sum(s.interest_due for s in schedules)
        expected_interest = Decimal('120000.00') * Decimal('0.10')  # 12,000
        self.assertAlmostEqual(
            float(total_interest),
            float(expected_interest),
            places=1
        )
        
        # Check all principal is accounted for
        total_principal = sum(s.principal_due for s in schedules)
        self.assertAlmostEqual(
            float(total_principal),
            float(Decimal('120000.00')),
            places=1
        )
    
    def test_generate_reducing_balance_schedule(self):
        """Test generating REDUCING_BALANCE repayment schedule"""
        loan = DirectLoan.objects.create(
            customer=self.user,
            loan_product=self.product_reducing,
            principal_amount=Decimal('100000.00'),
            interest_rate=Decimal('12.00'),
            term_months=12,
            status='DISBURSED',
            disbursement_date=date(2024, 1, 1),
            outstanding_principal=Decimal('100000.00')
        )
        
        schedules = LoanService.generate_repayment_schedule(
            loan=loan,
            start_date=date(2024, 2, 1),
            frequency='MONTHLY'
        )
        
        self.assertEqual(len(schedules), 12)
        
        # For reducing balance:
        # - Interest should decrease over time
        # - Principal should increase over time
        # - Total payment should be roughly equal
        
        first = schedules[0]
        last = schedules[-1]
        
        # Interest decreases
        self.assertGreater(first.interest_due, last.interest_due)
        
        # Principal increases
        self.assertLess(first.principal_due, last.principal_due)
        
        # All principal accounted for
        total_principal = sum(s.principal_due for s in schedules)
        self.assertAlmostEqual(
            float(total_principal),
            float(Decimal('100000.00')),
            places=0
        )
    
    def test_create_loan_with_schedule_atomic(self):
        """Test creating loan with schedule in one transaction"""
        loan = LoanService.create_loan_with_schedule(
            customer=self.user,
            loan_product=self.product_reducing,
            principal_amount=Decimal('150000.00'),
            term_months=24,
            disbursement_date=date.today(),
            status='DISBURSED',
            created_by=self.officer
        )
        
        self.assertIsNotNone(loan.pk)
        self.assertEqual(loan.repayment_schedules.count(), 24)
        self.assertEqual(loan.status, 'DISBURSED')
        self.assertEqual(loan.outstanding_principal, Decimal('150000.00'))
    
    def test_disburse_loan(self):
        """Test disbursing a pending loan"""
        loan = DirectLoan.objects.create(
            customer=self.user,
            loan_product=self.product_reducing,
            principal_amount=Decimal('75000.00'),
            interest_rate=Decimal('12.00'),
            term_months=12,
            status='APPROVED'
        )
        
        disbursed_loan = LoanService.disburse_loan(
            loan=loan,
            disbursement_date=date.today(),
            disbursed_by=self.officer
        )
        
        self.assertEqual(disbursed_loan.status, 'DISBURSED')
        self.assertEqual(disbursed_loan.outstanding_principal, Decimal('75000.00'))
        self.assertIsNotNone(disbursed_loan.disbursement_date)
        self.assertGreater(disbursed_loan.repayment_schedules.count(), 0)
    
    def test_disburse_already_disbursed_loan_fails(self):
        """Test that disbursing an already disbursed loan fails"""
        loan = DirectLoan.objects.create(
            customer=self.user,
            loan_product=self.product_reducing,
            principal_amount=Decimal('75000.00'),
            interest_rate=Decimal('12.00'),
            term_months=12,
            status='DISBURSED',
            disbursement_date=date.today(),
            outstanding_principal=Decimal('75000.00')
        )
        
        with self.assertRaises(ValidationError) as context:
            LoanService.disburse_loan(loan=loan)
        
        self.assertIn('cannot be disbursed', str(context.exception))
    
    def test_record_payment_single_installment(self):
        """Test recording payment that covers one installment"""
        loan = LoanService.create_loan_with_schedule(
            customer=self.user,
            loan_product=self.product_flat,
            principal_amount=Decimal('120000.00'),
            term_months=12,
            disbursement_date=date.today(),
            status='DISBURSED'
        )
        
        # Get first installment amount
        first_schedule = loan.repayment_schedules.first()
        payment_amount = first_schedule.get_total_due()
        
        result = LoanService.record_payment(
            loan=loan,
            amount=payment_amount,
            payment_date=date.today()
        )
        
        self.assertEqual(result['installments_paid'], 1)
        self.assertEqual(result['amount_applied'], payment_amount)
        self.assertEqual(result['excess_amount'], Decimal('0.00'))
        
        # Check installment is marked paid
        first_schedule.refresh_from_db()
        self.assertTrue(first_schedule.is_paid)
    
    def test_record_payment_multiple_installments(self):
        """Test recording large payment that covers multiple installments"""
        loan = LoanService.create_loan_with_schedule(
            customer=self.user,
            loan_product=self.product_flat,
            principal_amount=Decimal('120000.00'),
            term_months=12,
            disbursement_date=date.today(),
            status='DISBURSED'
        )
        
        # Pay for 3 installments
        schedules = loan.repayment_schedules.all()[:3]
        total_due = sum(s.get_total_due() for s in schedules)
        
        result = LoanService.record_payment(
            loan=loan,
            amount=total_due,
            payment_date=date.today()
        )
        
        self.assertEqual(result['installments_paid'], 3)
        self.assertEqual(result['excess_amount'], Decimal('0.00'))
        
        # Check all 3 are paid
        for schedule in schedules:
            schedule.refresh_from_db()
            self.assertTrue(schedule.is_paid)
    
    def test_record_payment_partial(self):
        """Test recording partial payment"""
        loan = LoanService.create_loan_with_schedule(
            customer=self.user,
            loan_product=self.product_flat,
            principal_amount=Decimal('120000.00'),
            term_months=12,
            disbursement_date=date.today(),
            status='DISBURSED'
        )
        
        result = LoanService.record_payment(
            loan=loan,
            amount=Decimal('5000.00'),
            payment_date=date.today()
        )
        
        self.assertGreaterEqual(result['installments_paid'], 0)
        self.assertEqual(result['amount_applied'], Decimal('5000.00'))
        
        first_schedule = loan.repayment_schedules.first()
        self.assertEqual(first_schedule.paid_amount, Decimal('5000.00'))
        self.assertFalse(first_schedule.is_paid)
    
    def test_record_payment_closes_loan_when_fully_paid(self):
        """Test that loan is closed when fully paid"""
        loan = LoanService.create_loan_with_schedule(
            customer=self.user,
            loan_product=self.product_flat,
            principal_amount=Decimal('120000.00'),
            term_months=12,
            disbursement_date=date.today(),
            status='DISBURSED'
        )
        
        # Pay entire loan
        total_due = sum(
            s.get_total_due() for s in loan.repayment_schedules.all()
        )
        
        result = LoanService.record_payment(
            loan=loan,
            amount=total_due,
            payment_date=date.today()
        )
        
        loan.refresh_from_db()
        self.assertEqual(loan.status, 'CLOSED')
        self.assertEqual(loan.outstanding_principal, Decimal('0.00'))
    
    def test_calculate_loan_summary(self):
        """Test calculating comprehensive loan summary"""
        loan = LoanService.create_loan_with_schedule(
            customer=self.user,
            loan_product=self.product_reducing,
            principal_amount=Decimal('100000.00'),
            term_months=12,
            disbursement_date=date.today(),
            status='DISBURSED'
        )
        
        # Make one payment
        first_schedule = loan.repayment_schedules.first()
        first_schedule.record_payment(
            first_schedule.get_total_due(),
            date.today()
        )
        
        summary = LoanService.calculate_loan_summary(loan)
        
        self.assertEqual(summary['principal_amount'], Decimal('100000.00'))
        self.assertEqual(summary['term_months'], 12)
        self.assertEqual(summary['status'], 'DISBURSED')
        self.assertEqual(summary['installments_total'], 12)
        self.assertEqual(summary['installments_paid'], 1)
        self.assertEqual(summary['installments_pending'], 11)
        self.assertGreater(summary['payment_progress'], Decimal('0.00'))
        self.assertLess(summary['payment_progress'], Decimal('100.00'))


class LoanScheduleFrequencyTest(TestCase):
    """Test different repayment frequencies"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='borrower4',
            email='borrower4@example.com',
            password='testpass123'
        )
        
        self.officer = User.objects.create_user(
            username='officer4',
            email='officer4@example.com',
            password='testpass123'
        )
        
        self.product = LoanProduct.objects.create(
            name='Flexible Loan',
            code='FLEX-001',
            description='Flexible frequency loan',
            interest_rate=Decimal('12.00'),
            interest_method='REDUCING_BALANCE',
            minimum_amount=Decimal('10000.00'),
            maximum_amount=Decimal('500000.00'),
            minimum_term_months=6,
            maximum_term_months=60,
            processing_fee_percentage=Decimal('2.00'),
            late_payment_penalty_percentage=Decimal('1.50'),
            grace_period_days=3,
            default_repayment_frequency='MONTHLY',
            created_by=self.officer
        )
    
    def test_weekly_schedule(self):
        """Test generating weekly repayment schedule"""
        loan = DirectLoan.objects.create(
            customer=self.user,
            loan_product=self.product,
            principal_amount=Decimal('50000.00'),
            interest_rate=Decimal('12.00'),
            term_months=12,
            status='DISBURSED',
            disbursement_date=date(2024, 1, 1),
            outstanding_principal=Decimal('50000.00')
        )
        
        schedules = LoanService.generate_repayment_schedule(
            loan=loan,
            start_date=date(2024, 1, 8),
            frequency='WEEKLY'
        )
        
        # Check dates are 7 days apart
        for i in range(len(schedules) - 1):
            diff = (schedules[i + 1].due_date - schedules[i].due_date).days
            self.assertEqual(diff, 7)
    
    def test_fortnightly_schedule(self):
        """Test generating fortnightly repayment schedule"""
        loan = DirectLoan.objects.create(
            customer=self.user,
            loan_product=self.product,
            principal_amount=Decimal('50000.00'),
            interest_rate=Decimal('12.00'),
            term_months=12,
            status='DISBURSED',
            disbursement_date=date(2024, 1, 1),
            outstanding_principal=Decimal('50000.00')
        )
        
        schedules = LoanService.generate_repayment_schedule(
            loan=loan,
            start_date=date(2024, 1, 8),
            frequency='FORTNIGHTLY'
        )
        
        # Check dates are 14 days apart
        for i in range(len(schedules) - 1):
            diff = (schedules[i + 1].due_date - schedules[i].due_date).days
            self.assertEqual(diff, 14)
    
    def test_quarterly_schedule(self):
        """Test generating quarterly repayment schedule"""
        loan = DirectLoan.objects.create(
            customer=self.user,
            loan_product=self.product,
            principal_amount=Decimal('50000.00'),
            interest_rate=Decimal('12.00'),
            term_months=12,
            status='DISBURSED',
            disbursement_date=date(2024, 1, 1),
            outstanding_principal=Decimal('50000.00')
        )
        
        schedules = LoanService.generate_repayment_schedule(
            loan=loan,
            start_date=date(2024, 1, 1),
            frequency='QUARTERLY'
        )
        
        # Check dates are 3 months apart
        self.assertEqual(schedules[0].due_date, date(2024, 1, 1))
        self.assertEqual(schedules[1].due_date, date(2024, 4, 1))
        self.assertEqual(schedules[2].due_date, date(2024, 7, 1))


class LoanDecimalPrecisionTest(TestCase):
    """Test that all calculations use Decimal properly"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='borrower5',
            email='borrower5@example.com',
            password='testpass123'
        )
        
        self.officer = User.objects.create_user(
            username='officer5',
            email='officer5@example.com',
            password='testpass123'
        )
        
        self.product = LoanProduct.objects.create(
            name='Precision Loan',
            code='PREC-001',
            description='Precision test loan',
            interest_rate=Decimal('12.00'),
            interest_method='REDUCING_BALANCE',
            minimum_amount=Decimal('10000.00'),
            maximum_amount=Decimal('500000.00'),
            minimum_term_months=6,
            maximum_term_months=60,
            processing_fee_percentage=Decimal('2.00'),
            late_payment_penalty_percentage=Decimal('1.50'),
            grace_period_days=3,
            default_repayment_frequency='MONTHLY',
            created_by=self.officer
        )
    
    def test_all_amounts_are_decimal(self):
        """Test that all monetary amounts are Decimal instances"""
        loan = LoanService.create_loan_with_schedule(
            customer=self.user,
            loan_product=self.product,
            principal_amount=Decimal('100000.00'),
            term_months=12,
            disbursement_date=date.today(),
            status='DISBURSED'
        )
        
        # Check loan amounts
        self.assertIsInstance(loan.principal_amount, Decimal)
        self.assertIsInstance(loan.interest_rate, Decimal)
        self.assertIsInstance(loan.outstanding_principal, Decimal)
        
        # Check schedule amounts
        for schedule in loan.repayment_schedules.all():
            self.assertIsInstance(schedule.principal_due, Decimal)
            self.assertIsInstance(schedule.interest_due, Decimal)
            self.assertIsInstance(schedule.penalty_due, Decimal)
            self.assertIsInstance(schedule.paid_amount, Decimal)
    
    def test_schedule_totals_match_principal(self):
        """Test that total principal in schedule equals loan principal"""
        loan = LoanService.create_loan_with_schedule(
            customer=self.user,
            loan_product=self.product,
            principal_amount=Decimal('123456.78'),
            term_months=12,
            disbursement_date=date.today(),
            status='DISBURSED'
        )
        
        total_principal = sum(
            s.principal_due for s in loan.repayment_schedules.all()
        )
        
        # Should match exactly (allowing for tiny rounding in last installment)
        self.assertAlmostEqual(
            float(total_principal),
            float(loan.principal_amount),
            places=2
        )
    
    def test_no_floating_point_errors(self):
        """Test that there are no floating point precision errors"""
        loan = LoanService.create_loan_with_schedule(
            customer=self.user,
            loan_product=self.product,
            principal_amount=Decimal('99999.99'),
            term_months=12,
            disbursement_date=date.today(),
            status='DISBURSED'
        )
        
        # No amount should have more than 2 decimal places
        for schedule in loan.repayment_schedules.all():
            # Check principal_due
            principal_str = str(schedule.principal_due)
            if '.' in principal_str:
                decimals = len(principal_str.split('.')[1])
                self.assertLessEqual(decimals, 2)
            
            # Check interest_due
            interest_str = str(schedule.interest_due)
            if '.' in interest_str:
                decimals = len(interest_str.split('.')[1])
                self.assertLessEqual(decimals, 2)
