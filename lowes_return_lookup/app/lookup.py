import re
from urllib.parse import quote
from bs4 import BeautifulSoup
from .policy import get_return_policy, POLICY_URL

async def lookup_product(query: str):
    # Playwright is intentionally imported here so the app can start even if
    # browser dependencies have not yet been installed.
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise RuntimeError("Playwright is not installed. Run: pip install -r requirements.txt && playwright install chromium")

    search_url = "https://www.lowes.com/search?searchTerm=" + quote(query)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"
        )
        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2500)

        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")

        candidates = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/pd/" in href:
                title = " ".join(a.stripped_strings)
                if title:
                    if href.startswith("/"):
                        href = "https://www.lowes.com" + href
                    candidates.append((href, title))

        # Prefer a result whose visible text contains the exact query.
        q = query.lower().strip()
        candidates.sort(key=lambda x: (q not in x[1].lower(), len(x[1])))

        if not candidates:
            await browser.close()
            return {
                "found": False,
                "query": query,
                "message": "No Lowe's product page was found for this item/model number.",
                "search_url": search_url,
                "policy_url": POLICY_URL
            }

        product_url, _ = candidates[0]
        product_page = await browser.new_page()
        await product_page.goto(product_url, wait_until="domcontentloaded", timeout=30000)
        await product_page.wait_for_timeout(1800)
        product_html = await product_page.content()
        product_text = BeautifulSoup(product_html, "html.parser").get_text(" ", strip=True)

        # Extract Item # and Model # from the rendered product page.
        item_match = re.search(r"Item\s*#\s*([A-Za-z0-9._-]+)", product_text, re.I)
        model_match = re.search(r"Model\s*#\s*([A-Za-z0-9._-]+)", product_text, re.I)

        item_number = item_match.group(1) if item_match else None
        model_number = model_match.group(1) if model_match else None

        # Page title is generally a useful product-name fallback.
        title = await product_page.title()
        title = re.sub(r"\s*\|\s*Lowe'?s.*$", "", title or "", flags=re.I).strip()

        # Try breadcrumbs / structured data for category.
        category = ""
        for selector in [
            '[data-testid*="breadcrumb"]',
            '[aria-label*="breadcrumb" i]',
            'nav'
        ]:
            loc = product_page.locator(selector)
            if await loc.count():
                txt = (await loc.first.inner_text()).strip()
                if txt:
                    category = txt
                    break

        # Try JSON-LD category when available.
        for script in soup.find_all("script", type="application/ld+json"):
            raw = script.get_text(" ", strip=True)
            if '"category"' in raw.lower():
                m = re.search(r'"category"\s*:\s*"([^"]+)"', raw, re.I)
                if m:
                    category = m.group(1)
                    break

        policy = get_return_policy(title, category)
        await product_page.close()
        await browser.close()

        return {
            "found": True,
            "query": query,
            "item_number": item_number,
            "model_number": model_number,
            "product_name": title or "Lowe's product",
            "category": category,
            "product_url": product_url,
            "search_url": search_url,
            "policy_url": POLICY_URL,
            **policy
        }
