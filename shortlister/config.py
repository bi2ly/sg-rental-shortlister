"""Search criteria from SPEC.md. Change values here, not in the logic."""

TARGET_RENT = 3000        # S$/month: always acceptable if other criteria pass
MAX_RENT = 3500           # S$/month: allowed only for a "good deal"
MIN_SQFT = 500

# Rent per sqft this far below the project's 25th percentile looks like a bait
# listing or a data error, so it gets flagged rather than celebrated.
SUSPICIOUS_BELOW_P25 = 0.20   # 20% under p25

# Fewer signed contracts than this means the benchmark is less reliable.
LOW_CONFIDENCE_CONTRACTS = 15

# How many recent quarters of data to combine per project.
QUARTERS_TO_USE = 4
