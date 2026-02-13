# 500 Magic

A Django web app to determine the 500 most famous Magic: The Gathering cards. Users see two random card images and pick which one they think is more famous. Over time, the votes reveal which cards are the most widely recognized.

## Setup

Requires Python 3.14+ and [uv](https://docs.astral.sh/uv/).

```sh
uv sync
```

### Card database

Download the AllPrintings SQLite database from [mtgjson.com](https://mtgjson.com/downloads/all-files/) and place it in `data/`:

```sh
curl -L https://mtgjson.com/api/v5/AllPrintings.sqlite.xz | xz -d > data/AllPrintings.sqlite
```

### Migrations

```sh
cd src
uv run python manage.py migrate
```

## Running

```sh
cd src
uv run python manage.py runserver
```

Then open http://127.0.0.1:8000/.

## Management Commands

### View matchup statistics

Display statistics about unvoted matchups bucketed by age:

```sh
cd src
uv run python manage.py matchup_stats
```

This shows the count and percentage of unvoted matchups in each age bucket:
- < 2 hours
- 2-8 hours
- 8-24 hours
- 24+ hours

### Clean up old matchups

Delete old unvoted matchups to prevent database bloat:

```sh
cd src
# Preview what would be deleted (dry-run)
uv run python manage.py cleanup_matchups --dry-run

# Delete matchups older than 24 hours (default)
uv run python manage.py cleanup_matchups

# Delete matchups older than a custom threshold
uv run python manage.py cleanup_matchups --hours 48
```

Only unvoted matchups are deleted. Voted matchups are preserved regardless of age.

## Tests

```sh
cd src
uv run python manage.py test matchup
```

Tests use in-memory databases and mock the mtgjson card selection, so the AllPrintings.sqlite file is not required to run them.
