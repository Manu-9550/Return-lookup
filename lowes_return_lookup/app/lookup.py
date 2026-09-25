import re
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

from .policy import get_return_policy, POLICY_URL


LOWES_BASE = "https://www.lowes.com"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/154.0.0.0 Safari/537.36"
)


def clean_text(value: str) -> str:
    """Normalize whitespace."""
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def normalize_value(value: str) -> str:
    """Normalize item/model numbers for comparison."""
    if not value:
        return ""
    return re.sub(r"[^a-zA-Z0-9]", "", value).upper()


def extract_number(text: str, label: str):
    """
    Extract Item # or Model # from page text.
    """
    if not text:
        return None

    pattern = rf"{re.escape(label)}\s*#?\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9._\-/]*)"

    match = re.search(pattern, text, re.IGNORECASE)

    if match:
        return match.group(1).strip()

    return None


def extract_product_links(soup: BeautifulSoup):
    """
    Extract Lowe's product (/pd/) links from a page.
    """

    results = []
    seen = set()

    for a in soup.find_all("a", href=True):

        href = a.get("href", "").strip()

        if not href:
            continue

        # Lowe's product pages use /pd/
        if "/pd/" not in href:
            continue

        href = urljoin(LOWES_BASE, href)

        # Remove query parameters/fragments.
        href = href.split("?")[0].split("#")[0]

        if href in seen:
            continue

        seen.add(href)

        title = clean_text(a.get_text(" ", strip=True))

        results.append({
            "url": href,
            "title": title
        })

    return results


async def create_browser(playwright):
    """
    Create a Chromium browser suitable for Render/Docker.
    """

    browser = await playwright.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--no-zygote",
            "--disable-blink-features=AutomationControlled",
        ],
    )

    return browser


async def get_page(playwright, browser):
    """
    Create a browser page with realistic headers.
    """

    context = await browser.new_context(
        user_agent=USER_AGENT,
        viewport={
            "width": 1366,
            "height": 900,
        },
        locale="en-US",
        timezone_id="America/New_York",
        extra_http_headers={
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": (
                "text/html,application/xhtml+xml,"
                "application/xml;q=0.9,image/avif,"
                "image/webp,*/*;q=0.8"
            ),
        },
    )

    page = await context.new_page()

    return context, page


async def search_lowes(page, query: str):
    """
    Search Lowe's using its public search page.

    We intentionally use several attempts because Lowe's search
    results are dynamically rendered.
    """

    search_url = (
        f"{LOWES_BASE}/search?searchTerm={quote(query)}"
    )

    try:

        await page.goto(
            search_url,
            wait_until="domcontentloaded",
            timeout=60000,
        )

    except Exception:
        # Continue and inspect whatever page was returned.
        pass

    # Give Lowe's JavaScript time to populate results.
    await page.wait_for_timeout(5000)

    # Wait for possible product links.
    try:

        await page.wait_for_selector(
            'a[href*="/pd/"]',
            timeout=15000,
        )

    except Exception:
        pass

    # Small additional delay for dynamically loaded results.
    await page.wait_for_timeout(2500)

    html = await page.content()

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    links = extract_product_links(soup)

    return search_url, links


def score_candidate(candidate, query):
    """
    Score a Lowe's product candidate.

    Exact model/item number matches are preferred.
    """

    query_normalized = normalize_value(query)

    text = normalize_value(
        candidate.get("title", "")
        + " "
        + candidate.get("url", "")
    )

    score = 0

    if query_normalized and query_normalized in text:
        score += 100

    # Model numbers are usually longer and more distinctive.
    if len(query_normalized) >= 6:
        score += 10

    # Prefer actual product pages.
    if "/pd/" in candidate.get("url", ""):
        score += 20

    return score


async def inspect_product_page(page, product_url, query):
    """
    Open the Lowe's product page and extract product information.
    """

    try:

        await page.goto(
            product_url,
            wait_until="domcontentloaded",
            timeout=60000,
        )

    except Exception:
        # The page may still have loaded enough information.
        pass

    # Allow product information to render.
    await page.wait_for_timeout(4000)

    html = await page.content()

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    text = clean_text(
        soup.get_text(
            " ",
            strip=True,
        )
    )

    # ---------------------------------------------------------
    # ITEM NUMBER
    # ---------------------------------------------------------

    item_number = extract_number(
        text,
        "Item",
    )

    # ---------------------------------------------------------
    # MODEL NUMBER
    # ---------------------------------------------------------

    model_number = extract_number(
        text,
        "Model",
    )

    # ---------------------------------------------------------
    # PRODUCT TITLE
    # ---------------------------------------------------------

    product_name = ""

    # Try OpenGraph title first.
    og_title = soup.find(
        "meta",
        property="og:title",
    )

    if og_title:
        product_name = clean_text(
            og_title.get("content", "")
        )

    # Try normal HTML title.
    if not product_name:

        title_tag = soup.find("title")

        if title_tag:
            product_name = clean_text(
                title_tag.get_text(
                    " ",
                    strip=True,
                )
            )

    # Remove Lowe's suffix.
    product_name = re.sub(
        r"\s*\|\s*Lowe'?s.*$",
        "",
        product_name,
        flags=re.IGNORECASE,
    ).strip()

    # ---------------------------------------------------------
    # CATEGORY
    # ---------------------------------------------------------

    category = ""

    # First inspect JSON-LD from the PRODUCT PAGE.
    # The previous version accidentally inspected the search page.
    scripts = soup.find_all(
        "script",
        type="application/ld+json",
    )

    for script in scripts:

        raw = script.get_text(
            " ",
            strip=True,
        )

        if not raw:
            continue

        # Category field.
        category_match = re.search(
            r'"category"\s*:\s*"([^"]+)"',
            raw,
            re.IGNORECASE,
        )

        if category_match:

            category = clean_text(
                category_match.group(1)
            )

            if category:
                break

    # ---------------------------------------------------------
    # BREADCRUMBS
    # ---------------------------------------------------------

    if not category:

        breadcrumb_selectors = [
            '[aria-label*="breadcrumb" i]',
            '[data-testid*="breadcrumb" i]',
            'nav',
        ]

        for selector in breadcrumb_selectors:

            try:

                elements = soup.select(selector)

                for element in elements:

                    breadcrumb_text = clean_text(
                        element.get_text(
                            " ",
                            strip=True,
                        )
                    )

                    if (
                        breadcrumb_text
                        and len(breadcrumb_text) < 500
                    ):
                        category = breadcrumb_text
                        break

                if category:
                    break

            except Exception:
                continue

    # ---------------------------------------------------------
    # FALLBACK CATEGORY FROM PRODUCT NAME
    # ---------------------------------------------------------

    if not category:

        name_lower = product_name.lower()

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

            if keyword in name_lower:

                category = keyword.title()
                break

    # ---------------------------------------------------------
    # EXTRA VALIDATION
    # ---------------------------------------------------------

    query_normalized = normalize_value(query)

    item_normalized = normalize_value(
        item_number or ""
    )

    model_normalized = normalize_value(
        model_number or ""
    )

    exact_match = False

    if query_normalized:

        if query_normalized == item_normalized:
            exact_match = True

        if query_normalized == model_normalized:
            exact_match = True

    return {
        "item_number": item_number,
        "model_number": model_number,
        "product_name": product_name,
        "category": category,
        "product_url": product_url,
        "exact_match": exact_match,
        "page_text": text,
    }


async def lookup_product(query: str):

    query = clean_text(query)

    if not query:

        return {
            "found": False,
            "query": query,
            "message": "Enter an item number or model number.",
            "policy_url": POLICY_URL,
        }

    try:

        from playwright.async_api import async_playwright

    except ImportError:

        raise RuntimeError(
            "Playwright is not installed. "
            "Run: pip install -r requirements.txt "
            "&& playwright install chromium"
        )

    search_url = (
        f"{LOWES_BASE}/search?searchTerm={quote(query)}"
    )

    async with async_playwright() as playwright:

        browser = await create_browser(
            playwright
        )

        context, page = await get_page(
            playwright,
            browser,
        )

        try:

            # -------------------------------------------------
            # STEP 1 — SEARCH LOWE'S
            # -------------------------------------------------

            search_url, candidates = await search_lowes(
                page,
                query,
            )

            # -------------------------------------------------
            # STEP 2 — IF SEARCH LINKS WERE NOT FOUND,
            # TRY A SECOND SEARCH FORMAT
            # -------------------------------------------------

            if not candidates:

                alternate_url = (
                    f"{LOWES_BASE}/search?"
                    f"searchTerm={quote(query)}"
                    f"&sortMethod=sortBy_featured"
                )

                try:

                    await page.goto(
                        alternate_url,
                        wait_until="domcontentloaded",
                        timeout=60000,
                    )

                except Exception:
                    pass

                await page.wait_for_timeout(
                    5000
                )

                try:

                    await page.wait_for_selector(
                        'a[href*="/pd/"]',
                        timeout=12000,
                    )

                except Exception:
                    pass

                await page.wait_for_timeout(
                    2000
                )

                html = await page.content()

                soup = BeautifulSoup(
                    html,
                    "html.parser",
                )

                candidates = extract_product_links(
                    soup
                )

            # -------------------------------------------------
            # STEP 3 — NO PRODUCTS FOUND
            # -------------------------------------------------

            if not candidates:

                return {
                    "found": False,
                    "query": query,
                    "message": (
                        "Lowe's search did not return a "
                        "product page for this item/model number."
                    ),
                    "search_url": search_url,
                    "policy_url": POLICY_URL,
                }

            # -------------------------------------------------
            # STEP 4 — RANK SEARCH RESULTS
            # -------------------------------------------------

            candidates.sort(
                key=lambda candidate: score_candidate(
                    candidate,
                    query,
                ),
                reverse=True,
            )

            # Inspect several candidates instead of blindly
            # choosing the first one.
            candidates_to_check = candidates[:5]

            best_product = None

            product_context = None

            for candidate in candidates_to_check:

                product_url = candidate["url"]

                try:

                    product_context = await context.new_page()

                    product_data = (
                        await inspect_product_page(
                            product_context,
                            product_url,
                            query,
                        )
                    )

                    # Exact item/model match gets priority.
                    if product_data["exact_match"]:

                        best_product = product_data
                        break

                    # Keep the first valid product as fallback.
                    if (
                        best_product is None
                        and product_data["product_name"]
                    ):
                        best_product = product_data

                except Exception:
                    continue

                finally:

                    if product_context:

                        try:
                            await product_context.close()
                        except Exception:
                            pass

                        product_context = None

            # -------------------------------------------------
            # STEP 5 — NO VALID PRODUCT PAGE
            # -------------------------------------------------

            if not best_product:

                return {
                    "found": False,
                    "query": query,
                    "message": (
                        "Lowe's product pages were found, "
                        "but the product information could "
                        "not be extracted."
                    ),
                    "search_url": search_url,
                    "policy_url": POLICY_URL,
                }

            # -------------------------------------------------
            # STEP 6 — APPLY RETURN POLICY
            # -------------------------------------------------

            policy = get_return_policy(
                best_product["product_name"],
                best_product["category"],
            )

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
                    or "Lowe's product"
                ),

                "category": (
                    best_product["category"]
                ),

                "product_url": (
                    best_product["product_url"]
                ),

                "search_url": search_url,

                "policy_url": POLICY_URL,

                **policy,
            }

        finally:

            try:
                await context.close()
            except Exception:
                pass

            try:
                await browser.close()
            except Exception:
                pass
