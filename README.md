# SG Rental Shortlister

A personal tool that helps find a condo to rent in Singapore.

It does **not** make decisions or handle tenancy paperwork. It works as a
**shortlister and pricing assistant**:

- Collects rental listings matching my criteria (drive time, budget, size, layout)
- Compares each asking rent against actual signed rental contracts
- Flags listings as fairly priced, above market, or suspiciously cheap
- Removes duplicate listings posted by multiple agents
- Sends a daily Telegram shortlist with direct links to each listing

## Data sources

- **URA Data Service API**: private residential rental contracts (condos, ECs, landed)
- **data.gov.sg**: URA quarterly rental statistics per condo project
- **Rental listing portals**: current listings to be shortlisted

Government data is used under the
[Singapore Open Data Licence](https://data.gov.sg/open-data-licence).

## Usage (pricing engine)

Needs Python 3.10+ and no extra packages.

```bash
# Download the latest market rents (also happens automatically when older than 7 days)
python -m shortlister refresh

# Check a listing: project name, monthly rent, size
python -m shortlister price "26 Newton" --rent 3400 --sqft 550 --study

# Find how a project is named in the market data
python -m shortlister lookup "newton"
```

Example output:

```
[KEEP] 26 Newton  ->  BELOW MEDIAN
  - S$3,400 for 550 sqft = S$6.18 psf
  - 5.2% below project median (S$6.52 psf; range S$6.16-6.92, 13 contracts, 2026-Q2)
  - above S$3,000 target but kept: priced below market
  - has a study (bonus)
  ! benchmark based on only 13 contracts
```

Rents are compared **per square foot**, so unit size is accounted for.
Budget and size rules live in `shortlister/config.py`.

Current limits of the data.gov.sg source: one benchmark per project (not per
bedroom count), and only major projects (100+ units, 10+ contracts a quarter).
Contract-level URA data will refine this once the URA access key is available.

Run tests with `pip install -r requirements-dev.txt && python -m pytest`.

## Status

🚧 Specification agreed (see [SPEC.md](SPEC.md)).

- [x] Pricing engine (data.gov.sg benchmarks)
- [ ] URA contract-level data (waiting for access key)
- [ ] Listing collection (99.co)
- [ ] Drive-time filter (≤25 min off-peak to Tanglin)
- [ ] Telegram bot: daily shortlist + on-demand search

## Disclaimer

Personal, non-commercial project. Price comparisons are indicative only and
are not professional valuation advice.
