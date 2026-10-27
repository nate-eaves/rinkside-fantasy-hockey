import email.utils, json, re, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlparse

DAILY_FANTASY_PAGE = "https://www.dailyfaceoff.com/nhl-fantasy"
DAILY_GENERAL_FEED = "https://www.dailyfaceoff.com/feed"
REDDIT_FEED = "https://www.reddit.com/r/fantasyhockey/hot/.rss?limit=20"

def tag_name(tag):
    return tag.rsplit("}", 1)[-1].lower()

def child_text(parent, names):
    for child in list(parent):
        if tag_name(child.tag) in names:
            value = "".join(child.itertext()).strip()
            if value:
                return value
            href = child.attrib.get("href")
            if href:
                return href
    return ""

def iso_date(value):
    if not value:
        return ""
    try:
        dt = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

def request_bytes(url):
    req = urllib.request.Request(url, headers={"User-Agent": "RinksideFantasyDashboard/1.0 (personal feed reader)"})
    with urllib.request.urlopen(req, timeout=18) as response:
        return response.read()

def normalized_url(url):
    return urldefrag(url).url.rstrip("/")

class FantasyArticleParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.items = []
        self.active = None

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        attrs = dict(attrs)
        href = attrs.get("href", "")
        absolute = urljoin(DAILY_FANTASY_PAGE, href)
        parsed = urlparse(absolute)
        if parsed.netloc.lower().endswith("dailyfaceoff.com") and parsed.path.startswith("/news/"):
            self.active = {"url": absolute, "parts": []}

    def handle_data(self, data):
        if self.active is not None:
            self.active["parts"].append(data)

    def handle_endtag(self, tag):
        if tag.lower() != "a" or self.active is None:
            return
        title = re.sub(r"\s+", " ", " ".join(self.active["parts"])).strip()
        url = self.active["url"]
        if title and not any(item["url"] == url for item in self.items):
            self.items.append({"source": "Daily Faceoff Fantasy", "title": title[:300], "url": url, "published": ""})
        self.active = None

def daily_feed_dates():
    dates = {}
    try:
        root = ET.fromstring(request_bytes(DAILY_GENERAL_FEED))
        entries = [node for node in root.iter() if tag_name(node.tag) in ("item", "entry")]
        for entry in entries:
            link = child_text(entry, {"link", "guid"})
            published = iso_date(child_text(entry, {"pubdate", "published", "updated", "date"}))
            if link and published:
                dates[normalized_url(link)] = published
    except Exception:
        pass
    return dates

items, statuses = [], []
try:
    parser = FantasyArticleParser()
    parser.feed(request_bytes(DAILY_FANTASY_PAGE).decode("utf-8", errors="replace"))
    daily_items = parser.items[:20]
    dates = daily_feed_dates()
    for item in daily_items:
        item["published"] = dates.get(normalized_url(item["url"]), "")
    items.extend(daily_items)
    statuses.append({"name": "Daily Faceoff Fantasy", "ok": bool(daily_items), "items": len(daily_items),
                     **({"error": "No fantasy article links found"} if not daily_items else {})})
except Exception as exc:
    statuses.append({"name": "Daily Faceoff Fantasy", "ok": False, "items": 0, "error": type(exc).__name__})

try:
    root = ET.fromstring(request_bytes(REDDIT_FEED))
    entries = [node for node in root.iter() if tag_name(node.tag) in ("item", "entry")]
    added = 0
    for entry in entries[:20]:
        title = re.sub(r"\s+", " ", child_text(entry, {"title"})).strip()
        link = child_text(entry, {"link", "guid"})
        if not title or not link.startswith(("https://", "http://")):
            continue
        published = iso_date(child_text(entry, {"pubdate", "published", "updated", "date"}))
        items.append({"source": "r/fantasyhockey", "title": title[:300], "url": link, "published": published})
        added += 1
    statuses.append({"name": "r/fantasyhockey", "ok": added > 0, "items": added,
                     **({"error": "No RSS entries returned"} if added == 0 else {})})
except Exception as exc:
    statuses.append({"name": "r/fantasyhockey", "ok": False, "items": 0, "error": type(exc).__name__})

items.sort(key=lambda item: item.get("published", ""), reverse=True)
payload = {"generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
           "sources": statuses, "items": items[:45]}
with open("news.json", "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=2)
