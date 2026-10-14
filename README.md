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

## Status

🚧 Specification agreed (see [SPEC.md](SPEC.md)). Implementation not started.

## Disclaimer

Personal, non-commercial project. Price comparisons are indicative only and
are not professional valuation advice.
