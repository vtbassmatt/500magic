# Copilot Instructions for 500magic

## Project Overview

A Django web app to determine the 500 most famous Magic: The Gathering cards via head-to-head voting. Users see two random card images and pick the more famous one.

## Build & Run

- **Package manager**: `uv`
- **Python version**: 3.14
- **Install dependencies**: `uv sync`
- **Run dev server**: `cd src && uv run python manage.py runserver`
- **Migrations**: `cd src && uv run python manage.py makemigrations && uv run python manage.py migrate`
- **Django shell**: `cd src && uv run python manage.py shell`

## Architecture

### Dual SQLite Databases
- **`default`** (`data/db.sqlite3`): Django-managed. Stores votes, auth, sessions.
- **`mtgjson`** (`data/AllPrintings.sqlite`): Readonly. Downloaded from [mtgjson.com](https://mtgjson.com/downloads/all-files/). Contains all MTG card data. **Not committed to git** — download manually and place in `data/`.

### Database Router (`matchup/db_router.py`)
Routes `Card` and `CardIdentifiers` models to the `mtgjson` database. All other models go to `default`. Prevents migrations from running against `mtgjson`.

### Django Project Layout
- `src/fivehundredmagic/` — Django project (settings, urls, wsgi)
- `src/matchup/` — Django app (models, views, templates)

### Models
- `Card`, `CardIdentifiers` — **Unmanaged** models mapping to mtgjson's `cards` and `cardIdentifiers` tables. Boolean fields in mtgjson use NULL for false — always use `.exclude(field=True)` rather than `.filter(field=False)`.
- `Vote` — **Managed** model recording each head-to-head choice.

### Card Images
Images are served from Scryfall's CDN. URL pattern: `https://cards.scryfall.io/normal/front/{id[0]}/{id[1]}/{scryfallId}.jpg`. The `scryfallId` comes from the `cardIdentifiers` table.

## Conventions

- All commands run from `src/` where `manage.py` lives.
- Use `uv run` prefix for all Python/Django commands.
- Keep type annotations on public APIs (`py.typed` marker present in package).
