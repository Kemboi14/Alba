"""
Customer Portal Forms
Forms for customer registration, loan application, and document upload
Implements SRS Section 3.5: Customer Portal
"""
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.core.validators import MinValueValidator, RegexValidator
from decimal import Decimal
from apps.core.models import User
from apps.loans.models import LoanApplication, LoanProduct, Customer


class CustomerRegistrationForm(UserCreationForm):
    """
    Customer registration form
    Creates customer account with email verification
    """
    INPUT_CLASS = 'w-full px-4 py-3 border-2 border-gray-200 rounded-lg focus:border-alba-orange focus:ring-2 focus:ring-alba-orange focus:ring-opacity-20 transition-all duration-200'
    
    first_name = forms.CharField(
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={
            'class': INPUT_CLASS,
            'placeholder': 'John'
        })
    )
    
    last_name = forms.CharField(
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={
            'class': INPUT_CLASS,
            'placeholder': 'Doe'
        })
    )
    
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': INPUT_CLASS,
            'placeholder': 'john.doe@example.com'
        })
    )
    
    phone_number = forms.CharField(
        max_length=20,
        required=True,
        validators=[RegexValidator(r'^\+?254\d{9}$', 'Enter a valid Kenyan phone number (e.g., +254712345678)')],
        widget=forms.TextInput(attrs={
            'class': INPUT_CLASS,
            'placeholder': '+254712345678'
        })
    )
    
    national_id = forms.CharField(
        max_length=20,
        required=True,
        validators=[RegexValidator(r'^\d{7,8}$', 'Enter a valid Kenyan ID number (7-8 digits)')],
        widget=forms.TextInput(attrs={
            'class': INPUT_CLASS,
            'placeholder': '12345678'
        })
    )
    
    date_of_birth = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': INPUT_CLASS,
            'max': '2008-12-31'  # Must be 18+ years old
        })
    )
    
    address = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': INPUT_CLASS,
            'placeholder': 'Residential Address',
            'rows': 3
        })
    )
    
    password1 = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={
            'class': INPUT_CLASS,
            'placeholder': 'Minimum 8 characters'
        })
    )
    
    password2 = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput(attrs={
            'class': INPUT_CLASS,
            'placeholder': 'Re-enter password'
        })
    )
    
    terms_accepted = forms.BooleanField(
        required=True,
        label='I accept the Terms and Conditions',
        widget=forms.CheckboxInput(attrs={
            'class': 'w-5 h-5 text-alba-orange border-gray-300 rounded focus:ring-alba-orange'
        })
    )
    
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'phone_number', 'national_id', 
                  'date_of_birth', 'address', 'password1', 'password2']
    
    def clean_email(self):
        """Ensure email is unique"""
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('This email address is already registered.')
        return email
    
    def clean_national_id(self):
        """Ensure national ID is unique"""
        national_id = self.cleaned_data.get('national_id')
        if User.objects.filter(national_id=national_id).exists():
            raise forms.ValidationError('This National ID is already registered.')
        return national_id


class CustomerLoanApplicationForm(forms.ModelForm):
    """
    Loan application form for customers
    Includes credit scoring fields
    """
    # Additional fields for credit scoring (not saved to model)
    monthly_income = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        widget=forms.NumberInput(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-alba-orange focus:border-transparent',
            'placeholder': 'e.g., 50000',
            'step': '0.01'
        }),
        help_text='Your total monthly income (gross)'
    )
    
    existing_obligations = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
        initial=Decimal('0'),
        widget=forms.NumberInput(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-alba-orange focus:border-transparent',
            'placeholder': 'e.g., 15000',
            'step': '0.01'
        }),
        help_text='Total monthly loan repayments and obligations'
    )
    
    employment_years = forms.IntegerField(
        validators=[MinValueValidator(0)],
        initial=0,
        widget=forms.NumberInput(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-alba-orange focus:border-transparent',
            'placeholder': 'e.g., 3',
            'min': '0'
        }),
        help_text='Years with current employer'
    )
    
    class Meta:
        model = LoanApplication
        fields = [
            'loan_product', 'requested_amount', 'purpose', 'loan_term_months', 
            'repayment_frequency'
        ]
        widgets = {
            'loan_product': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-alba-orange focus:border-transparent'
            }),
            'requested_amount': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-alba-orange focus:border-transparent',
                'placeholder': 'e.g., 100000',
                'step': '0.01'
            }),
            'purpose': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-alba-orange focus:border-transparent',
                'placeholder': 'Describe how you will use the loan',
                'rows': 4
            }),
            'loan_term_months': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-alba-orange focus:border-transparent',
                'placeholder': 'Number of months',
                'min': '1'
            }),
            'repayment_frequency': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-alba-orange focus:border-transparent'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show active loan products
        self.fields['loan_product'].queryset = LoanProduct.objects.filter(is_active=True)


class DocumentUploadForm(forms.Form):
    """Form for uploading loan application documents"""
    DOCUMENT_TYPE_CHOICES = [
        ('NATIONAL_ID', 'National ID Copy'),
        ('PAYSLIP', 'Payslip (Last 3 months)'),
        ('BANK_STATEMENT', 'Bank Statement (Last 6 months)'),
        ('PASSPORT_PHOTO', 'Passport Photo'),
        ('KRA_PIN', 'KRA PIN Certificate'),
        ('BUSINESS_PERMIT', 'Business Permit (for business loans)'),
        ('OTHER', 'Other Supporting Document'),
    ]
    
    document_type = forms.ChoiceField(
        choices=DOCUMENT_TYPE_CHOICES,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-alba-orange focus:border-transparent'
        })
    )
    
    documents = forms.FileField(
        widget=forms.FileInput(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-alba-orange focus:border-transparent',
            'accept': '.pdf,.jpg,.jpeg,.png'
        }),
        help_text='Accepted formats: PDF, JPG, PNG (Max 5MB per file)'
    )
    
    def clean_documents(self):
        """Validate file upload"""
        file = self.cleaned_data.get('documents')
        
        if not file:
            raise forms.ValidationError('Please select a file to upload.')
        
        max_size = 5 * 1024 * 1024  # 5MB
        allowed_extensions = ['.pdf', '.jpg', '.jpeg', '.png']
        
        # Check file size
        if file.size > max_size:
            raise forms.ValidationError(
                f'File {file.name} exceeds maximum size of 5MB.'
            )
        
        # Check file extension
        file_ext = '.' + file.name.split('.')[-1].lower()
        if file_ext not in allowed_extensions:
            raise forms.ValidationError(
                f'File {file.name} has unsupported format. '
                f'Allowed: PDF, JPG, PNG'
            )
        
        return file

