# VIBE-FASHION Project Guidelines

## Architecture
- Flask app using the app-factory pattern: [app/__init__.py](../app/__init__.py) `create_app()` registers blueprints from [app/routes](../app/routes).
- Routes live in `app/routes/<name>.py` as Blueprints (e.g. `main_bp`), registered in `create_app()`.
- Backend data store is Supabase (Postgres). Client is created in route modules via `supabase-py`, reading `SUPABASE_URL`/`SUPABASE_ANON_KEY` from `.env` (loaded with `python-dotenv`).
- Entry point is [run.py](../run.py), runs on `127.0.0.1:5000`.

## Database
- Schema, seed data, and verification queries are plain `.sql` files at the repo root: `schema.sql`, `seed.sql`, `verify.sql` — run manually in the Supabase SQL Editor in that order.
- `schema.sql` defines all tables, ENUM types, triggers (`handle_new_user` on `auth.users` insert, `set_updated_at`, customer grade recalculation), and RLS policies.
- When adding/renaming columns used by the app (e.g. `is_active`, `is_featured`), update `schema.sql`, `seed.sql`, and the querying route together.
- SQL is lowercase (`create table`, `select`), snake_case identifiers, and DDL/policy statements use `drop ... if exists` before `create` so scripts are safely re-runnable.

## Conventions
- Comments and docstrings in this codebase are written in Korean.
- Supabase calls must never crash the app: wrap queries in `try/except`, log the error to the terminal, and fall back to an empty list/`None`.
- Prices are formatted in Python as `f"{value:,}원"` before passing to templates — don't format currency in Jinja.

## Build and Test
- Activate the venv: `venv313\Scripts\activate` (Windows).
- Install deps: `pip install -r requirements.txt`.
- Run locally: `python run.py`.
