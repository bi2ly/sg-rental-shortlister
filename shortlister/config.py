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

# --- Listing search (Apify 99.co scraper) ------------------------------------
ANCHOR_LATLNG = (1.3048, 103.8237)   # Tanglin Mall
SEARCH_RADIUS_M = 8000               # rough stand-in for 25 min off-peak drive
MAX_RESULTS_PER_RUN = 60             # scraper is billed per listing returned
MAX_COST_USD_PER_RUN = 1.0           # hard spending cap sent to Apify
