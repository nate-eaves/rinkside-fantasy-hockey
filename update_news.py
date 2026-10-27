import email.utils, json, re, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timezone

FEEDS = [
    ("Daily Faceoff", "https://www.dailyfaceoff.com/feed"),
    ("RotoWire", "https://www.rotowire.com/rss/news.php?sport=NHL"),
    ("r/fantasyhockey", "https://www.reddit.com/r/fantasyhockey/hot/.rss?limit=20"),
]
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

items, statuses = [], []
for name, url in FEEDS:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "RinksideFantasyDashboard/1.0 (personal feed reader)"})
        with urllib.request.urlopen(req, timeout=18) as response:
            root = ET.fromstring(response.read())
        entries = [node for node in root.iter() if tag_name(node.tag) in ("item", "entry")]
        added = 0
        for entry in entries[:15]:
            title = re.sub(r"\s+", " ", child_text(entry, {"title"})).strip()
            link = child_text(entry, {"link", "guid"})
            if not title or not link.startswith(("https://", "http://")):
                continue
            published = iso_date(child_text(entry, {"pubdate", "published", "updated", "date"}))
            items.append({"source": name, "title": title[:300], "url": link, "published": published})
            added += 1
        statuses.append({"name": name, "ok": added > 0, "items": added, **({"error": "No RSS entries returned"} if added == 0 else {})})
    except Exception as exc:
        statuses.append({"name": name, "ok": False, "error": type(exc).__name__})
items.sort(key=lambda item: item["published"], reverse=True)
payload = {"generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
           "sources": statuses, "items": items[:45]}
with open("news.json", "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=2)
