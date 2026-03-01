"""
Helper Utilities - Data extraction and processing functions
"""
import re
import json
import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _parse_address_components(addr_line1: str, addr_line2: str, city: str, state: str, postal: str) -> Tuple[str, str, str, str, str]:
    """
    Smart address parser that handles messy Jotform address inputs.
    
    Handles cases like:
        addr_line2 = "Ripponlea VIC 3185"  (user put suburb in line 2)
        city       = "VIC 3185"            (only state+postcode left in city)
        city       = "Ripponlea VIC 3185"  (full combo in city)
        city       = "Ripponlea"           (normal)

    Returns:
        (addr_line1, addr_line2, suburb, state, postcode)
    """
    suburb = city.strip()
    state = state.strip()
    postcode = postal.strip()
    line1 = addr_line1.strip()
    line2 = addr_line2.strip()

    # -------------------------------------------------------
    # Step 1: Try to extract suburb/state/postcode from city field
    # -------------------------------------------------------

    # Case A: city = "Ripponlea VIC 3185"
    match_full = re.match(r'^(.+?)\s+([A-Z]{2,3})\s+(\d{4})$', suburb)
    if match_full:
        suburb = match_full.group(1).strip()
        if not state:
            state = match_full.group(2)
        if not postcode:
            postcode = match_full.group(3)

    # Case B: city = "VIC 3185" (suburb missing, only state+postcode in city)
    elif re.match(r'^([A-Z]{2,3})\s+(\d{4})$', suburb):
        match_sp = re.match(r'^([A-Z]{2,3})\s+(\d{4})$', suburb)
        if not state:
            state = match_sp.group(1)
        if not postcode:
            postcode = match_sp.group(2)
        suburb = ""  # city had no real suburb - look in line2

    # Case C: city = "VIC" only
    elif re.match(r'^([A-Z]{2,3})$', suburb):
        if not state:
            state = suburb
        suburb = ""

    # Case D: city = "Ripponlea VIC" (suburb + state, no postcode)
    else:
        match_ss = re.match(r'^(.+?)\s+([A-Z]{2,3})$', suburb)
        if match_ss:
            suburb = match_ss.group(1).strip()
            if not state:
                state = match_ss.group(2)

    # -------------------------------------------------------
    # Step 2: If suburb still empty, try to get it from addr_line2
    # e.g. addr_line2 = "Ripponlea VIC 3185" or "Ripponlea"
    # -------------------------------------------------------
    if not suburb and line2:
        # Try full combo in line2: "Ripponlea VIC 3185"
        match_l2_full = re.match(r'^(.+?)\s+([A-Z]{2,3})\s+(\d{4})$', line2)
        if match_l2_full:
            suburb = match_l2_full.group(1).strip()
            if not state:
                state = match_l2_full.group(2)
            if not postcode:
                postcode = match_l2_full.group(3)
            line2 = ""  # consumed into suburb/state/postcode

        else:
            # Try state only in line2: "Ripponlea VIC"
            match_l2_ss = re.match(r'^(.+?)\s+([A-Z]{2,3})$', line2)
            if match_l2_ss:
                suburb = match_l2_ss.group(1).strip()
                if not state:
                    state = match_l2_ss.group(2)
                line2 = ""
            else:
                # line2 is just a plain suburb name
                suburb = line2.strip()
                line2 = ""

    # -------------------------------------------------------
    # Step 3: Even if suburb exists, check if line2 looks like
    # address info "Ripponlea VIC 3185" and extract missing pieces
    # -------------------------------------------------------
    if line2:
        match_l2_full = re.match(r'^(.+?)\s+([A-Z]{2,3})\s+(\d{4})$', line2)
        if match_l2_full:
            if not suburb:
                suburb = match_l2_full.group(1).strip()
            if not state:
                state = match_l2_full.group(2)
            if not postcode:
                postcode = match_l2_full.group(3)
            line2 = ""

    # -------------------------------------------------------
    # Step 4: Clean postcode - extract 4 digits only
    # -------------------------------------------------------
    if postcode:
        pc_match = re.search(r'\d{4}', postcode)
        postcode = pc_match.group(0) if pc_match else postcode

    # -------------------------------------------------------
    # Step 5: Clean suburb - remove market/shopping suffixes
    # -------------------------------------------------------
    if suburb:
        suburb = suburb.replace(' Markets', '').replace(' Market', '').replace(' Shopping', '').strip()
        if suburb.startswith('The ') and len(suburb.split()) <= 2:
            suburb = suburb[4:].strip()

    logger.info(
        f"[ADDRESS PARSE] "
        f"line1='{line1}' | line2='{line2}' | "
        f"suburb='{suburb}' | state='{state}' | postcode='{postcode}'"
    )

    return line1, line2, suburb, state, postcode


def extract_field_value(raw_data: Dict, field_config: Dict) -> Any:
    """
    Extract field value from raw Jotform data based on configuration.
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

    if field_type in ("address_object", "address_line1", "address_line2",
                      "address_suburb", "address_state", "address_postcode") and isinstance(value, dict):

        raw_line1  = value.get('addr_line1', '')
        raw_line2  = value.get('addr_line2', '')
        raw_city   = value.get('city', '')
        raw_state  = value.get('state', '')
        raw_postal = value.get('postal', '')

        line1, line2, suburb, state, postcode = _parse_address_components(
            raw_line1, raw_line2, raw_city, raw_state, raw_postal
        )

        if field_type == "address_line1":
            return line1

        if field_type == "address_line2":
            return line2

        if field_type == "address_suburb":
            return suburb

        if field_type == "address_state":
            return state

        if field_type == "address_postcode":
            return postcode

        if field_type == "address_object":
            parts = [p for p in [line1, line2, suburb, state, postcode] if p]
            return ', '.join(parts)

    return str(value) if value else ""


def extract_products(raw_data: Dict, config: Dict) -> List[Dict]:
    """
    Extract product list from raw Jotform data.
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