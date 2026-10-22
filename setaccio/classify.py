"""Classificazione del tipo di prodotto e generazione della descrizione in italiano."""
from __future__ import annotations

import html
import json
import os
import re
import ssl
import urllib.request
from datetime import datetime, timezone

# tipo -> parole chiave (cercate in topic, nome, descrizione, README)
TYPES: dict[str, list[str]] = {
    "Lista curata / risorsa": ["awesome", "curated list", "collective list", "a list", "list", "directory of", "free apis", "awesome-list", "list of", "collection of", "resources",
                               "cheatsheet", "cheat sheet", "interview", "roadmap", "learning path"],
    "Materiale didattico": ["tutorial", "course", "book", "learn", "education", "exercises", "examples",
                            "lessons", "beginner", "workshop", "guide", "leetcode", "algorithms"],
    "Libreria / SDK": ["library", "sdk", "client library", "wrapper", "bindings", "package", "module",
                       "utility", "utilities", "parser", "npm package", "crate", "toolkit"],
    "Framework": ["framework", "web framework", "full-stack framework", "meta-framework"],
    "Tool da riga di comando": ["cli", "command-line", "command line", "terminal", "tui", "shell", "console tool"],
    "Applicazione web": ["web app", "webapp", "dashboard", "self-hosted", "selfhosted", "saas", "web application",
                         "platform", "admin panel", "cms", "e-commerce", "ecommerce", "blog"],
    "App mobile": ["android", "ios", "mobile app", "flutter", "react-native", "react native", "mobile"],
    "App desktop": ["desktop", "electron", "tauri", "gui", "windows app", "macos app", "linux app"],
    "API / servizio backend": ["api", "rest api", "microservice", "backend", "server", "graphql", "grpc", "proxy", "gateway"],
    "Database / storage": ["database", "key-value", "storage engine", "sql engine", "time-series", "vector database",
                           "orm", "query engine", "olap", "nosql"],
    "Infrastruttura / DevOps": ["kubernetes", "k8s", "devops", "docker", "terraform", "infrastructure", "monitoring",
                                "observability", "ci/cd", "deployment", "helm", "ansible", "cloud-native", "container"],
    "Progetto AI / LLM": ["llm", "gpt", "chatgpt", "ai agent", "rag", "ai agents", "ai agent framework", "large language model", "openai",
                          "claude", "stable diffusion", "transformer", "generative ai", "mcp", "chatbot", "ollama"],
    "Machine learning / data science": ["machine learning", "deep learning", "neural network", "data science",
                                        "pytorch", "tensorflow", "dataset", "computer vision", "nlp", "jupyter"],
    "Gioco / game engine": ["game", "game engine", "gamedev", "videogame", "minecraft", "unity", "godot", "emulator"],
    "Estensione / plugin": ["extension", "plugin", "addon", "add-on", "vscode", "neovim", "vim plugin", "chrome extension",
                            "browser extension", "obsidian", "wordpress plugin"],
    "Bot": ["bot", "discord bot", "telegram bot", "slack bot"],
    "Sicurezza": ["security", "pentest", "penetration testing", "vulnerability", "exploit", "ctf", "osint",
                  "malware analysis", "fuzzing", "encryption", "password"],
    "Template / boilerplate": ["template", "boilerplate", "starter", "starter-kit", "scaffold", "skeleton"],
    "Configurazione / dotfiles": ["dotfiles", "config", "configuration", "nvim config", "setup scripts"],
    "Linguaggio / compilatore": ["programming language", "compiler", "interpreter", "transpiler", "language server", "lsp"],
    "Sistema operativo / embedded": ["operating system", "kernel", "embedded", "firmware", "arduino", "esp32",
                                     "raspberry pi", "microcontroller", "rtos", "bootloader"],
    "Blockchain / crypto": ["blockchain", "ethereum", "solidity", "web3", "crypto", "bitcoin", "defi", "smart contract"],
}

TECH_CAT_TO_TYPE = {
    "Mobile": "App mobile", "Desktop": "App desktop", "CLI": "Tool da riga di comando", "Bot": "Bot",
    "Gaming": "Gioco / game engine", "AI/LLM": "Progetto AI / LLM", "Data/ML": "Machine learning / data science",
    "Estensione": "Estensione / plugin", "Blockchain": "Blockchain / crypto",
}

ARTICLE = {
    "Lista curata / risorsa": "una lista curata di risorse",
    "Materiale didattico": "un progetto didattico",
    "Libreria / SDK": "una libreria",
    "Framework": "un framework",
    "Tool da riga di comando": "uno strumento da riga di comando",
    "Applicazione web": "un'applicazione web",
    "App mobile": "un'app mobile",
    "App desktop": "un'applicazione desktop",
    "API / servizio backend": "un servizio backend / API",
    "Database / storage": "un sistema di gestione dati",
    "Infrastruttura / DevOps": "uno strumento di infrastruttura / DevOps",
    "Progetto AI / LLM": "un progetto di intelligenza artificiale",
    "Machine learning / data science": "un progetto di machine learning / data science",
    "Gioco / game engine": "un gioco o motore di gioco",
    "Estensione / plugin": "un'estensione / plugin",
    "Bot": "un bot",
    "Sicurezza": "uno strumento per la sicurezza informatica",
    "Template / boilerplate": "un template di partenza",
    "Configurazione / dotfiles": "una raccolta di configurazioni",
    "Linguaggio / compilatore": "un linguaggio di programmazione o compilatore",
    "Sistema operativo / embedded": "un progetto di sistema / embedded",
    "Blockchain / crypto": "un progetto blockchain",
    "Altro": "un progetto software",
}

AUDIENCE = {
    "Libreria / SDK": "sviluppatori", "Framework": "sviluppatori", "Tool da riga di comando": "sviluppatori e sysadmin",
    "Infrastruttura / DevOps": "team DevOps / SRE", "Database / storage": "sviluppatori e DBA",
    "Template / boilerplate": "sviluppatori", "Linguaggio / compilatore": "sviluppatori",
    "Materiale didattico": "studenti e chi vuole imparare", "Lista curata / risorsa": "chiunque cerchi risorse sul tema",
    "App mobile": "utenti finali", "App desktop": "utenti finali", "Applicazione web": "utenti finali / aziende",
    "Gioco / game engine": "giocatori o sviluppatori di giochi", "Sicurezza": "professionisti della sicurezza",
    "Machine learning / data science": "data scientist e ricercatori", "Progetto AI / LLM": "sviluppatori e utenti AI",
    "Estensione / plugin": "utenti dello strumento esteso", "Bot": "community e gestori di canali",
    "Configurazione / dotfiles": "utenti avanzati", "Sistema operativo / embedded": "sviluppatori di sistemi / maker",
    "Blockchain / crypto": "sviluppatori web3", "API / servizio backend": "sviluppatori",
}

INSTALL_PATTERNS = [
    (r"\bnpm (?:install|i) (?:-g )?", "npm"), (r"\byarn add\b", "npm"), (r"\bpnpm add\b", "npm"),
    (r"\bpip install\b", "pip"), (r"\buv (?:add|pip install|tool install)\b", "pip / uv"), (r"\bpipx install\b", "pipx"),
    (r"\bcargo install\b", "cargo"), (r"\bgo install\b", "go install"), (r"\bbrew install\b", "Homebrew"),
    (r"\bdocker (?:run|pull)\b", "Docker"), (r"\bdocker compose up\b|docker-compose up", "Docker Compose"),
    (r"\bapt(?:-get)? install\b", "apt"), (r"\bwinget install\b", "winget"), (r"\bhelm install\b", "Helm"),
    (r"\bgem install\b", "gem"), (r"\bcomposer require\b", "Composer"), (r"\bdotnet add package\b", "NuGet"),
    (r"\bflutter pub add\b", "pub"), (r"\bconda install\b", "conda"),
]


def clean_markdown(md: str) -> str:
    md = html.unescape(md)
    md = re.sub(r"<!--.*?-->", " ", md, flags=re.S)
    md = re.sub(r"```.*?```", " ", md, flags=re.S)
    md = re.sub(r"<[^>]+>", " ", md)
    md = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", md)          # immagini/badge
    md = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", md)         # link -> testo
    md = re.sub(r"[*_`]{1,3}", "", md)
    return md


def readme_summary(md: str, max_len: int = 420) -> str:
    """Primo paragrafo descrittivo del README."""
    text = clean_markdown(md)
    for para in re.split(r"\n\s*\n", text):
        p = " ".join(line.strip() for line in para.splitlines() if not line.strip().startswith(("#", "|", "-", "=", ">")))
        p = re.sub(r"\s+", " ", p).strip()
        if len(p) >= 60 and not re.search(r"^(table of contents|contents|license|installation)", p, re.I):
            return (p[:max_len].rsplit(" ", 1)[0] + "…") if len(p) > max_len else p
    return ""


def readme_features(md: str, limit: int = 6) -> list[str]:
    """Voci di elenco sotto un titolo tipo 'Features' / 'Caratteristiche'."""
    m = re.search(r"^#{1,4}\s*[^\n]*(features|highlights|key features|why|what it does|funzionalit|caratteristiche|capabilities)[^\n]*\n(.*?)(?=^#{1,4}\s|\Z)",
                  md, re.I | re.M | re.S)
    if not m:
        return []
    items = []
    for line in m.group(2).splitlines():
        line = line.strip()
        if re.match(r"^[-*+]\s+|^\d+\.\s+", line):
            item = clean_markdown(re.sub(r"^[-*+]\s+|^\d+\.\s+", "", line)).strip(" :-—")
            item = re.sub(r"^[^\w(]+", "", item)  # toglie emoji iniziali
            item = re.sub(r"\s+", " ", item)
            if 6 <= len(item) <= 160:
                items.append(item)
        if len(items) >= limit:
            break
    return items


def install_methods(md: str) -> list[str]:
    out = []
    for pat, name in INSTALL_PATTERNS:
        if re.search(pat, md, re.I) and name not in out:
            out.append(name)
    return out


def classify(meta: dict, readme: str, techs: dict[str, list[str]]) -> tuple[str, list[tuple[str, float]]]:
    topics = " ".join(meta.get("topics") or []).lower().replace("-", " ")
    name = (meta.get("name") or "").lower().replace("-", " ").replace("_", " ")
    desc = (meta.get("description") or "").lower()
    head = clean_markdown(readme[:4000]).lower()
    lead = readme_summary(readme).lower()
    scores: dict[str, float] = {}
    for t, kws in TYPES.items():
        s = 0.0
        for kw in kws:
            pat = r"\b" + re.escape(kw) + r"\b"
            if re.search(pat, topics):
                s += 2
            if re.search(pat, name):
                s += 2.5
            if re.search(pat, desc):
                s += 4
            if re.search(pat, lead):
                s += 2
            elif re.search(pat, head):
                s += 0.5
        scores[t] = s
    for cat, t in TECH_CAT_TO_TYPE.items():
        if cat in techs:
            scores[t] = scores.get(t, 0) + 1.5
    if name.startswith("awesome"):
        scores["Lista curata / risorsa"] += 10
    if (meta.get("language") is None) and len(readme) > 3000:
        scores["Lista curata / risorsa"] += 2
        scores["Materiale didattico"] += 1
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    if not ranked or ranked[0][1] < 1.5:
        return "Altro", ranked[:3]
    return ranked[0][0], ranked[:3]


def _ago(iso: str | None) -> int | None:
    if not iso:
        return None
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - dt).days


def status(meta: dict) -> str:
    if meta.get("archived"):
        return "Archiviato"
    days = _ago(meta.get("pushed_at"))
    if days is None:
        return "Sconosciuto"
    if days <= 30:
        return "Molto attivo"
    if days <= 180:
        return "Attivo"
    if days <= 540:
        return "Poco attivo"
    return "Fermo"


def popularity(stars: int) -> str:
    for limit, label in ((50000, "fenomeno globale"), (10000, "molto popolare"), (2000, "popolare"),
                         (300, "conosciuto nella sua nicchia"), (0, "di nicchia")):
        if stars >= limit:
            return label
    return "di nicchia"


def _join(items: list[str]) -> str:
    items = list(dict.fromkeys(items))
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " e " + items[-1]


def describe(meta: dict, langs: dict, techs: dict, ptype: str, readme: str) -> dict:
    """Descrizione strutturata in italiano, senza AI."""
    total = sum(langs.values()) or 1
    lang_pct = [(k, round(v * 100 / total)) for k, v in sorted(langs.items(), key=lambda kv: -kv[1])]
    main_langs = [k for k, p in lang_pct if p >= 10][:3] or ([meta["language"]] if meta.get("language") else [])
    created = (meta.get("created_at") or "")[:4]
    st = status(meta)
    stars = meta.get("stargazers_count", 0)
    key_tech = []
    for cat in ("Frontend", "Backend", "Mobile", "Desktop", "AI/LLM", "Data/ML", "Database", "API", "CLI", "Gaming"):
        key_tech += techs.get(cat, [])
    parts = [f"**{meta['name']}** è {ARTICLE.get(ptype, ARTICLE['Altro'])}"
             + (f" pensato per {AUDIENCE.get(ptype, 'sviluppatori')}." if ptype != "Altro" else ".")]
    if main_langs:
        parts.append(f"Linguaggi principali: {_join(main_langs)}.")
    if key_tech:
        parts.append(f"Si appoggia su {_join(key_tech[:6])}.")
    db = techs.get("Database", [])
    if db and not set(db) <= set(key_tech[:6]):
        parts.append(f"Lato dati usa {_join(db[:4])}.")
    infra = techs.get("Infrastruttura", [])
    if infra:
        parts.append(f"Per il deploy prevede {_join(infra[:4])}.")
    stars_txt = f"{stars:,}".replace(",", ".")
    when = f", nato nel {created}," if created else ""
    parts.append(f"Il progetto{when} è {popularity(stars)} ({stars_txt} stelle) e risulta {st.lower()}.")
    lic = (meta.get("license") or {}).get("spdx_id")
    if lic and lic != "NOASSERTION":
        parts.append(f"Licenza {lic}.")
    return {
        "text": " ".join(parts),
        "summary": readme_summary(readme),
        "features": readme_features(readme),
        "install": install_methods(readme),
        "audience": AUDIENCE.get(ptype, "sviluppatori"),
        "status": st,
        "languages": lang_pct[:6],
        "source": "euristica",
    }


# ---------------------------------------------------------------- LLM opzionale

LLM_PROMPT = """Analizza questo repository GitHub e rispondi SOLO con un oggetto JSON valido, in italiano, con le chiavi:
"tipo" (una tra: {types}),
"descrizione" (3-5 frasi: cosa fa, a chi serve, come è costruito, cosa lo distingue),
"punti_forza" (lista di max 4 stringhe brevi),
"casi_uso" (lista di max 3 stringhe brevi),
"pubblico" (stringa breve).

Nome: {name}
Descrizione GitHub: {desc}
Topic: {topics}
Linguaggi: {langs}
Tecnologie rilevate: {techs}
README (estratto):
{readme}
"""


def describe_llm(meta: dict, langs: dict, techs: dict, readme: str) -> dict | None:
    """Usa l'API Anthropic se ANTHROPIC_API_KEY è impostata. Restituisce None se non disponibile o in errore."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    model = os.environ.get("SETACCIO_MODEL", "claude-haiku-5-5")
    prompt = LLM_PROMPT.format(
        types=", ".join(list(TYPES) + ["Altro"]), name=meta.get("full_name"), desc=meta.get("description") or "-",
        topics=", ".join(meta.get("topics") or []) or "-", langs=", ".join(langs) or "-",
        techs=json.dumps(techs, ensure_ascii=False), readme=clean_markdown(readme)[:6000])
    body = json.dumps({"model": model, "max_tokens": 700,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(
        os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/") + "/v1/messages",
        data=body, headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        cafile = os.environ.get("SSL_CERT_FILE")
        ctx = ssl.create_default_context(cafile=cafile) if cafile else ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=60, context=ctx) as r:
            data = json.loads(r.read())
        text = "".join(b.get("text", "") for b in data.get("content", []))
        m = re.search(r"\{.*\}", text, re.S)
        return json.loads(m.group(0)) if m else None
    except Exception as e:  # noqa: BLE001
        print(f"  LLM non disponibile: {e}")
        return None
