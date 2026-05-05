import json
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


def _parse_price(text: str) -> float | None:
    match = re.search(r"(\d+)[.,](\d{2})", text)
    if match:
        try:
            return float(f"{match.group(1)}.{match.group(2)}")
        except ValueError:
            pass
    return None


def _extract_from_jsonld(soup: BeautifulSoup) -> dict:
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get("@type") == "Product":
                    result = {}
                    result["name"] = item.get("name", "").strip()
                    img = item.get("image")
                    if isinstance(img, list):
                        img = img[0]
                    if isinstance(img, dict):
                        img = img.get("url", "")
                    result["official_photo_url"] = img or ""
                    result["playmobil_url"] = item.get("url", "")

                    offers = item.get("offers", {})
                    if isinstance(offers, list):
                        offers = offers[0]
                    if isinstance(offers, dict):
                        try:
                            price = float(offers.get("price", 0) or 0)
                            result["public_price"] = price if price > 0 else None
                        except (ValueError, TypeError):
                            pass

                    desc = item.get("description", "")
                    pieces_match = re.search(r"(\d+)\s*pièces?", desc, re.IGNORECASE)
                    if pieces_match:
                        result["num_pieces"] = int(pieces_match.group(1))

                    return {k: v for k, v in result.items() if v}
        except (json.JSONDecodeError, AttributeError):
            continue
    return {}


def _extract_from_opengraph(soup: BeautifulSoup) -> dict:
    result = {}
    og_title = soup.find("meta", property="og:title")
    if og_title:
        title = og_title.get("content", "")
        title = re.sub(r"\s*[\|–\-]\s*PLAYMOBIL.*$", "", title, flags=re.IGNORECASE).strip()
        if title:
            result["name"] = title

    og_image = soup.find("meta", property="og:image")
    if og_image:
        result["official_photo_url"] = og_image.get("content", "")

    og_url = soup.find("meta", property="og:url")
    if og_url:
        result["playmobil_url"] = og_url.get("content", "")

    return {k: v for k, v in result.items() if v}


def scrape_playmobil(set_number: str) -> dict:
    """Scrape product data from playmobil.fr by set number. Returns empty dict on failure."""
    result: dict = {}

    urls_to_try = [
        f"https://www.playmobil.fr/search?q={set_number}",
        f"https://www.playmobil.fr/{set_number}",
    ]

    for url in urls_to_try:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")

            data = _extract_from_jsonld(soup)
            if data:
                result = data
                break

            data = _extract_from_opengraph(soup)
            if data.get("name"):
                result = data
                break

        except requests.RequestException as exc:
            logger.warning("Scraping request failed for set %s at %s: %s", set_number, url, exc)
        except Exception as exc:
            logger.warning("Scraping parsing failed for set %s: %s", set_number, exc)

    # Try to extract price from page text if not found yet
    if result and not result.get("public_price"):
        try:
            resp = requests.get(
                f"https://www.playmobil.fr/search?q={set_number}",
                headers=HEADERS, timeout=15
            )
            soup = BeautifulSoup(resp.text, "html.parser")
            for elem in soup.find_all(class_=re.compile(r"price", re.I)):
                price = _parse_price(elem.get_text())
                if price and price > 0:
                    result["public_price"] = price
                    break
        except Exception:
            pass

    return result
