"""
Mobile Message SMS Service - Integration Module
Sends delivery notifications via Mobile Message API

SMS Behavior:
  - TESTING MODE  → SMS abhi turant send hoti hai (real API call)
  - PRODUCTION MODE → SMS delivery date pe send hoti hai (Perth date match check)

FIXES:
  v14.5 - _should_send_now() mein Perth timezone use karo (pehle server local time tha)
         - TransVirtual webhook se directly call hota hai (InTransit / Delivered)
"""
import os
import logging
import pytz
from datetime import date, datetime
from typing import Dict, Optional
import requests
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)

# Perth timezone — date comparison ke liye
PERTH_TZ = pytz.timezone("Australia/Perth")


class MobileMessageService:
    """Mobile Message SMS Service for delivery notifications"""

    def __init__(self, sms_config: Dict = None):
        self.config = sms_config or {}

        # Credentials — env variables priority, phir config
        self.username  = os.getenv('MOBILE_MESSAGE_USERNAME',  self.config.get('username', ''))
        self.password  = os.getenv('MOBILE_MESSAGE_PASSWORD',  self.config.get('password', ''))
        self.sender_id = os.getenv('MOBILE_MESSAGE_SENDER_ID', self.config.get('sender_id', ''))

        self.enabled      = self.config.get('enabled', False) and all([self.username, self.password, self.sender_id])
        self.testing_mode = self.config.get('testing_mode', False)
        self.api_url      = "https://api.mobilemessage.com.au/v1/messages"

        self.message_template = self.config.get(
            'message_template',
            'Hi {customer_name},\nYour Tommy Sugo order is now out for delivery and will be arriving at your location shortly.\n\n'
            'To maintain the best quality, we kindly recommend bringing the products inside as soon as they arrive and placing them straight into the freezer.\n\n'
            'You can track your delivery here:\n{tracking_link}\n\n'
            'Thank you for choosing Tommy Sugo.\n\nWarm regards,\nNathan and the Tommy Sugo Team'
        )

        if self.enabled:
            mode = "TESTING MODE (sends real SMS immediately)" if self.testing_mode else "PRODUCTION MODE (sends on delivery date — Perth TZ)"
            logger.info(f"[MOBILE MESSAGE] ✅ SMS service enabled - {mode}")
            logger.info(f"[MOBILE MESSAGE] Sender ID: {self.sender_id}")
        else:
            logger.warning("[MOBILE MESSAGE] ❌ SMS service disabled - missing credentials")

    # ==================== HELPERS ====================

    def _format_phone_number(self, phone: str) -> str:
        """
        Format phone number for Australian mobile.
        Handles: 0412345678, +61412345678, 61412345678
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
        return f"https://mydel.info/Track/48497/{consignment_number}"

    def _format_message(self, customer_name: str, consignment_number: str = "") -> str:
        """Format SMS message with customer name and tracking link"""
        first_name    = self._get_first_name(customer_name)
        tracking_link = self._generate_tracking_link(consignment_number)
        message = self.message_template.replace('{customer_name}', first_name)
        message = message.replace('{tracking_link}', tracking_link)
        return message

    def _parse_delivery_date(self, delivery_date) -> Optional[date]:
        """
        Parse delivery date from various formats into a date object.

        Supports:
          - datetime / date objects
          - TransVirtual DateTime string: 'YYYY-MM-DD HH:MM'
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

        # String formats — TransVirtual 'YYYY-MM-DD HH:MM' bhi handle hoga
        if isinstance(delivery_date, str):
            formats = ['%Y-%m-%d %H:%M', '%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%m/%d/%Y']
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
        Decide whether to send SMS right now based on mode + Perth date.

        FIX v14.5: Perth timezone use karo — pehle server local time tha jo wrong tha.

        TESTING MODE  → Always send immediately (date check nahi)
        PRODUCTION MODE → Send only if today (Perth) == delivery date

        Returns:
            True  → send SMS now
            False → skip
        """
        if self.testing_mode:
            logger.info("[MOBILE MESSAGE] 🧪 TESTING MODE → Sending SMS immediately (real API call)")
            return True

        # Production: Perth date check
        parsed_date  = self._parse_delivery_date(delivery_date)
        today_perth  = datetime.now(PERTH_TZ).date()   # FIX v14.5: Perth TZ

        if parsed_date is None:
            logger.error(
                "[MOBILE MESSAGE] ❌ PRODUCTION MODE → delivery_date missing or invalid. "
                "Cannot determine send time. SMS skipped."
            )
            return False

        if parsed_date == today_perth:
            logger.info(
                f"[MOBILE MESSAGE] 🚀 PRODUCTION MODE → Today Perth ({today_perth}) matches "
                f"delivery date ({parsed_date}). Sending SMS now."
            )
            return True
        elif parsed_date > today_perth:
            logger.info(
                f"[MOBILE MESSAGE] ⏳ PRODUCTION MODE → Delivery date is {parsed_date} "
                f"(today Perth is {today_perth}). SMS will be sent on delivery day. Skipping."
            )
            return False
        else:
            logger.warning(
                f"[MOBILE MESSAGE] ⚠️  PRODUCTION MODE → Delivery date {parsed_date} is in the PAST "
                f"(today Perth is {today_perth}). SMS skipped."
            )
            return False

    # ==================== MAIN SEND FUNCTION ====================

    def send_delivery_notification(
        self,
        customer_name: str,
        customer_phone: str,
        consignment_number: str = "",
        invoice_no: str = "",
        delivery_date=None
    ) -> bool:
        """
        Send delivery notification SMS to customer with tracking link.

        Called from:
          - TransVirtual webhook (InTransit / Delivered) — main.py
          - Manual trigger endpoint — _process_notifications()

        Behavior:
          TESTING MODE  → sends real SMS immediately (no date check)
          PRODUCTION MODE → sends SMS only if today (Perth) == delivery_date

        Args:
            customer_name:      Customer's name
            customer_phone:     Customer's phone number (from TransVirtual ReceiverPhone)
            consignment_number: Consignment number
            invoice_no:         Invoice/consignment number for logging
            delivery_date:      Delivery date — TransVirtual DateTime string or Jotform dict

        Returns:
            True if SMS sent successfully, False otherwise
        """
        if not self.enabled:
            logger.warning("[MOBILE MESSAGE] ⏭️  SMS skipped - service disabled")
            return False

        if not customer_phone or not customer_phone.strip():
            logger.warning(f"[MOBILE MESSAGE] ⏭️  SMS skipped - no phone number for {invoice_no or consignment_number}")
            return False

        # Date/mode check
        if not self._should_send_now(delivery_date):
            return False

        try:
            formatted_phone = self._format_phone_number(customer_phone)
            message         = self._format_message(customer_name, consignment_number)

            logger.info("=" * 80)
            logger.info("[MOBILE MESSAGE] 📱 Sending SMS...")
            logger.info(f"  Invoice/Consignment : {invoice_no or consignment_number}")
            logger.info(f"  Customer            : {customer_name}")
            logger.info(f"  Original Phone      : {customer_phone}")
            logger.info(f"  Formatted Phone     : {formatted_phone}")
            logger.info(f"  Consignment         : {consignment_number}")
            logger.info(f"  Delivery Date       : {delivery_date}")
            logger.info(f"  Tracking Link       : {self._generate_tracking_link(consignment_number)}")
            logger.info(f"  Message Length      : {len(message)} chars")
            logger.info(f"  Mode                : {'TESTING' if self.testing_mode else 'PRODUCTION'}")
            logger.info("-" * 80)
            logger.info(f"  Message Preview:\n{message}")
            logger.info("-" * 80)

            result = self._send_sms_api(formatted_phone, message, invoice_no or consignment_number)

            if result:
                logger.info("[MOBILE MESSAGE] ✅ SMS SENT SUCCESSFULLY")
            else:
                logger.error("[MOBILE MESSAGE] ❌ SMS SEND FAILED")

            logger.info("=" * 80)
            return result

        except Exception as e:
            logger.error("=" * 80)
            logger.error(f"[MOBILE MESSAGE] ❌ SMS ERROR")
            logger.error(f"  Customer : {customer_name}")
            logger.error(f"  Phone    : {customer_phone}")
            logger.error(f"  Error    : {e}")
            logger.error("=" * 80)
            return False

    # ==================== API CALL ====================

    def _send_sms_api(self, phone: str, message: str, invoice_no: str = "") -> bool:
        """Send SMS via Mobile Message API"""
        try:
            payload = {
                "enable_unicode": True,
                "messages": [
                    {
                        "to"        : phone,
                        "message"   : message,
                        "sender"    : self.sender_id,
                        "custom_ref": f"invoice_{invoice_no}" if invoice_no else None
                    }
                ]
            }
            # None values hata do
            payload["messages"][0] = {k: v for k, v in payload["messages"][0].items() if v is not None}

            logger.info("[MOBILE MESSAGE] 📡 Making API request...")
            logger.info(f"  URL    : {self.api_url}")
            logger.info(f"  Sender : {self.sender_id}")
            logger.info(f"  To     : {phone}")

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
                        logger.info(f"  Message ID : {results[0].get('message_id', 'N/A')}")
                        logger.info(f"  Cost       : {results[0].get('cost', 'N/A')} credits")
                        logger.info(f"  Encoding   : {results[0].get('encoding', 'N/A')}")
                        return True
                    else:
                        error_msg = results[0].get('status', 'unknown error') if results else 'no results'
                        logger.error(f"[MOBILE MESSAGE] ❌ Message failed: {error_msg}")
                        return False
                else:
                    logger.error(f"[MOBILE MESSAGE] ❌ Batch status: {result.get('status', 'unknown')}")
                    return False
            else:
                logger.error(f"[MOBILE MESSAGE] ❌ HTTP ERROR {response.status_code}: {response.text}")
                return False

        except requests.exceptions.Timeout:
            logger.error("[MOBILE MESSAGE] ❌ TIMEOUT ERROR - request timed out after 30s")
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"[MOBILE MESSAGE] ❌ REQUEST ERROR: {e}")
            return False
        except Exception as e:
            logger.error(f"[MOBILE MESSAGE] ❌ UNEXPECTED ERROR: {e}")
            return False