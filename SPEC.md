# SG Rental Shortlister — Specification

## Purpose

A personal agent that **shortlists condo rentals in Singapore** and checks whether
each asking rent is fair. It does **not** make decisions, contact agents, or handle
tenancy documents. The final choice always stays with me.

## Search criteria

| Criterion | Rule |
|---|---|
| Property type | Whole-unit **condo only** (no HDB, no room rentals) |
| Location | Within **25 minutes off-peak driving** to Tanglin |
| Budget | Target **S$3,000/month**; up to **S$3,500** only if it is a "good deal" |
| Size | Minimum **500 sqft** |
| Layout | 1 bedroom minimum; **1 bedroom + study** preferred (ranked higher) |
| Condition | Well maintained (see scoring below) |

## Definition of a "good deal"

A listing between S$3,000 and S$3,500 is kept only if at least one is true:

1. Asking rent is **below the recent median** of signed rents for similar units
   (same project, similar size, last 12 months), or
2. It offers **clearly more space for the price**: rent per sqft is below the
   median for comparable units in the same project or nearby projects.

Listings at or under S$3,000 are always kept if they meet the other criteria.

## Pricing data

- **URA Data Service API** (`PMI_Resi_Rental`): private residential rental
  contracts for the past 3 years, used as the main fair-price benchmark.
- **data.gov.sg**: URA quarterly rental statistics per project (median,
  25th and 75th percentile), used as a fallback when contract data is thin.

The URA access key is stored in a local `.env` file and is **never committed**.

## Listings data

- A **99.co** rental scraper (via Apify) pulls current condo rental listings
  matching the filters above.
- Each listing must keep its **direct link** so I can open it immediately.

## Processing pipeline

1. **Collect**: fetch condo rental listings matching budget and size filters.
2. **Filter**: drop listings over S$3,500, under 500 sqft, non-condo, or beyond
   25 minutes off-peak drive to Tanglin.
3. **Deduplicate**: merge the same unit posted by several agents (same project,
   size, floor range and similar rent); keep the cheapest version.
4. **Price check**: compare each listing with URA signed rents for similar units.
5. **Score and rank** (see below).
6. **Explain**: write a short reason for each pick.
7. **Deliver** via Telegram.

## Drive time

- Measured **off-peak** from each condo to Tanglin.
- Calculated once per condo project and cached, since off-peak times are stable.
- Preferred routing source: **OneMap** (Singapore government, free). Fallback:
  another routing API if OneMap is unsuitable.

## Scoring (highest first)

| Factor | Effect |
|---|---|
| Rent vs. market median | Below median ranks higher; the further below, the better |
| Rent per sqft | Lower ranks higher |
| Layout | 1 bedroom + study gets a bonus |
| Build year | Newer projects rank higher |
| Listing quality | Renovation mentioned, multiple photos → bonus |
| Red flags | No photos, rent suspiciously far below market (possible bait), stale listing → flagged |

## Output format

Each shortlisted listing shows:

- Project name and **direct link**
- Monthly rent, size (sqft), rent per sqft
- Rent vs. market: e.g. "8% below recent median"
- Layout (1BR / 1BR + study), build year
- Off-peak drive time to Tanglin
- One or two lines explaining why it was picked, plus any flags

## Delivery

- **Telegram bot**
- **Daily**: one shortlist message every morning with new or changed listings
- **On demand**: commands such as `/search` to run a fresh search at any time,
  optionally with temporary overrides (e.g. a different budget)

## Out of scope

- HDB flats and room rentals (may be added later)
- Contacting agents or landlords
- Tenancy agreements, legal or financial documents
- Making the final decision

## Status

Specification agreed. Implementation not started.
