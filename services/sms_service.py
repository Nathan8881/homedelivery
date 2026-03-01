"""
Mobile Message SMS Service - Integration Module
Sends delivery notifications via Mobile Message API

SMS Behavior:
  - TESTING MODE  → SMS abhi turant send hoti hai (real API call)
  - PRODUCTION MODE → SMS delivery date pe send hoti hai (date match check)
"""
import os
import logging
from datetime import date, datetime
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
        
        self.message_template = self.config.get(
            'message_template',
            'Hi {customer_name},\nYour Tommy Sugo order is now out for delivery and will be arriving at your location shortly.\n\nTo maintain the best quality, we kindly recommend bringing the products inside as soon as they arrive and placing them straight into the freezer.\n\nYou can track your delivery here:\n{tracking_link}\n\nThank you for choosing Tommy Sugo.\n\nWarm regards,\nNathan and the Tommy Sugo Team'
        )
        
        if self.enabled:
            if self.testing_mode:
                logger.info("[MOBILE MESSAGE] ✅ SMS service enabled - TESTING MODE (sends real SMS immediately)")
            else:
                logger.info("[MOBILE MESSAGE] ✅ SMS service enabled - PRODUCTION MODE (sends on delivery date)")
            logger.info(f"[MOBILE MESSAGE] Sender ID: {self.sender_id}")
        else:
            logger.warning("[MOBILE MESSAGE] ❌ SMS service disabled - missing credentials")
    
    def _format_phone_number(self, phone: str) -> str:
        """
        Format phone number for Australian mobile
        Handles formats: 0412345678, +61412345678, 61412345678
        """
        if not phone:
            return ""
        
        clean_phone = ''.join(filter(str.isdigit, phone.replace('+', '')))
        
        if clean_phone.startswith('61'):
            clean_phone = '0' + clean_phone[2:]
        
        if not clean_phone.startswith('0'):
            clean_phone = '0' + clean_phone
        
        return clean_phone
    
    def _get_first_name(self, full_name: str) -> str:
        """Extract first name from full name"""
        if not full_name or not full_name.strip():
            return "Customer"
        
        if isinstance(full_name, dict):
            first = full_name.get('first', '')
            if first:
                return first
            full_name = f"{full_name.get('first', '')} {full_name.get('last', '')}".strip()
        
        parts = str(full_name).split()
        return parts[0] if parts else "Customer"
    
    def _generate_tracking_link(self, consignment_number: str) -> str:
        """Generate tracking link from consignment number"""
        if not consignment_number:
            return "Tracking link not available"
        base_url = "https://mydel.info/Track/48497"
        return f"{base_url}/{consignment_number}"
    
    def _format_message(self, customer_name: str, consignment_number: str = "") -> str:
        """Format SMS message with customer name and tracking link"""
        first_name = self._get_first_name(customer_name)
        tracking_link = self._generate_tracking_link(consignment_number)
        
        message = self.message_template.replace('{customer_name}', first_name)
        message = message.replace('{tracking_link}', tracking_link)
        return message

    def _parse_delivery_date(self, delivery_date) -> Optional[date]:
        """
        Parse delivery date from various formats into a date object.
        
        Supports:
          - datetime / date objects
          - strings: 'YYYY-MM-DD', 'DD/MM/YYYY', 'DD-MM-YYYY', 'MM/DD/YYYY'
          - Jotform date dict: {'month': '03', 'day': '15', 'year': '2025'}
        
        Returns:
            date object or None if parsing fails
        """
        if delivery_date is None:
            return None
        
        # Already a date/datetime
        if isinstance(delivery_date, datetime):
            return delivery_date.date()
        if isinstance(delivery_date, date):
            return delivery_date
        
        # Jotform date dict e.g. {'month': '03', 'day': '15', 'year': '2025'}
        if isinstance(delivery_date, dict):
            try:
                return date(
                    int(delivery_date['year']),
                    int(delivery_date['month']),
                    int(delivery_date['day'])
                )
            except (KeyError, ValueError, TypeError) as e:
                logger.error(f"[MOBILE MESSAGE] ❌ Could not parse delivery date dict: {delivery_date} | {e}")
                return None
        
        # String formats
        if isinstance(delivery_date, str):
            formats = ['%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%m/%d/%Y']
            for fmt in formats:
                try:
                    return datetime.strptime(delivery_date.strip(), fmt).date()
                except ValueError:
                    continue
            logger.error(f"[MOBILE MESSAGE] ❌ Could not parse delivery date string: {delivery_date}")
            return None
        
        logger.error(f"[MOBILE MESSAGE] ❌ Unsupported delivery date type: {type(delivery_date)}")
        return None

    def _should_send_now(self, delivery_date=None) -> bool:
        """
        Decide whether to send the SMS right now based on mode.

        TESTING MODE  → Always send immediately (ignore delivery date)
        PRODUCTION MODE → Send only if today == delivery date
        
        Returns:
            True  → send SMS now
            False → skip (not the right time)
        """
        if self.testing_mode:
            # Testing: send immediately, no date check
            logger.info("[MOBILE MESSAGE] 🧪 TESTING MODE → Sending SMS immediately (real API call)")
            return True
        
        # Production: delivery date check
        parsed_date = self._parse_delivery_date(delivery_date)
        today = date.today()
        
        if parsed_date is None:
            logger.error(
                "[MOBILE MESSAGE] ❌ PRODUCTION MODE → delivery_date missing or invalid. "
                "Cannot determine send time. SMS skipped."
            )
            return False
        
        if parsed_date == today:
            logger.info(
                f"[MOBILE MESSAGE] 🚀 PRODUCTION MODE → Today ({today}) matches delivery date "
                f"({parsed_date}). Sending SMS now."
            )
            return True
        elif parsed_date > today:
            logger.info(
                f"[MOBILE MESSAGE] ⏳ PRODUCTION MODE → Delivery date is {parsed_date} "
                f"(today is {today}). SMS will be sent on delivery day. Skipping for now."
            )
            return False
        else:
            logger.warning(
                f"[MOBILE MESSAGE] ⚠️  PRODUCTION MODE → Delivery date {parsed_date} is in the PAST "
                f"(today is {today}). SMS skipped."
            )
            return False

    def send_delivery_notification(
        self, 
        customer_name: str, 
        customer_phone: str, 
        consignment_number: str = "",
        invoice_no: str = "",
        delivery_date=None          # ✅ NEW: pass customer's selected delivery date
    ) -> bool:
        """
        Send delivery notification SMS to customer with tracking link.

        Behavior:
          - TESTING MODE  → sends real SMS immediately
          - PRODUCTION MODE → sends SMS only on the customer's delivery date
        
        Args:
            customer_name:      Customer's name
            customer_phone:     Customer's phone number
            consignment_number: Consignment number from Transvirtual
            invoice_no:         Invoice number for logging
            delivery_date:      Customer's selected delivery date (date/datetime/str/dict)
        
        Returns:
            True if SMS sent successfully or scheduled for future, False on error
        """
        if not self.enabled:
            logger.warning("[MOBILE MESSAGE] ⏭️  SMS skipped - service disabled")
            return False
        
        if not customer_phone or not customer_phone.strip():
            logger.warning(f"[MOBILE MESSAGE] ⏭️  SMS skipped - no phone number for invoice {invoice_no}")
            return False
        
        # Date/mode check — should we send now?
        if not self._should_send_now(delivery_date):
            # In production, returning True means "order recorded, SMS will fire on delivery day"
            return not self.testing_mode   # False in testing (genuine skip), True in production (deferred)
        
        try:
            formatted_phone = self._format_phone_number(customer_phone)
            message = self._format_message(customer_name, consignment_number)
            
            logger.info("=" * 80)
            logger.info("[MOBILE MESSAGE] 📱 Attempting to send SMS...")
            logger.info(f"  Invoice:         {invoice_no}")
            logger.info(f"  Customer:        {customer_name}")
            logger.info(f"  Original Phone:  {customer_phone}")
            logger.info(f"  Formatted Phone: {formatted_phone}")
            logger.info(f"  Consignment:     {consignment_number}")
            logger.info(f"  Delivery Date:   {delivery_date}")
            logger.info(f"  Tracking Link:   {self._generate_tracking_link(consignment_number)}")
            logger.info(f"  Message Length:  {len(message)} chars")
            logger.info(f"  Mode:            {'TESTING (sending now)' if self.testing_mode else 'PRODUCTION (delivery date matched)'}")
            logger.info("-" * 80)
            logger.info(f"  Message Preview:\n{message}")
            logger.info("-" * 80)
            logger.info("[MOBILE MESSAGE] 🚀 Sending to API...")
            
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
            logger.error(f"  Phone:    {customer_phone}")
            logger.error(f"  Error:    {e}")
            logger.error("=" * 80)
            return False
    
    def _send_sms_api(self, phone: str, message: str, invoice_no: str = "") -> bool:
        """Send SMS via Mobile Message API"""
        try:
            payload = {
                "enable_unicode": True,
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
            logger.info(f"  URL:    {self.api_url}")
            logger.info(f"  Sender: {self.sender_id}")
            
            response = requests.post(
                self.api_url,
                auth=HTTPBasicAuth(self.username, self.password),
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=30
            )
            
            logger.info(f"  HTTP Status: {response.status_code}")
            
            if response.status_code in [200, 201]:
                result = response.json()
                logger.info("[MOBILE MESSAGE] ✅ API Response Success")
                
                if result.get('status') == 'complete':
                    results = result.get('results', [])
                    if results and results[0].get('status') == 'success':
                        message_id = results[0].get('message_id', 'N/A')
                        cost      = results[0].get('cost', 'N/A')
                        encoding  = results[0].get('encoding', 'N/A')
                        logger.info(f"  Message ID: {message_id}")
                        logger.info(f"  Cost:       {cost} credits")
                        logger.info(f"  Encoding:   {encoding}")
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
                logger.error(f"  Response:    {response.text}")
                return False
                
        except requests.exceptions.Timeout:
            logger.error("[MOBILE MESSAGE] ❌ TIMEOUT ERROR - request timed out after 30s")
            return False
        except requests.exceptions.HTTPError as e:
            logger.error(f"[MOBILE MESSAGE] ❌ HTTP ERROR: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"  Response: {e.response.text}")
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"[MOBILE MESSAGE] ❌ REQUEST ERROR: {e}")
            return False
        except Exception as e:
            logger.error(f"[MOBILE MESSAGE] ❌ UNEXPECTED ERROR: {e}")
            return False