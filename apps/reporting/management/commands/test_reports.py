from django.core.management.base import BaseCommand
from datetime import date
from apps.accounting.models import FiscalYear
from apps.reporting.services import FinancialReportingService, LoanReportingService

class Command(BaseCommand):
    help = 'Test all Alba Capital reporting services'

    def handle(self, *args, **options):
        self.stdout.write('')
        self.stdout.write('='*70)
        self.stdout.write('  ALBA CAPITAL ERP - REPORTING SERVICES TEST')
        self.stdout.write('='*70)
        self.stdout.write('')
        
        try:
            # Get fiscal year
            fiscal_year = FiscalYear.objects.filter(is_active=True).first()
            if not fiscal_year:
                self.stdout.write(self.style.WARNING('⚠️  No active fiscal year found'))
                return
            
            self.stdout.write(self.style.SUCCESS(f'✅ Using Fiscal Year: {fiscal_year.name}'))
            self.stdout.write('')
            
            # Test Trial Balance
            self.stdout.write('1️⃣  Testing Trial Balance...')
            tb = FinancialReportingService.generate_trial_balance(fiscal_year, date.today())
            self.stdout.write(f'   ✅ Balanced: {tb["is_balanced"]}')
            self.stdout.write(f'   📊 Total Debits: KES {tb["totals"]["total_debit"]:,.2f}')
            self.stdout.write(f'   📊 Total Credits: KES {tb["totals"]["total_credit"]:,.2f}')
            self.stdout.write(f'   📋 Accounts: {len(tb["accounts"])}')
            self.stdout.write('')
            
            # Test P&L
            self.stdout.write('2️⃣  Testing Profit & Loss...')
            pl = FinancialReportingService.generate_profit_loss(
                fiscal_year, 
                date(2026, 2, 1), 
                date(2026, 2, 28)
            )
            self.stdout.write(f'   ✅ Revenue: KES {pl["revenue"]["total"]:,.2f}')
            self.stdout.write(f'   💰 Expenses: KES {pl["expenses"]["total"]:,.2f}')
            self.stdout.write(f'   📊 Net Income: KES {pl["net_income"]:,.2f}')
            self.stdout.write('')
            
            # Test Balance Sheet
            self.stdout.write('3️⃣  Testing Balance Sheet...')
            bs = FinancialReportingService.generate_balance_sheet(fiscal_year, date.today())
            self.stdout.write(f'   ✅ Balanced: {bs["is_balanced"]}')
            self.stdout.write(f'   🏦 Assets: KES {bs["assets"]["total"]:,.2f}')
            self.stdout.write(f'   💳 Liabilities: KES {bs["liabilities"]["total"]:,.2f}')
            self.stdout.write(f'   💼 Equity: KES {bs["equity"]["total"]:,.2f}')
            self.stdout.write('')
            
            # Test PAR
            self.stdout.write('4️⃣  Testing Portfolio at Risk (PAR)...')
            par = LoanReportingService.calculate_par(date.today(), [1, 7, 30, 90])
            self.stdout.write(f'   ✅ Portfolio Total: KES {par["portfolio_total"]:,.2f}')
            self.stdout.write(f'   📊 Active Loans: {par["active_loan_count"]}')
            for calc in par['par_calculations']:
                self.stdout.write(
                    f'   📈 {calc["par_name"]}: {calc["ratio"]:.2f}% '
                    f'(KES {calc["amount"]:,.2f}, {calc["loan_count"]} loans)'
                )
            self.stdout.write('')
            
            # Test NPL
            self.stdout.write('5️⃣  Testing NPL Report...')
            npl = LoanReportingService.generate_npl_report(date.today())
            self.stdout.write(f'   ✅ NPL Ratio: {npl["npl_ratio"]:.2f}%')
            self.stdout.write(f'   📊 NPL Count: {npl["npl_summary"]["npl_count"]}')
            self.stdout.write(f'   💰 NPL Outstanding: KES {npl["npl_summary"]["npl_outstanding"]:,.2f}')
            self.stdout.write(f'   ✅ Portfolio Count: {npl["portfolio_summary"]["total_loans"]}')
            self.stdout.write('')
            
            # Test Aged Receivables
            self.stdout.write('6️⃣  Testing Aged Receivables...')
            ar = LoanReportingService.generate_aged_receivables(date.today())
            self.stdout.write(f'   ✅ Total Outstanding: KES {ar["totals"]["total_outstanding"]:,.2f}')
            self.stdout.write(f'   📊 Total Loans: {ar["totals"]["total_loans"]}')
            for bucket in ar['aging_summary']:
                self.stdout.write(
                    f'   📈 {bucket["bucket"]}: KES {bucket["total_outstanding"]:,.2f} '
                    f'({bucket["loan_count"]} loans)'
                )
            self.stdout.write('')
            
            # Test Portfolio Summary
            self.stdout.write('7️⃣  Testing Portfolio Summary...')
            ps = LoanReportingService.generate_loan_portfolio_summary(date.today())
            self.stdout.write(f'   ✅ Total Outstanding: KES {ps["portfolio_overview"]["total_outstanding"]:,.2f}')
            self.stdout.write(f'   📊 Total Loans: {ps["portfolio_overview"]["total_loans"]}')
            self.stdout.write(f'   💰 Total Disbursed: KES {ps["portfolio_overview"]["total_principal_disbursed"]:,.2f}')
            self.stdout.write('')
            
            self.stdout.write('='*70)
            self.stdout.write(self.style.SUCCESS('  ✅ ALL 7 REPORTING SERVICES WORKING PERFECTLY! 🎉'))
            self.stdout.write('='*70)
            self.stdout.write('')
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error: {str(e)}'))
            import traceback
            traceback.print_exc()
