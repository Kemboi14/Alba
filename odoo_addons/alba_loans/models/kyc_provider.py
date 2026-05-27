# -*- coding: utf-8 -*-
import json
import logging
import requests
from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class AlbaKYCProvider(models.Model):
    """
    Automated Identity Verification API Provider Configuration.
    Supports pluggable backends (e.g., Sandbox, Smile Identity, Metamap).
    """
    _name = "alba.kyc.provider"
    _description = "Alba KYC / Identity Provider"
    _inherit = ["mail.thread"]
    _order = "sequence asc, id desc"

    name = fields.Char(string="Provider Name", required=True)
    provider_type = fields.Selection([
        ('sandbox', 'Sandbox / Mock (Testing)'),
        ('smile_identity', 'Smile Identity'),
        ('metamap', 'Metamap'),
        ('iprs', 'Kenya IPRS (Direct)'),
        ('custom', 'Custom Provider'),
    ], string="Provider Backend", required=True, default='sandbox')
    
    is_active = fields.Boolean(string="Active Provider", default=False, 
                               help="Only one provider should be active at a time.")
    sequence = fields.Integer(default=10)
    
    api_key = fields.Char(string="API Key", groups="alba_loans.group_director")
    api_secret = fields.Char(string="API Secret", groups="alba_loans.group_director")
    api_base_url = fields.Char(string="API Base URL", help="e.g., https://api.smileidentity.com/v1")
    
    # Custom provider configuration
    auth_method = fields.Selection([
        ('api_key', 'API Key'),
        ('api_key_secret', 'API Key + Secret'),
        ('bearer_token', 'Bearer Token'),
        ('basic_auth', 'Basic Auth'),
        ('custom_header', 'Custom Header'),
        ('none', 'No Authentication'),
    ], string="Authentication Method", default='api_key_secret')
    
    custom_headers = fields.Text(string="Custom Headers", 
                             help="JSON format headers for custom authentication, e.g., {'X-API-Version': 'v1'}")
    
    verify_endpoint = fields.Char(string="Verification Endpoint", 
                             help="API endpoint for identity verification, e.g., /verify")
    
    request_format = fields.Selection([
        ('json', 'JSON'),
        ('form', 'Form Data'),
        ('xml', 'XML'),
    ], string="Request Format", default='json')
    
    success_response_path = fields.Char(string="Success Response Path", 
                                   help="JSON path to check for success, e.g., result.status or verified")
    
    response_mapping = fields.Text(string="Response Mapping", 
                               help="Map API response to our fields. JSON format: {'status': 'result.verification_status', 'confidence': 'result.score'}")
    
    @api.constrains('is_active')
    def _check_single_active(self):
        for rec in self:
            if rec.is_active:
                others = self.search([('id', '!=', rec.id), ('is_active', '=', True)])
                if others:
                    others.write({'is_active': False})

    def action_test_connection(self):
        self.ensure_one()
        if self.provider_type == 'sandbox':
            self.message_post(body=_("Sandbox connection test successful!"))
            return True
        elif self.provider_type == 'custom':
            return self._test_custom_connection()
        else:
            raise UserError(_("Connection testing for %s is not yet implemented.") % self.provider_type)

    def verify_identity(self, id_number, first_name=None, last_name=None, document_image=None):
        """
        Verify given identity using active backend.
        Returns a dictionary:
        {
            'status': 'verified' | 'rejected' | 'manual_review',
            'confidence_score': 0-100,
            'provider_reference': 'txn_12345',
            'notes': 'Matched against IPRS successfully.'
        }
        """
        self.ensure_one()
        
        if self.provider_type == 'sandbox':
            return self._verify_sandbox(id_number, first_name, last_name)
        elif self.provider_type == 'custom':
            return self._verify_custom(id_number, first_name, last_name, document_image)
        else:
            # Placeholder for real API implementations
            return {
                'status': 'manual_review',
                'confidence_score': 0,
                'provider_reference': '',
                'notes': _("Provider backend %s not fully implemented. Please verify manually.") % self.provider_type
            }

    def _test_custom_connection(self):
        """
        Test connection to custom KYC provider API.
        """
        if not self.api_base_url:
            raise UserError(_("API Base URL is required for testing connection."))
        
        try:
            # Start with base headers
            headers = {'Content-Type': 'application/json'}
            
            # Add custom headers FIRST (they should override defaults)
            if self.custom_headers:
                try:
                    custom_headers = json.loads(self.custom_headers)
                    headers.update(custom_headers)
                    _logger.info("Applied custom headers for KYC provider %s: %s", self.name, list(custom_headers.keys()))
                except json.JSONDecodeError:
                    _logger.warning("Invalid custom headers format for KYC provider %s", self.name)
            
            # Only add default authentication if no custom Authorization header is provided
            if 'Authorization' not in headers and 'X-API-Key' not in headers:
                if self.auth_method == 'api_key' and self.api_key:
                    headers['X-API-Key'] = self.api_key
                elif self.auth_method == 'api_key_secret' and self.api_key:
                    headers['X-API-Key'] = self.api_key
                    if self.api_secret:
                        headers['X-API-Secret'] = self.api_secret
                elif self.auth_method == 'bearer_token' and self.api_key:
                    headers['Authorization'] = f'Bearer {self.api_key}'
                elif self.auth_method == 'basic_auth' and self.api_key and self.api_secret:
                    import base64
                    credentials = f"{self.api_key}:{self.api_secret}"
                    encoded_credentials = base64.b64encode(credentials.encode()).decode()
                    headers['Authorization'] = f'Basic {encoded_credentials}'
                elif self.auth_method == 'custom_header' and self.api_key:
                    # For custom_header method, use api_key as the value
                    headers['X-API-Key'] = self.api_key
            elif 'Authorization' in headers:
                _logger.info("Using custom Authorization header for KYC provider %s", self.name)
            elif 'X-API-Key' in headers:
                _logger.info("Using custom X-API-Key header for KYC provider %s", self.name)
            
            # Test with a simple health check or ping endpoint
            test_url = self.api_base_url.rstrip('/')
            if self.verify_endpoint and self.verify_endpoint != '/':
                # Try the actual verification endpoint with test data
                test_url = f"{self.api_base_url.rstrip('/')}/{self.verify_endpoint.lstrip('/')}"
                test_data = {
                    'id_number': 'TEST123',
                    'first_name': 'Test',
                    'last_name': 'User'
                }
                response = requests.post(test_url, json=test_data, headers=headers, timeout=10)
            else:
                # Try a simple GET request to base URL
                response = requests.get(test_url, headers=headers, timeout=10)
            
            response.raise_for_status()
            
            # If we get here, connection is successful
            self.message_post(body=_("Custom provider connection test successful! URL: %s") % test_url)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Connection Test Successful'),
                    'message': _('Successfully connected to %s') % self.name,
                    'type': 'success',
                    'sticky': False,
                }
            }
            
        except requests.exceptions.RequestException as e:
            error_msg = _("Connection test failed: %s") % str(e)
            self.message_post(body=error_msg)
            raise UserError(error_msg)
        except Exception as e:
            error_msg = _("Connection test error: %s") % str(e)
            self.message_post(body=error_msg)
            raise UserError(error_msg)

    def _verify_sandbox(self, id_number, first_name, last_name):
        """
        Sandbox logic:
        - If ID starts with '99', simulate a Fraud / Rejected response.
        - If ID starts with '88', simulate a 'Needs Manual Review' response.
        - Otherwise, simulate a successful verification.
        """
        if not id_number:
            return {'status': 'rejected', 'confidence_score': 0, 'notes': 'ID Number is missing.'}
            
        id_str = str(id_number).strip()
        
        if id_str.startswith('99'):
            return {
                'status': 'rejected',
                'confidence_score': 12,
                'provider_reference': f'SANDBOX-REJ-{id_str}',
                'notes': 'Sandbox: ID number flagged on fraud watchlist.'
            }
        elif id_str.startswith('88'):
            return {
                'status': 'manual_review',
                'confidence_score': 65,
                'provider_reference': f'SANDBOX-REV-{id_str}',
                'notes': 'Sandbox: Document blurry or name mismatch. Manual review required.'
            }
        else:
            return {
                'status': 'verified',
                'confidence_score': 98,
                'provider_reference': f'SANDBOX-VER-{id_str}',
                'notes': f'Sandbox: ID {id_str} verified successfully against national registry.'
            }

    def _verify_custom(self, id_number, first_name=None, last_name=None, document_image=None):
        """
        Verify identity using custom API provider.
        """
        if not self.api_base_url or not self.verify_endpoint:
            return {
                'status': 'manual_review',
                'confidence_score': 0,
                'provider_reference': '',
                'notes': 'Custom provider not properly configured. Missing API URL or endpoint.'
            }
        
        try:
            # Start with base headers
            headers = {'Content-Type': 'application/json'}
            
            # Add custom headers FIRST (they should override defaults)
            if self.custom_headers:
                try:
                    custom_headers = json.loads(self.custom_headers)
                    headers.update(custom_headers)
                    _logger.info("Applied custom headers for KYC provider %s: %s", self.name, list(custom_headers.keys()))
                except json.JSONDecodeError:
                    _logger.warning("Invalid custom headers format for KYC provider %s", self.name)
            
            # Only add default authentication if no custom Authorization header is provided
            if 'Authorization' not in headers and 'X-API-Key' not in headers:
                if self.auth_method == 'api_key' and self.api_key:
                    headers['X-API-Key'] = self.api_key
                elif self.auth_method == 'api_key_secret' and self.api_key:
                    headers['X-API-Key'] = self.api_key
                    if self.api_secret:
                        headers['X-API-Secret'] = self.api_secret
                elif self.auth_method == 'bearer_token' and self.api_key:
                    headers['Authorization'] = f'Bearer {self.api_key}'
                elif self.auth_method == 'basic_auth' and self.api_key and self.api_secret:
                    import base64
                    credentials = f"{self.api_key}:{self.api_secret}"
                    encoded_credentials = base64.b64encode(credentials.encode()).decode()
                    headers['Authorization'] = f'Basic {encoded_credentials}'
                elif self.auth_method == 'custom_header' and self.api_key:
                    # For custom_header method, use api_key as the value
                    headers['X-API-Key'] = self.api_key
            elif 'Authorization' in headers:
                _logger.info("Using custom Authorization header for KYC provider %s", self.name)
            elif 'X-API-Key' in headers:
                _logger.info("Using custom X-API-Key header for KYC provider %s", self.name)
            
            # Prepare request data
            data = {
                'id_number': id_number,
                'first_name': first_name,
                'last_name': last_name,
            }
            
            # Make API request
            url = f"{self.api_base_url.rstrip('/')}/{self.verify_endpoint.lstrip('/')}"
            response = requests.post(url, json=data, headers=headers, timeout=30)
            response.raise_for_status()
            
            # Parse response
            result = response.json()
            
            # Map response using custom mapping if provided
            if self.response_mapping:
                try:
                    mapping = json.loads(self.response_mapping)
                    mapped_result = {}
                    
                    for field, path in mapping.items():
                        value = result
                        for key in path.split('.'):
                            if isinstance(value, dict) and key in value:
                                value = value[key]
                            else:
                                value = None
                                break
                        mapped_result[field] = value
                    
                    result = mapped_result
                except (json.JSONDecodeError, Exception):
                    _logger.warning("Invalid response mapping for KYC provider %s", self.name)
            
            # Check success status
            status = 'manual_review'
            confidence_score = 0
            notes = 'Verification completed with custom provider.'
            
            if self.success_response_path:
                try:
                    success_value = result
                    for key in self.success_response_path.split('.'):
                        if isinstance(success_value, dict) and key in success_value:
                            success_value = success_value[key]
                        else:
                            break
                    
                    if success_value in [True, 'success', 'verified', 'approved']:
                        status = 'verified'
                    elif success_value in [False, 'failed', 'rejected', 'declined']:
                        status = 'rejected'
                except Exception:
                    pass
            
            # Extract confidence score if available
            if 'confidence' in result:
                confidence_score = result['confidence']
            elif 'score' in result:
                confidence_score = result['score']
            
            return {
                'status': status,
                'confidence_score': confidence_score,
                'provider_reference': result.get('reference', result.get('id', '')),
                'notes': result.get('message', notes)
            }
            
        except requests.exceptions.RequestException as e:
            _logger.error("KYC API request failed for provider %s: %s", self.name, str(e))
            return {
                'status': 'manual_review',
                'confidence_score': 0,
                'provider_reference': '',
                'notes': f'API request failed: {str(e)}'
            }
        except Exception as e:
            _logger.error("KYC verification failed for provider %s: %s", self.name, str(e))
            return {
                'status': 'manual_review',
                'confidence_score': 0,
                'provider_reference': '',
                'notes': f'Verification failed: {str(e)}'
            }
