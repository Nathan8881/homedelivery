"""
Mobile Message SMS Service - Integration Module
Sends delivery notifications via Mobile Message API
"""
import os
import logging
from typing import Dict, Optional
import requests
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)


class MobileMessageService:
    """Mobile Message SMS Service for delivery notifications"""
    
    def __init__(self, sms_config: Dict = None):
        """
        Initialize Mobile Message service
        
        Args:
            sms_config: SMS configuration from home_delivery.json
        """
        self.config = sms_config or {}
        
        # Get credentials from environment or config
        self.username = os.getenv('MOBILE_MESSAGE_USERNAME', self.config.get('username', ''))
        self.password = os.getenv('MOBILE_MESSAGE_PASSWORD', self.config.get('password', ''))
        self.sender_id = os.getenv('MOBILE_MESSAGE_SENDER_ID', self.config.get('sender_id', ''))
        
        # Configuration
        self.enabled = self.config.get('enabled', False) and all([self.username, self.password, self.sender_id])
        self.testing_mode = self.config.get('testing_mode', False)
        self.api_url = "https://api.mobilemessage.com.au/v1/messages"
        
        # Message template
        self.message_template = self.config.get(
            'message_template',
            'Hi {customer_name}, your Tommy Sugo order is out for delivery and will arrive shortly. Thank you!'
        )
        
        if self.enabled:
            mode = "TESTING MODE" if self.testing_mode else "PRODUCTION MODE"
            logger.info(f"[MOBILE MESSAGE] ✅ SMS service enabled - {mode}")
            logger.info(f"[MOBILE MESSAGE] Sender ID: {self.sender_id}")
        else:
            logger.warning("[MOBILE MESSAGE] ❌ SMS service disabled - missing credentials")
    
    def _format_phone_number(self, phone: str) -> str:
        """
        Format phone number for Australian mobile
        Handles formats: 0412345678, +61412345678, 61412345678
        
        Args:
            phone: Phone number in any format
            
        Returns:
            Formatted phone number (Australian local format: 04xxxxxxxx)
        """
        if not phone:
            return ""
        
        # Clean the phone number
        clean_phone = ''.join(filter(str.isdigit, phone.replace('+', '')))
        
        # Convert international format to local
        if clean_phone.startswith('61'):
            clean_phone = '0' + clean_phone[2:]
        
        # Ensure it starts with 0
        if not clean_phone.startswith('0'):
            clean_phone = '0' + clean_phone
        
        return clean_phone
    
    def _get_first_name(self, full_name: str) -> str:
        """
        Extract first name from full name
        
        Args:
            full_name: Customer's full name
            
        Returns:
            First name only
        """
        if not full_name or not full_name.strip():
            return "Customer"
        
        # Handle name object from Jotform
        if isinstance(full_name, dict):
            first = full_name.get('first', '')
            if first:
                return first
            # Fallback to full name if available
            full_name = f"{full_name.get('first', '')} {full_name.get('last', '')}".strip()
        
        # Split and get first name
        parts = str(full_name).split()
        return parts[0] if parts else "Customer"
    
    def _format_message(self, customer_name: str) -> str:
        """
        Format SMS message with customer name
        
        Args:
            customer_name: Customer's name
            
        Returns:
            Formatted message
        """
        first_name = self._get_first_name(customer_name)
        return self.message_template.replace('{customer_name}', first_name)
    
    def send_delivery_notification(
        self, 
        customer_name: str, 
        customer_phone: str, 
        invoice_no: str = ""
    ) -> bool:
        """
        Send delivery notification SMS to customer
        
        Args:
            customer_name: Customer's name
            customer_phone: Customer's phone number
            invoice_no: Invoice number for logging
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            logger.warning("[MOBILE MESSAGE] ⏭️  SMS skipped - service disabled")
            return False
        
        if not customer_phone or not customer_phone.strip():
            logger.warning(f"[MOBILE MESSAGE] ⏭️  SMS skipped - no phone number for invoice {invoice_no}")
            return False
        
        try:
            formatted_phone = self._format_phone_number(customer_phone)
            message = self._format_message(customer_name)
            
            logger.info("=" * 80)
            logger.info("[MOBILE MESSAGE] 📱 Attempting to send SMS...")
            logger.info(f"  Invoice: {invoice_no}")
            logger.info(f"  Customer: {customer_name}")
            logger.info(f"  Original Phone: {customer_phone}")
            logger.info(f"  Formatted Phone: {formatted_phone}")
            logger.info(f"  Message: {message}")
            logger.info(f"  Message Length: {len(message)} chars")
            logger.info(f"  Mode: {'TESTING' if self.testing_mode else 'PRODUCTION'}")
            
            if self.testing_mode:
                logger.info("-" * 80)
                logger.info("[MOBILE MESSAGE] 🧪 TESTING MODE - SMS NOT SENT")
                logger.info("[MOBILE MESSAGE] ✅ Would have sent successfully (simulated)")
                logger.info("=" * 80)
                return True
            
            # Production mode - send via API
            logger.info("-" * 80)
            logger.info("[MOBILE MESSAGE] 🚀 PRODUCTION MODE - Sending to API...")
            result = self._send_sms_api(formatted_phone, message, invoice_no)
            
            if result:
                logger.info("[MOBILE MESSAGE] ✅ SMS SENT SUCCESSFULLY")
            else:
                logger.error("[MOBILE MESSAGE] ❌ SMS SEND FAILED")
            
            logger.info("=" * 80)
            return result
            
        except Exception as e:
            logger.error("=" * 80)
            logger.error(f"[MOBILE MESSAGE] ❌ SMS ERROR for invoice {invoice_no}")
            logger.error(f"  Customer: {customer_name}")
            logger.error(f"  Phone: {customer_phone}")
            logger.error(f"  Error: {e}")
            logger.error("=" * 80)
            return False
    
    def _send_sms_api(self, phone: str, message: str, invoice_no: str = "") -> bool:
        """
        Send SMS via Mobile Message API
        
        Args:
            phone: Formatted phone number
            message: Message text
            invoice_no: Invoice number for reference
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Prepare API payload
            payload = {
                "enable_unicode": True,  # Support emojis and special characters
                "messages": [
                    {
                        "to": phone,
                        "message": message,
                        "sender": self.sender_id,
                        "custom_ref": f"invoice_{invoice_no}" if invoice_no else None
                    }
                ]
            }
            
            # Remove None values
            payload["messages"][0] = {k: v for k, v in payload["messages"][0].items() if v is not None}
            
            logger.info("[MOBILE MESSAGE] 📡 Making API request...")
            logger.info(f"  URL: {self.api_url}")
            logger.info(f"  Sender: {self.sender_id}")
            
            # Make API request
            response = requests.post(
                self.api_url,
                auth=HTTPBasicAuth(self.username, self.password),
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=30
            )
            
            logger.info(f"  HTTP Status: {response.status_code}")
            
            # Check response
            if response.status_code in [200, 201]:
                result = response.json()
                logger.info("[MOBILE MESSAGE] ✅ API Response Success")
                
                # Check if message was actually sent
                if result.get('status') == 'complete':
                    results = result.get('results', [])
                    if results and results[0].get('status') == 'success':
                        message_id = results[0].get('message_id', 'N/A')
                        cost = results[0].get('cost', 'N/A')
                        encoding = results[0].get('encoding', 'N/A')
                        
                        logger.info(f"  Message ID: {message_id}")
                        logger.info(f"  Cost: {cost} credits")
                        logger.info(f"  Encoding: {encoding}")
                        return True
                    else:
                        error_msg = results[0].get('status', 'unknown error') if results else 'no results'
                        logger.error(f"[MOBILE MESSAGE] ❌ Message failed: {error_msg}")
                        return False
                else:
                    logger.error(f"[MOBILE MESSAGE] ❌ Batch status: {result.get('status', 'unknown')}")
                    return False
            else:
                logger.error("[MOBILE MESSAGE] ❌ HTTP ERROR")
                logger.error(f"  Status Code: {response.status_code}")
                logger.error(f"  Response: {response.text}")
                return False
                
        except requests.exceptions.Timeout:
            logger.error("[MOBILE MESSAGE] ❌ TIMEOUT ERROR")
            logger.error("  API request timed out after 30 seconds")
            return False
            
        except requests.exceptions.HTTPError as e:
            logger.error("[MOBILE MESSAGE] ❌ HTTP ERROR")
            logger.error(f"  Error: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"  Response: {e.response.text}")
            return False
            
        except requests.exceptions.RequestException as e:
            logger.error("[MOBILE MESSAGE] ❌ REQUEST ERROR")
            logger.error(f"  Error: {e}")
            return False
            
        except Exception as e:
            logger.error("[MOBILE MESSAGE] ❌ UNEXPECTED ERROR")
            logger.error(f"  Error: {e}")
            return False