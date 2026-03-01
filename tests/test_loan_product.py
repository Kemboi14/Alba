"""
Test Suite for LoanProduct Model

Comprehensive tests covering configuration, validation, and calculations.
"""
from decimal import Decimal
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

from apps.loans.models import LoanProduct
from apps.accounting.models import AccountType, Account

User = get_user_model()


class LoanProductModelTest(TestCase):
    """Test LoanProduct model"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User',
        )
        
        # Create account types
        self.asset_type = AccountType.objects.create(
            name=AccountType.ASSET,
            normal_balance='DEBIT'
        )
        
        self.income_type = AccountType.objects.create(
            name=AccountType.INCOME,
            normal_balance='CREDIT'
        )
        
        # Create GL accounts
        self.loans_receivable = Account.objects.create(
            code="1200",
            name="Loans Receivable",
            account_type=self.asset_type,
            created_by=self.user,
        )
        
        self.interest_income = Account.objects.create(
            code="4100",
            name="Interest Income",
            account_type=self.income_type,
            created_by=self.user,
        )
        
        self.fee_income = Account.objects.create(
            code="4200",
            name="Fee Income",
            account_type=self.income_type,
            created_by=self.user,
        )
        
        self.penalty_income = Account.objects.create(
            code="4300",
            name="Penalty Income",
            account_type=self.income_type,
            created_by=self.user,
        )
    
    def test_create_loan_product(self):
        """Test creating a loan product"""
        product = LoanProduct.objects.create(
            name="Salary Advance",
            code="SAL-ADV",
            description="Short-term salary advance loan",
            interest_rate=Decimal('12.00'),
            interest_method='FLAT',
            minimum_amount=Decimal('5000.00'),
            maximum_amount=Decimal('50000.00'),
            minimum_term_months=1,
            maximum_term_months=6,
            processing_fee_percentage=Decimal('2.00'),
            late_payment_penalty_percentage=Decimal('5.00'),
            grace_period_days=3,
            default_repayment_frequency='MONTHLY',
            created_by=self.user,
            loan_receivable_account=self.loans_receivable,
            interest_income_account=self.interest_income,
            fee_income_account=self.fee_income,
            penalty_income_account=self.penalty_income,
        )
        
        self.assertEqual(product.name, "Salary Advance")
        self.assertEqual(product.code, "SAL-ADV")
        self.assertEqual(product.interest_method, 'FLAT')
        self.assertTrue(product.is_active)
        self.assertIsNotNone(product.created_at)
        self.assertIsNotNone(product.updated_at)
    
    def test_loan_product_unique_code(self):
        """Test loan product code must be unique"""
        LoanProduct.objects.create(
            name="Product 1",
            code="TEST-001",
            description="Test product",
            interest_rate=Decimal('10.00'),
            minimum_amount=Decimal('1000.00'),
            maximum_amount=Decimal('10000.00'),
            minimum_term_months=1,
            maximum_term_months=12,
            created_by=self.user,
        )
        
        with self.assertRaises(Exception):
            LoanProduct.objects.create(
                name="Product 2",
                code="TEST-001",  # Duplicate code
                description="Another product",
                interest_rate=Decimal('15.00'),
                minimum_amount=Decimal('2000.00'),
                maximum_amount=Decimal('20000.00'),
                minimum_term_months=1,
                maximum_term_months=12,
                created_by=self.user,
            )
    
    def test_minimum_greater_than_maximum_amount(self):
        """Test validation fails when minimum > maximum amount"""
        product = LoanProduct(
            name="Test Product",
            code="TEST-002",
            description="Test",
            interest_rate=Decimal('10.00'),
            minimum_amount=Decimal('50000.00'),
            maximum_amount=Decimal('10000.00'),  # Less than minimum!
            minimum_term_months=1,
            maximum_term_months=12,
            created_by=self.user,
        )
        
        with self.assertRaises(ValidationError) as cm:
            product.clean()
        
        self.assertIn('minimum_amount', str(cm.exception))
    
    def test_minimum_greater_than_maximum_term(self):
        """Test validation fails when minimum > maximum term"""
        product = LoanProduct(
            name="Test Product",
            code="TEST-003",
            description="Test",
            interest_rate=Decimal('10.00'),
            minimum_amount=Decimal('5000.00'),
            maximum_amount=Decimal('50000.00'),
            minimum_term_months=12,
            maximum_term_months=6,  # Less than minimum!
            created_by=self.user,
        )
        
        with self.assertRaises(ValidationError) as cm:
            product.clean()
        
        self.assertIn('minimum_term_months', str(cm.exception))
    
    def test_interest_rate_too_high(self):
        """Test validation warns on unusually high interest rate"""
        product = LoanProduct(
            name="Test Product",
            code="TEST-004",
            description="Test",
            interest_rate=Decimal('60.00'),  # > 50%
            minimum_amount=Decimal('5000.00'),
            maximum_amount=Decimal('50000.00'),
            minimum_term_months=1,
            maximum_term_months=12,
            created_by=self.user,
        )
        
        with self.assertRaises(ValidationError) as cm:
            product.clean()
        
        self.assertIn('interest_rate', str(cm.exception))
    
    def test_processing_fee_percent_too_high(self):
        """Test validation warns on unusually high processing fee"""
        product = LoanProduct(
            name="Test Product",
            code="TEST-005",
            description="Test",
            interest_rate=Decimal('10.00'),
            minimum_amount=Decimal('5000.00'),
            maximum_amount=Decimal('50000.00'),
            minimum_term_months=1,
            maximum_term_months=12,
            processing_fee_percentage=Decimal('25.00'),  # > 20%
            created_by=self.user,
        )
        
        with self.assertRaises(ValidationError) as cm:
            product.clean()
        
        self.assertIn('processing_fee_percentage', str(cm.exception))
    
    def test_penalty_rate_too_high(self):
        """Test validation warns on unusually high penalty rate"""
        product = LoanProduct(
            name="Test Product",
            code="TEST-006",
            description="Test",
            interest_rate=Decimal('10.00'),
            minimum_amount=Decimal('5000.00'),
            maximum_amount=Decimal('50000.00'),
            minimum_term_months=1,
            maximum_term_months=12,
            late_payment_penalty_percentage=Decimal('30.00'),  # > 20%
            created_by=self.user,
        )
        
        with self.assertRaises(ValidationError) as cm:
            product.clean()
        
        self.assertIn('late_payment_penalty_percentage', str(cm.exception))
    
    def test_requires_guarantor_but_minimum_zero(self):
        """Test validation fails when guarantor required but minimum is 0"""
        product = LoanProduct(
            name="Test Product",
            code="TEST-007",
            description="Test",
            interest_rate=Decimal('10.00'),
            minimum_amount=Decimal('5000.00'),
            maximum_amount=Decimal('50000.00'),
            minimum_term_months=1,
            maximum_term_months=12,
            requires_guarantor=True,
            minimum_guarantors=0,  # Should be at least 1!
            created_by=self.user,
        )
        
        with self.assertRaises(ValidationError) as cm:
            product.clean()
        
        self.assertIn('minimum_guarantors', str(cm.exception))
    
    def test_gl_account_type_validation_loan_receivable(self):
        """Test loan receivable account must be ASSET type"""
        liability_type = AccountType.objects.create(
            name=AccountType.LIABILITY,
            normal_balance='CREDIT'
        )
        
        wrong_account = Account.objects.create(
            code="2000",
            name="Wrong Account",
            account_type=liability_type,
            created_by=self.user,
        )
        
        product = LoanProduct(
            name="Test Product",
            code="TEST-008",
            description="Test",
            interest_rate=Decimal('10.00'),
            minimum_amount=Decimal('5000.00'),
            maximum_amount=Decimal('50000.00'),
            minimum_term_months=1,
            maximum_term_months=12,
            loan_receivable_account=wrong_account,  # Wrong type!
            created_by=self.user,
        )
        
        with self.assertRaises(ValidationError) as cm:
            product.clean()
        
        self.assertIn('loan_receivable_account', str(cm.exception))
    
    def test_gl_account_type_validation_interest_income(self):
        """Test interest income account must be INCOME type"""
        wrong_account = Account.objects.create(
            code="2100",
            name="Wrong Account",
            account_type=self.asset_type,
            created_by=self.user,
        )
        
        product = LoanProduct(
            name="Test Product",
            code="TEST-009",
            description="Test",
            interest_rate=Decimal('10.00'),
            minimum_amount=Decimal('5000.00'),
            maximum_amount=Decimal('50000.00'),
            minimum_term_months=1,
            maximum_term_months=12,
            interest_income_account=wrong_account,  # Wrong type!
            created_by=self.user,
        )
        
        with self.assertRaises(ValidationError) as cm:
            product.clean()
        
        self.assertIn('interest_income_account', str(cm.exception))
    
    def test_calculate_processing_fee(self):
        """Test processing fee calculation"""
        product = LoanProduct.objects.create(
            name="Test Product",
            code="TEST-010",
            description="Test",
            interest_rate=Decimal('10.00'),
            minimum_amount=Decimal('5000.00'),
            maximum_amount=Decimal('50000.00'),
            minimum_term_months=1,
            maximum_term_months=12,
            processing_fee_percentage=Decimal('2.00'),
            processing_fee_fixed=Decimal('500.00'),
            created_by=self.user,
        )
        
        loan_amount = Decimal('10000.00')
        fee = product.calculate_processing_fee(loan_amount)
        
        # 2% of 10,000 = 200, plus 500 fixed = 700
        self.assertEqual(fee, Decimal('700.00'))
    
    def test_calculate_processing_fee_negative_amount(self):
        """Test processing fee calculation rejects negative amounts"""
        product = LoanProduct.objects.create(
            name="Test Product",
            code="TEST-011",
            description="Test",
            interest_rate=Decimal('10.00'),
            minimum_amount=Decimal('5000.00'),
            maximum_amount=Decimal('50000.00'),
            minimum_term_months=1,
            maximum_term_months=12,
            created_by=self.user,
        )
        
        with self.assertRaises(ValueError):
            product.calculate_processing_fee(Decimal('-1000.00'))
    
    def test_calculate_flat_interest(self):
        """Test flat interest calculation"""
        product = LoanProduct.objects.create(
            name="Test Product",
            code="TEST-012",
            description="Test",
            interest_rate=Decimal('12.00'),  # 12% annual
            interest_method='FLAT',
            minimum_amount=Decimal('5000.00'),
            maximum_amount=Decimal('50000.00'),
            minimum_term_months=1,
            maximum_term_months=12,
            created_by=self.user,
        )
        
        loan_amount = Decimal('10000.00')
        term_months = 12
        
        interest = product.calculate_flat_interest(loan_amount, term_months)
        
        # 12% of 10,000 for 12 months = 1,200
        self.assertEqual(interest, Decimal('1200.00'))
    
    def test_calculate_flat_interest_6_months(self):
        """Test flat interest calculation for 6 months"""
        product = LoanProduct.objects.create(
            name="Test Product",
            code="TEST-013",
            description="Test",
            interest_rate=Decimal('12.00'),  # 12% annual
            interest_method='FLAT',
            minimum_amount=Decimal('5000.00'),
            maximum_amount=Decimal('50000.00'),
            minimum_term_months=1,
            maximum_term_months=12,
            created_by=self.user,
        )
        
        loan_amount = Decimal('10000.00')
        term_months = 6
        
        interest = product.calculate_flat_interest(loan_amount, term_months)
        
        # 12% of 10,000 for 6 months = 600
        self.assertEqual(interest, Decimal('600.00'))
    
    def test_calculate_monthly_payment_flat(self):
        """Test monthly payment calculation with flat rate"""
        product = LoanProduct.objects.create(
            name="Test Product",
            code="TEST-014",
            description="Test",
            interest_rate=Decimal('12.00'),
            interest_method='FLAT',
            minimum_amount=Decimal('5000.00'),
            maximum_amount=Decimal('50000.00'),
            minimum_term_months=1,
            maximum_term_months=12,
            created_by=self.user,
        )
        
        loan_amount = Decimal('10000.00')
        term_months = 12
        
        monthly_payment = product.calculate_monthly_payment(loan_amount, term_months)
        
        # Principal + Interest / Term = (10,000 + 1,200) / 12 = 933.33
        expected = Decimal('933.33')
        self.assertAlmostEqual(monthly_payment, expected, places=2)
    
    def test_calculate_monthly_payment_reducing_balance(self):
        """Test monthly payment calculation with reducing balance"""
        product = LoanProduct.objects.create(
            name="Test Product",
            code="TEST-015",
            description="Test",
            interest_rate=Decimal('12.00'),
            interest_method='REDUCING_BALANCE',
            minimum_amount=Decimal('5000.00'),
            maximum_amount=Decimal('50000.00'),
            minimum_term_months=1,
            maximum_term_months=12,
            created_by=self.user,
        )
        
        loan_amount = Decimal('10000.00')
        term_months = 12
        
        monthly_payment = product.calculate_monthly_payment(loan_amount, term_months)
        
        # EMI calculation - should be around 888
        self.assertGreater(monthly_payment, Decimal('880.00'))
        self.assertLess(monthly_payment, Decimal('900.00'))
    
    def test_calculate_monthly_payment_zero_interest(self):
        """Test monthly payment with zero interest"""
        product = LoanProduct.objects.create(
            name="Test Product",
            code="TEST-016",
            description="Test",
            interest_rate=Decimal('0.00'),
            interest_method='REDUCING_BALANCE',
            minimum_amount=Decimal('5000.00'),
            maximum_amount=Decimal('50000.00'),
            minimum_term_months=1,
            maximum_term_months=12,
            created_by=self.user,
        )
        
        loan_amount = Decimal('12000.00')
        term_months = 12
        
        monthly_payment = product.calculate_monthly_payment(loan_amount, term_months)
        
        # Simple division when interest is 0
        self.assertEqual(monthly_payment, Decimal('1000.00'))
    
    def test_is_amount_valid(self):
        """Test amount validation"""
        product = LoanProduct.objects.create(
            name="Test Product",
            code="TEST-017",
            description="Test",
            interest_rate=Decimal('10.00'),
            minimum_amount=Decimal('5000.00'),
            maximum_amount=Decimal('50000.00'),
            minimum_term_months=1,
            maximum_term_months=12,
            created_by=self.user,
        )
        
        self.assertTrue(product.is_amount_valid(Decimal('10000.00')))
        self.assertTrue(product.is_amount_valid(Decimal('5000.00')))
        self.assertTrue(product.is_amount_valid(Decimal('50000.00')))
        self.assertFalse(product.is_amount_valid(Decimal('4999.00')))
        self.assertFalse(product.is_amount_valid(Decimal('50001.00')))
    
    def test_is_term_valid(self):
        """Test term validation"""
        product = LoanProduct.objects.create(
            name="Test Product",
            code="TEST-018",
            description="Test",
            interest_rate=Decimal('10.00'),
            minimum_amount=Decimal('5000.00'),
            maximum_amount=Decimal('50000.00'),
            minimum_term_months=3,
            maximum_term_months=24,
            created_by=self.user,
        )
        
        self.assertTrue(product.is_term_valid(6))
        self.assertTrue(product.is_term_valid(3))
        self.assertTrue(product.is_term_valid(24))
        self.assertFalse(product.is_term_valid(2))
        self.assertFalse(product.is_term_valid(25))
    
    def test_property_aliases(self):
        """Test API-friendly property aliases"""
        product = LoanProduct.objects.create(
            name="Test Product",
            code="TEST-019",
            description="Test",
            interest_rate=Decimal('10.00'),
            interest_method='FLAT',
            minimum_amount=Decimal('5000.00'),
            maximum_amount=Decimal('50000.00'),
            minimum_term_months=1,
            maximum_term_months=12,
            processing_fee_percentage=Decimal('2.50'),
            late_payment_penalty_percentage=Decimal('5.00'),
            default_repayment_frequency='MONTHLY',
            created_by=self.user,
        )
        
        # Test property aliases
        self.assertEqual(product.interest_type, 'flat')
        self.assertEqual(product.processing_fee_percent, Decimal('2.50'))
        self.assertEqual(product.penalty_rate, Decimal('5.00'))
        self.assertEqual(product.repayment_frequency, 'monthly')
    
    def test_reducing_balance_alias(self):
        """Test reducing_balance alias returns correctly"""
        product = LoanProduct.objects.create(
            name="Test Product",
            code="TEST-020",
            description="Test",
            interest_rate=Decimal('10.00'),
            interest_method='REDUCING_BALANCE',
            minimum_amount=Decimal('5000.00'),
            maximum_amount=Decimal('50000.00'),
            minimum_term_months=1,
            maximum_term_months=12,
            created_by=self.user,
        )
        
        self.assertEqual(product.interest_type, 'reducing_balance')


class LoanProductBusinessLogicTest(TestCase):
    """Test business logic and edge cases"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User',
        )
    
    def test_repayment_frequencies(self):
        """Test all repayment frequency options"""
        frequencies = ['WEEKLY', 'FORTNIGHTLY', 'MONTHLY', 'QUARTERLY']
        
        for i, freq in enumerate(frequencies):
            product = LoanProduct.objects.create(
                name=f"Product {freq}",
                code=f"TEST-FREQ-{i}",
                description="Test",
                interest_rate=Decimal('10.00'),
                minimum_amount=Decimal('5000.00'),
                maximum_amount=Decimal('50000.00'),
                minimum_term_months=1,
                maximum_term_months=12,
                default_repayment_frequency=freq,
                created_by=self.user,
            )
            
            self.assertEqual(product.default_repayment_frequency, freq)
    
    def test_interest_methods(self):
        """Test both interest methods"""
        for method in ['FLAT', 'REDUCING_BALANCE']:
            product = LoanProduct.objects.create(
                name=f"Product {method}",
                code=f"TEST-INT-{method}",
                description="Test",
                interest_rate=Decimal('10.00'),
                interest_method=method,
                minimum_amount=Decimal('5000.00'),
                maximum_amount=Decimal('50000.00'),
                minimum_term_months=1,
                maximum_term_months=12,
                created_by=self.user,
            )
            
            self.assertEqual(product.interest_method, method)
    
    def test_zero_grace_period(self):
        """Test product with zero grace period"""
        product = LoanProduct.objects.create(
            name="Strict Product",
            code="TEST-STRICT",
            description="No grace period",
            interest_rate=Decimal('10.00'),
            minimum_amount=Decimal('5000.00'),
            maximum_amount=Decimal('50000.00'),
            minimum_term_months=1,
            maximum_term_months=12,
            grace_period_days=0,
            created_by=self.user,
        )
        
        self.assertEqual(product.grace_period_days, 0)
    
    def test_high_grace_period(self):
        """Test product with extended grace period"""
        product = LoanProduct.objects.create(
            name="Lenient Product",
            code="TEST-LENIENT",
            description="Long grace period",
            interest_rate=Decimal('10.00'),
            minimum_amount=Decimal('5000.00'),
            maximum_amount=Decimal('50000.00'),
            minimum_term_months=1,
            maximum_term_months=12,
            grace_period_days=30,
            created_by=self.user,
        )
        
        self.assertEqual(product.grace_period_days, 30)


# Run tests with: python manage.py test tests.test_loan_product
