import re
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

from .policy import get_return_policy, POLICY_URL


LOWES_BASE = "https://www.lowes.com"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/154.0.0.0 Safari/537.36"
)

REQUEST_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/avif,"
        "image/webp,*/*;q=0.8"
    ),
}


def clean_text(value):
    if not value:
        return ""

    return re.sub(r"\s+", " ", value).strip()


def normalize_value(value):
    if not value:
        return ""

    return re.sub(
        r"[^A-Z0-9]",
        "",
        value.upper()
    )


def extract_number(text, label):
    """
    Extract Item # or Model # from page text.
    """

    if not text:
        return None

    patterns = [
        rf"{re.escape(label)}\s*#?\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9._\-/]*)",
        rf"{re.escape(label)}\s+Number\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9._\-/]*)",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:
            return match.group(1).strip()

    return None


def extract_product_links(soup):
    """
    Extract Lowe's /pd/ product URLs.
    """

    products = []
    seen = set()

    for link in soup.find_all("a", href=True):

        href = link.get("href", "").strip()

        if not href:
            continue

        if "/pd/" not in href.lower():
            continue

        href = urljoin(
            LOWES_BASE,
            href
        )

        href = href.split("?")[0]
        href = href.split("#")[0]

        if href in seen:
            continue

        seen.add(href)

        products.append({
            "url": href,
            "title": clean_text(
                link.get_text(
                    " ",
                    strip=True
                )
            )
        })

    return products


# ============================================================
# METHOD 1
# LOWE'S DIRECT SEARCH
# ============================================================

def lowes_direct_search(query):
    """
    Try Lowe's search page using requests.

    This is a fallback because Lowe's search can be
    JavaScript-rendered or protected.
    """

    url = (
        f"{LOWES_BASE}/search"
        f"?searchTerm={quote(query)}"
    )

    try:

        response = requests.get(
            url,
            headers=REQUEST_HEADERS,
            timeout=25,
        )

        if response.status_code != 200:
            return []

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        return extract_product_links(soup)

    except Exception:
        return []


# ============================================================
# METHOD 2
# BING SEARCH
# ============================================================

def bing_search(query):
    """
    Search Bing for Lowe's product pages.

    Example query:

    site:lowes.com/pd/ WRS315SDHZ
    """

    search_query = (
        f"site:lowes.com/pd/ {query}"
    )

    url = (
        "https://www.bing.com/search"
        f"?q={quote(search_query)}"
    )

    products = []

    try:

        response = requests.get(
            url,
            headers=REQUEST_HEADERS,
            timeout=25,
        )

        if response.status_code != 200:
            return []

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        # Normal Bing result links
        for result in soup.select("li.b_algo"):

            anchor = result.find(
                "a",
                href=True
            )

            if not anchor:
                continue

            href = anchor.get("href", "")

            if "lowes.com/pd/" not in href.lower():
                continue

            href = href.split("?")[0]
            href = href.split("#")[0]

            if href not in [
                x["url"] for x in products
            ]:

                products.append({
                    "url": href,
                    "title": clean_text(
                        anchor.get_text(
                            " ",
                            strip=True
                        )
                    )
                })

        # Additional fallback:
        # scan all anchors.
        if not products:

            for anchor in soup.find_all(
                "a",
                href=True
            ):

                href = anchor.get(
                    "href",
                    ""
                )

                if "lowes.com/pd/" not in href.lower():
                    continue

                href = href.split("?")[0]
                href = href.split("#")[0]

                if href not in [
                    x["url"] for x in products
                ]:

                    products.append({
                        "url": href,
                        "title": clean_text(
                            anchor.get_text(
                                " ",
                                strip=True
                            )
                        )
                    })

        return products

    except Exception:
        return []


# ============================================================
# METHOD 3
# GOOGLE SEARCH FALLBACK
# ============================================================

def google_search(query):
    """
    Additional search-engine fallback.

    Searches specifically for Lowe's product pages.
    """

    search_query = (
        f"site:lowes.com/pd/ {query}"
    )

    url = (
        "https://www.google.com/search"
        f"?q={quote(search_query)}"
    )

    products = []

    try:

        response = requests.get(
            url,
            headers=REQUEST_HEADERS,
            timeout=25,
        )

        if response.status_code != 200:
            return []

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        for anchor in soup.find_all(
            "a",
            href=True
        ):

            href = anchor.get(
                "href",
                ""
            )

            # Google sometimes wraps URLs.
            if "/url?q=" in href:

                href = href.split(
                    "/url?q=",
                    1
                )[1]

                href = href.split(
                    "&",
                    1
                )[0]

            if "lowes.com/pd/" not in href.lower():
                continue

            href = href.split("?")[0]
            href = href.split("#")[0]

            if href not in [
                x["url"] for x in products
            ]:

                products.append({
                    "url": href,
                    "title": clean_text(
                        anchor.get_text(
                            " ",
                            strip=True
                        )
                    )
                })

        return products

    except Exception:
        return []


# ============================================================
# SCORE SEARCH RESULTS
# ============================================================

def score_candidate(candidate, query):
    """
    Rank candidate Lowe's pages.

    Exact model/item number matches receive
    a very high score.
    """

    query_normalized = normalize_value(
        query
    )

    title = normalize_value(
        candidate.get(
            "title",
            ""
        )
    )

    url = normalize_value(
        candidate.get(
            "url",
            ""
        )
    )

    combined = (
        title
        + " "
        + url
    )

    score = 0

    # Exact query occurrence
    if query_normalized in combined:
        score += 200

    # Product page
    if "/PD/" in candidate.get(
        "url",
        ""
    ).upper():

        score += 50

    # Model number in title
    if query_normalized in title:
        score += 300

    return score


# ============================================================
# EXTRACT PRODUCT PAGE
# ============================================================

def extract_product_data(
    html,
    product_url,
    query
):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    text = clean_text(
        soup.get_text(
            " ",
            strip=True
        )
    )

    # --------------------------------------------------------
    # TITLE
    # --------------------------------------------------------

    product_name = ""

    og_title = soup.find(
        "meta",
        property="og:title"
    )

    if og_title:

        product_name = clean_text(
            og_title.get(
                "content",
                ""
            )
        )

    if not product_name:

        title_tag = soup.find(
            "title"
        )

        if title_tag:

            product_name = clean_text(
                title_tag.get_text(
                    " ",
                    strip=True
                )
            )

    product_name = re.sub(
        r"\s*\|\s*Lowe'?s.*$",
        "",
        product_name,
        flags=re.IGNORECASE
    ).strip()

    # --------------------------------------------------------
    # ITEM NUMBER
    # --------------------------------------------------------

    item_number = extract_number(
        text,
        "Item"
    )

    # --------------------------------------------------------
    # MODEL NUMBER
    # --------------------------------------------------------

    model_number = extract_number(
        text,
        "Model"
    )

    # --------------------------------------------------------
    # JSON-LD
    # --------------------------------------------------------

    category = ""

    for script in soup.find_all(
        "script",
        type="application/ld+json"
    ):

        raw = script.get_text(
            " ",
            strip=True
        )

        if not raw:
            continue

        match = re.search(
            r'"category"\s*:\s*"([^"]+)"',
            raw,
            re.IGNORECASE
        )

        if match:

            category = clean_text(
                match.group(1)
            )

            if category:
                break

    # --------------------------------------------------------
    # BREADCRUMB FALLBACK
    # --------------------------------------------------------

    if not category:

        selectors = [
            '[aria-label*="breadcrumb" i]',
            '[data-testid*="breadcrumb" i]',
            "nav"
        ]

        for selector in selectors:

            elements = soup.select(
                selector
            )

            for element in elements:

                value = clean_text(
                    element.get_text(
                        " ",
                        strip=True
                    )
                )

                if (
                    value
                    and len(value) < 500
                ):

                    category = value
                    break

            if category:
                break

    # --------------------------------------------------------
    # PRODUCT NAME CATEGORY FALLBACK
    # --------------------------------------------------------

    if not category:

        lower_name = product_name.lower()

        categories = [
            "refrigerator",
            "freezer",
            "dishwasher",
            "washer",
            "dryer",
            "range",
            "oven",
            "microwave",
            "air conditioner",
            "lawn mower",
            "leaf blower",
            "chainsaw",
            "pressure washer",
            "generator",
            "television",
            "tv",
            "water heater",
            "paint",
            "tile saw",
        ]

        for keyword in categories:

            if keyword in lower_name:

                category = keyword.title()
                break

    # --------------------------------------------------------
    # EXACT MATCH
    # --------------------------------------------------------

    query_normalized = normalize_value(
        query
    )

    item_normalized = normalize_value(
        item_number or ""
    )

    model_normalized = normalize_value(
        model_number or ""
    )

    exact_match = (
        query_normalized == item_normalized
        or
        query_normalized == model_normalized
    )

    return {
        "item_number": item_number,
        "model_number": model_number,
        "product_name": product_name,
        "category": category,
        "product_url": product_url,
        "exact_match": exact_match,
        "page_text": text,
    }


# ============================================================
# FETCH PRODUCT PAGE
# ============================================================

def fetch_product_page(
    product_url
):

    try:

        response = requests.get(
            product_url,
            headers=REQUEST_HEADERS,
            timeout=30,
        )

        if response.status_code != 200:
            return None

        return response.text

    except Exception:

        return None


# ============================================================
# MAIN LOOKUP FUNCTION
# ============================================================

async def lookup_product(query):

    query = clean_text(
        query
    )

    if not query:

        return {
            "found": False,
            "query": "",
            "message": (
                "Please enter a Lowe's "
                "Item # or Model #."
            ),
            "policy_url": POLICY_URL,
        }

    candidates = []

    # ========================================================
    # METHOD 1 — LOWE'S DIRECT SEARCH
    # ========================================================

    candidates.extend(
        lowes_direct_search(
            query
        )
    )

    # ========================================================
    # METHOD 2 — BING
    # ========================================================

    candidates.extend(
        bing_search(
            query
        )
    )

    # ========================================================
    # METHOD 3 — GOOGLE
    # ========================================================

    candidates.extend(
        google_search(
            query
        )
    )

    # ========================================================
    # REMOVE DUPLICATES
    # ========================================================

    unique = {}

    for candidate in candidates:

        url = candidate.get(
            "url"
        )

        if not url:
            continue

        unique[url] = candidate

    candidates = list(
        unique.values()
    )

    # ========================================================
    # NO SEARCH RESULT
    # ========================================================

    if not candidates:

        return {
            "found": False,
            "query": query,
            "message": (
                "No Lowe's product page could "
                "be found for this item/model number."
            ),
            "policy_url": POLICY_URL,
        }

    # ========================================================
    # RANK RESULTS
    # ========================================================

    candidates.sort(
        key=lambda candidate:
        score_candidate(
            candidate,
            query
        ),
        reverse=True
    )

    # ========================================================
    # CHECK UP TO 5 PRODUCT PAGES
    # ========================================================

    best_product = None

    for candidate in candidates[:5]:

        product_url = candidate.get(
            "url"
        )

        if not product_url:
            continue

        html = fetch_product_page(
            product_url
        )

        if not html:
            continue

        product = extract_product_data(
            html,
            product_url,
            query
        )

        # Exact match = stop immediately
        if product["exact_match"]:

            best_product = product
            break

        # Otherwise keep first usable result
        if (
            best_product is None
            and product["product_name"]
        ):

            best_product = product

    # ========================================================
    # NOTHING USABLE
    # ========================================================

    if not best_product:

        return {
            "found": False,
            "query": query,
            "message": (
                "A Lowe's search result was found, "
                "but the product page could not "
                "be read."
            ),
            "policy_url": POLICY_URL,
        }

    # ========================================================
    # APPLY RETURN POLICY
    # ========================================================

    policy = get_return_policy(
        best_product["product_name"],
        best_product["category"]
    )

    # ========================================================
    # FINAL RESPONSE
    # ========================================================

    return {
        "found": True,

        "query": query,

        "item_number": (
            best_product["item_number"]
        ),

        "model_number": (
            best_product["model_number"]
        ),

        "product_name": (
            best_product["product_name"]
            or "Lowe's Product"
        ),

        "category": (
            best_product["category"]
        ),

        "product_url": (
            best_product["product_url"]
        ),

        "policy_url": POLICY_URL,

        **policy,
    }
