"""
Deal Resolver Service
---------------------
Meal Pack deals ko individual products mein expand karta hai.

Kyun static hai?
- Deals change nahi hote frequently
- Factory ko exact product codes chahiye
- Webhook se sirf deal name aata hai, products nahi

Usage (main.py ya webhook handler mein):
    from services.deal_resolver import resolve_deals

    # order_data['items'] already parse hue hain Jotform se
    order_data['items'] = resolve_deals(order_data.get('items', []))
    # Ab items mein deal ke products bhi include hain
"""

import logging

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# STATIC DEAL DEFINITIONS
# Har deal mein products list hai: {'qty': str, 'product_name': str, 'product_code': str}
# FREE items bhi include hain — factory ko pata hona chahiye
# ─────────────────────────────────────────────────────────────────────────────

DEALS: dict = {

    "Vegetarian Meal Pack": {
        "label": "Vegetarian Meal Pack (22 serves • $185.00)",
        "products": [
            {"qty": "1", "product_name": "Ricotta Spinach Ravioli 1kg",                          "product_code": "HD2017"},
            {"qty": "1", "product_name": "Ricotta Spinach Cannelloni 1kg",                        "product_code": "HD3002"},
            {"qty": "2", "product_name": "Napolitana Sauce 500g",                                 "product_code": "HD4000"},
            {"qty": "1", "product_name": "Pumpkin Feta Ravioli 375g",                             "product_code": "HD2006"},
            {"qty": "1", "product_name": "Porcini Mushroom Mascarpone Truffle Ravioli 375g",      "product_code": "HD2001"},
            {"qty": "1", "product_name": "Baked Ricotta Sundried Tomato Tortellini 375g",         "product_code": "HD2003"},
            {"qty": "1", "product_name": "Spinach & 5 Cheese Arancini 270g",                     "product_code": "HD1000"},
            {"qty": "1", "product_name": "Eight Vegetable Lasagna 1kg",                           "product_code": "HD3003"},
            {"qty": "1", "product_name": "FREE Croquettes Pumpkin Feta 270g",                    "product_code": "HD1005"},
        ]
    },

    "Carnivore Meal Pack": {
        "label": "Carnivore Meal Pack (22 serves • $184.00)",
        "products": [
            {"qty": "1", "product_name": "Harvey Beef Lasagna 1kg",                              "product_code": "HD3000"},
            {"qty": "1", "product_name": "Napolitana Sauce 500g",                                "product_code": "HD4000"},
            {"qty": "1", "product_name": "Tommy's Meatballs 500g",                               "product_code": "HD2028"},
            {"qty": "1", "product_name": "Meatballs in Sauce 500g",                              "product_code": "HD2029"},
            {"qty": "1", "product_name": "Beef Cheek Ravioli 375g",                              "product_code": "HD2015"},
            {"qty": "1", "product_name": "Duck Ravioli 375g",                                    "product_code": "HD2007"},
            {"qty": "1", "product_name": "Tortellini Beef 1kg",                                  "product_code": "HD2018"},
            {"qty": "1", "product_name": "Veal Chicken & Sauteed Bacon Tortellini 375g",         "product_code": "HD2002"},
            {"qty": "1", "product_name": "Siciliana Sauce 500g",                                 "product_code": "HD4002"},
            {"qty": "1", "product_name": "FREE Arancini Beef 270g",                              "product_code": "HD1006"},
        ]
    },

    "The Gourmet Meal Pack": {
        "label": "The Gourmet Meal Pack (25 serves • $250.00)",
        "products": [
            {"qty": "1", "product_name": "Harvey Beef Lasagna 1kg",                              "product_code": "HD3000"},
            {"qty": "1", "product_name": "Ricotta Spinach Cannelloni 1kg",                       "product_code": "HD3002"},
            {"qty": "1", "product_name": "Beef Cheek Lasagna 1kg",                               "product_code": "HD3001"},
            {"qty": "1", "product_name": "Beef Cheek Ravioli 375g",                              "product_code": "HD2015"},
            {"qty": "1", "product_name": "Duck Ravioli 375g",                                    "product_code": "HD2007"},
            {"qty": "2", "product_name": "Porcini Mushroom Ravioli 375g",                        "product_code": "HD2001"},
            {"qty": "1", "product_name": "Baked Ricotta Tortellini 375g",                        "product_code": "HD2003"},
            {"qty": "1", "product_name": "Croquettes Pumpkin Feta 270g",                         "product_code": "HD1005"},
            {"qty": "1", "product_name": "Mushroom Arancini 270g",                               "product_code": "HD1001"},
            {"qty": "2", "product_name": "Napolitana Sauce 500g",                                "product_code": "HD4000"},
            {"qty": "1", "product_name": "Siciliana Sauce 500g",                                 "product_code": "HD4002"},
            {"qty": "1", "product_name": "FREE Arancini Cheese 270g",                            "product_code": "HD1000"},
        ]
    },

    "The Busy Life Heat & Eat Relief Pack": {
        "label": "The Busy Life Heat & Eat Relief Pack (24 serves • $205.00)",
        "products": [
            {"qty": "1", "product_name": "Harvey Beef Lasagna 1kg",                              "product_code": "HD3000"},
            {"qty": "1", "product_name": "Ricotta Spinach Cannelloni 1kg",                       "product_code": "HD3002"},
            {"qty": "1", "product_name": "Eight Vegetable Lasagna 1kg",                          "product_code": "HD3003"},
            {"qty": "1", "product_name": "Sicilian Beef Cannelloni with Napolitana 1kg",         "product_code": "HD3008"},
            {"qty": "1", "product_name": "Beef Cheek Lasagna 1kg",                               "product_code": "HD3001"},
            {"qty": "1", "product_name": "Croquettes Pumpkin Feta 270g",                         "product_code": "HD1005"},
            {"qty": "1", "product_name": "Cheese & Spinach Croquettes 270g",                     "product_code": "HD1004"},
            {"qty": "1", "product_name": "Arancini Beef 270g",                                   "product_code": "HD1006"},
            {"qty": "1", "product_name": "FREE Arancini Cheese 270g",                            "product_code": "HD1000"},
        ]
    },

    "The Entertainer Pack": {
        "label": "The Entertainer Pack (32-40 serves • $140.00)",
        "products": [
            {"qty": "2", "product_name": "Spinach & 5 Cheese Arancini Balls 270g",               "product_code": "HD1000"},
            {"qty": "2", "product_name": "Mushroom Arancini Balls 270g",                         "product_code": "HD1001"},
            {"qty": "2", "product_name": "Pumpkin & Feta Croquettes 270g",                       "product_code": "HD1005"},
            {"qty": "2", "product_name": "Harvey Beef Arancini Balls 270g",                      "product_code": "HD1006"},
            {"qty": "2", "product_name": "Cheese & Spinach Croquettes 270g",                     "product_code": "HD1004"},
            {"qty": "1", "product_name": "FREE Cheese Arancini 270g",                            "product_code": "HD1000"},
        ]
    },

    "The Party Pack": {
        "label": "The Party Pack ($70.00)",
        "products": [
            {"qty": "1", "product_name": "Spinach & 5 Cheese Arancini Balls 270g",               "product_code": "HD1000"},
            {"qty": "1", "product_name": "Mushroom Arancini Balls 270g",                         "product_code": "HD1001"},
            {"qty": "1", "product_name": "Harvey Beef Arancini Balls 270g",                      "product_code": "HD1006"},
            {"qty": "1", "product_name": "Pumpkin & Feta Croquettes 270g",                       "product_code": "HD1005"},
            {"qty": "1", "product_name": "Cheese & Spinach Croquettes 270g",                     "product_code": "HD1004"},
        ]
    },

    "The Sauce Pack": {
        "label": "The Sauce Pack (20 serves • $68.00)",
        "products": [
            {"qty": "1", "product_name": "Napolitana Sauce 500g",                                "product_code": "HD4000"},
            {"qty": "1", "product_name": "Primavera Sauce 500g",                                 "product_code": "HD4001"},
            {"qty": "1", "product_name": "Siciliana Sauce 500g",                                 "product_code": "HD4002"},
            {"qty": "1", "product_name": "Traditional Bolognese Sauce 500g",                     "product_code": "HD4004"},
            {"qty": "1", "product_name": "Extra Creamy Carbonara Sauce 500g",                    "product_code": "HD4003"},
        ]
    },

    "The Halal Pack": {
        "label": "The Halal Pack (34 serves • $208.00)",
        "products": [
            {"qty": "1", "product_name": "Beef Cheek Lasagna 1kg",                               "product_code": "HD3001"},
            {"qty": "1", "product_name": "Eight Vegetable Lasagne 1kg",                          "product_code": "HD3003"},
            {"qty": "1", "product_name": "Ricotta & Spinach Cannelloni 1kg",                     "product_code": "HD3002"},
            {"qty": "1", "product_name": "Tortellini Beef 1kg Family Pack",                      "product_code": "HD2018"},
            {"qty": "1", "product_name": "Pumpkin Feta Ravioli 375g",                            "product_code": "HD2006"},
            {"qty": "1", "product_name": "Porcini Mushroom Mascarpone Truffle Ravioli 375g",     "product_code": "HD2001"},
            {"qty": "1", "product_name": "Baked Ricotta Sundried Tomato Tortellini 375g",        "product_code": "HD2003"},
            {"qty": "2", "product_name": "Napolitana Sauce 500g",                                "product_code": "HD4000"},
            {"qty": "1", "product_name": "FREE Spinach & 5 Cheese Arancini Balls 270g",          "product_code": "HD1000"},
        ]
    },

    "Heat + Eat Deluxe Pack": {
        "label": "Heat + Eat Deluxe Pack (31 serves • $285.00)",
        "products": [
            {"qty": "1", "product_name": "Beef Cheek Lasagna 1kg",                               "product_code": "HD3001"},
            {"qty": "1", "product_name": "Harvey Beef Lasagna 1kg",                              "product_code": "HD3000"},
            {"qty": "1", "product_name": "Eight Vegetable Lasagna 1kg",                          "product_code": "HD3003"},
            {"qty": "1", "product_name": "Creamy Bechamel Lasagna 1kg",                          "product_code": "HD3007"},
            {"qty": "1", "product_name": "Sicilian Beef Cannelloni with Napolitana 1kg",         "product_code": "HD3008"},
            {"qty": "1", "product_name": "Porcini Mushroom & Ricotta Cannelloni 1kg",            "product_code": "HD3009"},
            {"qty": "1", "product_name": "Ricotta & Spinach Cannelloni 400g",                    "product_code": ""},
            {"qty": "1", "product_name": "Harvey Beef Lasagna 400g",                             "product_code": ""},
            {"qty": "1", "product_name": "Macaroni & Cheese 400g",                               "product_code": ""},
            {"qty": "1", "product_name": "FREE Mushroom Arancini 270g",                          "product_code": "HD1001"},
        ]
    },

    "The Best of Our Best Meal Pack": {
        "label": "The Best of Our Best Meal Pack (25 serves • $273.00)",
        "products": [
            {"qty": "1", "product_name": "Tommy's Meatballs 1kg",                                "product_code": "HD2027"},
            {"qty": "1", "product_name": "Cheese & Spinach Croquettes 270g",                     "product_code": "HD1004"},
            {"qty": "1", "product_name": "Ricotta & Spinach Cannelloni 1kg",                     "product_code": "HD3002"},
            {"qty": "1", "product_name": "Beef Cheek Lasagna 1kg",                               "product_code": "HD3001"},
            {"qty": "1", "product_name": "Harvey Beef Lasagna 1kg",                              "product_code": "HD3000"},
            {"qty": "1", "product_name": "Porcini Mushroom Mascarpone Truffle Ravioli 375g",     "product_code": "HD2001"},
            {"qty": "1", "product_name": "Beef Cheek & Red Wine Ravioli 1kg",                    "product_code": "HD2032"},
            {"qty": "1", "product_name": "Duck Ravioli Wild Mushroom & Kakadu Plum 375g",        "product_code": "HD2007"},
            {"qty": "2", "product_name": "Napolitana Sauce 500g",                                "product_code": "HD4000"},
            {"qty": "1", "product_name": "Siciliana Sauce 500g",                                 "product_code": "HD4002"},
            {"qty": "1", "product_name": "FREE Spinach & 5 Cheese Arancini 270g",                "product_code": "HD1000"},
        ]
    },

    "Family Feast 4 Course Meal Pack": {
        "label": "Family Feast 4 Course Meal Pack ($142.00)",
        "products": [
            {"qty": "1", "product_name": "Harvey Beef Arancini 270g",                            "product_code": "HD1006"},
            {"qty": "1", "product_name": "Beef Cheek Lasagna 1kg",                               "product_code": "HD3001"},
            {"qty": "1", "product_name": "Baked Ricotta Sundried Tomato Tortellini 375g",        "product_code": "HD2003"},
            {"qty": "1", "product_name": "Veal Chicken & Sauteed Bacon Tortellini 375g",         "product_code": "HD2002"},
            {"qty": "1", "product_name": "Tommy's Tiramisu 500g",                                "product_code": ""},
            {"qty": "1", "product_name": "Extra Creamy Carbonara Sauce 500g",                    "product_code": "HD4003"},
            {"qty": "1", "product_name": "Primavera Sauce 500g",                                 "product_code": "HD4001"},
            {"qty": "1", "product_name": "FREE Cheese & Spinach Croquettes 270g",                "product_code": "HD1004"},
        ]
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# DEAL NAME MATCHING — partial/fuzzy match support
# Jotform se aane wale deal names exactly match nahi karte hamesha
# ─────────────────────────────────────────────────────────────────────────────

def _find_deal(deal_name: str) -> dict | None:
    """
    Deal name se DEALS dict mein match dhundho.
    Exact match pehle, phir partial (case-insensitive).
    """
    if not deal_name:
        return None

    name_clean = deal_name.strip()

    # 1. Exact match
    if name_clean in DEALS:
        return DEALS[name_clean]

    # 2. Case-insensitive exact
    for key, val in DEALS.items():
        if key.lower() == name_clean.lower():
            return val

    # 3. Partial match — deal key found in jotform string ya vice versa
    name_lower = name_clean.lower()
    for key, val in DEALS.items():
        if key.lower() in name_lower or name_lower in key.lower():
            return val

    return None


# ─────────────────────────────────────────────────────────────────────────────
# MAIN PUBLIC FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def resolve_deals(items: list) -> list:
    """
    items list mein jo bhi deal items hain unhe expand karo.

    Har item jo deal hai (product_code starts with 'DEAL' ya product_name
    matches a known deal) woh hata diya jaata hai aur uski jagah
    deal ke individual products insert ho jaate hain.

    Non-deal items as-is rahte hain.

    Args:
        items: order_data['items'] list — dicts with qty, product_name, product_code

    Returns:
        Expanded items list
    """
    if not items:
        return items

    resolved = []
    deal_count = 0

    for item in items:
        product_name = item.get('product_name', '')
        product_code = item.get('product_code', '')
        qty = int(item.get('qty', 1))

        # Deal detect karo — code se ya name se
        is_deal = (
            str(product_code).upper().startswith('DEAL') or
            _find_deal(product_name) is not None
        )

        if is_deal:
            deal = _find_deal(product_name) or _find_deal(product_code)
            if deal:
                deal_count += 1
                logger.info(
                    f"[DEAL RESOLVER] 🎁 Deal detected: '{product_name}' → "
                    f"{len(deal['products'])} products (qty x{qty})"
                )

                # Agar deal ki qty > 1 hai toh har product ki qty multiply karo
                for prod in deal['products']:
                    expanded_qty = int(prod['qty']) * qty
                    resolved.append({
                        'qty': str(expanded_qty),
                        'product_name': prod['product_name'],
                        'product_code': prod['product_code'],
                    })
            else:
                # Deal keyword tha but match nahi mila — as-is rakh do, log karo
                logger.warning(
                    f"[DEAL RESOLVER] ⚠️ Possible deal not matched: '{product_name}' (code: {product_code})"
                )
                resolved.append(item)
        else:
            resolved.append(item)

    if deal_count:
        logger.info(
            f"[DEAL RESOLVER] ✅ {deal_count} deal(s) expanded → "
            f"{len(resolved)} total items"
        )

    return resolved


def get_all_deal_names() -> list:
    """Saare available deal names return karo — debugging ke liye useful"""
    return list(DEALS.keys())


def get_deal_info(deal_name: str) -> dict | None:
    """Ek deal ki info return karo — testing ke liye"""
    return _find_deal(deal_name)