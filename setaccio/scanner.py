"""Setaccio — scanner dei repository pubblici di GitHub.

Uso tipico:
    python -m setaccio.scanner --per-query 30 --min-stars 500
    python -m setaccio.scanner --repos torvalds/linux,microsoft/vscode
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .classify import classify, describe, describe_llm
from .detect import MANIFESTS, MANIFEST_SUFFIXES, map_technologies, parse_deps
from .github import GitHub
from .storage import _dt, open_store

DEFAULT_LANGUAGES = [
    "Python", "JavaScript", "TypeScript", "Go", "Rust", "Java", "Kotlin", "C#", "C++", "C",
    "PHP", "Ruby", "Swift", "Dart", "Scala", "Elixir", "Shell", "Jupyter Notebook", "Lua", "Zig",
]

ROOT = Path(__file__).resolve().parent.parent


def discover(gh: GitHub, args) -> list[dict]:
    """Elenco dei repo candidati tramite Search API, a fette per linguaggio."""
    since = (datetime.now(timezone.utc) - timedelta(days=args.pushed_within)).date().isoformat()
    base = f"stars:>={args.min_stars} pushed:>={since} fork:false archived:false"
    if args.query:
        queries = [f"{args.query} {base}"]
    else:
        langs = args.languages.split(",") if args.languages else DEFAULT_LANGUAGES
        queries = [f'{base} language:"{lang}"' for lang in langs]
    seen: dict[str, dict] = {}
    for q in queries:
        print(f"🔎 {q}")
        for item in gh.search_repos(q, max_results=args.per_query):
            seen.setdefault(item["full_name"], item)
    print(f"→ {len(seen)} repository candidati")
    return list(seen.values())


def analyze(gh: GitHub, meta: dict, use_llm: bool) -> dict:
    full = meta["full_name"]
    langs = gh.languages(full)
    readme = gh.readme(full)
    root = gh.root_files(full)
    names = [f["name"] for f in root]
    deps: set[str] = set()
    dockerish = ""
    to_read = [n for n in names if n in MANIFESTS or n.endswith(MANIFEST_SUFFIXES)][:6]
    for n in to_read:
        text = gh.file_text(full, n)
        if n.lower().startswith(("dockerfile", "docker-compose", "compose")):
            dockerish += "\n" + text
        else:
            deps |= parse_deps(n, text)
    techs = map_technologies(deps, names, dockerish)
    for lang in langs:  # linguaggi dichiarati da GitHub Linguist
        techs.setdefault("Linguaggio", [])
        if lang not in techs["Linguaggio"]:
            techs["Linguaggio"].append(lang)
    techs["Linguaggio"] = techs.get("Linguaggio", [])[:8]

    ptype, ranking = classify(meta, readme, techs)
    info = describe(meta, langs, techs, ptype, readme)
    if use_llm:
        llm = describe_llm(meta, langs, techs, readme)
        if llm:
            ptype = llm.get("tipo") or ptype
            info.update({
                "text": llm.get("descrizione") or info["text"],
                "strengths": llm.get("punti_forza") or [],
                "use_cases": llm.get("casi_uso") or [],
                "audience": llm.get("pubblico") or info["audience"],
                "source": "AI",
            })
    return {
        "full_name": full,
        "name": meta["name"],
        "owner": meta["owner"]["login"],
        "owner_type": meta["owner"].get("type"),
        "avatar": meta["owner"].get("avatar_url"),
        "url": meta["html_url"],
        "homepage": meta.get("homepage") or "",
        "github_description": meta.get("description") or "",
        "topics": meta.get("topics") or [],
        "stars": meta.get("stargazers_count", 0),
        "forks": meta.get("forks_count", 0),
        "open_issues": meta.get("open_issues_count", 0),
        "license": ((meta.get("license") or {}).get("spdx_id") or "").replace("NOASSERTION", ""),
        "created_at": meta.get("created_at"),
        "pushed_at": meta.get("pushed_at"),
        "size_kb": meta.get("size", 0),
        "primary_language": meta.get("language"),
        "type": ptype,
        "type_ranking": [[t, s] for t, s in ranking],
        "technologies": techs,
        "dependencies_count": len(deps),
        "manifests": to_read,
        **info,
        "scanned_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def export(store, out: Path) -> int:
    rows = store.all()
    rows.sort(key=lambda r: -r["stars"])
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "count": len(rows), "repos": rows}
    out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return len(rows)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Setaccio — scanner di repository GitHub")
    p.add_argument("--repos", help="lista esplicita owner/repo separata da virgole (salta la ricerca)")
    p.add_argument("--query", help="query di ricerca GitHub aggiuntiva (es. 'topic:llm')")
    p.add_argument("--languages", help="linguaggi da scansionare, separati da virgola")
    p.add_argument("--min-stars", type=int, default=200)
    p.add_argument("--pushed-within", type=int, default=365, help="solo repo aggiornati negli ultimi N giorni")
    p.add_argument("--per-query", type=int, default=30, help="repo per fetta di ricerca (max 1000)")
    p.add_argument("--limit", type=int, default=0, help="massimo repo da analizzare in questa esecuzione")
    p.add_argument("--rescan-days", type=int, default=7, help="rianalizza solo se più vecchio di N giorni o con nuovi push")
    p.add_argument("--max-minutes", type=int, default=0, help="ferma l'analisi dopo N minuti (0 = nessun limite)")
    p.add_argument("--force", action="store_true", help="rianalizza tutto, ignorando la cache")
    p.add_argument("--no-llm", action="store_true", help="non usare l'AI anche se ANTHROPIC_API_KEY è presente")
    p.add_argument("--db", default=str(ROOT / "data" / "setaccio.db"), help="file SQLite (usato se DATABASE_URL non c'è)")
    p.add_argument("--out", default=str(ROOT / "docs" / "data" / "repos.json"))
    args = p.parse_args(argv)

    gh = GitHub()
    store = open_store(os.environ.get("DATABASE_URL"), Path(args.db))
    print(f"Archivio: {store.kind}")
    started = datetime.now(timezone.utc)
    use_llm = bool(os.environ.get("ANTHROPIC_API_KEY")) and not args.no_llm
    print(f"Descrizioni: {'AI (' + os.environ.get('SETACCIO_MODEL', 'claude-haiku-5-5') + ')' if use_llm else 'euristiche'}")

    if args.repos:
        candidates = [m for m in (gh.repo(r.strip()) for r in args.repos.split(",")) if m]
    else:
        candidates = discover(gh, args)

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.rescan_days)
    done = skipped = failed = 0
    t0 = time.time()
    for meta in candidates:
        if args.limit and done >= args.limit:
            break
        if args.max_minutes and time.time() - t0 > args.max_minutes * 60:
            print("⏱  tempo massimo raggiunto, mi fermo qui (riprendo alla prossima esecuzione)")
            break
        row = store.state(meta["full_name"])
        if row and not args.force and row[0] == _dt(meta.get("pushed_at")) and row[1] > cutoff:
            skipped += 1
            continue
        try:
            rec = analyze(gh, meta, use_llm)
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  ✗ {meta['full_name']}: {e}")
            continue
        store.save(rec)
        done += 1
        print(f"  ✓ {rec['full_name']:<45} {rec['type']:<32} ★{rec['stars']}")

    total = export(store, Path(args.out))
    store.log_scan(started_at=started, analyzed=done, skipped=skipped, failed=failed, api_calls=gh.calls)
    store.close()
    print(f"\nAnalizzati {done}, saltati {skipped} (già aggiornati), errori {failed}. "
          f"Totale in archivio: {total}. Chiamate API: {gh.calls}. Tempo: {time.time() - t0:.0f}s")
    print(f"Dati esportati in {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
