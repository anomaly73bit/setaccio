"""Rilevamento deterministico delle tecnologie dai file del repository."""
from __future__ import annotations

import json
import re
import tomllib

# File "manifesto" da leggere se presenti nella root
MANIFESTS = {
    "package.json", "requirements.txt", "pyproject.toml", "setup.py", "Pipfile",
    "Cargo.toml", "go.mod", "pom.xml", "build.gradle", "build.gradle.kts",
    "Gemfile", "composer.json", "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    "compose.yml", "compose.yaml", "pubspec.yaml", "mix.exs", "Package.swift",
    "CMakeLists.txt", "deno.json", "build.sbt", "Chart.yaml", "main.tf",
}
MANIFEST_SUFFIXES = (".csproj", ".fsproj", ".sln", ".tf", ".cabal", ".nimble")

# Segnali dalla sola presenza di file/cartelle nella root
FILE_SIGNALS = {
    "Dockerfile": ("Docker", "Infrastruttura"),
    "docker-compose.yml": ("Docker Compose", "Infrastruttura"),
    "docker-compose.yaml": ("Docker Compose", "Infrastruttura"),
    "compose.yml": ("Docker Compose", "Infrastruttura"),
    "Chart.yaml": ("Helm", "Infrastruttura"),
    "main.tf": ("Terraform", "Infrastruttura"),
    "vercel.json": ("Vercel", "Infrastruttura"),
    "netlify.toml": ("Netlify", "Infrastruttura"),
    "fly.toml": ("Fly.io", "Infrastruttura"),
    "Procfile": ("Heroku", "Infrastruttura"),
    "serverless.yml": ("Serverless Framework", "Infrastruttura"),
    ".github": ("GitHub Actions", "CI/CD"),
    ".gitlab-ci.yml": ("GitLab CI", "CI/CD"),
    "Jenkinsfile": ("Jenkins", "CI/CD"),
    "tsconfig.json": ("TypeScript", "Linguaggio"),
    "tailwind.config.js": ("Tailwind CSS", "Frontend"),
    "tailwind.config.ts": ("Tailwind CSS", "Frontend"),
    "next.config.js": ("Next.js", "Frontend"),
    "next.config.mjs": ("Next.js", "Frontend"),
    "nuxt.config.ts": ("Nuxt", "Frontend"),
    "vite.config.ts": ("Vite", "Build"),
    "vite.config.js": ("Vite", "Build"),
    "angular.json": ("Angular", "Frontend"),
    "svelte.config.js": ("SvelteKit", "Frontend"),
    "manage.py": ("Django", "Backend"),
    "artisan": ("Laravel", "Backend"),
    "pubspec.yaml": ("Flutter/Dart", "Mobile"),
    "AndroidManifest.xml": ("Android", "Mobile"),
    "Podfile": ("CocoaPods (iOS)", "Mobile"),
    "Package.swift": ("Swift Package", "Linguaggio"),
    "CMakeLists.txt": ("CMake", "Build"),
    "Makefile": ("Make", "Build"),
    "flake.nix": ("Nix", "Build"),
    "mkdocs.yml": ("MkDocs", "Documentazione"),
    "docusaurus.config.js": ("Docusaurus", "Documentazione"),
    "Cargo.toml": ("Cargo", "Build"),
    "go.mod": ("Go modules", "Build"),
    "deno.json": ("Deno", "Runtime"),
    "bun.lockb": ("Bun", "Runtime"),
    "pnpm-lock.yaml": ("pnpm", "Build"),
    "yarn.lock": ("Yarn", "Build"),
    "turbo.json": ("Turborepo", "Build"),
    "nx.json": ("Nx", "Build"),
    "lerna.json": ("Lerna", "Build"),
    "k8s": ("Kubernetes", "Infrastruttura"),
    "kubernetes": ("Kubernetes", "Infrastruttura"),
    "helm": ("Helm", "Infrastruttura"),
    "terraform": ("Terraform", "Infrastruttura"),
    "ansible": ("Ansible", "Infrastruttura"),
    "android": ("Android", "Mobile"),
    "ios": ("iOS", "Mobile"),
    "notebooks": ("Jupyter", "Data/ML"),
}

# Dipendenza (normalizzata, minuscolo) -> (nome leggibile, categoria)
DEPS = {
    # --- JavaScript / TypeScript
    "react": ("React", "Frontend"), "react-dom": ("React", "Frontend"),
    "next": ("Next.js", "Frontend"), "vue": ("Vue", "Frontend"), "nuxt": ("Nuxt", "Frontend"),
    "svelte": ("Svelte", "Frontend"), "@sveltejs/kit": ("SvelteKit", "Frontend"),
    "@angular/core": ("Angular", "Frontend"), "solid-js": ("SolidJS", "Frontend"),
    "preact": ("Preact", "Frontend"), "astro": ("Astro", "Frontend"), "@remix-run/react": ("Remix", "Frontend"),
    "gatsby": ("Gatsby", "Frontend"), "jquery": ("jQuery", "Frontend"), "lit": ("Lit", "Frontend"),
    "tailwindcss": ("Tailwind CSS", "Frontend"), "@mui/material": ("Material UI", "Frontend"),
    "antd": ("Ant Design", "Frontend"), "bootstrap": ("Bootstrap", "Frontend"),
    "@chakra-ui/react": ("Chakra UI", "Frontend"), "styled-components": ("styled-components", "Frontend"),
    "redux": ("Redux", "Frontend"), "@reduxjs/toolkit": ("Redux", "Frontend"), "zustand": ("Zustand", "Frontend"),
    "@tanstack/react-query": ("TanStack Query", "Frontend"),
    "three": ("Three.js", "Grafica/3D"), "d3": ("D3.js", "Data viz"), "chart.js": ("Chart.js", "Data viz"),
    "echarts": ("ECharts", "Data viz"), "phaser": ("Phaser", "Gaming"), "pixi.js": ("PixiJS", "Gaming"),
    "express": ("Express", "Backend"), "fastify": ("Fastify", "Backend"), "koa": ("Koa", "Backend"),
    "@nestjs/core": ("NestJS", "Backend"), "hono": ("Hono", "Backend"), "socket.io": ("Socket.IO", "Backend"),
    "graphql": ("GraphQL", "API"), "@apollo/server": ("Apollo GraphQL", "API"), "apollo-server": ("Apollo GraphQL", "API"),
    "@trpc/server": ("tRPC", "API"),
    "prisma": ("Prisma", "Database"), "@prisma/client": ("Prisma", "Database"), "typeorm": ("TypeORM", "Database"),
    "sequelize": ("Sequelize", "Database"), "mongoose": ("MongoDB", "Database"), "mongodb": ("MongoDB", "Database"),
    "pg": ("PostgreSQL", "Database"), "mysql2": ("MySQL", "Database"), "mysql": ("MySQL", "Database"),
    "redis": ("Redis", "Database"), "ioredis": ("Redis", "Database"), "drizzle-orm": ("Drizzle ORM", "Database"),
    "better-sqlite3": ("SQLite", "Database"), "mssql": ("SQL Server", "Database"), "tedious": ("SQL Server", "Database"),
    "@supabase/supabase-js": ("Supabase", "Database"), "firebase": ("Firebase", "Backend"),
    "electron": ("Electron", "Desktop"), "@tauri-apps/api": ("Tauri", "Desktop"),
    "react-native": ("React Native", "Mobile"), "expo": ("Expo", "Mobile"), "@capacitor/core": ("Capacitor", "Mobile"),
    "@ionic/core": ("Ionic", "Mobile"),
    "commander": ("Commander (CLI)", "CLI"), "yargs": ("yargs (CLI)", "CLI"), "inquirer": ("Inquirer (CLI)", "CLI"),
    "oclif": ("oclif (CLI)", "CLI"), "@oclif/core": ("oclif (CLI)", "CLI"),
    "jest": ("Jest", "Test"), "vitest": ("Vitest", "Test"), "mocha": ("Mocha", "Test"),
    "@playwright/test": ("Playwright", "Test"), "cypress": ("Cypress", "Test"), "puppeteer": ("Puppeteer", "Automazione"),
    "webpack": ("webpack", "Build"), "vite": ("Vite", "Build"), "esbuild": ("esbuild", "Build"), "rollup": ("Rollup", "Build"),
    "typescript": ("TypeScript", "Linguaggio"),
    "openai": ("OpenAI API", "AI/LLM"), "@anthropic-ai/sdk": ("Anthropic API", "AI/LLM"),
    "langchain": ("LangChain", "AI/LLM"), "@langchain/core": ("LangChain", "AI/LLM"), "ai": ("Vercel AI SDK", "AI/LLM"),
    "@modelcontextprotocol/sdk": ("MCP", "AI/LLM"), "@tensorflow/tfjs": ("TensorFlow.js", "Data/ML"),
    "discord.js": ("discord.js", "Bot"), "telegraf": ("Telegraf (Telegram)", "Bot"), "@slack/bolt": ("Slack Bolt", "Bot"),
    "stripe": ("Stripe", "Pagamenti"), "aws-sdk": ("AWS SDK", "Cloud"), "@aws-sdk/client-s3": ("AWS SDK", "Cloud"),
    "vscode": ("VS Code API", "Estensione"), "@types/vscode": ("VS Code API", "Estensione"),
    "@docusaurus/core": ("Docusaurus", "Documentazione"), "vitepress": ("VitePress", "Documentazione"),
    "ethers": ("ethers.js", "Blockchain"), "web3": ("web3.js", "Blockchain"), "hardhat": ("Hardhat", "Blockchain"),
    # --- Python
    "django": ("Django", "Backend"), "flask": ("Flask", "Backend"), "fastapi": ("FastAPI", "Backend"),
    "starlette": ("Starlette", "Backend"), "tornado": ("Tornado", "Backend"), "aiohttp": ("aiohttp", "Backend"),
    "djangorestframework": ("Django REST Framework", "API"), "celery": ("Celery", "Backend"),
    "sqlalchemy": ("SQLAlchemy", "Database"), "psycopg2": ("PostgreSQL", "Database"), "psycopg2-binary": ("PostgreSQL", "Database"),
    "psycopg": ("PostgreSQL", "Database"), "asyncpg": ("PostgreSQL", "Database"), "pymongo": ("MongoDB", "Database"),
    "pyodbc": ("ODBC / SQL Server", "Database"), "pymssql": ("SQL Server", "Database"), "duckdb": ("DuckDB", "Database"),
    "numpy": ("NumPy", "Data/ML"), "pandas": ("pandas", "Data/ML"), "polars": ("Polars", "Data/ML"),
    "scipy": ("SciPy", "Data/ML"), "scikit-learn": ("scikit-learn", "Data/ML"), "sklearn": ("scikit-learn", "Data/ML"),
    "torch": ("PyTorch", "Data/ML"), "pytorch-lightning": ("PyTorch Lightning", "Data/ML"), "lightning": ("PyTorch Lightning", "Data/ML"),
    "tensorflow": ("TensorFlow", "Data/ML"), "keras": ("Keras", "Data/ML"), "jax": ("JAX", "Data/ML"),
    "xgboost": ("XGBoost", "Data/ML"), "lightgbm": ("LightGBM", "Data/ML"),
    "transformers": ("Hugging Face Transformers", "AI/LLM"), "diffusers": ("Diffusers", "AI/LLM"),
    "langchain": ("LangChain", "AI/LLM"), "llama-index": ("LlamaIndex", "AI/LLM"), "llama_index": ("LlamaIndex", "AI/LLM"),
    "anthropic": ("Anthropic API", "AI/LLM"), "vllm": ("vLLM", "AI/LLM"), "sentence-transformers": ("Sentence Transformers", "AI/LLM"),
    "mcp": ("MCP", "AI/LLM"), "chromadb": ("Chroma", "AI/LLM"), "faiss-cpu": ("FAISS", "AI/LLM"),
    "opencv-python": ("OpenCV", "Computer vision"), "pillow": ("Pillow", "Immagini"),
    "matplotlib": ("Matplotlib", "Data viz"), "plotly": ("Plotly", "Data viz"), "seaborn": ("Seaborn", "Data viz"),
    "streamlit": ("Streamlit", "Frontend"), "gradio": ("Gradio", "Frontend"), "dash": ("Dash", "Frontend"),
    "jupyter": ("Jupyter", "Data/ML"), "notebook": ("Jupyter", "Data/ML"),
    "click": ("Click (CLI)", "CLI"), "typer": ("Typer (CLI)", "CLI"), "rich": ("Rich", "CLI"), "textual": ("Textual (TUI)", "CLI"),
    "pytest": ("pytest", "Test"), "requests": ("requests", "HTTP"), "httpx": ("httpx", "HTTP"),
    "scrapy": ("Scrapy", "Scraping"), "beautifulsoup4": ("BeautifulSoup", "Scraping"), "selenium": ("Selenium", "Automazione"),
    "playwright": ("Playwright", "Automazione"), "pydantic": ("Pydantic", "Backend"),
    "pyqt5": ("PyQt", "Desktop"), "pyqt6": ("PyQt", "Desktop"), "pyside6": ("PySide", "Desktop"), "kivy": ("Kivy", "Desktop"),
    "pygame": ("Pygame", "Gaming"), "discord.py": ("discord.py", "Bot"), "python-telegram-bot": ("python-telegram-bot", "Bot"),
    "boto3": ("AWS SDK", "Cloud"), "airflow": ("Airflow", "Data engineering"), "apache-airflow": ("Airflow", "Data engineering"),
    "pyspark": ("Apache Spark", "Data engineering"), "dbt-core": ("dbt", "Data engineering"),
    "sphinx": ("Sphinx", "Documentazione"), "mkdocs": ("MkDocs", "Documentazione"),
    # --- Rust (crates)
    "tokio": ("Tokio", "Runtime"), "actix-web": ("Actix Web", "Backend"), "axum": ("Axum", "Backend"),
    "rocket": ("Rocket", "Backend"), "warp": ("warp", "Backend"), "serde": ("Serde", "Serializzazione"),
    "clap": ("clap (CLI)", "CLI"), "ratatui": ("Ratatui (TUI)", "CLI"), "sqlx": ("SQLx", "Database"),
    "diesel": ("Diesel", "Database"), "tiberius": ("SQL Server", "Database"), "tauri": ("Tauri", "Desktop"),
    "bevy": ("Bevy", "Gaming"), "wgpu": ("wgpu", "Grafica/3D"), "egui": ("egui", "Desktop"), "iced": ("iced", "Desktop"),
    "leptos": ("Leptos", "Frontend"), "yew": ("Yew", "Frontend"), "dioxus": ("Dioxus", "Frontend"),
    "wasm-bindgen": ("WebAssembly", "Runtime"), "reqwest": ("reqwest", "HTTP"), "candle-core": ("Candle", "AI/LLM"),
    # --- Go
    "github.com/gin-gonic/gin": ("Gin", "Backend"), "github.com/labstack/echo": ("Echo", "Backend"),
    "github.com/labstack/echo/v4": ("Echo", "Backend"), "github.com/gofiber/fiber/v2": ("Fiber", "Backend"),
    "github.com/go-chi/chi/v5": ("chi", "Backend"), "github.com/gorilla/mux": ("gorilla/mux", "Backend"),
    "github.com/spf13/cobra": ("Cobra (CLI)", "CLI"), "github.com/urfave/cli/v2": ("urfave/cli", "CLI"),
    "github.com/charmbracelet/bubbletea": ("Bubble Tea (TUI)", "CLI"), "gorm.io/gorm": ("GORM", "Database"),
    "github.com/jackc/pgx/v5": ("PostgreSQL", "Database"), "github.com/lib/pq": ("PostgreSQL", "Database"),
    "github.com/go-sql-driver/mysql": ("MySQL", "Database"), "github.com/microsoft/go-mssqldb": ("SQL Server", "Database"),
    "github.com/redis/go-redis/v9": ("Redis", "Database"), "google.golang.org/grpc": ("gRPC", "API"),
    "k8s.io/client-go": ("Kubernetes", "Infrastruttura"), "github.com/prometheus/client_golang": ("Prometheus", "Osservabilità"),
    # --- Java/Kotlin (artifactId)
    "spring-boot-starter-web": ("Spring Boot", "Backend"), "spring-boot-starter": ("Spring Boot", "Backend"),
    "spring-boot-starter-data-jpa": ("Spring Data JPA", "Database"), "hibernate-core": ("Hibernate", "Database"),
    "quarkus-core": ("Quarkus", "Backend"), "micronaut-core": ("Micronaut", "Backend"), "ktor-server-core": ("Ktor", "Backend"),
    "junit-jupiter": ("JUnit", "Test"), "mssql-jdbc": ("SQL Server", "Database"), "postgresql": ("PostgreSQL", "Database"),
    "kafka-clients": ("Apache Kafka", "Data engineering"), "spark-core": ("Apache Spark", "Data engineering"),
    # --- PHP
    "laravel/framework": ("Laravel", "Backend"), "symfony/framework-bundle": ("Symfony", "Backend"),
    "symfony/console": ("Symfony Console", "CLI"), "slim/slim": ("Slim", "Backend"), "phpunit/phpunit": ("PHPUnit", "Test"),
    "livewire/livewire": ("Livewire", "Frontend"), "filament/filament": ("Filament", "Backend"),
    # --- Ruby
    "rails": ("Ruby on Rails", "Backend"), "sinatra": ("Sinatra", "Backend"), "rspec": ("RSpec", "Test"), "sidekiq": ("Sidekiq", "Backend"),
    "jekyll": ("Jekyll", "Documentazione"),
    # --- Dart / Flutter
    "flutter": ("Flutter", "Mobile"), "flutter_bloc": ("Bloc", "Mobile"), "provider": ("Provider", "Mobile"),
    "riverpod": ("Riverpod", "Mobile"), "flutter_riverpod": ("Riverpod", "Mobile"),
}

DOCKER_IMAGES = {
    "postgres": "PostgreSQL", "mysql": "MySQL", "mariadb": "MariaDB", "mongo": "MongoDB", "redis": "Redis",
    "mcr.microsoft.com/mssql": "SQL Server", "elasticsearch": "Elasticsearch", "rabbitmq": "RabbitMQ",
    "nginx": "Nginx", "clickhouse": "ClickHouse", "minio": "MinIO", "kafka": "Apache Kafka",
    "grafana": "Grafana", "prometheus": "Prometheus", "qdrant": "Qdrant", "ollama": "Ollama",
}


def _norm(name: str) -> str:
    return re.split(r"[\s\[<>=!~;]", name.strip(), maxsplit=1)[0].lower()


def parse_deps(filename: str, text: str) -> set[str]:
    """Estrae i nomi delle dipendenze da un file manifesto."""
    deps: set[str] = set()
    fn = filename.lower()
    try:
        if fn in ("package.json", "composer.json"):
            j = json.loads(text)
            for k in ("dependencies", "devDependencies", "peerDependencies", "require", "require-dev"):
                deps.update(x.lower() for x in (j.get(k) or {}))
        elif fn == "requirements.txt":
            for line in text.splitlines():
                line = line.split("#")[0].strip()
                if line and not line.startswith("-"):
                    deps.add(_norm(line))
        elif fn == "pyproject.toml":
            t = tomllib.loads(text)
            proj = t.get("project", {})
            for d in proj.get("dependencies", []) or []:
                deps.add(_norm(d))
            for group in (proj.get("optional-dependencies") or {}).values():
                deps.update(_norm(d) for d in group)
            poetry = t.get("tool", {}).get("poetry", {})
            deps.update(k.lower() for k in (poetry.get("dependencies") or {}))
            deps.update(k.lower() for k in (poetry.get("dev-dependencies") or {}))
        elif fn == "cargo.toml":
            t = tomllib.loads(text)
            for k in ("dependencies", "dev-dependencies", "build-dependencies"):
                deps.update(x.lower() for x in (t.get(k) or {}))
            ws = t.get("workspace", {}).get("dependencies") or {}
            deps.update(x.lower() for x in ws)
        elif fn == "go.mod":
            for m in re.finditer(r"^\s*(?:require\s+)?([a-z0-9.\-]+\.[a-z]+/[^\s]+)\s+v", text, re.M | re.I):
                deps.add(m.group(1).lower())
        elif fn == "pom.xml" or fn.startswith("build.gradle"):
            deps.update(m.lower() for m in re.findall(r"<artifactId>([^<]+)</artifactId>", text))
            deps.update(m.group(2).lower() for m in re.finditer(r"['\"]([\w.\-]+):([\w.\-]+)(?::[^'\"]*)?['\"]", text))
        elif fn == "gemfile":
            deps.update(m.lower() for m in re.findall(r"^\s*gem\s+['\"]([^'\"]+)['\"]", text, re.M))
        elif fn == "pubspec.yaml":
            deps.update(m.lower() for m in re.findall(r"^\s{2}([a-z_][a-z0-9_]*):", text, re.M))
        elif fn == "setup.py":
            block = re.search(r"install_requires\s*=\s*\[(.*?)\]", text, re.S)
            if block:
                deps.update(_norm(x) for x in re.findall(r"['\"]([^'\"]+)['\"]", block.group(1)))
        elif fn.endswith((".csproj", ".fsproj")):
            deps.update(m.lower() for m in re.findall(r'PackageReference\s+Include="([^"]+)"', text))
    except Exception:
        pass
    return {d for d in deps if d}


DOTNET = {
    "microsoft.aspnetcore": ("ASP.NET Core", "Backend"), "microsoft.entityframeworkcore": ("Entity Framework Core", "Database"),
    "microsoft.data.sqlclient": ("SQL Server", "Database"), "system.data.sqlclient": ("SQL Server", "Database"),
    "dapper": ("Dapper", "Database"), "npgsql": ("PostgreSQL", "Database"), "xunit": ("xUnit", "Test"),
    "nunit": ("NUnit", "Test"), "avalonia": ("Avalonia", "Desktop"), "microsoft.maui": ("MAUI", "Mobile"),
    "serilog": ("Serilog", "Osservabilità"), "mediatr": ("MediatR", "Backend"), "unityengine": ("Unity", "Gaming"),
}


def map_technologies(deps: set[str], root_names: list[str], dockerish: str = "") -> dict[str, list[str]]:
    """Restituisce {categoria: [tecnologie]} ordinate."""
    found: dict[str, set[str]] = {}

    def add(name: str, cat: str):
        found.setdefault(cat, set()).add(name)

    for d in deps:
        if d in DEPS:
            add(*DEPS[d])
            continue
        for prefix, val in DOTNET.items():
            if d.startswith(prefix):
                add(*val)
                break
        if d.startswith("@angular/"):
            add("Angular", "Frontend")
        elif d.startswith("@aws-sdk/"):
            add("AWS SDK", "Cloud")
        elif d.startswith("@google-cloud/") or d.startswith("google-cloud-"):
            add("Google Cloud", "Cloud")
        elif d.startswith("@azure/") or d.startswith("azure-"):
            add("Azure", "Cloud")
    for n in root_names:
        if n in FILE_SIGNALS:
            add(*FILE_SIGNALS[n])
        elif n.endswith(".csproj") or n.endswith(".sln"):
            add(".NET", "Runtime")
        elif n.endswith(".tf"):
            add("Terraform", "Infrastruttura")
        elif n.endswith(".ipynb"):
            add("Jupyter", "Data/ML")
    low = dockerish.lower()
    for key, name in DOCKER_IMAGES.items():
        if re.search(r"image:\s*['\"]?" + re.escape(key) + r"|FROM\s+" + re.escape(key), low, re.I):
            cat = "Infrastruttura" if name in ("Nginx", "Grafana", "Prometheus", "MinIO") else "Database"
            if name in ("Ollama", "Qdrant"):
                cat = "AI/LLM"
            add(name, cat)
    return {k: sorted(v) for k, v in sorted(found.items())}
