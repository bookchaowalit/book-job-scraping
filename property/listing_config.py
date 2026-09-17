"""Small, dependency-free helpers shared by property collection jobs."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


TYPE_ALIASES = {
    "condo": "condo_rent_bkk",
    "condo_rent": "condo_rent_bkk",
    "condo_sale": "condo_sale_bkk",
    "house_sale": "house_sale_bkk",
    "house_rent": "house_rent_bkk",
    "townhouse_sale": "townhouse_bkk",
    "land_sale": "land_sale_bkk",
}

PROPERTY_SOURCE_HOSTS = {
    "ddproperty.com": "ddproperty",
    "propertyhub.in.th": "propertyhub",
    "renthub.in.th": "renthub",
    "ennxo.com": "ennxo",
    "livinginsider.com": "livinginsider",
    "zmyhome.com": "zmyhome",
    "meezub.com": "meezub",
    "dotproperty.co.th": "dotproperty",
    "baania.com": "baania",
    "tgcondo.com": "tgcondo",
}

# Sources accepted by the user-provided property export importer.  These
# domains are intentionally separate from PROPERTY_SOURCE_HOSTS: adding a
# portal here does not silently widen any scheduled scraper or search
# fallback.  A source still has to be opened by the user and exported as a
# public row before the importer will accept it.
PROPERTY_CAPTURE_SOURCE_HOSTS = {
    "propertyhub.in.th": "propertyhub",
    "renthub.in.th": "renthub",
    "dotproperty.co.th": "dotproperty",
    "baania.com": "baania",
    "tgcondo.com": "tgcondo",
    "zmyhome.com": "zmyhome",
    "meezub.com": "meezub",
    "ennxo.com": "ennxo",
    "livinginsider.com": "livinginsider",
    "kaidee.com": "kaidee",
}


def resolve_listing_type(value: str, known_types: set[str] | None = None) -> str:
    """Resolve scheduler shorthand and fail closed for an unknown type."""

    resolved = TYPE_ALIASES.get(value, value)
    if known_types is not None and resolved not in known_types:
        raise ValueError(f"unknown property listing type: {value}")
    return resolved


def build_page_url(url: str, page: int) -> str:
    """Add a 1-based page query without dropping existing query parameters."""

    if page < 1:
        raise ValueError("page must be >= 1")
    if page == 1:
        return url
    parsed = urlsplit(url)
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key != "page"]
    query.append(("page", str(page)))
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


def property_source_platform(url: str) -> str:
    """Return an allowlisted property source for a URL, or an empty string."""

    host = (urlsplit(str(url or "")).hostname or "").lower().removeprefix("www.")
    for domain, platform in PROPERTY_SOURCE_HOSTS.items():
        if host == domain or host.endswith(f".{domain}"):
            return platform
    return ""
