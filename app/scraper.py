import logging
import re

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


def scrape_klickypedia(set_number: str) -> dict:
    """Scrape set data from klickypedia.com. Returns empty dict on failure."""
    url = f"https://www.klickypedia.com/sets/{set_number}"
    result: dict = {"klickypedia_url": url}

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        if resp.status_code != 200:
            logger.warning("Klickypedia returned %s for set %s", resp.status_code, set_number)
            return {}

        soup = BeautifulSoup(resp.text, "html.parser")

        # --- Name ---
        og_title = soup.find("meta", property="og:title")
        if og_title:
            title = og_title.get("content", "").strip()
            title = re.sub(r"\s*[\|–\-]\s*[Kk]lickypedia.*$", "", title).strip()
            if title:
                result["name"] = title
        if not result.get("name"):
            h1 = soup.find("h1")
            if h1:
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
