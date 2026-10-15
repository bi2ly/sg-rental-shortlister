from . import ninetynine, propertyguru
from .apify import load_file, ninetynine_input, propertyguru_input, run_live, search_input


def normalise(rows):
    """Normalise rows from any supported source (detected per row).
    Returns (listings, [(name, reason) dropped], {listing_id: street})."""
    pg = [r for r in rows if propertyguru.is_propertyguru(r)]
    other = [r for r in rows if not propertyguru.is_propertyguru(r)]
    a, da = propertyguru.normalise(pg)
    b, db = ninetynine.normalise(other)
    streets = {str(r.get("listingId")): propertyguru.street_of(r) for r in pg}
    return a + b, da + db, streets


__all__ = ["load_file", "normalise", "ninetynine_input", "propertyguru_input",
           "run_live", "search_input"]
