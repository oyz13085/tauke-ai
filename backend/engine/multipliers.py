"""
Malaysian F&B demand multipliers for weather, events, and day-of-week.
All values sourced from the Tauke.AI system blueprint.
"""

# Internal category slugs used as dict keys
CAT_BEV_HOT  = "beverage_hot"
CAT_BEV_COLD = "beverage_cold"
CAT_FOOD     = "food"
CAT_DRY      = "dry_goods"

# Map product.category string → internal multiplier category
CATEGORY_MAP: dict[str, str] = {
    "beverage":      CAT_BEV_HOT,
    "beverage_hot":  CAT_BEV_HOT,
    "beverage_cold": CAT_BEV_COLD,
    "bread":         CAT_FOOD,
    "protein":       CAT_FOOD,
    "veg":           CAT_FOOD,
    "food":          CAT_FOOD,
    "dry_goods":     CAT_DRY,
    "uncategorised": CAT_BEV_HOT,   # mamak default assumption
}

# weather_condition → {category → multiplier}
WEATHER_MULTIPLIERS: dict[str, dict[str, float]] = {
    "heavy_rain": {
        CAT_BEV_HOT:  1.40,
        CAT_BEV_COLD: 0.70,
        CAT_FOOD:     1.25,
        CAT_DRY:      1.00,
    },
    "hot_sunny": {
        CAT_BEV_HOT:  0.85,
        CAT_BEV_COLD: 1.55,
        CAT_FOOD:     0.90,
        CAT_DRY:      1.00,
    },
    "normal": {
        CAT_BEV_HOT:  1.00,
        CAT_BEV_COLD: 1.00,
        CAT_FOOD:     1.00,
        CAT_DRY:      1.00,
    },
}

# Special event → overall demand multiplier
EVENT_MULTIPLIERS: dict[str, float] = {
    "um_exam_week":         0.65,
    "um_orientation_week":  1.40,
    "hari_raya_eve_day1_2": 0.20,   # dapur closures; dry_goods override below
    "hari_raya_day3_14":    1.60,
    "cny_day1_2":           0.30,
    "public_holiday":       1.35,
}

# Dry-goods overrides that replace the base EVENT_MULTIPLIERS value
EVENT_DRY_GOODS_OVERRIDES: dict[str, float] = {
    "hari_raya_eve_day1_2": 2.00,
}

# Day-of-week multipliers (Python weekday: Monday=0, Sunday=6)
DOW_MULTIPLIERS: dict[int, float] = {
    0: 1.00,  # Monday
    1: 1.00,  # Tuesday
    2: 1.00,  # Wednesday
    3: 1.00,  # Thursday
    4: 1.25,  # Friday  — weekend surge begins
    5: 1.25,  # Saturday
    6: 1.10,  # Sunday
}
