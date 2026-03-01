"""
Credit Bureau Integration Module
Implements third-party credit scoring via Kenyan credit bureaus

Supported Bureaus:
- Metropol CRB
- TransUnion Kenya
- Creditinfo Kenya

SRS Compliance: Section 3.1.3 - Credit Scoring with external data sources
"""
from decimal import Decimal
from typing import Dict, Any, Optional
import logging
import requests
from django.conf import settings
from django.core.cache import cache

from apps.loans.models import Customer

logger = logging.getLogger(__name__)


class CreditBureauService:
    """
    Service for fetching credit reports from external credit bureaus
    
    Features:
    - Multi-bureau support (Metropol, TransUnion, Creditinfo)
    - Caching to reduce API calls (24-hour cache)
    - Fallback to internal scoring if bureau unavailable
    - Score normalization (bureau score → 0-100 scale)
    """
    
    # Bureau API configurations (from settings)
    METROPOL_API_URL = getattr(settings, 'METROPOL_API_URL', 'https://api.metropol.co.ke/v1')
    METROPOL_API_KEY = getattr(settings, 'METROPOL_API_KEY', '')
    
    TRANSUNION_API_URL = getattr(settings, 'TRANSUNION_API_URL', 'https://api.transunion.co.ke/v2')
    TRANSUNION_API_KEY = getattr(settings, 'TRANSUNION_API_KEY', '')
    
    CREDITINFO_API_URL = getattr(settings, 'CREDITINFO_API_URL', 'https://api.creditinfo.co.ke/v1')
    CREDITINFO_API_KEY = getattr(settings, 'CREDITINFO_API_KEY', '')
    
    # Bureau priority (checked in order)
    BUREAU_PRIORITY = ['metropol', 'transunion', 'creditinfo']
    
    # Cache settings
    CACHE_TTL = 86400  # 24 hours
    
    def fetch_credit_report(
        self,
        customer: Customer,
        bureau: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Fetch credit report from bureau
        
        Args:
            customer: Customer instance
            bureau: Specific bureau ('metropol', 'transunion', 'creditinfo') or None for auto
            
        Returns:
            Dict with:
                - bureau_score: 0-100 normalized score
                - internal_score: Our credit score
                - combined_score: Weighted average
                - report_data: Raw bureau response
                - bureau_name: Which bureau provided data
                - cached: Whether result was cached
        """
        try:
            # Check cache first
            cache_key = f"credit_report_{customer.national_id}"
            cached_report = cache.get(cache_key)
            
            if cached_report:
                logger.info(f"Using cached credit report for {customer.national_id}")
                cached_report['cached'] = True
                return cached_report
            
            # Try bureaus in priority order
            bureaus_to_try = [bureau] if bureau else self.BUREAU_PRIORITY
            
            for bureau_name in bureaus_to_try:
                try:
                    report = self._fetch_from_bureau(customer, bureau_name)
                    if report:
                        # Cache the result
                        cache.set(cache_key, report, self.CACHE_TTL)
                        report['cached'] = False
                        return report
                except Exception as e:
                    logger.warning(f"Failed to fetch from {bureau_name}: {str(e)}")
                    continue
            
            # All bureaus failed - return internal score only
            logger.warning(f"All credit bureaus unavailable for {customer.national_id}")
            return {
                'bureau_score': None,
                'internal_score': None,  # Will be calculated by main scoring engine
                'combined_score': None,
                'report_data': {},
                'bureau_name': None,
                'cached': False,
                'error': 'Credit bureaus unavailable - using internal scoring only'
            }
            
        except Exception as e:
            logger.error(f"Credit report fetch failed for {customer.national_id}: {str(e)}")
            return {
                'bureau_score': None,
                'internal_score': None,
                'combined_score': None,
                'report_data': {},
                'bureau_name': None,
                'error': str(e)
            }
    
    def _fetch_from_bureau(self, customer: Customer, bureau: str) -> Optional[Dict[str, Any]]:
        """
        Fetch from specific bureau
        
        Args:
            customer: Customer instance
            bureau: Bureau name
            
        Returns:
            Dict with credit report data or None if failed
        """
        if bureau == 'metropol':
            return self._fetch_from_metropol(customer)
        elif bureau == 'transunion':
            return self._fetch_from_transunion(customer)
        elif bureau == 'creditinfo':
            return self._fetch_from_creditinfo(customer)
        else:
            raise ValueError(f"Unknown bureau: {bureau}")
    
    def _fetch_from_metropol(self, customer: Customer) -> Optional[Dict[str, Any]]:
        """
        Fetch credit report from Metropol CRB
        
        API Documentation: https://developer.metropol.co.ke/
        """
        if not self.METROPOL_API_KEY:
            logger.warning("Metropol API key not configured")
            return None
        
        try:
            response = requests.post(
                f"{self.METROPOL_API_URL}/credit-report",
                json={
                    'national_id': customer.national_id,
                    'full_name': customer.get_full_name(),
                    'phone': customer.phone_number,
                    'report_type': 'full'
                },
                headers={
                    'Authorization': f'Bearer {self.METROPOL_API_KEY}',
                    'Content-Type': 'application/json'
                },
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Metropol scores: 200-800 scale
                # Normalize: (score - 200) / 600 * 100
                raw_score = data.get('credit_score', 400)
                normalized_score = max(0, min(100, ((raw_score - 200) / 600) * 100))
                
                return {
                    'bureau_score': round(normalized_score, 2),
                    'bureau_name': 'Metropol CRB',
                    'report_data': data,
                    'raw_score': raw_score,
                    'score_scale': '200-800',
                    'report_date': data.get('report_date'),
                    'negative_listings': data.get('negative_listings', []),
                    'account_summary': data.get('account_summary', {})
                }
            else:
                logger.error(f"Metropol API error: {response.status_code}")
                return None
                
        except requests.Timeout:
            logger.error("Metropol API timeout")
            return None
        except Exception as e:
            logger.error(f"Metropol fetch error: {str(e)}")
            return None
    
    def _fetch_from_transunion(self, customer: Customer) -> Optional[Dict[str, Any]]:
        """
        Fetch credit report from TransUnion Kenya
        
        API Documentation: https://developer.transunion.co.ke/
        """
        if not self.TRANSUNION_API_KEY:
            logger.warning("TransUnion API key not configured")
            return None
        
        try:
            response = requests.get(
                f"{self.TRANSUNION_API_URL}/consumer-report",
                params={
                    'id_number': customer.national_id,
                    'product': 'consumer_score'
                },
                headers={
                    'X-API-Key': self.TRANSUNION_API_KEY,
                    'Accept': 'application/json'
                },
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # TransUnion scores: 300-900 scale
                # Normalize: (score - 300) / 600 * 100
                raw_score = data.get('score', 500)
                normalized_score = max(0, min(100, ((raw_score - 300) / 600) * 100))
                
                return {
                    'bureau_score': round(normalized_score, 2),
                    'bureau_name': 'TransUnion Kenya',
                    'report_data': data,
                    'raw_score': raw_score,
                    'score_scale': '300-900',
                    'report_date': data.get('date'),
                    'risk_grade': data.get('risk_grade'),
                    'payment_history': data.get('payment_history', {})
                }
            else:
                logger.error(f"TransUnion API error: {response.status_code}")
                return None
                
        except requests.Timeout:
            logger.error("TransUnion API timeout")
            return None
        except Exception as e:
            logger.error(f"TransUnion fetch error: {str(e)}")
            return None
    
    def _fetch_from_creditinfo(self, customer: Customer) -> Optional[Dict[str, Any]]:
        """
        Fetch credit report from Creditinfo Kenya
        
        API Documentation: https://developer.creditinfo.co.ke/
        """
        if not self.CREDITINFO_API_KEY:
            logger.warning("Creditinfo API key not configured")
            return None
        
        try:
            response = requests.post(
                f"{self.CREDITINFO_API_URL}/reports/individual",
                json={
                    'nationalId': customer.national_id,
                    'firstName': customer.first_name,
                    'lastName': customer.last_name,
                    'mobile': customer.phone_number
                },
                headers={
                    'API-Key': self.CREDITINFO_API_KEY,
                    'Content-Type': 'application/json'
                },
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Creditinfo scores: 1-10 scale
                # Normalize: (score / 10) * 100
                raw_score = data.get('creditScore', 5)
                normalized_score = (raw_score / 10) * 100
                
                return {
                    'bureau_score': round(normalized_score, 2),
                    'bureau_name': 'Creditinfo Kenya',
                    'report_data': data,
                    'raw_score': raw_score,
                    'score_scale': '1-10',
                    'report_date': data.get('reportDate'),
                    'credit_grade': data.get('creditGrade'),
                    'delinquency_status': data.get('delinquencyStatus')
                }
            else:
                logger.error(f"Creditinfo API error: {response.status_code}")
                return None
                
        except requests.Timeout:
            logger.error("Creditinfo API timeout")
            return None
        except Exception as e:
            logger.error(f"Creditinfo fetch error: {str(e)}")
            return None
    
    def combine_scores(
        self,
        internal_score: float,
        bureau_score: Optional[float]
    ) -> float:
        """
        Combine internal and bureau scores with weights
        
        Weights:
        - Bureau score: 60% (if available)
        - Internal score: 40%
        
        Args:
            internal_score: Our calculated score (0-100)
            bureau_score: Bureau score (0-100 normalized) or None
            
        Returns:
            Combined score (0-100)
        """
        if bureau_score is None:
            # No bureau data - use internal only
            return internal_score
        
        # Weighted average: 60% bureau, 40% internal
        combined = (bureau_score * 0.6) + (internal_score * 0.4)
        
        return round(combined, 2)
    
    def check_negative_listings(
        self,
        customer: Customer
    ) -> Dict[str, Any]:
        """
        Check if customer has negative credit listings
        
        Returns:
            Dict with:
                - has_listings: bool
                - listings: List of negative listings
                - recommendation: 'APPROVE' or 'REJECT'
        """
        try:
            report = self.fetch_credit_report(customer)
            
            if not report or not report.get('report_data'):
                return {
                    'has_listings': False,
                    'listings': [],
                    'recommendation': 'MANUAL_REVIEW',
                    'note': 'Unable to verify with credit bureau'
                }
            
            # Check for negative listings
            negative_listings = report.get('report_data', {}).get('negative_listings', [])
            
            if negative_listings:
                return {
                    'has_listings': True,
                    'listings': negative_listings,
                    'recommendation': 'REJECT',
                    'note': f'Found {len(negative_listings)} negative listing(s)'
                }
            else:
                return {
                    'has_listings': False,
                    'listings': [],
                    'recommendation': 'APPROVE',
                    'note': 'No negative credit listings found'
                }
                
        except Exception as e:
            logger.error(f"Negative listing check failed: {str(e)}")
            return {
                'has_listings': False,
                'listings': [],
                'recommendation': 'MANUAL_REVIEW',
                'note': f'Error: {str(e)}'
            }


class HybridCreditScoringService:
    """
    Hybrid credit scoring combining internal + bureau scores
    
    Decision Logic:
    1. Fetch bureau report (if configured)
    2. Calculate internal score
    3. Combine scores (60% bureau, 40% internal)
    4. Check for negative listings (auto-reject)
    5. Return final decision
    """
    
    def __init__(self):
        self.bureau_service = CreditBureauService()
    
    def evaluate_loan_application(
        self,
        customer: Customer,
        loan_amount: Decimal,
        loan_product,
        monthly_income: Decimal,
        existing_obligations: Decimal,
        employment_years: int = 0
    ) -> Dict[str, Any]:
        """
        Complete credit evaluation with bureau integration
        
        Returns:
            Dict with:
                - final_score: Combined score
                - decision: AUTO_APPROVED/MANUAL_REVIEW/AUTO_REJECTED
                - internal_score: Our calculated score
                - bureau_score: Bureau score (if available)
                - bureau_name: Bureau provider
                - negative_listings: Any adverse listings
                - recommendation: Final recommendation
        """
        from apps.loans.credit_scoring import CreditScoringService
        
        logger.info(f"Starting hybrid credit evaluation for {customer.email}")
        
        # 1. Calculate internal score
        internal_scorer = CreditScoringService()
        internal_result = internal_scorer.calculate_credit_score(
            customer=customer,
            loan_amount=loan_amount,
            loan_product=loan_product,
            monthly_income=monthly_income,
            existing_obligations=existing_obligations,
            employment_years=employment_years
        )
        
        internal_score = internal_result['score']
        
        # 2. Fetch bureau report (if configured)
        bureau_report = self.bureau_service.fetch_credit_report(customer)
        bureau_score = bureau_report.get('bureau_score')
        bureau_name = bureau_report.get('bureau_name', 'None')
        
        # 3. Check negative listings (auto-reject if found)
        negative_check = self.bureau_service.check_negative_listings(customer)
        
        if negative_check['has_listings'] and negative_check['recommendation'] == 'REJECT':
            logger.warning(f"Auto-rejecting {customer.email} due to negative listings")
            return {
                'final_score': 0,
                'decision': 'AUTO_REJECTED',
                'internal_score': internal_score,
                'bureau_score': bureau_score,
                'bureau_name': bureau_name,
                'negative_listings': negative_check['listings'],
                'recommendation': 'REJECT',
                'reason': 'Negative credit bureau listings found',
                'breakdown': internal_result['breakdown']
            }
        
        # 4. Combine scores
        if bureau_score:
            final_score = self.bureau_service.combine_scores(internal_score, bureau_score)
            scoring_method = 'Hybrid (60% Bureau + 40% Internal)'
        else:
            final_score = internal_score
            scoring_method = 'Internal Only (Bureau unavailable)'
        
        # 5. Make decision based on combined score
        if final_score >= 70:
            decision = 'AUTO_APPROVED'
            recommendation = 'APPROVE'
        elif final_score >= 55:
            decision = 'MANUAL_REVIEW'
            recommendation = 'REVIEW'
        else:
            decision = 'AUTO_REJECTED'
            recommendation = 'REJECT'
        
        logger.info(
            f"Hybrid credit evaluation complete for {customer.email}: "
            f"Internal={internal_score:.2f}, Bureau={bureau_score or 'N/A'}, "
            f"Final={final_score:.2f} ({decision})"
        )
        
        return {
            'final_score': final_score,
            'decision': decision,
            'internal_score': internal_score,
            'bureau_score': bureau_score,
            'bureau_name': bureau_name,
            'scoring_method': scoring_method,
            'negative_listings': negative_check.get('listings', []),
            'recommendation': recommendation,
            'breakdown': internal_result['breakdown'],
            'bureau_report': bureau_report.get('report_data', {})
        }


# Convenience function for easy import
def evaluate_credit(customer, loan_amount, loan_product, monthly_income, existing_obligations, employment_years=0):
    """Quick access to hybrid credit scoring"""
    service = HybridCreditScoringService()
    return service.evaluate_loan_application(
        customer, loan_amount, loan_product, monthly_income, existing_obligations, employment_years
    )
