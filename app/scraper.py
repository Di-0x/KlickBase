import html
import json
import logging
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}

_LABEL_YEAR = re.compile(r"ann[eé]e|sortie|release|year", re.I)
_LABEL_THEME = re.compile(r"th[eè]me|theme|collection|s[eé]rie|serie", re.I)
_LABEL_PIECES = re.compile(r"pi[eè]ce|piece|part|brique|brick|element", re.I)


def _find_labeled_value(soup: BeautifulSoup, label_re: re.Pattern) -> str | None:
    """Search for a value associated with a matching label in common HTML structures."""
    # dl > dt / dd
    for dt in soup.find_all("dt"):
        if label_re.search(dt.get_text()):
            dd = dt.find_next_sibling("dd")
            if dd:
                return dd.get_text(strip=True)

    # table: label cell followed by value cell
    for td in soup.find_all(["td", "th"]):
        if label_re.search(td.get_text()):
            sibling = td.find_next_sibling(["td", "th"])
            if sibling:
                return sibling.get_text(strip=True)

    # div / span with a label class / data attribute
    for elem in soup.find_all(class_=re.compile(r"label|key|title|header", re.I)):
        if label_re.search(elem.get_text()):
            val = elem.find_next_sibling()
            if val:
                return val.get_text(strip=True)
            parent = elem.parent
            if parent:
                siblings = [s for s in parent.children if s != elem and hasattr(s, "get_text")]
                if siblings:
                    return siblings[0].get_text(strip=True)

    return None


def _extract_figures(soup: BeautifulSoup) -> int | None:
    """Extract the number of figures by looking for <strong>Figures: </strong> in the page."""
    for strong in soup.find_all("strong"):
        if re.search(r"figures?\s*:", strong.get_text(), re.I):
            next_node = strong.next_sibling
            if next_node:
                m = re.search(r"\d+", str(next_node))
                if m:
                    return int(m.group())
            # Fallback: scan parent text after the label
            parent_text = strong.parent.get_text()
            after = parent_text[parent_text.lower().find("figure"):].replace(strong.get_text(), "", 1)
            m = re.search(r"\d+", after)
            if m:
                return int(m.group())
    return None


def _extract_int(text: str | None) -> int | None:
    if not text:
        return None
    m = re.search(r"\d+", text)
    return int(m.group()) if m else None


def _extract_year(text: str | None) -> int | None:
    if not text:
        return None
    m = re.search(r"\b(19[7-9]\d|20[0-4]\d)\b", text)
    return int(m.group()) if m else None


KLICKYPEDIA_BASE = "https://www.klickypedia.com"

# Set pages are titled like "Playmobil 72030 - Astronaut"
_SET_TITLE_RE = re.compile(r"playmobil\s*#?\s*(\d{3,6}[A-Za-z]?)\s*(?:[-–—:]\s*(.*))?", re.I)


def _parse_set_title(text: str | None) -> tuple[str | None, str | None]:
    """Extract (set_number, clean_name) from a title like 'Playmobil 72030 - Astronaut'."""
    if not text:
        return None, None
    m = _SET_TITLE_RE.search(text)
    if not m:
        return None, None
    name = (m.group(2) or "").strip() or None
    return m.group(1), name


def search_klickypedia(set_number: str) -> list[dict]:
    """Search klickypedia.com for a set number.

    Returns candidates as [{"url", "title", "number"}], where "number" is the
    set number parsed from the result title — URL slugs are unreliable: several
    sets can share the same slug prefix, and slugs sometimes contain typos.
    """
    candidates: list[dict] = []
    seen: set[str] = set()

    def _add(url: str, title: str):
        url = url.split("#")[0].split("?")[0]
        if "/sets/" not in url or url.rstrip("/").endswith("/sets"):
            return
        if url in seen:
            # A result can appear twice (thumbnail link without text + title link)
            if title:
                for c in candidates:
                    if c["url"] == url and not c["title"]:
                        c["title"] = title
                        c["number"] = _parse_set_title(title)[0]
            return
        seen.add(url)
        candidates.append({"url": url, "title": title, "number": _parse_set_title(title)[0]})

    # 1) WordPress REST API (clean JSON when available)
    try:
        resp = requests.get(
            f"{KLICKYPEDIA_BASE}/wp-json/wp/v2/search",
            params={"search": set_number, "per_page": 20},
            headers=HEADERS, timeout=15,
        )
        if resp.status_code == 200:
            for item in resp.json():
                if isinstance(item, dict):
                    _add(item.get("url", ""), html.unescape(item.get("title") or ""))
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Klickypedia REST search failed for %s: %s", set_number, exc)

    if candidates:
        return candidates

    # 2) Fallback: parse the HTML search results page
    try:
        resp = requests.get(KLICKYPEDIA_BASE, params={"s": set_number}, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                title = a.get_text(strip=True) or a.get("title", "")
                # Keep only results actually related to the searched number:
                # the slug may not contain it (typos), but the title then does.
                if set_number in href or set_number in title:
                    _add(urljoin(KLICKYPEDIA_BASE, href), title)
    except requests.RequestException as exc:
        logger.warning("Klickypedia HTML search failed for %s: %s", set_number, exc)

    return candidates


def scrape_klickypedia_page(url: str, set_number: str) -> dict:
    """Scrape a klickypedia.com set page. Returns empty dict on failure.

    The result includes "set_number_found" (the number displayed on the page)
    and "number_mismatch" when it differs from the requested number: only the
    page title is authoritative, never the URL.
    """
    result: dict = {"klickypedia_url": url}

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        if resp.status_code != 200:
            logger.warning("Klickypedia returned %s for %s", resp.status_code, url)
            return {}
        result["klickypedia_url"] = resp.url

        soup = BeautifulSoup(resp.text, "html.parser")

        # --- Page title: "Playmobil 72030 - Astronaut" (authoritative) ---
        h1 = (
            soup.find("h1", attrs={"itemprop": "name"})
            or soup.find("h1", class_=re.compile("entry-title", re.I))
            or soup.find("h1")
        )
        found_number, clean_name = _parse_set_title(h1.get_text(" ", strip=True) if h1 else None)
        if found_number:
            result["set_number_found"] = found_number
            result["number_mismatch"] = bool(set_number) and found_number != set_number
        if clean_name:
            result["name"] = clean_name

        # --- Name fallback (og:title) ---
        if not result.get("name"):
            og_title = soup.find("meta", property="og:title")
            if og_title:
                title = og_title.get("content", "").strip()
                title = re.sub(r"\s*[\|–\-]\s*[Kk]lickypedia.*$", "", title).strip()
                if title:
                    result["name"] = title
        if not result.get("name") and h1:
            result["name"] = h1.get_text(strip=True)

        # --- Main photo ---
        og_image = soup.find("meta", property="og:image")
        if og_image and og_image.get("content"):
            result["official_photo_url"] = og_image["content"]
        else:
            # Fallback: largest <img> that looks like a product photo
            for img in soup.find_all("img"):
                src = img.get("src", "")
                alt = img.get("alt", "")
                if set_number in src or set_number in alt:
                    result["official_photo_url"] = src
                    break
            if not result.get("official_photo_url"):
                # Take first non-icon image
                for img in soup.find_all("img"):
                    src = img.get("src", "")
                    if src and not re.search(r"logo|icon|avatar|banner", src, re.I):
                        result["official_photo_url"] = src
                        break

        # --- Release year ---
        raw_year = _find_labeled_value(soup, _LABEL_YEAR)
        year = _extract_year(raw_year)
        if not year:
            # Sometimes the year appears in the page title or heading as 4 digits
            page_text = soup.get_text(" ", strip=True)
            m = re.search(r"\b(19[7-9]\d|20[0-4]\d)\b", page_text)
            if m:
                year = int(m.group())
        if year:
            result["year"] = year

        # --- Theme / collection ---
        raw_theme = _find_labeled_value(soup, _LABEL_THEME)
        if raw_theme:
            result["collection"] = raw_theme.strip()

        # --- Number of figurines ---
        figures = _extract_figures(soup)
        if figures is not None:
            result["num_figures"] = figures

        # --- Number of pieces ---
        raw_pieces = _find_labeled_value(soup, _LABEL_PIECES)
        pieces = _extract_int(raw_pieces)
        if pieces is not None:
            result["num_pieces"] = pieces

    except requests.RequestException as exc:
        logger.warning("Klickypedia request failed for set %s: %s", set_number, exc)
        return {}
    except Exception as exc:
        logger.warning("Klickypedia parsing failed for set %s: %s", set_number, exc)
        return {}

    # Return only if we got at least a name or a photo
    if result.get("name") or result.get("official_photo_url"):
        return result
    return {}


PLAYMOBIL_BASE = "https://www.playmobil.com"
PLAYMOBIL_LOCALE = "fr-fr"


def _jsonld_products(soup: BeautifulSoup):
    """Yield JSON-LD nodes of @type Product found in the page."""
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            graph = item.get("@graph")
            nodes = [item] + (graph if isinstance(graph, list) else [])
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                node_type = node.get("@type")
                if node_type == "Product" or (isinstance(node_type, list) and "Product" in node_type):
                    yield node


def _fetch_playmobil_product(set_number: str) -> tuple[str, str] | None:
    """Locate the product page on playmobil.com. Returns (url, html) or None."""
    # The on-site search often redirects straight to the product page when the
    # query is an exact set number; otherwise we pick the first product link.
    search_url = f"{PLAYMOBIL_BASE}/{PLAYMOBIL_LOCALE}/search?q={set_number}"
    try:
        resp = requests.get(search_url, headers=HEADERS, timeout=15, allow_redirects=True)
        if resp.status_code == 200:
            if set_number in resp.url and "search" not in resp.url:
                return resp.url, resp.text
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if set_number in href and "search" not in href:
                    product_url = urljoin(PLAYMOBIL_BASE, href)
                    prod_resp = requests.get(product_url, headers=HEADERS, timeout=15, allow_redirects=True)
                    if prod_resp.status_code == 200:
                        return prod_resp.url, prod_resp.text
                    break
    except requests.RequestException as exc:
        logger.warning("Playmobil search failed for set %s: %s", set_number, exc)

    # Fallback: known direct URL patterns
    for candidate in (
        f"{PLAYMOBIL_BASE}/{PLAYMOBIL_LOCALE}/{set_number}.html",
        f"{PLAYMOBIL_BASE}/{PLAYMOBIL_LOCALE}/p/{set_number}",
    ):
        try:
            resp = requests.get(candidate, headers=HEADERS, timeout=15, allow_redirects=True)
            if resp.status_code == 200:
                return resp.url, resp.text
        except requests.RequestException:
            continue
    return None


def scrape_playmobil(set_number: str) -> dict:
    """Scrape set data from the official playmobil.com shop. Returns empty dict on failure."""
    fetched = _fetch_playmobil_product(set_number)
    if not fetched:
        logger.warning("No Playmobil product page found for set %s", set_number)
        return {}
    url, html = fetched
    result: dict = {"playmobil_url": url}

    try:
        soup = BeautifulSoup(html, "html.parser")

        # --- Structured data (JSON-LD Product) ---
        product = next(_jsonld_products(soup), None)
        if product:
            name = product.get("name")
            if isinstance(name, str) and name.strip():
                result["name"] = name.strip()

            image = product.get("image")
            if isinstance(image, list):
                image = image[0] if image else None
            if isinstance(image, dict):
                image = image.get("url")
            if isinstance(image, str) and image.strip():
                result["official_photo_url"] = urljoin(PLAYMOBIL_BASE, image.strip())

            offers = product.get("offers")
            if isinstance(offers, list):
                offers = offers[0] if offers else None
            if isinstance(offers, dict):
                price = offers.get("price") or offers.get("lowPrice")
                if price is not None:
                    try:
                        result["public_price"] = float(str(price).replace(",", "."))
                    except ValueError:
                        pass

        # --- Open Graph fallbacks ---
        if not result.get("name"):
            og_title = soup.find("meta", property="og:title")
            if og_title and og_title.get("content"):
                result["name"] = og_title["content"].strip()
        if not result.get("official_photo_url"):
            og_image = soup.find("meta", property="og:image")
            if og_image and og_image.get("content"):
                result["official_photo_url"] = urljoin(PLAYMOBIL_BASE, og_image["content"].strip())

        # Clean up shop suffixes like "Grand manège - 70819 | PLAYMOBIL®"
        if result.get("name"):
            name = re.sub(r"\s*[\|–\-]\s*PLAYMOBIL.*$", "", result["name"], flags=re.I)
            name = re.sub(rf"\s*[\|–\-]\s*{re.escape(set_number)}\s*$", "", name).strip()
            if name:
                result["name"] = name

    except Exception as exc:
        logger.warning("Playmobil parsing failed for set %s: %s", set_number, exc)
        return {}

    if result.get("name") or result.get("official_photo_url"):
        return result
    return {}


def lookup_set(set_number: str) -> dict:
    """Find set data online: Klickypedia first, official Playmobil shop as fallback.

    Returns one of:
      {"status": "found", "source": ..., **data}        — unambiguous, verified match
      {"status": "ambiguous", "source": "Klickypedia",
       "candidates": [{"url", "title", "number"}]}      — the user must choose
      {"status": "not_found"}
    """
    candidates = search_klickypedia(set_number)
    exact = [c for c in candidates if c["number"] == set_number]

    target = None
    if len(exact) == 1:
        target = exact[0]
    elif not exact and len(candidates) == 1:
        target = candidates[0]
    elif not candidates:
        # Search unavailable: try the legacy direct URL, but verify the number
        # displayed on the page (WordPress guesses redirects from slug prefixes).
        data = scrape_klickypedia_page(f"{KLICKYPEDIA_BASE}/sets/{set_number}", set_number)
        if data:
            if not data.get("number_mismatch"):
                return {"status": "found", "source": "Klickypedia", **data}
            # Wrong set behind the guessed URL: offer it as a candidate
            candidates = [{
                "url": data["klickypedia_url"],
                "title": f"Playmobil {data.get('set_number_found', '?')} - {data.get('name', '')}".strip(" -"),
                "number": data.get("set_number_found"),
            }]

    if target:
        data = scrape_klickypedia_page(target["url"], set_number)
        if data and not data.get("number_mismatch"):
            return {"status": "found", "source": "Klickypedia", **data}

    if candidates:
        return {
            "status": "ambiguous",
            "source": "Klickypedia",
            "candidates": exact if len(exact) > 1 else candidates,
        }

    data = scrape_playmobil(set_number)
    if data:
        return {"status": "found", "source": "Playmobil", **data}
    return {"status": "not_found"}
