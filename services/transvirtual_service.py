"""
Transvirtual API Service - Courier consignment creation
"""
import logging
import requests
import re
import os
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class TransvirtualService:
    def __init__(self, config: Dict):
        self.config = config.get('transvirtual', {})
        self.enabled = self.config.get('enabled', False)
        self.api_key = os.getenv('TRANSVIRTUAL_API_KEY', self.config.get('api_key', ''))
        self.api_url = self.config.get('api_url', '')
        self.headers = {"Authorization": self.api_key, "Content-Type": "application/json"}
        
        logger.info(f"Transvirtual: {'ENABLED' if self.enabled else 'DISABLED'}")
    
    def create_consignment(self, order_data: Dict) -> Optional[Dict]:
        """
        Create a consignment in Transvirtual system.
        For GIFT ORDERS: Send gift recipient details to courier
        For NORMAL ORDERS: Send customer details to courier
        
        Args:
            order_data: Order data dictionary
            
        Returns:
            Optional[Dict]: Dict with barcode_number, consignment_id, consignment_number or None
        """
        if not self.enabled or not self.api_key:
            return None
        
        try:
            # Check if this is a gift order
            is_gift_order = bool(order_data.get('gift_note', '').strip())
            use_gift_recipient = self.config.get('use_gift_recipient_for_gift_orders', True)
            
            # For gift orders, send to gift recipient; otherwise send to customer
            if is_gift_order and use_gift_recipient:
                receiver_name = order_data.get('gift_recipient', order_data.get('customer_name', ''))
                receiver_phone = order_data.get('gift_phone', order_data.get('customer_phone', ''))
                logger.info(f"[TRANSVIRTUAL] 🎁 GIFT ORDER - Sending to: {receiver_name}")
            else:
                receiver_name = order_data.get('customer_name', '')
                receiver_phone = order_data.get('customer_phone', '')
                logger.info(f"[TRANSVIRTUAL] 📦 NORMAL ORDER - Sending to: {receiver_name}")
            
            # Parse delivery date
            delivery_date_obj = order_data.get('delivery_date_obj', {})
            day = delivery_date_obj.get('day', '01')
            month = delivery_date_obj.get('month', '01')
            year = delivery_date_obj.get('year', '2026')
            delivery_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            
            sender = self.config.get('sender', {})
            
            # Parse receiver address
            receiver_address_line1 = order_data.get('delivery_address_line1', '').strip()
            receiver_address_line2 = order_data.get('delivery_address_line2', '').strip()
            receiver_suburb = order_data.get('delivery_suburb', '').strip()
            receiver_state = order_data.get('delivery_state', '').strip()
            receiver_postcode = order_data.get('delivery_postcode', '').strip()
            
            # Merge address lines if needed
            if receiver_address_line1 and receiver_address_line2:
                if receiver_address_line1.replace(' ', '').isdigit():
                    receiver_address_line1 = f"{receiver_address_line1} {receiver_address_line2}"
                    receiver_address_line2 = ""
            
            # Clean suburb name
            if receiver_suburb:
                suburb_clean = receiver_suburb.replace('The ', '').replace(' Markets', '')
                suburb_clean = suburb_clean.replace(' Market', '').replace(' Shopping', '').strip()
                suburb_parts = suburb_clean.split()
                if len(suburb_parts) > 2:
                    suburb_clean = ' '.join(suburb_parts[:2])
                receiver_suburb = suburb_clean
            
            # Default state
            if not receiver_state:
                receiver_state = 'WA'
            
            # Extract postcode
            if receiver_postcode:
                postcode_match = re.search(r'\d{4}', receiver_postcode)
                if postcode_match:
                    receiver_postcode = postcode_match.group(0)
            
            # Fallback to full address if components missing
            if not receiver_address_line1 or not receiver_suburb or not receiver_postcode:
                full_address = order_data.get('delivery_address', '').strip()
                if full_address:
                    address_parts = [p.strip() for p in full_address.split(',')]
                    if not receiver_address_line1 and len(address_parts) >= 1:
                        receiver_address_line1 = address_parts[0]
                    if not receiver_suburb and len(address_parts) >= 2:
                        suburb_raw = address_parts[1].strip().replace('The ', '').replace(' Markets', '')
                        receiver_suburb = suburb_raw
                    if not receiver_state and len(address_parts) >= 3:
                        state_part = address_parts[2].strip()
                        if len(state_part) <= 3 and state_part.isalpha():
                            receiver_state = state_part
                    if not receiver_postcode:
                        for part in reversed(address_parts):
                            postcode_match = re.search(r'\b(\d{4})\b', part)
                            if postcode_match:
                                receiver_postcode = postcode_match.group(1)
                                break
            
            # Final defaults
            if not receiver_address_line1:
                receiver_address_line1 = order_data.get('delivery_address', 'N/A')[:50]
            if not receiver_suburb:
                receiver_suburb = "N/A"
            if not receiver_postcode:
                receiver_postcode = "0000"
            if not receiver_state:
                receiver_state = "WA"
            
            # Build API payload
            payload = {
                "CustomerCode": self.config.get('customer_code', ''),
                "Date": f"{delivery_date}T12:00",
                "ConsignmentServiceType": self.config.get('service_type', 'MCX'),
                "PickupRequest": self.config.get('pickup_request', 'y'),
                "ReturnPdfLabels": self.config.get('return_pdf_labels', 'y'),
                "SenderName": sender.get('name', ''),
                "SenderAddress": sender.get('address', ''),
                "SenderSuburb": sender.get('suburb', ''),
                "SenderPostcode": sender.get('postcode', ''),
                "SenderEmail": sender.get('email', ''),
                "SenderPhone": sender.get('phone', ''),
                "ReceiverName": receiver_name,  # Gift recipient OR customer
                "ReceiverAddress": receiver_address_line1,
                "ReceiverAddress2": receiver_address_line2,
                "ReceiverSuburb": receiver_suburb,
                "ReceiverState": receiver_state,
                "ReceiverPostcode": receiver_postcode,
                "ConsignmentReceiverPhone": receiver_phone,  # Gift recipient phone OR customer phone
                "ReceiverEmail": order_data.get('customer_email', ''),  # Always customer email for tracking
                "ConsignmentBookingDateTime": f"{delivery_date}T12:00",
                "SpecialInstructions": order_data.get('courier_note', ''),
                "Rows": [{
                    "Qty": 1,
                    "Description": "Carton",
                    "ItemContentsDescription": "Eski",
                    "Weight": "1",
                    "Width": "1",
                    "Length": "1",
                    "Height": "1"
                }]
            }
            
            # Make API request
            response = requests.post(self.api_url, headers=self.headers, json=payload, timeout=30)
            response.raise_for_status()
            result = response.json()
            
            # Extract barcode and consignment details
            barcode_number = ''
            consignment_id = ''
            consignment_number = ''
            
            if 'Data' in result:
                item_scan_values = result['Data'].get('ItemScanValues', [])
                barcode_number = item_scan_values[0] if item_scan_values else ''
                consignment_id = result['Data'].get('Id', '')
                consignment_number = result['Data'].get('ConsignmentNumber', '')
            
            if not barcode_number and 'Items' in result:
                items = result.get('Items', [])
                if items:
                    barcode_number = items[0].get('ItemScanValue', '')
            
            if not barcode_number:
                barcode_number = result.get('ItemScanValue', '')
            
            if barcode_number:
                logger.info(f"[SUCCESS] ✅ Consignment created! Barcode: {barcode_number}")
            
            return {
                'barcode_number': barcode_number,
                'consignment_id': consignment_id,
                'consignment_number': consignment_number
            }
            
        except Exception as e:
            logger.error(f"[ERROR] ❌ Transvirtual failed: {e}")
            return None