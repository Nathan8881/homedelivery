"""
Helper Utilities - Data extraction and processing functions
"""
import re
import json
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


def extract_field_value(raw_data: Dict, field_config: Dict) -> Any:
    """
    Extract field value from raw Jotform data based on configuration.
    
    Args:
        raw_data: Raw Jotform submission data
        field_config: Field configuration dictionary
        
    Returns:
        Extracted and processed field value
    """
    if "static_value" in field_config:
        return field_config["static_value"]
    
    jotform_field = field_config.get("jotform_field")
    if not jotform_field or jotform_field not in raw_data:
        return ""
    
    value = raw_data[jotform_field]
    field_type = field_config.get("field_type", "text")
    
    if field_type == "name_object" and isinstance(value, dict):
        first = value.get('first', '')
        last = value.get('last', '')
        return f"{first} {last}".strip()
    
    if field_type == "date_object" and isinstance(value, dict):
        day = value.get('day', 'N/A')
        month = value.get('month', 'N/A')
        year = value.get('year', 'N/A')
        return f"{day}-{month}-{year}"
    
    if field_type == "address_object" and isinstance(value, dict):
        parts = []
        addr_line1 = value.get('addr_line1', '').strip()
        if addr_line1:
            parts.append(addr_line1)
        addr_line2 = value.get('addr_line2', '').strip()
        if addr_line2:
            parts.append(addr_line2)
        city = value.get('city', '').strip()
        if city:
            parts.append(city)
        state = value.get('state', '').strip()
        if state:
            parts.append(state)
        postal = value.get('postal', '').strip()
        if postal:
            parts.append(postal)
        return ', '.join(parts) if parts else ''
    
    if field_type == "address_line1" and isinstance(value, dict):
        return value.get('addr_line1', '').strip()
    
    if field_type == "address_line2" and isinstance(value, dict):
        return value.get('addr_line2', '').strip()
    
    if field_type == "address_suburb" and isinstance(value, dict):
        return value.get('city', '').strip()
    
    if field_type == "address_state" and isinstance(value, dict):
        return value.get('state', '').strip()
    
    if field_type == "address_postcode" and isinstance(value, dict):
        return value.get('postal', '').strip()
    
    return str(value) if value else ""


def extract_products(raw_data: Dict, config: Dict) -> List[Dict]:
    """
    Extract product list from raw Jotform data.
    
    Args:
        raw_data: Raw Jotform submission data
        config: Form configuration
        
    Returns:
        List of product dictionaries
    """
    product_config = config['products']
    products_field = product_config["jotform_field"]
    products_key = product_config["products_key"]
    
    if products_field not in raw_data:
        return []
    
    products = raw_data[products_field].get(products_key, [])
    items = []
    
    for product in products:
        item = {}
        extracted_code = None
        
        for column in product_config["columns"]:
            col_name = column["name"]
            jotform_key = column["jotform_key"]
            value = product.get(jotform_key)
            
            if "process_function" in column and value:
                if column["process_function"] == "extract_product_code":
                    patterns = [r'\b(HD\d{4})\b', r'\b(HDGF\d+)\b', r'\b(HD[A-Z]+\d+)\b']
                    for pattern in patterns:
                        match = re.search(pattern, str(value))
                        if match:
                            extracted_code = match.group(1)
                            break
                    value = extracted_code if extracted_code else ''
            
            item[col_name] = value if value else ""
        
        # Clean product name
        if extracted_code and 'product_name' in item:
            original_name = item['product_name']
            cleaned_name = original_name.replace(f" - {extracted_code}", "")
            cleaned_name = cleaned_name.replace(f" {extracted_code}", "")
            cleaned_name = cleaned_name.replace(extracted_code, "")
            cleaned_name = re.sub(r'\s+', ' ', cleaned_name).strip()
            item['product_name'] = cleaned_name
        
        items.append(item)
    
    return items


def extract_form_id(raw_data: Dict) -> Optional[str]:
    """
    Extract form ID from Jotform submission data.
    
    Args:
        raw_data: Raw Jotform submission data
        
    Returns:
        Optional[str]: Form ID or None
    """
    for field in ['formID', 'form_id']:
        if field in raw_data and raw_data[field]:
            form_id = str(raw_data[field])
            logger.info(f"Form ID from {field}: {form_id}")
            return form_id
    
    if 'path' in raw_data:
        match = re.search(r'/submit/(\d+)', raw_data['path'])
        if match:
            form_id = match.group(1)
            logger.info(f"Form ID from path: {form_id}")
            return form_id
    
    if 'slug' in raw_data:
        match = re.search(r'submit/(\d+)', raw_data['slug'])
        if match:
            form_id = match.group(1)
            logger.info(f"Form ID from slug: {form_id}")
            return form_id
    
    logger.error("Could not extract form ID")
    return None