"""Archivio dei risultati: PostgreSQL se DATABASE_URL è impostata, altrimenti SQLite locale."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path


def _dt(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


class SQLiteStore:
    kind = "SQLite"

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("""CREATE TABLE IF NOT EXISTS repos (
            full_name TEXT PRIMARY KEY, pushed_at TEXT, scanned_at TEXT, data TEXT NOT NULL)""")

    def state(self, full_name: str):
        row = self.db.execute("SELECT pushed_at, scanned_at FROM repos WHERE full_name=?", (full_name,)).fetchone()
        return (_dt(row[0]), _dt(row[1])) if row else None

    def save(self, rec: dict) -> None:
        self.db.execute("INSERT OR REPLACE INTO repos VALUES (?,?,?,?)",
                        (rec["full_name"], rec["pushed_at"], rec["scanned_at"], json.dumps(rec, ensure_ascii=False)))
        self.db.commit()

    def all(self) -> list[dict]:
        return [json.loads(r[0]) for r in self.db.execute("SELECT data FROM repos")]

    def log_scan(self, **_):
        pass

    def close(self):
        self.db.close()


PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS repos (
    full_name        text PRIMARY KEY,
    name             text NOT NULL,
    owner            text NOT NULL,
    url              text NOT NULL,
    type             text,
    primary_language text,
    stars            integer NOT NULL DEFAULT 0,
    forks            integer NOT NULL DEFAULT 0,
    open_issues      integer NOT NULL DEFAULT 0,
    license          text,
    status           text,
    description_source text,
    created_at       timestamptz,
    pushed_at        timestamptz,
    scanned_at       timestamptz NOT NULL,
    data             jsonb NOT NULL,
    search           tsvector GENERATED ALWAYS AS (
        to_tsvector('simple',
            coalesce(full_name, '') || ' ' ||
            coalesce(data->>'github_description', '') || ' ' ||
            coalesce(data->>'text', '') || ' ' ||
            coalesce(data->>'summary', ''))
    ) STORED
);
CREATE INDEX IF NOT EXISTS repos_type_idx   ON repos (type);
CREATE INDEX IF NOT EXISTS repos_lang_idx   ON repos (primary_language);
CREATE INDEX IF NOT EXISTS repos_stars_idx  ON repos (stars DESC);
CREATE INDEX IF NOT EXISTS repos_search_idx ON repos USING gin (search);

CREATE TABLE IF NOT EXISTS repo_technologies (
    full_name text NOT NULL REFERENCES repos ON DELETE CASCADE,
    category  text NOT NULL,
    name      text NOT NULL,
    PRIMARY KEY (full_name, category, name)
);
CREATE INDEX IF NOT EXISTS repo_tech_name_idx ON repo_technologies (name);

CREATE TABLE IF NOT EXISTS repo_topics (
    full_name text NOT NULL REFERENCES repos ON DELETE CASCADE,
    topic     text NOT NULL,
    PRIMARY KEY (full_name, topic)
);
CREATE INDEX IF NOT EXISTS repo_topics_topic_idx ON repo_topics (topic);

CREATE TABLE IF NOT EXISTS scans (
    id          bigserial PRIMARY KEY,
    started_at  timestamptz NOT NULL,
    finished_at timestamptz NOT NULL DEFAULT now(),
    analyzed    integer, skipped integer, failed integer, api_calls integer
);

CREATE OR REPLACE VIEW v_types AS
    SELECT type, count(*) AS repos, sum(stars) AS stars FROM repos GROUP BY type ORDER BY repos DESC;
CREATE OR REPLACE VIEW v_technologies AS
    SELECT category, name, count(*) AS repos FROM repo_technologies
    WHERE category <> 'Linguaggio' GROUP BY category, name ORDER BY repos DESC;
"""


class PostgresStore:
    kind = "PostgreSQL"

    def __init__(self, url: str):
        import psycopg  # importato solo se serve
        self.conn = psycopg.connect(url, autocommit=False)
        with self.conn.cursor() as cur:
            cur.execute(PG_SCHEMA)
        self.conn.commit()

    def is_empty(self) -> bool:
        with self.conn.cursor() as cur:
            cur.execute("SELECT NOT EXISTS (SELECT 1 FROM repos)")
            return cur.fetchone()[0]

    def state(self, full_name: str):
        with self.conn.cursor() as cur:
            cur.execute("SELECT pushed_at, scanned_at FROM repos WHERE full_name=%s", (full_name,))
            row = cur.fetchone()
        return (row[0], row[1]) if row else None

    def save(self, rec: dict) -> None:
        from psycopg.types.json import Jsonb
        fn = rec["full_name"]
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO repos (full_name, name, owner, url, type, primary_language, stars, forks, open_issues,
                                   license, status, description_source, created_at, pushed_at, scanned_at, data)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (full_name) DO UPDATE SET
                    name=EXCLUDED.name, owner=EXCLUDED.owner, url=EXCLUDED.url, type=EXCLUDED.type,
                    primary_language=EXCLUDED.primary_language, stars=EXCLUDED.stars, forks=EXCLUDED.forks,
                    open_issues=EXCLUDED.open_issues, license=EXCLUDED.license, status=EXCLUDED.status,
                    description_source=EXCLUDED.description_source, created_at=EXCLUDED.created_at,
                    pushed_at=EXCLUDED.pushed_at, scanned_at=EXCLUDED.scanned_at, data=EXCLUDED.data""",
                (fn, rec["name"], rec["owner"], rec["url"], rec.get("type"), rec.get("primary_language"),
                 rec.get("stars", 0), rec.get("forks", 0), rec.get("open_issues", 0), rec.get("license") or None,
                 rec.get("status"), rec.get("source"), _dt(rec.get("created_at")), _dt(rec.get("pushed_at")),
                 _dt(rec["scanned_at"]), Jsonb(rec)))
            cur.execute("DELETE FROM repo_technologies WHERE full_name=%s", (fn,))
            tech_rows = [(fn, cat, name) for cat, names in (rec.get("technologies") or {}).items() for name in names]
            if tech_rows:
                cur.executemany("INSERT INTO repo_technologies VALUES (%s,%s,%s) ON CONFLICT DO NOTHING", tech_rows)
            cur.execute("DELETE FROM repo_topics WHERE full_name=%s", (fn,))
            if rec.get("topics"):
                cur.executemany("INSERT INTO repo_topics VALUES (%s,%s) ON CONFLICT DO NOTHING",
                                [(fn, t) for t in rec["topics"]])
        self.conn.commit()

    def all(self) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT data FROM repos")
            return [r[0] for r in cur.fetchall()]

    def log_scan(self, started_at, analyzed, skipped, failed, api_calls):
        with self.conn.cursor() as cur:
            cur.execute("INSERT INTO scans (started_at, analyzed, skipped, failed, api_calls) VALUES (%s,%s,%s,%s,%s)",
                        (started_at, analyzed, skipped, failed, api_calls))
        self.conn.commit()

    def close(self):
        self.conn.close()


def open_store(database_url: str | None, sqlite_path: Path):
    """Apre l'archivio giusto. Al primo uso di Postgres importa i dati già presenti nel file SQLite."""
    if not database_url:
        return SQLiteStore(sqlite_path)
    store = PostgresStore(database_url)
    if store.is_empty() and sqlite_path.exists():
        old = SQLiteStore(sqlite_path)
        rows = old.all()
        old.close()
        for rec in rows:
            store.save(rec)
        print(f"📦 Importati {len(rows)} progetti dal file SQLite in PostgreSQL")
    return store
