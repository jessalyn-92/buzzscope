"""Pure HTML parsing for PTT pages (no network) — easy to unit-test with fixtures."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup

from buzzscope.models import Comment, Post

PTT_BASE = "https://www.ptt.cc"
TAIPEI = timezone(timedelta(hours=8))
_ID_RE = re.compile(r"M\.(\d{9,11})\.A\.[0-9A-F]{3}")


@dataclass
class ListEntry:
    post_id: str
    board: str
    title: str
    url: str
    published_at: datetime
    n_push: str


def anonymize(user: str, salt: str) -> str:
    """Store a salted hash instead of the PTT account id (no personal data in our DB)."""
    user = user.split(" ")[0].strip()
    if not user:
        return "anon"
    return "u_" + hashlib.sha1(f"{salt}:{user}".encode()).hexdigest()[:10]


def post_time_from_id(post_id: str) -> datetime | None:
    """PTT article ids embed the Unix timestamp: M.1697800000.A.1B2 → 2023-10-20 ..."""
    m = _ID_RE.search(post_id)
    if not m:
        return None
    return datetime.fromtimestamp(int(m.group(1)), tz=TAIPEI).replace(tzinfo=None)


def parse_list_page(html: str) -> list[ListEntry]:
    """Parse a board index or search-result page into entries (deleted posts are skipped)."""
    soup = BeautifulSoup(html, "html.parser")
    entries = []
    for row in soup.select("div.r-ent"):
        link = row.select_one("div.title a")
        if link is None:  # deleted article
            continue
        href = link.get("href", "")
        m = re.match(r"/bbs/([^/]+)/(M\.[^/]+)\.html", href)
        if not m:
            continue
        board, post_id = m.group(1), m.group(2)
        published = post_time_from_id(post_id)
        if published is None:
            continue
        nrec = row.select_one("div.nrec")
        entries.append(
            ListEntry(
                post_id=post_id,
                board=board,
                title=link.get_text(strip=True),
                url=PTT_BASE + href,
                published_at=published,
                n_push=nrec.get_text(strip=True) if nrec else "",
            )
        )
    return entries


def _parse_push_time(raw: str, year: int) -> datetime | None:
    m = re.search(r"(\d{2})/(\d{2})\s+(\d{2}):(\d{2})", raw)
    if not m:
        return None
    month, day, hour, minute = map(int, m.groups())
    try:
        return datetime(year, month, day, hour, minute)
    except ValueError:
        return None


def parse_article(html: str, entry: ListEntry, salt: str) -> Post | None:
    soup = BeautifulSoup(html, "html.parser")
    main = soup.select_one("#main-content")
    if main is None:
        return None

    meta = {}
    for line in main.select("div.article-metaline, div.article-metaline-right"):
        tag, value = line.select_one(".article-meta-tag"), line.select_one(".article-meta-value")
        if tag and value:
            meta[tag.get_text(strip=True)] = value.get_text(strip=True)
        line.decompose()

    comments = []
    for push in main.select("div.push"):
        tag = push.select_one(".push-tag")
        user = push.select_one(".push-userid")
        content = push.select_one(".push-content")
        when = push.select_one(".push-ipdatetime")
        if tag and content:
            comments.append(
                Comment(
                    tag=tag.get_text(strip=True),
                    author=anonymize(user.get_text(strip=True) if user else "", salt),
                    content=content.get_text().lstrip(":").strip(),
                    time=_parse_push_time(when.get_text() if when else "", entry.published_at.year),
                )
            )
        push.decompose()

    for span in main.select("span.f2"):  # ※ 發信站 / ※ 文章網址 / ※ 編輯 lines
        span.decompose()

    body = main.get_text()
    body = body.split("\n--\n")[0]  # signature separator
    body = "\n".join(line.rstrip() for line in body.strip().splitlines() if line.strip())

    return Post(
        post_id=entry.post_id,
        board=entry.board,
        title=meta.get("標題", entry.title),
        author=anonymize(meta.get("作者", ""), salt),
        published_at=entry.published_at,
        content=body,
        url=entry.url,
        comments=comments,
    )
