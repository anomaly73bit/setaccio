"""Client minimale per la REST API di GitHub (solo libreria standard)."""
from __future__ import annotations

import base64
import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.github.com"


class GitHub:
    def __init__(self, token: str | None = None, verbose: bool = True):
        self.token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        self.verbose = verbose
        cafile = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
        self.ctx = ssl.create_default_context(cafile=cafile) if cafile else ssl.create_default_context()
        self.calls = 0

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(msg, flush=True)

    def get(self, path: str, params: dict | None = None, raw: bool = False, retries: int = 4):
        url = path if path.startswith("http") else API + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        headers = {
            "Accept": "application/vnd.github.raw+json" if raw else "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "setaccio-scanner",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(url, headers=headers)
        for attempt in range(retries):
            try:
                self.calls += 1
                with urllib.request.urlopen(req, context=self.ctx, timeout=30) as r:
                    body = r.read()
                    return body.decode("utf-8", "replace") if raw else json.loads(body)
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return None
                if e.code in (403, 429):
                    reset = e.headers.get("X-RateLimit-Reset")
                    retry_after = e.headers.get("Retry-After")
                    if retry_after:
                        wait = int(retry_after)
                    elif reset and e.headers.get("X-RateLimit-Remaining") == "0":
                        wait = max(1, int(reset) - int(time.time()) + 2)
                    else:
                        wait = 30 * (attempt + 1)
                    self._log(f"  rate limit ({e.code}), attendo {wait}s…")
                    time.sleep(min(wait, 3700))
                    continue
                if e.code >= 500:
                    time.sleep(2 ** attempt)
                    continue
                raise
            except (urllib.error.URLError, TimeoutError):
                time.sleep(2 ** attempt)
        return None

    # ---- helper di alto livello ------------------------------------------

    def search_repos(self, query: str, max_results: int = 100, sort: str = "stars"):
        """Restituisce fino a max_results repo (l'API ne consente al massimo 1000 per query)."""
        out, page = [], 1
        while len(out) < max_results and page <= 10:
            data = self.get("/search/repositories",
                            {"q": query, "sort": sort, "order": "desc",
                             "per_page": min(100, max_results - len(out)), "page": page})
            if not data or not data.get("items"):
                break
            out.extend(data["items"])
            if len(data["items"]) < 100:
                break
            page += 1
            time.sleep(2.1)  # search API: 30 richieste/minuto
        return out

    def repo(self, full_name: str):
        return self.get(f"/repos/{full_name}")

    def languages(self, full_name: str) -> dict:
        return self.get(f"/repos/{full_name}/languages") or {}

    def readme(self, full_name: str) -> str:
        return self.get(f"/repos/{full_name}/readme", raw=True) or ""

    def root_files(self, full_name: str) -> list[dict]:
        data = self.get(f"/repos/{full_name}/contents/")
        return data if isinstance(data, list) else []

    def file_text(self, full_name: str, path: str) -> str:
        data = self.get(f"/repos/{full_name}/contents/{urllib.parse.quote(path)}")
        if isinstance(data, dict) and data.get("encoding") == "base64":
            try:
                return base64.b64decode(data["content"]).decode("utf-8", "replace")
            except Exception:
                return ""
        return ""
