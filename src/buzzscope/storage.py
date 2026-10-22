"""SQLite cache for scraped posts, so re-running an analysis doesn't re-scrape PTT."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from buzzscope.models import Comment, Post

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    post_id      TEXT PRIMARY KEY,
    board        TEXT NOT NULL,
    title        TEXT NOT NULL,
    author       TEXT NOT NULL,
    published_at TEXT NOT NULL,
    content      TEXT NOT NULL,
    url          TEXT,
    comments     TEXT NOT NULL,
    fetched_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_posts_board_time ON posts(board, published_at);
"""


class PostStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.executescript(SCHEMA)

    def has(self, post_id: str) -> bool:
        return self.conn.execute("SELECT 1 FROM posts WHERE post_id = ?", (post_id,)).fetchone() is not None

    def get(self, post_id: str) -> Post | None:
        row = self.conn.execute("SELECT * FROM posts WHERE post_id = ?", (post_id,)).fetchone()
        return self._to_post(row) if row else None

    def upsert(self, posts: list[Post]) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        self.conn.executemany(
            "INSERT OR REPLACE INTO posts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    p.post_id,
                    p.board,
                    p.title,
                    p.author,
                    p.published_at.isoformat(),
                    p.content,
                    p.url,
                    json.dumps([c.model_dump(mode="json") for c in p.comments], ensure_ascii=False),
                    now,
                )
                for p in posts
            ],
        )
        self.conn.commit()

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]

    @staticmethod
    def _to_post(row: tuple) -> Post:
        post_id, board, title, author, published_at, content, url, comments, _ = row
        return Post(
            post_id=post_id,
            board=board,
            title=title,
            author=author,
            published_at=datetime.fromisoformat(published_at),
            content=content,
            url=url,
            comments=[Comment.model_validate(c) for c in json.loads(comments)],
        )

    def close(self) -> None:
        self.conn.close()
