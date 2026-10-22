# Setaccio

**Setaccio** passa al setaccio i repository pubblici di GitHub, tiene quelli che valgono e li descrive in italiano su una pagina web:

- **tipo di prodotto** (libreria, framework, CLI, app web/mobile/desktop, progetto AI, infrastruttura, gioco, lista curata…)
- **tecnologie** rilevate leggendo i file di progetto (`package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `pom.xml`, `.csproj`, `Dockerfile`…), raggruppate per categoria: frontend, backend, database, AI/LLM, infrastruttura, test…
- **linguaggi** con percentuali, **stato** (molto attivo → fermo), popolarità, licenza
- dal README: riassunto, **funzionalità** dichiarate, metodi di **installazione**
- descrizione testuale generata in automatico (euristica, oppure AI se configurata)

## Come funziona

```
Search API (fette per linguaggio, stelle, data)  →  per ogni repo:
  metadati · linguaggi · README · file della root · manifest
  → rilevamento tecnologie (deterministico)
  → classificazione tipo prodotto
  → descrizione (euristica o Claude)
  → cache SQLite (data/setaccio.db) → docs/data/repos.json → pagina web (docs/)
```

Ogni repo viene rianalizzato solo se ha nuovi push o se l'analisi ha più di 7 giorni.

## Uso locale

Richiede Python 3.11+ e nessuna dipendenza esterna.

```bash
export GITHUB_TOKEN=ghp_...          # token personale (5.000 richieste/ora)
python -m setaccio.scanner --per-query 20 --min-stars 500
python -m setaccio.scanner --query "topic:llm" --per-query 100
python -m setaccio.scanner --repos fastapi/fastapi,ollama/ollama
python -m http.server -d docs 8000   # poi apri http://localhost:8000
```

Opzioni principali: `--languages`, `--min-stars`, `--pushed-within` (giorni), `--per-query` (max 1000), `--limit`, `--max-minutes`, `--no-llm`.

## Automazione

Il workflow `.github/workflows/scan.yml` gira ogni notte (e a mano da *Actions → Scansione GitHub → Run workflow*), aggiorna i dati e fa commit. La pagina è pubblicata con GitHub Pages dalla cartella `docs/`.

Segreti facoltativi (*Settings → Secrets and variables → Actions*):

| Segreto | A cosa serve |
|---|---|
| `SCAN_TOKEN` | token personale: 5.000 richieste/ora invece delle 1.000 del token di Actions |
| `ANTHROPIC_API_KEY` | descrizioni scritte da Claude (punti di forza, casi d'uso) invece che euristiche |

Modello AI configurabile con la variabile `SETACCIO_MODEL` (default `claude-haiku-5-5`).

## Limiti

- La Search API restituisce al massimo 1.000 risultati per query: per coprire di più si moltiplicano le fette (linguaggio × fasce di stelle × date).
- Ogni repo costa circa 5–8 chiamate API: con un token personale si analizzano circa 700–1.000 repo l'ora.
- Il rilevamento legge solo i file nella root: nei monorepo alcune tecnologie possono sfuggire.
