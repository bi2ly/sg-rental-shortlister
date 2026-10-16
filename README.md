# SG Rental Shortlister

A personal tool that helps find a condo to rent in Singapore.

It does **not** make decisions or handle tenancy paperwork. It works as a
**shortlister and pricing assistant**:

- Collects rental listings matching my criteria (area, budget, size, layout)
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

## Usage (listing collector)

Collects condo rentals through Apify scrapers, removes rooms, walk-ups, HDB,
studios and duplicates, keeps only listings inside the search area, price-checks
every unit and prints a ranked shortlist with direct links.

| Source | Apify actor | Approx. cost |
|---|---|---|
| PropertyGuru (main) | automation-lab/propertyguru-singapore-listings-agent-leads-scraper | ~US$1-2 / 1,000 listings |
| 99.co (optional) | sian.agency/99co-property-scraper | ~US$12 / 1,000 listings |

```bash
cp .env.example .env          # then paste your Apify token into .env

python -m shortlister collect --live                     # PropertyGuru
python -m shortlister collect --live --new-only          # alert only on unseen / cheaper listings
python -m shortlister collect --live --source all        # PropertyGuru + 99.co
python -m shortlister collect --file pg.json 99co.json   # from Apify JSON exports
```

Every live run is capped at US$1 (Apify's minimum cap). Search areas and the
map bounding box live in `shortlister/config.py`.

The shortlist has four sections:
- **Shortlist**: meets the spec (within S$3,000, or S$3,000-3,500 and below market)
- **Worth negotiating**: asking S$3,500-3,800, at least 5% below market, and 650+ sqft (550+ with a study);
  shows the discount needed to reach S$3,500 / S$3,700
- **Needs price check**: S$3,000-3,500 but the project has no market data yet
- **Skipped** (with `--show-skipped`): rejected, with the reason

Lessons from real data: 99.co mixes room rentals into condo results; agents list
studios as 1-bedrooms (1BRs under 550 sqft are flagged "check the floor plan";
minimum 500 sqft);
99.co's own listing URLs 404, so links use `99.co/property/<id>`; PropertyGuru
card data has no coordinates, so buildings are located with OneMap.

## Daily run on GitHub (no server needed)

`.github/workflows/daily-shortlist.yml` runs every day at **07:47 and 19:47 Singapore time**
on GitHub's machines: it sweeps every current PropertyGuru listing in the search
districts (PropertyGuru's own filters keep it to relevant units), filters and
price-checks them, alerts only on listings not sent before or now cheaper, and shows the shortlist on the run's page
(**Actions** tab -> *Daily shortlist* -> latest run). The report is also kept as
a downloadable file for 30 days.

Setup: add your Apify token as a repository secret named `APIFY_TOKEN`
(Settings -> Secrets and variables -> Actions -> New repository secret).
To run it now, open *Daily shortlist* in the Actions tab and click **Run workflow**
(untick "Only listings posted since the last run" for a full sweep).

To receive it on Telegram, also add the secrets `TELEGRAM_BOT_TOKEN` (from
@BotFather) and `TELEGRAM_CHAT_ID` (your own chat ID). Without them the run
still works and the report stays in the Actions tab.

The memory of listings already sent is kept in your Apify account (key-value
store `sg-rental-shortlister`), so it survives even if GitHub's cache is cleared.
It is only updated after Telegram confirms delivery. Building coordinates and
market rents are kept in GitHub's cache (losing them only costs a re-download).

Run tests with `pip install -r requirements-dev.txt && python -m pytest`.

## Status

🚧 Specification agreed (see [SPEC.md](SPEC.md)).

- [x] Pricing engine (data.gov.sg benchmarks)
- [ ] URA contract-level data (waiting for access key)
- [x] Listing collection (99.co via Apify): room filter, dedupe, ranked shortlist
- [x] PropertyGuru as main source, cross-site duplicate merge
- [x] Search-area filter (OneMap building coordinates)
- [x] Twice-daily run on GitHub Actions (07:47 and 19:47 SGT)
- [x] Telegram: daily shortlist sent from GitHub Actions
- [ ] Telegram: on-demand /search

## Disclaimer

Personal, non-commercial project. Price comparisons are indicative only and
are not professional valuation advice.
