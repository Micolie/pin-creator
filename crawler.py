import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

HEADERS  = {"User-Agent": "Mozilla/5.0 (compatible; PinCreator/1.0)"}
NO_PROXY = {"http": None, "https": None}  # bypass PythonAnywhere proxy for crawling

SKIP_LINK_PATTERNS = [
    "/tag/", "/tags/", "/category/", "/categories/",
    "/page/", "/author/", "/search/", "/feed/",
    "/wp-content/", "/wp-admin/", "/wp-json/",
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg",
    "javascript:", "mailto:", "tel:",
]

SKIP_IMAGE_HINTS = ["logo", "icon", "avatar", "sprite", "pixel", "button"]


def extract_domain(url):
    """Return bare domain like 'myblog.com'."""
    parsed = urlparse(url)
    domain = parsed.netloc or url
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def _absolute(src, base_url):
    if not src:
        return ""
    if src.startswith("//"):
        return "https:" + src
    if src.startswith("/"):
        p = urlparse(base_url)
        return f"{p.scheme}://{p.netloc}{src}"
    return src


# ── The single page-parsing primitive ─────────────────────────────────────────

def parse_page(url, want_all_images=False):
    """Fetch & parse ONE page.

    Returns a dict:
        {title, description, image, images}
      - image:  the single best hero image (og:image preferred)
      - images: full list of usable images (only when want_all_images=True)
    Returns None if the page can't be fetched.
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=8)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception:
        return None

    # Title
    og_title = soup.find("meta", property="og:title")
    title = og_title["content"].strip() if (og_title and og_title.get("content")) else ""
    if not title:
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text().strip()
    if not title and soup.title:
        title = (soup.title.string or "").strip()

    # Description
    og_desc = soup.find("meta", property="og:description")
    description = og_desc["content"].strip() if (og_desc and og_desc.get("content")) else ""

    # Best hero image — og:image wins
    best_image = ""
    og_img = soup.find("meta", property="og:image")
    if og_img and og_img.get("content"):
        best_image = _absolute(og_img["content"].strip(), url)

    # Walk <img> tags (for fallback hero and/or full list)
    images = []
    if best_image:
        images.append(best_image)

    for tag in soup.find_all("img"):
        src = _absolute((tag.get("src") or tag.get("data-src") or "").strip(), url)
        if not src or not src.startswith("http") or src in images:
            continue
        low = src.lower()
        if any(hint in low for hint in SKIP_IMAGE_HINTS):
            continue
        images.append(src)
        if not best_image:
            # first content-y image becomes the hero fallback
            if any(ext in low for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                best_image = src

    if not best_image and images:
        best_image = images[0]

    return {
        "title":       title,
        "description": description,
        "image":       best_image,
        "images":      images[:20] if want_all_images else [],
    }


# ── Multi-article site crawl (reuses parse_page) ──────────────────────────────

def _is_article_link(href, base_netloc):
    parsed = urlparse(href)
    if parsed.netloc and parsed.netloc != base_netloc:
        return False
    if not parsed.path or parsed.path == "/":
        return False
    low = href.lower()
    return not any(pat in low for pat in SKIP_LINK_PATTERNS)


def _fetch_article(url):
    """Per-article view: needs a real title AND an image, else skip."""
    page = parse_page(url)
    if not page:
        return None
    if not page["title"] or len(page["title"]) < 8:
        return None
    if not page["image"]:
        return None
    return {"title": page["title"], "image": page["image"], "url": url}


def _norm(url):
    return url.split("?")[0].split("#")[0].rstrip("/")


def crawl_site(base_url, max_articles=15):
    """Parse the given page AND any article links it points to.

    Works whether the URL is a homepage (discovers many articles) or a single
    article page (yields at least that one). Returns:
        {"articles": [...], "error": str|None}
    """
    # Auto-fix missing scheme
    if base_url and not base_url.startswith(("http://", "https://")):
        base_url = "https://" + base_url

    try:
        resp = requests.get(base_url, headers=HEADERS, timeout=10)
    except Exception as e:
        name = e.__class__.__name__
        if name == "MissingSchema":
            msg = "Invalid URL — please include https:// at the start."
        elif "ProxyError" in name or "proxy" in str(e).lower():
            msg = ("Could not reach that site. On PythonAnywhere free accounts "
                   "only allow-listed domains are accessible. "
                   "Upgrade to the Hacker plan for unrestricted access.")
        elif "ConnectionError" in name or "Timeout" in name:
            msg = "Could not connect to the site. Check the URL and try again."
        else:
            msg = f"Could not reach the site ({name}). Check the URL and try again."
        return {"articles": [], "error": msg}

    if resp.status_code != 200:
        hint = (" The site may be blocking automated requests, or on PythonAnywhere "
                "free tier it may not be on the allowed-hosts list."
                if resp.status_code in (401, 403) else "")
        return {"articles": [],
                "error": f"Site returned HTTP {resp.status_code}.{hint}"}

    soup        = BeautifulSoup(resp.text, "html.parser")
    base_netloc = urlparse(base_url).netloc

    # The page itself is always candidate #1 (handles single-article URLs).
    seen       = {_norm(base_url)}
    candidates = [base_url]

    for a in soup.find_all("a", href=True):
        full = urljoin(base_url, a["href"].strip())
        if _norm(full) not in seen and _is_article_link(full, base_netloc):
            seen.add(_norm(full))
            candidates.append(full)

    articles = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(_fetch_article, link): link
                   for link in candidates[: max_articles * 2]}
        for future in as_completed(futures):
            data = future.result()
            if data:
                articles.append(data)

    # Keep the seed page first if it qualified, then the rest.
    articles.sort(key=lambda a: 0 if _norm(a["url"]) == _norm(base_url) else 1)

    err = None
    if not articles:
        err = ("Reached the site, but found no usable articles "
               "(each needs a title and an image).")
    return {"articles": articles[:max_articles], "error": err}
