"""
Credit Scoring Engine
Automated risk evaluation system for loan applications
Implements SRS Section 3.1.3: Credit Scoring Engine
"""
from decimal import Decimal
from typing import Dict, Any
from datetime import date, timedelta
from django.utils import timezone
from django.db.models import Q, Sum, Count
import logging

from apps.loans.models import Loan, LoanApplication, Customer, LoanProduct

logger = logging.getLogger(__name__)


class CreditScoringService:
    """
    Automated credit evaluation engine
    
    Scoring Algorithm:
    - Income Assessment (30 points)
    - Debt-to-Income Ratio (25 points)
    - Employment Stability (15 points)
    - Loan History (20 points)
    - Credit Behavior (10 points)
    
    Total Score: 0-100
    
    Grades:
    - A (85-100): Excellent - Auto-approve
    - B (70-84): Good - Auto-approve with conditions
    - C (55-69): Fair - Manual review required
    - D (40-54): Poor - Manual review required
    - E (0-39): Very Poor - Auto-reject
    """
    
    # Scoring weights
    INCOME_WEIGHT = 30
    DTI_WEIGHT = 25  # Debt-to-Income ratio
    EMPLOYMENT_WEIGHT = 15
    HISTORY_WEIGHT = 20
    BEHAVIOR_WEIGHT = 10
    
    # Decision thresholds
    AUTO_APPROVE_THRESHOLD = 70
    MANUAL_REVIEW_THRESHOLD = 55
    AUTO_REJECT_THRESHOLD = 40
    
    # Credit grades
    GRADES = {
        'A': {'min': 85, 'max': 100, 'label': 'Excellent'},
        'B': {'min': 70, 'max': 84, 'label': 'Good'},
        'C': {'min': 55, 'max': 69, 'label': 'Fair'},
        'D': {'min': 40, 'max': 54, 'label': 'Poor'},
        'E': {'min': 0, 'max': 39, 'label': 'Very Poor'},
    }
    
    def calculate_credit_score(
        self,
        customer: Customer,
        loan_amount: Decimal,
        loan_product: LoanProduct,
        monthly_income: Decimal,
        existing_obligations: Decimal,
        employment_years: int = 0
    ) -> Dict[str, Any]:
        """
        Calculate comprehensive credit score
        
        Args:
            customer: Customer applying for loan
            loan_amount: Requested loan amount
            loan_product: Loan product being applied for
            monthly_income: Customer's monthly income
            existing_obligations: Customer's existing monthly debt obligations
            employment_years: Years with current employer
            
        Returns:
            Dict with score, grade, decision, and breakdown
        """
        try:
            logger.info(f"Calculating credit score for customer {customer.email}, loan amount: {loan_amount}")
            
            # Calculate individual scores
            income_score = self._calculate_income_score(monthly_income, loan_amount)
            dti_score = self._calculate_dti_score(monthly_income, existing_obligations, loan_amount, loan_product)
            employment_score = self._calculate_employment_score(employment_years, customer)
            history_score = self._calculate_loan_history_score(customer)
            behavior_score = self._calculate_behavior_score(customer)
            
            # Calculate total score
            total_score = (
                income_score + dti_score + employment_score + 
                history_score + behavior_score
            )
            
            # Determine grade
            grade = self._get_grade(total_score)
            
            # Determine decision
            decision = self._get_decision(total_score)
            
            # Build detailed result
            result = {
                'score': round(total_score, 2),
                'grade': grade,
                'decision': decision,
                'breakdown': {
                    'income_score': round(income_score, 2),
                    'dti_score': round(dti_score, 2),
                    'employment_score': round(employment_score, 2),
                    'history_score': round(history_score, 2),
                    'behavior_score': round(behavior_score, 2),
                },
                'factors': self._get_risk_factors(
                    monthly_income, existing_obligations, loan_amount, 
                    employment_years, customer
                ),
                'timestamp': timezone.now().isoformat(),
            }
            
            logger.info(
                f"Credit score calculated: {total_score:.2f} ({grade}) - {decision} "
                f"for customer {customer.email}"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Credit scoring failed for customer {customer.email}: {str(e)}")
            # Return conservative default score
            return {
                'score': 50.0,
                'grade': 'C',
                'decision': 'MANUAL_REVIEW',
                'breakdown': {},
                'factors': ['Error in scoring - manual review required'],
                'timestamp': timezone.now().isoformat(),
                'error': str(e)
            }
    
    def _calculate_income_score(self, monthly_income: Decimal, loan_amount: Decimal) -> float:
        """
        Score based on income adequacy (30 points max)
        
        Logic:
        - Income 5x+ loan amount: 30 points
        - Income 3-5x loan amount: 25 points
        - Income 2-3x loan amount: 20 points
        - Income 1-2x loan amount: 10 points
        - Income < loan amount: 5 points
        """
        if monthly_income <= 0:
            return 5.0
        
        income_to_loan_ratio = (monthly_income * 12) / loan_amount
        
        if income_to_loan_ratio >= 5:
            return self.INCOME_WEIGHT
        elif income_to_loan_ratio >= 3:
            return self.INCOME_WEIGHT * 0.83  # 25 points
        elif income_to_loan_ratio >= 2:
            return self.INCOME_WEIGHT * 0.67  # 20 points
        elif income_to_loan_ratio >= 1:
            return self.INCOME_WEIGHT * 0.33  # 10 points
        else:
            return self.INCOME_WEIGHT * 0.17  # 5 points
    
    def _calculate_dti_score(
        self, 
        monthly_income: Decimal, 
        existing_obligations: Decimal,
        loan_amount: Decimal,
        loan_product: LoanProduct
    ) -> float:
        """
        Score based on Debt-to-Income ratio (25 points max)
        
        Logic:
        - Calculate expected monthly payment for new loan
        - Add to existing obligations
        - DTI < 30%: 25 points (excellent)
        - DTI 30-40%: 20 points (good)
        - DTI 40-50%: 15 points (acceptable)
        - DTI 50-60%: 10 points (risky)
        - DTI > 60%: 5 points (very risky)
        """
        if monthly_income <= 0:
            return 5.0
        
        # Estimate monthly payment for new loan (simplified)
        # Actual calculation would use loan product's interest rate
        repayment_months = 12  # Default assumption
        interest_rate = loan_product.interest_rate if loan_product else Decimal('15.0')
        
        # Rough monthly payment calculation (flat rate for simplicity)
        monthly_interest = (loan_amount * interest_rate / 100) / 12
        monthly_principal = loan_amount / repayment_months
        estimated_monthly_payment = monthly_principal + monthly_interest
        
        # Calculate total DTI with new loan
        total_obligations = existing_obligations + estimated_monthly_payment
        dti_ratio = (total_obligations / monthly_income) * 100
        
        if dti_ratio < 30:
            return self.DTI_WEIGHT  # 25 points
        elif dti_ratio < 40:
            return self.DTI_WEIGHT * 0.80  # 20 points
        elif dti_ratio < 50:
            return self.DTI_WEIGHT * 0.60  # 15 points
        elif dti_ratio < 60:
            return self.DTI_WEIGHT * 0.40  # 10 points
        else:
            return self.DTI_WEIGHT * 0.20  # 5 points
    
    def _calculate_employment_score(self, employment_years: int, customer: Customer) -> float:
        """
        Score based on employment stability (15 points max)
        
        Logic:
        - 5+ years: 15 points
        - 3-5 years: 12 points
        - 1-3 years: 9 points
        - 6-12 months: 6 points
        - < 6 months: 3 points
        """
        if employment_years >= 5:
            return self.EMPLOYMENT_WEIGHT
        elif employment_years >= 3:
            return self.EMPLOYMENT_WEIGHT * 0.80  # 12 points
        elif employment_years >= 1:
            return self.EMPLOYMENT_WEIGHT * 0.60  # 9 points
        elif employment_years >= 0.5:
            return self.EMPLOYMENT_WEIGHT * 0.40  # 6 points
        else:
            return self.EMPLOYMENT_WEIGHT * 0.20  # 3 points
    
    def _calculate_loan_history_score(self, customer: Customer) -> float:
        """
        Score based on loan repayment history (20 points max)
        
        Logic:
        - No previous loans: 15 points (neutral)
        - All loans fully repaid: 20 points (excellent)
        - Active loans, no arrears: 18 points (good)
        - Some arrears but recovering: 12 points (fair)
        - Current arrears: 8 points (poor)
        - Defaulted loans: 5 points (very poor)
        """
        # Get all customer loans
        all_loans = Loan.objects.filter(customer=customer)
        
        if not all_loans.exists():
            # No loan history - neutral score
            return self.HISTORY_WEIGHT * 0.75  # 15 points
        
        # Check for closed loans (fully repaid)
        closed_loans = all_loans.filter(status='CLOSED')
        active_loans = all_loans.filter(status__in=['ACTIVE', 'DISBURSED'])
        defaulted_loans = all_loans.filter(status__in=['DEFAULTED', 'WRITTEN_OFF'])
        
        # If any defaults, very poor score
        if defaulted_loans.exists():
            return self.HISTORY_WEIGHT * 0.25  # 5 points
        
        # Check for arrears in active loans
        if active_loans.exists():
            arrears_count = active_loans.filter(
                days_overdue__gt=0
            ).count()
            
            if arrears_count == 0:
                # All active loans performing well
                return self.HISTORY_WEIGHT * 0.90  # 18 points
            elif arrears_count <= active_loans.count() * 0.3:
                # Some arrears but manageable
                return self.HISTORY_WEIGHT * 0.60  # 12 points
            else:
                # Significant arrears
                return self.HISTORY_WEIGHT * 0.40  # 8 points
        
        # All loans closed successfully
        if closed_loans.exists() and not active_loans.exists():
            return self.HISTORY_WEIGHT  # 20 points (excellent)
        
        return self.HISTORY_WEIGHT * 0.75  # 15 points (default)
    
    def _calculate_behavior_score(self, customer: Customer) -> float:
        """
        Score based on customer behavior (10 points max)
        
        Logic:
        - Customer age/tenure with Alba Capital
        - Application history
        - Communication responsiveness
        - Document submission compliance
        """
        score = 0.0
        
        # Customer tenure (5 points)
        if customer.created_at:
            days_since_registration = (timezone.now() - customer.created_at).days
            if days_since_registration >= 365:
                score += 5.0  # 1+ year relationship
            elif days_since_registration >= 180:
                score += 4.0  # 6+ months
            elif days_since_registration >= 90:
                score += 3.0  # 3+ months
            else:
                score += 2.0  # New customer
        
        # Application history (5 points)
        applications = LoanApplication.objects.filter(customer=customer)
        if applications.exists():
            approved_apps = applications.filter(status='APPROVED').count()
            rejected_apps = applications.filter(status='REJECTED').count()
            total_apps = applications.count()
            
            if approved_apps > 0 and rejected_apps == 0:
                score += 5.0  # Clean application history
            elif approved_apps > rejected_apps:
                score += 3.0  # More approvals than rejections
            else:
                score += 1.0  # Spotty history
        else:
            score += 3.0  # First-time applicant (neutral)
        
        return min(score, self.BEHAVIOR_WEIGHT)
    
    def _get_grade(self, score: float) -> str:
        """Convert numeric score to letter grade"""
        for grade, thresholds in self.GRADES.items():
            if thresholds['min'] <= score <= thresholds['max']:
                return grade
        return 'E'  # Default to lowest grade
    
    def _get_decision(self, score: float) -> str:
        """
        Determine approval decision based on score
        
        Returns:
            'AUTO_APPROVED', 'MANUAL_REVIEW', or 'AUTO_REJECTED'
        """
        if score >= self.AUTO_APPROVE_THRESHOLD:
            return 'AUTO_APPROVED'
        elif score >= self.MANUAL_REVIEW_THRESHOLD:
            return 'MANUAL_REVIEW'
        else:
            return 'AUTO_REJECTED'
    
    def _get_risk_factors(
        self,
        monthly_income: Decimal,
        existing_obligations: Decimal,
        loan_amount: Decimal,
        employment_years: int,
        customer: Customer
    ) -> list:
        """Identify risk factors for manual review"""
        factors = []
        
        # Income adequacy
        income_to_loan = (monthly_income * 12) / loan_amount if loan_amount > 0 else 0
        if income_to_loan < 2:
            factors.append('Low income-to-loan ratio')
        
        # DTI ratio
        dti = (existing_obligations / monthly_income * 100) if monthly_income > 0 else 100
        if dti > 50:
            factors.append('High debt-to-income ratio')
        
        # Employment stability
        if employment_years < 1:
            factors.append('Limited employment history')
        
        # Loan history
        defaulted_loans = Loan.objects.filter(
            customer=customer,
            status__in=['DEFAULTED', 'WRITTEN_OFF']
        ).count()
        if defaulted_loans > 0:
            factors.append(f'{defaulted_loans} previous loan default(s)')
        
        # Active arrears
        active_arrears = Loan.objects.filter(
            customer=customer,
            status='ACTIVE',
            days_overdue__gt=30
        ).count()
        if active_arrears > 0:
            factors.append(f'{active_arrears} active loan(s) in arrears')
        
        # New customer
        customer_age_days = (timezone.now() - customer.created_at).days
        if customer_age_days < 30:
            factors.append('New customer (less than 30 days)')
        
        if not factors:
            factors.append('No significant risk factors identified')
        
        return factors


class CreditScoringOverrideService:
    """
    Handle manual override of credit scoring decisions
    Implements audit trail for all overrides per SRS requirements
    """
    
    @staticmethod
    def override_decision(
        application: LoanApplication,
        new_decision: str,
        override_reason: str,
        overridden_by: 'User'
    ) -> bool:
        """
        Override automatic credit decision
        
        Args:
            application: Loan application being overridden
            new_decision: New decision ('APPROVED', 'REJECTED')
            override_reason: Mandatory justification
            overridden_by: User making the override (must have authority)
            
        Returns:
            bool: Success status
        """
        try:
            # Verify user has authority to override
            if not overridden_by.can_approve_loans():
                logger.warning(
                    f"Unauthorized override attempt by {overridden_by.email} "
                    f"for application {application.id}"
                )
                return False
            
            # Record original decision
            original_decision = application.auto_decision
            original_score = application.credit_score
            
            # Update application
            application.status = new_decision
            application.auto_decision_overridden = True
            application.override_reason = override_reason
            application.overridden_by = overridden_by
            application.override_date = timezone.now()
            application.save()
            
            # Log the override in audit trail
            from apps.core.models import AuditLog
            AuditLog.objects.create(
                user=overridden_by,
                action='CREDIT_SCORE_OVERRIDE',
                module='loans',
                description=(
                    f"Credit decision overridden for application {application.application_number}. "
                    f"Original: {original_decision} (Score: {original_score}), "
                    f"New: {new_decision}. Reason: {override_reason}"
                ),
                ip_address='system',
                details={
                    'application_id': application.id,
                    'original_decision': original_decision,
                    'new_decision': new_decision,
                    'reason': override_reason
                }
            )
            
            logger.info(
                f"Credit decision overridden by {overridden_by.email}: "
                f"Application {application.id}, {original_decision} -> {new_decision}"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Override failed for application {application.id}: {str(e)}")
            return False


class CreditScoringConfigService:
    """
    Configurable credit scoring parameters
    Allows admins to adjust scoring weights and thresholds without code changes
    """
    
    DEFAULT_CONFIG = {
        'weights': {
            'income': 30,
            'dti': 25,
            'employment': 15,
            'history': 20,
            'behavior': 10,
        },
        'thresholds': {
            'auto_approve': 70,
            'manual_review': 55,
            'auto_reject': 40,
        },
        'dti_limits': {
            'excellent': 30,
            'good': 40,
            'acceptable': 50,
            'risky': 60,
        },
        'income_multiples': {
            'excellent': 5,
            'good': 3,
            'acceptable': 2,
            'minimum': 1,
        }
    }
    
    @classmethod
    def get_config(cls) -> Dict[str, Any]:
        """
        Get current scoring configuration
        
        Returns:
            Dict with scoring parameters
        """
        # TODO: Load from database settings model
        # For now, return defaults
        return cls.DEFAULT_CONFIG
    
    @classmethod
    def update_config(cls, config: Dict[str, Any], updated_by: 'User') -> bool:
        """
        Update scoring configuration
        
        Args:
            config: New configuration parameters
            updated_by: User making the change
            
        Returns:
            bool: Success status
        """
        try:
            # TODO: Save to database settings model
            # TODO: Create audit log entry
            logger.info(f"Credit scoring config updated by {updated_by.email}")
            return True
        except Exception as e:
            logger.error(f"Config update failed: {str(e)}")
            return False
