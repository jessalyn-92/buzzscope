"""Live PTT scraper (web version, www.ptt.cc).

Design choices:
- Uses PTT's board search (/bbs/<board>/search?q=...), which matches article titles.
- Polite by default: one request at a time, PTT_DELAY_SEC between requests, retries with backoff.
- Article bodies are cached in SQLite, so re-runs only fetch new posts.
- Account ids are replaced by salted hashes before anything is stored.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from urllib.parse import quote

import requests

from buzzscope.config import Settings
from buzzscope.models import Post, ResearchPlan
from buzzscope.scraper.base import ProgressFn, matches_plan
from buzzscope.scraper.parser import PTT_BASE, ListEntry, parse_article, parse_list_page
from buzzscope.storage import PostStore

USER_AGENT = "BuzzScope/0.1 (opinion-analysis research project; polite crawler)"


class PTTSource:
    def __init__(self, settings: Settings, session: requests.Session | None = None):
        self.name = "ptt"
        self.settings = settings
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.session.cookies.set("over18", "1", domain="www.ptt.cc")
        self.store = PostStore(settings.db_path)
        self._last_request = 0.0
        self.reference_now = datetime.now()

    def _get(self, url: str) -> str | None:
        for attempt in range(3):
            wait = self.settings.ptt_delay_sec - (time.monotonic() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.monotonic()
            try:
                resp = self.session.get(url, timeout=15)
            except requests.RequestException:
                time.sleep(2**attempt)
                continue
            if resp.status_code == 404:
                return None
            if resp.status_code >= 500 or resp.status_code == 429:
                time.sleep(2**attempt)
                continue
            resp.raise_for_status()
            return resp.text
        return None

    def search_board(self, board: str, keyword: str, since: datetime) -> list[ListEntry]:
        found: list[ListEntry] = []
        for page in range(1, self.settings.ptt_max_pages + 1):
            html = self._get(f"{PTT_BASE}/bbs/{board}/search?page={page}&q={quote(keyword)}")
            if not html:
                break
            entries = parse_list_page(html)
            if not entries:
                break
            found.extend(e for e in entries if e.published_at >= since)
            if min(e.published_at for e in entries) < since:  # results are newest-first
                break
        return found

    def fetch(self, plan: ResearchPlan, on_progress: ProgressFn | None = None) -> list[Post]:
        say = on_progress or (lambda _msg: None)
        since = self.reference_now - timedelta(days=plan.days)
        entries: dict[str, ListEntry] = {}
        for board in plan.boards:
            for kw in plan.keywords:
                hits = self.search_board(board, kw, since)
                say(f"PTT/{board} 搜尋「{kw}」：{len(hits)} 篇")
                for e in hits:
                    entries.setdefault(e.post_id, e)

        posts: list[Post] = []
        new = 0
        for i, entry in enumerate(entries.values(), 1):
            post = self.store.get(entry.post_id)
            if post is None:
                html = self._get(entry.url)
                post = parse_article(html, entry, self.settings.anonymize_salt) if html else None
                if post is None:
                    continue
                self.store.upsert([post])
                new += 1
            posts.append(post)
            if i % 25 == 0:
                say(f"文章下載進度 {i}/{len(entries)}")
        say(f"取得 {len(posts)} 篇文章（新下載 {new} 篇，其餘來自快取）")
        return [p for p in posts if matches_plan(p, plan)]
