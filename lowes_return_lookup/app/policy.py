POLICY_URL = "https://www.lowes.com/l/help/returns-policy"

# Ordered from most specific to general. Keep these rules synchronized with
# Lowe's official policy page before production use.
RULES = [
    (["christmas", "halloween"], "Holiday items", "On or before the day of the holiday", 
     "Christmas and Halloween items must be returned on or before the day of the holiday. Items purchased after the holiday are final sale."),
    (["tree", "trees", "shrub", "shrubs", "perennial", "perennials"], "Trees, shrubs and perennials", "365 days",
     "Receipt required for replacement/refund."),
    (["major appliance", "refrigerator", "refrigerators", "freezer", "freezers", "washer", "washers", "dryer", "dryers",
      "range hood", "dishwasher", "dishwashers", "over-the-range microwave", "cooktop", "wall oven", "washer and dryer pedestal",
      "range"], "Major appliance", "48 hours",
     "Return must be initiated within 48 hours of delivery or store pickup. Original, unopened, undamaged, factory-sealed items may qualify for 30 days; qualifying account/payment methods may also qualify for 30 days."),
    (["air conditioner", "air conditioners", "evaporative cooler"], "Air conditioners / evaporative coolers", "48 hours",
     "Return must be initiated within 48 hours of delivery or store pickup. Certain unopened/factory-sealed items may qualify for 30 days."),
    (["paint sprayer", "paint sprayers"], "Paint sprayer", "48 hours",
     "Certain unopened/factory-sealed items may qualify for 30 days."),
    (["tile saw", "tile saws"], "Tile saw", "48 hours",
     "Certain unopened/factory-sealed items may qualify for 30 days."),
    (["utility vehicle", "golf cart", "go-kart", "motorized bike"], "Motorized recreational/utility vehicle", "48 hours",
     "Special return location/document requirements may apply."),
    (["construction heat"], "Construction heat", "48 hours", "See Lowe's policy for detailed conditions."),
    (["portable generator", "pressure washer", "chainsaw", "pole saw"], "Specified gas-powered outdoor equipment", "48 hours",
     "These items are listed under 48-hour returns and are not eligible for the 30-day credit extension."),
    (["liquid paint"], "Liquid paint", "30 days", ""),
    (["tv", "television", "electronics", "electronic"], "TV / electronics", "30 days", ""),
    (["water heater", "water heaters"], "Water heater", "30 days", ""),
    (["hvac", "heating, ventilating and air-conditioning", "heating ventilation and air conditioning"], "HVAC system", "30 days", ""),
    (["lawn mower", "lawn mowers"], "Lawn mower", "30 days",
     "CRAFTSMAN branded battery/electric outdoor power equipment has a 90-day policy."),
    (["leaf blower", "leaf blowers"], "Leaf blower", "30 days",
     "CRAFTSMAN branded battery/electric outdoor power equipment has a 90-day policy."),
    (["log splitter", "shredder", "snow blower", "tiller", "trimmer", "trimmer attachment", "auger",
      "chipper", "cultivator", "edger", "subcompact tractor", "bonnie plants", "annuals", "house and patio plants"],
     "Specified outdoor power equipment / plants", "30 days",
     "CRAFTSMAN branded battery/electric outdoor power equipment has a 90-day policy. Trees, shrubs and perennials are 365 days."),
    (["craftsman"], "CRAFTSMAN outdoor power equipment", "90 days",
     "Lowe's policy states CRAFTSMAN corded and cordless outdoor power equipment has a 90-day return policy."),
]

def get_return_policy(product_name: str, category: str = "") -> dict:
    text = f"{product_name} {category}".lower()
    # Brand-specific CRAFTSMAN rule should take precedence when the product is
    # clearly outdoor power equipment.
    if "craftsman" in text and any(x in text for x in [
        "mower", "blower", "chainsaw", "trimmer", "edger", "cultivator", "tiller",
        "chipper", "shredder", "splitter", "outdoor power", "snow blower"
    ]):
        return {
            "timeframe": "90 days",
            "policy_category": "CRAFTSMAN outdoor power equipment",
            "reason": "CRAFTSMAN outdoor power equipment",
            "notes": "CRAFTSMAN corded and cordless outdoor power equipment has a 90-day return policy."
        }

    for keywords, policy_category, timeframe, notes in RULES:
        if any(k in text for k in keywords):
            return {
                "timeframe": timeframe,
                "policy_category": policy_category,
                "reason": f"Matched product/category terms: {policy_category}",
                "notes": notes
            }

    return {
        "timeframe": "90 days",
        "policy_category": "Most new, unused merchandise",
        "reason": "No specific Lowe's exception was detected from the product information.",
        "notes": "Most new, unused merchandise can be returned within 90 days with proof of purchase, unless an exception applies."
    }
