"""
AI Service - GROQ Integration with Built-in Marketing Calendar
Ultra-fast and cost-effective alternative to OpenAI
"""
import json
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from openai import OpenAI
import os

logger = logging.getLogger(__name__)


class TommySugoCalendar:
    """
    Tommy Sugo 2026 Marketing Calendar (Perth)
    Simple date-based event checker - NO LLM CALLS for checking dates
    """
    
    @staticmethod
    def get_current_event(marketing_window_days: int = 14) -> Optional[Dict]:
        """
        Check if we're in a marketing window for any event
        Returns event details if active, None otherwise
        
        Args:
            marketing_window_days: Days before event to start marketing (default 14)
        """
        now = datetime.now()
        current_year = now.year
        
        # 🗓️ TOMMY SUGO 2026 MARKETING CALENDAR
        events = [
            # JANUARY
            {
                "name": "New Year",
                "date": datetime(current_year, 1, 1),
                "market_from_days_before": 12,  # Dec 20 - Jan 2
                "messages": [
                    "Start the new year with gourmet comfort food!",
                    "No cooking after the holidays - we've got you covered!",
                    "Healthy reset with our delicious pasta meals!"
                ]
            },
            {
                "name": "Australia Day",
                "date": datetime(current_year, 1, 26),
                "market_from_days_before": 16,  # Jan 10 - 26
                "messages": [
                    "Perfect for Australia Day celebrations!",
                    "BBQ alternative - serve gourmet Italian!",
                    "Entertaining made easy with our family bundles!"
                ]
            },
            
            # FEBRUARY
            {
                "name": "Valentine's Day",
                "date": datetime(current_year, 2, 14),
                "market_from_days_before": 13,  # Feb 1 - 14
                "messages": [
                    "Perfect for a romantic dinner at home!",
                    "Surprise your loved one with gourmet pasta!",
                    "Love is in the air - and on your plate!"
                ]
            },
            {
                "name": "Back to School",
                "date": datetime(current_year, 2, 2),
                "market_from_days_before": 13,  # Jan 20 - Feb 15
                "messages": [
                    "School night survival meals for busy families!",
                    "Make weeknight dinners easy with our family bundles!",
                    "No more dinner stress - we've got you covered!"
                ]
            },
            
            # MARCH
            {
                "name": "St Patrick's Day",
                "date": datetime(current_year, 3, 17),
                "market_from_days_before": 16,  # Mar 1 - 17
                "messages": [
                    "Celebrate with a family feast!",
                    "Perfect for St Patrick's Day gatherings!",
                    "Feed the whole crew with our family packs!"
                ]
            },
            
            # APRIL
            {
                "name": "Easter",
                "date": datetime(current_year, 4, 5),  # Easter Sunday 2026
                "market_from_days_before": 26,  # Mar 10 - Apr 5
                "messages": [
                    "Perfect for Easter family gatherings!",
                    "Stock up the freezer for the Easter break!",
                    "Feed the family this Easter - entertaining made easy!"
                ]
            },
            {
                "name": "School Holidays",
                "date": datetime(current_year, 4, 11),  # Mid-point of holidays
                "market_from_days_before": 22,  # Mar 20 - Apr 19
                "messages": [
                    "School holidays sorted with our family bundles!",
                    "Keep the kids happy with delicious pasta!",
                    "Bulk family packs for stress-free holidays!"
                ]
            },
            
            # MAY
            {
                "name": "Mother's Day",
                "date": datetime(current_year, 5, 10),
                "market_from_days_before": 20,  # Apr 20 - May 10
                "messages": [
                    "Treat mum to a gourmet feast!",
                    "Mum deserves the best - dinner sorted!",
                    "Show mum some love with delicious food!"
                ]
            },
            
            # JUNE - AUGUST (Winter Comfort)
            {
                "name": "Winter Comfort Season",
                "date": datetime(current_year, 7, 1),  # Mid-winter
                "market_from_days_before": 60,  # May 1 - July 31
                "messages": [
                    "Winter comfort food at its finest!",
                    "Hibernate with our delicious lasagna!",
                    "Warm up with gourmet Italian comfort food!"
                ]
            },
            
            # SEPTEMBER
            {
                "name": "Father's Day",
                "date": datetime(current_year, 9, 6),  # First Sunday of Sept (AU)
                "market_from_days_before": 22,  # Aug 15 - Sept 6
                "messages": [
                    "Dad would love this!",
                    "Perfect gift for Father's Day!",
                    "Celebrate dad with gourmet Italian!"
                ]
            },
            {
                "name": "AFL Grand Final",
                "date": datetime(current_year, 9, 26),
                "market_from_days_before": 21,  # Sept 5 - 26
                "messages": [
                    "Game night sorted with our catering trays!",
                    "Arancini for the game - perfect finger food!",
                    "Feed the footy crowd with our party packs!"
                ]
            },
            {
                "name": "Kings Park Festival",
                "date": datetime(current_year, 9, 15),  # Mid-Sept
                "market_from_days_before": 30,  # All Sept
                "messages": [
                    "Perfect for a Kings Park picnic!",
                    "Pack a gourmet feast for the festival!",
                    "Picnic-ready pasta packs!"
                ]
            },
            
            # OCTOBER
            {
                "name": "Halloween",
                "date": datetime(current_year, 10, 31),
                "market_from_days_before": 21,  # Oct 10 - 31
                "messages": [
                    "Feed the ghouls with our family packs!",
                    "Perfect for Halloween parties!",
                    "Spooky good food for the whole family!"
                ]
            },
            
            # NOVEMBER - DECEMBER (BIGGEST SEASON)
            {
                "name": "Christmas",
                "date": datetime(current_year, 12, 25),
                "market_from_days_before": 40,  # Nov 15 - Dec 24
                "messages": [
                    "Perfect for Christmas dinner!",
                    "Festive feast made easy - catering trays available!",
                    "Make Christmas extra special with gourmet Italian!"
                ]
            },
            {
                "name": "New Year's Eve",
                "date": datetime(current_year, 12, 31),
                "market_from_days_before": 16,  # Dec 15 - 31
                "messages": [
                    "Ring in the new year with a feast!",
                    "Party catering sorted - entertaining made easy!",
                    "Perfect for New Year's Eve celebrations!"
                ]
            },
            {
                "name": "Summer Holidays",
                "date": datetime(current_year, 12, 24),  # Christmas Eve
                "market_from_days_before": 14,  # Dec 10 - Jan
                "messages": [
                    "Don't cook these holidays - we've got you!",
                    "Fill the freezer for the summer break!",
                    "Beach-ready meals for lazy summer days!"
                ]
            }
        ]
        
        # Check which event is currently active
        for event in events:
            event_date = event['date']
            days_before = event.get('market_from_days_before', marketing_window_days)
            
            # Calculate marketing window
            market_start = event_date - timedelta(days=days_before)
            market_end = event_date + timedelta(days=1)  # Day after event
            
            # Check if we're in the marketing window
            if market_start <= now <= market_end:
                days_until = (event_date - now).days
                
                return {
                    'name': event['name'],
                    'date': event_date.strftime('%d %B %Y'),
                    'days_until': days_until,
                    'messages': event['messages']
                }
        
        return None


class OpenAIService:
    def __init__(self, config: Dict):
        self.config = config.get('openai', {})
        
        # Try GROQ first, fallback to OpenAI
        groq_key = os.getenv('GROQ_API_KEY', '')
        openai_key = os.getenv('OPENAI_API_KEY', '')
        
        if groq_key:
            # Use GROQ (fast & free!)
            self.client = OpenAI(
                base_url="https://api.groq.com/openai/v1",
                api_key=groq_key
            )
            self.model = "llama-3.3-70b-versatile"
            self.provider = "GROQ"
            logger.info(f"[AI] ✅ Using GROQ (Model: {self.model})")
        elif openai_key:
            # Fallback to OpenAI
            self.client = OpenAI(api_key=openai_key)
            self.model = "gpt-3.5-turbo"
            self.provider = "OpenAI"
            logger.info(f"[AI] ✅ Using OpenAI (Model: {self.model})")
        else:
            self.client = None
            self.model = None
            self.provider = None
            logger.warning("[AI] ❌ No API key found")
        
        self.enabled = self.config.get('enabled', True) and bool(self.client)
        
        if self.enabled:
            logger.info(f"[AI SERVICE] ✅ ENABLED ({self.provider})")
        else:
            logger.warning("[AI SERVICE] ❌ DISABLED")
    
    def validate_and_fix_data(self, order_data: Dict) -> Dict:
        """
        Validate and fix typos ONLY in customer info and notes.
        Does NOT send items/products list to save tokens!
        """
        if not self.client or not self.enabled:
            logger.info("[AI VALIDATOR] ⏭️  SKIPPED (disabled or no API key)")
            return order_data
        
        try:
            logger.info("=" * 80)
            logger.info(f"[AI VALIDATOR] 📥 VALIDATION STARTED ({self.provider})")
            logger.info("-" * 80)
            
            # Check if gift order
            is_gift_order = bool(order_data.get('gift_recipient', '').strip())
            
            # ⬇️ ONLY these fields will be validated
            fields_to_validate = {
                'customer_name': order_data.get('customer_name', ''),
                'customer_phone': order_data.get('customer_phone', ''),
                'customer_email': order_data.get('customer_email', ''),
                'delivery_address': order_data.get('delivery_address', ''),
                'courier_note': order_data.get('courier_note', ''),
                'customer_love_note': order_data.get('customer_love_note', '')
            }
            
            # Add gift fields ONLY if it's a gift order
            if is_gift_order:
                fields_to_validate['gift_recipient'] = order_data.get('gift_recipient', '')
                fields_to_validate['gift_phone'] = order_data.get('gift_phone', '')
                fields_to_validate['gift_note'] = order_data.get('gift_note', '')
            
            # Remove empty fields to save tokens
            fields_to_validate = {k: v for k, v in fields_to_validate.items() 
                                if v and str(v).strip()}
            
            if not fields_to_validate:
                logger.info("[AI VALIDATOR] ⏭️  No fields to validate")
                logger.info("=" * 80)
                return order_data
            
            logger.info(f"[AI VALIDATOR] 📝 Validating {len(fields_to_validate)} fields:")
            for field, value in fields_to_validate.items():
                logger.info(f"  • {field}: '{value[:50]}{'...' if len(str(value)) > 50 else ''}'")
            
            prompt = f"""Fix ONLY obvious typos and grammar errors in these customer fields.

CRITICAL RULES:
1. DO NOT change person names (keep exactly as is)
2. DO NOT change phone numbers
3. DO NOT change email addresses
4. ONLY fix obvious spelling/grammar errors in addresses and notes
5. If something looks correct, don't change it
6. Return JSON with same keys

Fields to validate:
{json.dumps(fields_to_validate, indent=2)}"""
            
            logger.info("-" * 80)
            logger.info(f"[AI VALIDATOR] 🤖 Calling {self.provider} API...")
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a data validator. Return ONLY valid JSON, no markdown. NEVER change person names, phone numbers, or emails."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=1000
            )
            
            # Log usage (if available)
            if hasattr(response, 'usage') and response.usage:
                usage = response.usage
                logger.info(f"[AI VALIDATOR] 📊 Token Usage:")
                logger.info(f"  Input: {usage.prompt_tokens}")
                logger.info(f"  Output: {usage.completion_tokens}")
                logger.info(f"  Total: {usage.total_tokens}")
            
            response_content = response.choices[0].message.content.strip()
            response_content = response_content.replace('```json', '').replace('```', '').strip()
            corrected_fields = json.loads(response_content)
            
            logger.info("-" * 80)
            logger.info("[AI VALIDATOR] 📤 VALIDATION RESULTS:")
            logger.info("-" * 80)
            
            changes_made = []
            for field in fields_to_validate.keys():
                before = str(order_data.get(field, ''))
                after = str(corrected_fields.get(field, ''))
                
                if before != after:
                    logger.info(f"  ✏️  {field}:")
                    logger.info(f"      BEFORE: '{before[:100]}{'...' if len(before) > 100 else ''}'")
                    logger.info(f"      AFTER:  '{after[:100]}{'...' if len(after) > 100 else ''}'")
                    changes_made.append(field)
                    order_data[field] = after
                else:
                    logger.info(f"  ✓ {field}: No change")
            
            logger.info("-" * 80)
            if changes_made:
                logger.info(f"[AI VALIDATOR] ✅ SUCCESS - {len(changes_made)} field(s) corrected")
            else:
                logger.info(f"[AI VALIDATOR] ✅ SUCCESS - No corrections needed")
            logger.info("=" * 80)
            
            return order_data
            
        except Exception as e:
            logger.error("=" * 80)
            logger.error(f"[AI VALIDATOR] ❌ ERROR: {e}")
            logger.error("=" * 80)
            import traceback
            logger.error(traceback.format_exc())
            return order_data
    
    def generate_feedback_response(self, customer_feedback: str, customer_name: str) -> str:
        """Generate a personalized response to customer feedback."""
        if not self.client or not self.enabled or not customer_feedback.strip():
            return ""
        
        try:
            first_name = customer_name.split()[0] if customer_name else "Customer"
            
            logger.info(f"[AI FEEDBACK] 🤖 Generating response ({self.provider})...")
            logger.info(f"  Customer: {first_name}")
            logger.info(f"  Feedback: {customer_feedback[:100]}{'...' if len(customer_feedback) > 100 else ''}")
            
            prompt = f'Customer "{first_name}" left this feedback: "{customer_feedback}"\n\nWrite a warm, personal ONE-LINE response (max 15 words) thanking them.'
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Write SHORT, warm, friendly responses only. Be casual and heartfelt."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1000
            )
            
            feedback_response = response.choices[0].message.content.strip()
            logger.info(f"[AI FEEDBACK] ✅ Generated: '{feedback_response}'")
            return feedback_response
            
        except Exception as e:
            logger.error(f"[AI FEEDBACK] ❌ ERROR: {e}")
            return ""
    
    def generate_product_recommendation(self, ordered_products: List[Dict], 
                                       all_products: List[str], 
                                       is_gift_order: bool = False) -> str:
        """
        Generate product recommendation with EVENT-AWARE MARKETING.
        Uses Tommy Sugo calendar to add relevant event context.
        
        COST-SAVING STRATEGY:
        - Date checking done with Python (FREE)
        - Only active event context sent to LLM
        - LLM only called once per recommendation
        """
        if not self.client or not self.enabled:
            return ""
        
        # ⬇️ SKIP for gift orders
        if is_gift_order:
            logger.info("[AI RECOMMEND] ⏭️  SKIPPED (gift order)")
            return ""
        
        try:
            # ⬇️ STEP 1: Check for active marketing event (NO LLM CALL - FREE!)
            current_event = TommySugoCalendar.get_current_event()
            
            # ⬇️ STEP 2: Rule-based filtering
            ordered_names = [p.get('product_name', '') for p in ordered_products]
            unordered_products = [p for p in all_products if p not in ordered_names]
            
            if not unordered_products:
                logger.info("[AI RECOMMEND] ⏭️  All products already ordered!")
                return ""
            
            logger.info(f"[AI RECOMMEND] 🤖 Generating recommendation ({self.provider})...")
            logger.info(f"  Ordered: {len(ordered_names)} products")
            logger.info(f"  Available: {len(unordered_products)} unordered products")
            
            # ⬇️ STEP 3: Build event context (if active)
            event_context = ""
            if current_event:
                event_name = current_event['name']
                days_until = current_event['days_until']
                
                # Pick first marketing message
                marketing_msg = current_event['messages'][0]
                
                event_context = f"\n\n🎯 ACTIVE EVENT: {event_name} is in {days_until} days. {marketing_msg}"
                
                logger.info(f"  📅 Event Context: {event_name} ({days_until} days)")
            else:
                logger.info(f"  📅 No active events - general recommendation")
            
            # ⬇️ Limit lists to save tokens
            ordered_sample = ordered_names[:5]
            unordered_sample = unordered_products[:10]
            
            # ⬇️ Build prompt with optional event context
            prompt = f"""Customer ordered: {', '.join(ordered_sample)}

Available products they didn't order: {', '.join(unordered_sample)}{event_context}

Write ONE short, friendly marketing line (max 30 -50 words) recommending ONE unordered product.{' Make it relevant to the event if mentioned.' if event_context else ''}"""
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Write SHORT, friendly, casual marketing recommendations. Connect products to events/holidays when relevant. Engage customers warmly.And make it atleast 30 - 50 words(max)"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1000
            )
            
            recommendation = response.choices[0].message.content.strip()
            
            if current_event:
                logger.info(f"[AI RECOMMEND] ✅ Generated (EVENT-AWARE): '{recommendation}'")
            else:
                logger.info(f"[AI RECOMMEND] ✅ Generated: '{recommendation}'")
            
            return recommendation
            
        except Exception as e:
            logger.error(f"[AI RECOMMEND] ❌ ERROR: {e}")
            return ""