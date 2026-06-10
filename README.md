# 🧩 KlickBase

[![Docker Image](https://ghcr.io/di-0x/klickbase/badge)](https://ghcr.io/di-0x/klickbase)
[![Build & Publish](https://github.com/di-0x/klickbase/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/di-0x/klickbase/actions/workflows/docker-publish.yml)
![Platforms](https://img.shields.io/badge/platform-amd64%20%7C%20arm64-blue)
![License](https://img.shields.io/badge/license-MIT-green)

**KlickBase** is a self-hosted web application to manage your personal Playmobil collection. Browse, filter, and track every set you own — from a phone or a desktop browser.

> **Home-made project** · No account required · No external service dependency · Your data stays on your machine

---

## Screenshots

### Main page
![Main Page](https://raw.githubusercontent.com/Di-0x/KlickBase/refs/heads/main/Screenshot%202026-05-06%20at%2008-55-20%20KlickBase%20%E2%80%94%20Ma%20collection.png)

---

## Features

- **Grid & list views** — switch between card grid and compact list, preference saved in browser
- **Live filtering** — filter by collection, box condition, price range, missing pieces, manual presence, and custom tags; results update without page reload
- **Sorting** — sort by set number, name, purchase price, purchase date, collection, or date added
- **Set detail sheet** — tracks:
  - Set number & official name
  - Official Playmobil collection (Pirates, City Life, Farm…)
  - Number of pieces
  - Price paid & public price
  - Purchase date & year of release
  - Box condition (Neuf → Sans boîte)
  - Manual present (yes/no)
  - Missing pieces (yes/no + description)
  - Free-form notes
  - Custom tags for personal collections
- **Photo gallery** — upload multiple photos per set, choose the primary photo; falls back to the official Playmobil photo if none uploaded
- **Auto-scraping** — when you type a set number, the form automatically looks the set up online and fills in name, official photo, release year, theme, number of pieces, and number of figurines from [Klickypedia](https://www.klickypedia.com), with the official [Playmobil shop](https://www.playmobil.com) as fallback (best-effort, no API key required). When several Klickypedia pages match the number, the form lists them and lets you pick the right one; set numbers are always verified against the page title, never the URL slug. Also available as a one-click refresh on the set detail page.
- **Responsive** — mobile-first design, works on smartphone and desktop

---

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Backend | Python 3.12 + FastAPI | Lightweight, fast, easy to read |
| Database | SQLite (file) | Zero extra container, trivial backup |
| Templates | Jinja2 + HTMX | Server-side rendering, no build step |
| Interactivity | Alpine.js | Minimal JS for toggles and modals |
| Styling | Tailwind CSS (CDN) | Responsive, no build step |
| Image | `python:3.12-slim` | ~150 MB, non-root user, read-only FS |
| Scraping | `requests` + `beautifulsoup4` → [Klickypedia](https://www.klickypedia.com), fallback [playmobil.com](https://www.playmobil.com) | Fan database with set metadata, official shop as backup |

---

## Requirements

- [Docker](https://docs.docker.com/get-docker/) ≥ 24
- [Docker Compose](https://docs.docker.com/compose/install/) ≥ 2.20
- Internet access from the **browser** (Tailwind, HTMX, Alpine.js are loaded from CDN)

---

## Deployment

### Option A — Pre-built image from GHCR *(recommended)*

No need to clone the repository. Create a `docker-compose.yml` file anywhere on your server:

```bash
mkdir klickbase && cd klickbase
curl -fsSL https://raw.githubusercontent.com/di-0x/klickbase/main/docker-compose.yml -o docker-compose.yml
docker compose up -d
```

Or create the file manually:

```yaml
# docker-compose.yml
services:
  klickbase:
    image: ghcr.io/di-0x/klickbase:latest
    ports:
      - "8000:8000"
    volumes:
      - ./data:/data
    restart: unless-stopped
    environment:
      - DATA_DIR=/data
    read_only: true
    tmpfs:
      - /tmp
```

```bash
docker compose up -d
```

The app is available at **http://localhost:8000**.

> **Architectures supported:** `linux/amd64` (standard PC/server) and `linux/arm64` (Raspberry Pi 4/5, Apple Silicon).

### Option B — Build from source

```bash
git clone https://github.com/di-0x/klickbase.git
cd klickbase
# Edit docker-compose.yml: replace `image:` with `build: .`
docker compose up --build -d
```

### Access from another device on your network

Replace `localhost` with the IP address of the host machine:

```
http://192.168.x.x:8000
```

### Stop

```bash
docker compose down
```

---

## Updating

### Pre-built image

```bash
docker compose pull
docker compose up -d
```

### Built from source

```bash
git pull
docker compose up --build -d
```

The database schema is backward-compatible — your data is preserved on update.

---

## Data persistence

All data is stored in the `./data/` directory on the host:

```
data/
├── klickbase.db      # SQLite database (sets, tags, photos metadata)
└── photos/           # Uploaded photos
```

This directory is mounted as a Docker volume and **survives container restarts and image updates**.

### Backup

```bash
cp -r ./data ./data_backup_$(date +%Y%m%d)
```

### Restore

```bash
docker compose down
cp -r ./data_backup_YYYYMMDD ./data
docker compose up -d
```

---

## Configuration

To change the host port (default `8000`):

```yaml
ports:
  - "9000:8000"   # change 9000 to any available port
```

To pin a specific version instead of `latest`:

```yaml
image: ghcr.io/di-0x/klickbase:1.0.0
```

Available tags are listed on the [packages page](https://github.com/di-0x/klickbase/pkgs/container/klickbase).

---

## CI/CD

Every push to `main` and every version tag (`v*.*.*`) automatically triggers a GitHub Actions workflow that:

1. Builds a multi-arch image (`amd64` + `arm64`)
2. Pushes it to `ghcr.io/di-0x/klickbase`
3. Tags it as `latest` (main branch) or `x.y.z` (version tag)

Layer caching is enabled — subsequent builds are fast.

---

## Project structure

```
klickbase/
├── .github/
│   └── workflows/
│       └── docker-publish.yml   # Build & push to GHCR
├── app/
│   ├── main.py                  # FastAPI app entry point
│   ├── database.py              # SQLite setup and context manager
│   ├── scraper.py               # Klickypedia + playmobil.com scraping logic
│   ├── routes/
│   │   ├── sets.py              # CRUD routes for sets
│   │   └── photos.py            # Photo upload/management routes
│   └── templates/
│       ├── base.html
│       ├── index.html           # Main listing page
│       ├── set_detail.html      # Set detail sheet
│       ├── set_form.html        # Create / edit form
│       └── partials/            # HTMX partial templates
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## Security notes

- The application has **no authentication** by design — intended for trusted local networks only.  
  Do **not** expose port 8000 to the public internet without adding a reverse proxy with authentication (e.g. [Caddy](https://caddyserver.com/) + basic auth).
- The Docker container runs as a **non-root user** with a **read-only filesystem** (only `/data` and `/tmp` are writable).
- Uploaded files are validated by MIME type and capped at 10 MB.

---

## Contributing

This is a personal home-made project, but issues and pull requests are welcome.

1. Fork the repository
2. Create a feature branch (`git checkout -b feat/your-feature`)
3. Commit your changes
4. Open a pull request

---

## Disclaimer

> **This project is provided "as is", without warranty of any kind, express or implied.**
>
> The author is not responsible for any data loss, hardware damage, security incidents, or any other issue arising from the use, misuse, or inability to use this software. This includes but is not limited to:
>
> - Loss or corruption of your collection data
> - Unauthorized access if the application is improperly exposed to a public network
> - Any issue caused by third-party scraping of [Klickypedia](https://www.klickypedia.com) or [playmobil.com](https://www.playmobil.com) (availability, accuracy of data, terms of service)
> - Incompatibilities with your environment or Docker configuration
>
> Use this software at your own risk. Always keep backups of your `./data` directory.

---

## License

[MIT](LICENSE) — © di-0x
