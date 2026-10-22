from datetime import datetime
from pathlib import Path

from buzzscope.config import get_settings
from buzzscope.models import ResearchPlan
from buzzscope.scraper.parser import anonymize, parse_article, parse_list_page, post_time_from_id
from buzzscope.scraper.ptt import PTTSource

FIXTURES = Path(__file__).parent / "fixtures"


def test_post_time_from_id():
    assert post_time_from_id("M.1792400000.A.1B2") == datetime(2026, 10, 19, 16, 53, 20)
    assert post_time_from_id("not-an-id") is None


def test_parse_list_page_skips_deleted_posts():
    entries = parse_list_page((FIXTURES / "ptt_search.html").read_text(encoding="utf-8"))
    assert [e.post_id for e in entries] == ["M.1792400000.A.1B2", "M.1792300000.A.3C4"]
    assert entries[0].board == "Food"
    assert entries[0].url == "https://www.ptt.cc/bbs/Food/M.1792400000.A.1B2.html"
    assert entries[1].n_push == "爆"


def test_parse_article_extracts_body_and_comments_without_raw_ids():
    entry = parse_list_page((FIXTURES / "ptt_search.html").read_text(encoding="utf-8"))[0]
    post = parse_article((FIXTURES / "ptt_article.html").read_text(encoding="utf-8"), entry, salt="s")
    assert post is not None
    assert post.title == "[食記] 中壢 晨光咖啡 燕麥拿鐵"
    assert "燕麥拿鐵香氣很足" in post.content
    assert "發信站" not in post.content and "作者" not in post.content
    assert [c.tag for c in post.comments] == ["推", "噓", "→"]
    assert post.comments[0].content == "燕麥拿鐵真的好喝"
    assert post.comments[1].time == datetime(2026, 10, 19, 18, 2)
    # privacy: raw account ids never stored
    assert post.author == anonymize("coffeelover", "s")
    assert all(c.author.startswith("u_") for c in post.comments)
    assert "alice" not in post.model_dump_json()


class FakeResponse:
    def __init__(self, text: str, status: int = 200):
        self.text, self.status_code = text, status

    def raise_for_status(self):
        pass


class FakeSession:
    """Serves fixture pages instead of hitting www.ptt.cc."""

    def __init__(self):
        self.headers, self.urls = {}, []
        self.cookies = type("C", (), {"set": lambda *a, **k: None})()

    def get(self, url, timeout):
        self.urls.append(url)
        if "search?page=1" in url:
            return FakeResponse((FIXTURES / "ptt_search.html").read_text(encoding="utf-8"))
        if "search" in url:
            return FakeResponse("<html><body></body></html>")
        if url.endswith("M.1792400000.A.1B2.html"):
            return FakeResponse((FIXTURES / "ptt_article.html").read_text(encoding="utf-8"))
        return FakeResponse("", 404)


def test_ptt_source_end_to_end_with_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("BUZZSCOPE_DB", str(tmp_path / "t.db"))
    monkeypatch.setenv("PTT_DELAY_SEC", "0")
    session = FakeSession()
    source = PTTSource(get_settings(), session=session)
    source.reference_now = datetime(2026, 10, 20)
    plan = ResearchPlan(question="q", entity="晨光咖啡", keywords=["晨光"], boards=["Food"], days=30)

    posts = source.fetch(plan)
    assert [p.post_id for p in posts] == ["M.1792400000.A.1B2"]  # second article 404s

    n_requests = len(session.urls)
    source.fetch(plan)
    article_requests = [u for u in session.urls[n_requests:] if u.endswith("1B2.html")]
    assert article_requests == []  # served from SQLite cache
