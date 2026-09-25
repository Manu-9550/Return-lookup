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

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "en-US,en;q=0.9",
}


# ============================================================
# BASIC HELPERS
# ============================================================

def clean_text(value):
    if not value:
        return ""

    return re.sub(r"\s+", " ", value).strip()


def normalize(value):
    if not value:
        return ""

    return re.sub(
        r"[^A-Z0-9]",
        "",
        value.upper()
    )


def extract_number(text, label):

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


# ============================================================
# EXTRACT LOWE'S PRODUCT LINKS
# ============================================================

def extract_product_links(soup):

    products = []
    seen = set()

    for anchor in soup.find_all(
        "a",
        href=True
    ):

        href = anchor.get(
            "href",
            ""
        ).strip()

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
                anchor.get_text(
                    " ",
                    strip=True
                )
            )
        })

    return products


# ============================================================
# BING SEARCH
# ============================================================

def bing_search(query):

    search_query = (
        f"site:lowes.com/pd/ {query}"
    )

    url = (
        "https://www.bing.com/search"
        f"?q={quote(search_query)}"
    )

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30
        )

        if response.status_code != 200:
            return []

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        products = []

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

            if href in [
                item["url"]
                for item in products
            ]:
                continue

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
# GOOGLE SEARCH
# ============================================================

def google_search(query):

    search_query = (
        f"site:lowes.com/pd/ {query}"
    )

    url = (
        "https://www.google.com/search"
        f"?q={quote(search_query)}"
    )

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30
        )

        if response.status_code != 200:
            return []

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        products = []

        for anchor in soup.find_all(
            "a",
            href=True
        ):

            href = anchor.get(
                "href",
                ""
            )

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

            if href in [
                item["url"]
                for item in products
            ]:
                continue

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
# LOWE'S DIRECT SEARCH
# ============================================================

def lowes_search(query):

    url = (
        f"{LOWES_BASE}/search"
        f"?searchTerm={quote(query)}"
    )

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30
        )

        if response.status_code != 200:
            return []

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        return extract_product_links(
            soup
        )

    except Exception:
        return []


# ============================================================
# SCORE RESULTS
# ============================================================

def score_product(product, query):

    q = normalize(query)

    title = normalize(
        product.get(
            "title",
            ""
        )
    )

    url = normalize(
        product.get(
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

    if q in combined:
        score += 100

    if q in title:
        score += 200

    if "/PD/" in product.get(
        "url",
        ""
    ).upper():
        score += 50

    return score


# ============================================================
# PLAYWRIGHT PRODUCT PAGE
# ============================================================

async def read_lowes_product_page(
    page,
    product_url
):

    try:

        await page.goto(
            product_url,
            wait_until="domcontentloaded",
            timeout=90000
        )

    except Exception:
        # Lowe's sometimes continues loading after
        # the navigation timeout.
        pass

    # Allow dynamic content to render.
    await page.wait_for_timeout(
        8000
    )

    # Try waiting for common product information.
    selectors = [
        "h1",
        '[data-testid*="product"]',
        '[class*="product"]',
    ]

    for selector in selectors:

        try:

            await page.wait_for_selector(
                selector,
                timeout=5000
            )

            break

        except Exception:
            continue

    await page.wait_for_timeout(
        3000
    )

    html = await page.content()

    return html


# ============================================================
# EXTRACT PRODUCT INFORMATION
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
    # PRODUCT NAME
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

        h1 = soup.find("h1")

        if h1:

            product_name = clean_text(
                h1.get_text(
                    " ",
                    strip=True
                )
            )

    if not product_name:

        title = soup.find("title")

        if title:

            product_name = clean_text(
                title.get_text(
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
    # CATEGORY
    # --------------------------------------------------------

    category = ""

    # JSON-LD
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

    # Breadcrumb
    if not category:

        selectors = [
            '[aria-label*="breadcrumb" i]',
            '[data-testid*="breadcrumb" i]',
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

                if value:

                    category = value
                    break

            if category:
                break

    # Product-name fallback
    if not category:

        lower = product_name.lower()

        category_keywords = [
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

        for keyword in category_keywords:

            if keyword in lower:

                category = keyword.title()
                break

    # --------------------------------------------------------
    # EXACT MATCH
    # --------------------------------------------------------

    q = normalize(query)

    item = normalize(
        item_number or ""
    )

    model = normalize(
        model_number or ""
    )

    exact_match = (
        q == item
        or
        q == model
    )

    return {
        "item_number": item_number,
        "model_number": model_number,
        "product_name": product_name,
        "category": category,
        "product_url": product_url,
        "exact_match": exact_match,
    }


# ============================================================
# MAIN LOOKUP
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
                "Please enter an Item # "
                "or Model #."
            ),
            "policy_url": POLICY_URL,
        }

    # --------------------------------------------------------
    # FIND PRODUCT URLs
    # --------------------------------------------------------

    candidates = []

    candidates.extend(
        lowes_search(query)
    )

    candidates.extend(
        bing_search(query)
    )

    candidates.extend(
        google_search(query)
    )

    # Remove duplicates.
    unique = {}

    for candidate in candidates:

        url = candidate.get(
            "url"
        )

        if url:
            unique[url] = candidate

    candidates = list(
        unique.values()
    )

    if not candidates:

        return {
            "found": False,
            "query": query,
            "message": (
                "No Lowe's product page "
                "could be found for this "
                "item/model number."
            ),
            "policy_url": POLICY_URL,
        }

    # Rank.
    candidates.sort(
        key=lambda x:
        score_product(
            x,
            query
        ),
        reverse=True
    )

    # --------------------------------------------------------
    # USE PLAYWRIGHT FOR PRODUCT PAGE
    # --------------------------------------------------------

    from playwright.async_api import (
        async_playwright
    )

    async with async_playwright() as playwright:

        browser = await playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--no-zygote",
                "--disable-blink-features=AutomationControlled",
            ]
        )

        context = await browser.new_context(
            user_agent=USER_AGENT,
            viewport={
                "width": 1366,
                "height": 900
            },
            locale="en-US",
            timezone_id="America/New_York",
            extra_http_headers={
                "Accept-Language":
                    "en-US,en;q=0.9"
            }
        )

        page = await context.new_page()

        best_product = None

        try:

            for candidate in candidates[:5]:

                product_url = candidate["url"]

                try:

                    html = await read_lowes_product_page(
                        page,
                        product_url
                    )

                    if not html:
                        continue

                    product = extract_product_data(
                        html,
                        product_url,
                        query
                    )

                    # Exact model/item match.
                    if product["exact_match"]:

                        best_product = product
                        break

                    # Keep usable fallback.
                    if (
                        best_product is None
                        and product["product_name"]
                    ):

                        best_product = product

                except Exception:
                    continue

        finally:

            await context.close()
            await browser.close()

    # --------------------------------------------------------
    # PRODUCT PAGE COULD NOT BE READ
    # --------------------------------------------------------

    if not best_product:

        return {
            "found": False,
            "query": query,
            "message": (
                "A Lowe's search result was "
                "found, but the product page "
                "could not be read."
            ),
            "policy_url": POLICY_URL,
        }

    # --------------------------------------------------------
    # RETURN POLICY
    # --------------------------------------------------------

    policy = get_return_policy(
        best_product["product_name"],
        best_product["category"]
    )

    # --------------------------------------------------------
    # FINAL RESULT
    # --------------------------------------------------------

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
