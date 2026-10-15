"""Search criteria from SPEC.md. Change values here, not in the logic."""

TARGET_RENT = 3000        # S$/month: always acceptable if other criteria pass
MAX_RENT = 3500           # S$/month: allowed only for a "good deal"
MIN_SQFT = 550           # raised from 500: smaller "1BRs" were often studios
MIN_SQFT_WITH_STUDY = 500 # a unit with a study can't be a hidden studio
REJECT_STUDIOS = True     # need a separate bedroom (bed and living area not shared)
# Agents sometimes list studios as "1 bedroom" (e.g. Lumiere, 506 sqft studio
# tagged 1BR). 1-bedrooms below this size get a "check the floor plan" flag.
STUDIO_CHECK_SQFT = 550   # only matters if MIN_SQFT is lowered again

# Rent per sqft this far below the project's 25th percentile looks like a bait
# listing or a data error, so it gets flagged rather than celebrated.
SUSPICIOUS_BELOW_P25 = 0.20   # 20% under p25

# Fewer signed contracts than this means the benchmark is less reliable.
LOW_CONFIDENCE_CONTRACTS = 15

# How many recent quarters of data to combine per project.
QUARTERS_TO_USE = 4

# --- Search area --------------------------------------------------------------
# From the map agreed on 2026-10-15: West Coast/Queenstown to Bedok/East Coast,
# Harbourfront to Ang Mo Kio. Replaces the earlier drive-time idea.
AREA_BBOX = {"lat_min": 1.262, "lat_max": 1.380, "lng_min": 103.765, "lng_max": 103.935}

# PropertyGuru only searches by area name, so one search per area below.
AREA_KEYWORDS = [
    "Tanglin", "River Valley", "Orchard", "Botanic Gardens", "Bukit Timah", "Farrer Road",
    "Holland", "Queenstown", "Commonwealth", "West Coast", "Bukit Merah", "Tiong Bahru",
    "Harbourfront", "Novena", "Newton", "Balestier", "Toa Payoh", "Bishan", "Ang Mo Kio",
    "Serangoon", "Whampoa", "Kallang", "Geylang", "Katong", "Marine Parade", "East Coast",
    "Siglap", "Bedok", "Tanjong Pagar", "City Hall",
]

# --- Listing sources (Apify) -----------------------------------------------------
PG_ACTOR = "automation-lab/propertyguru-singapore-listings-agent-leads-scraper"
PG_MAX_PAGES_PER_AREA = 3
PG_KEEP_TYPES = {"CONDO", "APT", "EXEC"}   # drop HDB, walk-ups, landed
MAX_RESULTS_PER_RUN = 500            # across all areas (~US$0.50 for a full sweep)
MAX_COST_USD_PER_RUN = 1.0           # hard spending cap sent to Apify (minimum allowed)

# 99.co is now secondary (about 10x the price of PropertyGuru per listing).
NINETYNINE_ACTOR = "sian.agency/99co-property-scraper"
ANCHOR_LATLNG = (1.3048, 103.8237)   # Tanglin Mall, centre of the 99.co radius search
SEARCH_RADIUS_M = 9000
