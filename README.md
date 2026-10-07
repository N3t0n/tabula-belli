# Tabula Belli

Tabula Belli is a Django platform for discovering, publishing, and managing
European tabletop gaming events: trading card games, role-playing games,
wargames, and board game meetups.

The project started as an academic web application and was later reviewed,
hardened, and prepared as a portfolio project with reproducible setup,
PostgreSQL-backed tests, deterministic demo data, and deployment-oriented
configuration.

## Features

- Event discovery with search, filters, sorting, pagination, and HTMX updates.
- Event creation, editing, and cancellation for verified users.
- Registration lifecycle with capacity checks and cancellation support.
- Organizer tools for participant management.
- My Events dashboard for events a user organizes or attends.
- Public signup with mandatory email verification through django-allauth.
- Login by username or email, native password reset/change, and native email
  change flow.
- Public read-only demo account support for portfolio evaluation.
- Account deletion reviews and cancels upcoming organized events and pending registrations in one transaction. Past event and participation records retain a “Deleted account” label; organizer contact emails are removed. An organized event in progress blocks deletion until it ends. Demo and superuser accounts remain protected.
- Event lifecycle command for completing past events.
- Health endpoint, production logging, and custom 403/404/500 pages.

## Engineering Highlights

- Django monolith with a custom `Player` user model and domain-focused apps.
- PostgreSQL-only runtime; there is no automatic SQLite fallback.
- HTMX + Alpine.js + Tailwind CSS + Flowbite for a server-rendered interactive UI.
- django-allauth handles account flows; demo-account restrictions are small
  server-side guards around approved sensitive operations.
- Authorization rules protect event management and participant data from IDOR.
- Registration and event mutations are tested for concurrency and consistency.
- Deterministic, idempotent seeds build a reproducible synthetic demo dataset.
- `reset_demo` safely rebuilds disposable demo data behind explicit production
  safeguards.
- CI validates Python, PostgreSQL, dependency health, tests, frontend assets,
  `collectstatic`, and deployment checks.

## Tech Stack

- Python 3.12
- Django 5.2
- PostgreSQL 16
- django-allauth
- django-anymail with Resend for production transactional email
- django-cities-light / GeoNames
- HTMX 1.9, Alpine.js 3.14, Tailwind CSS 4, Flowbite 3
- Gunicorn and WhiteNoise for the production runtime
- GitHub Actions for CI

Runtime versions are declared in `.python-version`, `.node-version`,
`requirements.txt`, and `package-lock.json`.

## Local Setup

The detailed setup is documented in
[MANUAL_DE_INSTALACION.md](MANUAL_DE_INSTALACION.md). The short version is:

1. Install Python 3.12, PostgreSQL 16, and Node.js 24.
2. Copy `.env.example` to `.env`.
3. Generate a local `SECRET_KEY` and replace the PostgreSQL placeholders.
4. Create and activate `.venv`.
5. Install Python dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```

6. Install and build frontend assets:

   ```bash
   npm ci
   npm run build
   ```

7. Prepare the database:

   ```bash
   python src/manage.py migrate
   python src/manage.py loaddata fixtures/locations/europe-2026-10-06.json.gz
   python src/manage.py seed_games
   python src/manage.py seed_users
   python src/manage.py seed_events
   python src/manage.py seed_registrations
   ```

8. Start the development server:

   ```bash
   python src/manage.py runserver
   ```

9. Open `http://localhost:8000`.

New empty databases load the fixed GeoNames catalogue from `fixtures/locations/`; no network is needed for this step. See its README and manifest for provenance, integrity and scope. Do not load the fixture over an existing catalogue. `load_cities` remains available for deliberate catalogue refreshes in a separate empty database.

## Demo Data

The demo dataset is synthetic.

- `seed_users` creates 18 synthetic users.
- `horus_lupercal` is the intended public demo account.
- The other 17 seed users have unusable passwords after the seed repair policy.
- Events and registrations are synthetic and deterministic.
- `reset_demo --confirm` can rebuild the disposable demo dataset, preserving
  Locations and recreating Games, Users, Events, Registrations, and the private
  admin in the approved order.

Try the [live app](https://tabula-belli.n3t0n.com/) with `horus_lupercal` /
`TestPass123!`, or create your own account. The login form can fill these public
credentials. For your own local administrator, run
`python src/manage.py createsuperuser`; never reuse production credentials.

During a reset, PostgreSQL locks drain in-flight requests, show a temporary
maintenance page, and skip event completion until the next scheduled run. Locks
release after success, rollback, or connection termination. Connect directly to
PostgreSQL, without transaction pooling. Keep reset credentials and permission
restricted to the reset job. See the operations manual for scheduler setup and
failure handling.

## Testing

Run the Django suite and checks against PostgreSQL:

```bash
env DEBUG=False .venv/bin/python src/manage.py test
env DEBUG=False .venv/bin/python src/manage.py check
env DEBUG=False .venv/bin/python src/manage.py makemigrations --check --dry-run
.venv/bin/python -m pip check
```

Build and validate frontend assets:

```bash
npm ci
npm ls
npm audit
npm run build
```

## CI

GitHub Actions is defined in `.github/workflows/ci.yml`. It validates:

- Python dependency installation and `pip check`;
- Python dependency audit;
- Django checks, migrations, and PostgreSQL-backed tests with coverage;
- frontend dependency install/audit;
- frontend build;
- `collectstatic`;
- production deployment checks;
- repository cleanliness after generated assets are rebuilt.

No badge is included yet because the final public repository URL has not been
created.

## Deployment Readiness

The application is deployed at [tabula-belli.n3t0n.com](https://tabula-belli.n3t0n.com/).

The current production strategy is:

- PostgreSQL as the only database backend;
- Gunicorn as the application server;
- WhiteNoise for collected static files;
- Resend via django-anymail for django-allauth transactional email;
- Formspree for the public Contact form;
- `/health/` as a minimal healthcheck endpoint;
- scheduled `complete_past_events`;
- scheduled `reset_demo --confirm` for disposable demo refreshes.

The event completion job runs every five minutes. Enable periodic demo resets
only after deploying the maintenance protection to the web and both jobs; see
[the operations manual](MANUAL_DE_INSTALACION.md) for the safeguards.

## Project Structure

```text
tabula_belli/
├── .github/workflows/ci.yml        # CI pipeline
├── fixtures/                       # Demo fixtures and game datasets
├── MANUAL_DE_INSTALACION.md        # Detailed setup and operations manual
├── package.json                    # Frontend build scripts and dependencies
├── requirements.in                 # Direct Python dependencies
├── requirements.txt                # Fully pinned Python environment
└── src/
    ├── apps/                       # Domain apps
    ├── config/                     # Django settings and URL configuration
    ├── static/                     # Static sources and versioned assets
    └── templates/                  # Shared templates
```

## Publication Notes

Screenshots and the final publication review remain pending. Private credentials
belong in local environment files or provider secrets, never in this repository.
