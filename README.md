# 🧩 KlickBase

**KlickBase** is a self-hosted web application to manage your personal Playmobil collection. Browse, filter, and track every set you own — from a phone or a desktop browser.

> **Home-made project** · No account required · No external service dependency · Your data stays on your machine

---

## Screenshots

| Listing (grid) | Set detail |
|---|---|
| *Grid view with filters* | *Detail sheet with photo gallery* |

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
- **Auto-scraping** — one-click fetch of name, official photo, and public price from `playmobil.fr` (best-effort, no API key required)
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

---

## Requirements

- [Docker](https://docs.docker.com/get-docker/) ≥ 24
- [Docker Compose](https://docs.docker.com/compose/install/) ≥ 2.20
- Internet access from the **browser** (Tailwind, HTMX, Alpine.js are loaded from CDN)

---

## Deployment

### 1. Clone the repository

```bash
git clone https://github.com/di-0x/klickbase.git
cd klickbase
```

### 2. Build and start

```bash
docker compose up --build -d
```

The app is now available at **http://localhost:8000**.

### 3. Access from another device on your network

Replace `localhost` with the IP address of the host machine:

```
http://192.168.x.x:8000
```

### 4. Stop

```bash
docker compose down
```

---

## Data persistence

All data is stored in the `./data/` directory on the host:

```
data/
├── klickbase.db      # SQLite database (sets, tags, photos metadata)
└── photos/           # Uploaded photos
```

This directory is mounted as a Docker volume and **survives container restarts and rebuilds**.

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

The only configurable variable is the data directory path, set via environment variable in `docker-compose.yml`:

```yaml
environment:
  - DATA_DIR=/data
```

To change the host port (default `8000`):

```yaml
ports:
  - "9000:8000"   # change 9000 to any available port
```

---

## Updating

```bash
git pull
docker compose up --build -d
```

The database schema is backward-compatible — your data is preserved on update.

---

## Project structure

```
klickbase/
├── app/
│   ├── main.py              # FastAPI app entry point
│   ├── database.py          # SQLite setup and context manager
│   ├── scraper.py           # playmobil.fr scraping logic
│   ├── routes/
│   │   ├── sets.py          # CRUD routes for sets
│   │   └── photos.py        # Photo upload/management routes
│   └── templates/
│       ├── base.html
│       ├── index.html       # Main listing page
│       ├── set_detail.html  # Set detail sheet
│       ├── set_form.html    # Create / edit form
│       └── partials/        # HTMX partial templates
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
> - Any issue caused by third-party scraping of `playmobil.fr` (availability, accuracy of data, terms of service)
> - Incompatibilities with your environment or Docker configuration
>
> Use this software at your own risk. Always keep backups of your `./data` directory.

---

## License

[MIT](LICENSE) — © di-0x
