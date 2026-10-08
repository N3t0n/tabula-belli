# Installation guide

This guide explains how to run Tabula Belli locally with its reference catalogue and synthetic demo data. You do not need accounts with Northflank, Cloudflare, Resend, or Formspree.

For a quick evaluation without installing anything, use the [published application](https://tabula-belli.n3t0n.com/). For application workflows, see the [User guide](user-guide.md).

## 1. Prerequisites

Install these tools before starting:

| Tool | Version |
| --- | --- |
| Python | 3.12 |
| PostgreSQL server and client tools | 17, with current maintenance updates |
| Node.js | 24.14.0, as recorded in `.node-version` |
| Git | A recent version |

Use the versions recorded in the repository if they change in a later release. PostgreSQL is the application's database backend; there is no SQLite installation path.

You need internet access to clone the repository and install dependencies. The location catalogue is included in the repository and does not require a GeoNames download.

The commands below use the repository root as the working directory. Keep that directory throughout the guide. Unix commands apply to Linux/macOS unless indicated otherwise; Windows examples use PowerShell. Installing and starting PostgreSQL depends on your operating system and installation method.

Check that the tools are available:

```sh
python --version
node --version
npm --version
psql --version
git --version
```

On Linux/macOS, Python may initially be named `python3.12`; on Windows, use `py -3.12` if necessary. After activating the virtual environment below, use `python`.

Check the server's version in step 4 as well: the `psql` client version alone does not identify the server you connect to.

## 2. Get the project

```sh
git clone https://github.com/N3t0n/tabula-belli.git
cd tabula-belli
```

Create a virtual environment and activate it:

```sh
# Linux/macOS
python3.12 -m venv .venv
source .venv/bin/activate
```

```powershell
# Windows PowerShell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell prevents activation, you can use `.\.venv\Scripts\python.exe` instead of `python` for the remaining Python commands; changing your machine's execution policy is not required.

Install the pinned Python dependencies:

```sh
python -m pip install -r requirements.txt
python -m pip check
```

## 3. Create local configuration

Copy the configuration template:

```sh
# Linux/macOS
cp .env.example .env
```

```powershell
# Windows PowerShell
Copy-Item .env.example .env
```

Generate a unique Django secret:

```sh
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Edit `.env` in the repository root. Replace `SECRET_KEY` with the generated value and replace the database placeholders with the credentials you create in step 4. Preserve the generated key exactly; surrounding single quotes can be used for the value in `.env`.

For local development, use:

```dotenv
DJANGO_ENV=development
DEBUG=True
LOG_LEVEL=INFO
ALLOWED_HOSTS=localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=
DB_NAME=tabula_belli_local
DB_USER=tabula_belli_local
DB_PASSWORD=REPLACE_WITH_YOUR_LOCAL_DATABASE_PASSWORD
DB_HOST=127.0.0.1
DB_PORT=5432
DB_SSLMODE=prefer
DEFAULT_FROM_EMAIL=noreply@example.com
RESEND_API_KEY=
FORMSPREE_FORM_ID=
PUBLIC_DEMO_USERNAME=horus_lupercal
DEMO_RESET_ALLOWED=False
```

The `SECRET_KEY` line from the template is also required; it is not repeated above because you must generate your own value.

The `DEMO_RESET_DATABASE_NAME` and `DEMO_ADMIN_*` settings are not needed for this installation recipe. Leave reset disabled; loading the initial dataset does not require the destructive reset command or private administrator credentials.

`.env` is ignored by Git. Do not commit it or copy configuration from the published deployment.

## 4. Create a PostgreSQL database

Start your PostgreSQL 17 server. Open a PostgreSQL administration session using the administrator account from your installation:

```sh
psql -h 127.0.0.1 -U postgres -d postgres
```

On Linux installations that use local peer authentication, the equivalent is often:

```sh
sudo -u postgres psql
```

In that administration session, create a dedicated local role and database:

```sql
CREATE ROLE tabula_belli_local LOGIN;
\password tabula_belli_local
CREATE DATABASE tabula_belli_local OWNER tabula_belli_local;
\q
```

The `\password` command prompts for the password rather than placing it directly in the SQL statement. Set `DB_PASSWORD` in your local `.env` to the same value.

Verify the application role's connection:

```sh
psql -h 127.0.0.1 -U tabula_belli_local -d tabula_belli_local -c "SELECT version();"
```

Confirm that the connected server is PostgreSQL 17. If you use a different port or database/role names, update `.env` accordingly. Connect directly to PostgreSQL; the application's maintenance coordination uses session locks and does not support a transaction-pooling connection.

## 5. Build the frontend

```sh
npm ci
npm run build
```

This compiles Tailwind CSS and copies the pinned HTMX, Alpine.js, and Flowbite files into the static directory. Node is used for asset preparation, not as a second application server.

Generated assets, `node_modules`, and the Python virtual environment are not included in a clean checkout. `npm run watch:css` is available when editing styles locally.

## 6. Create the schema and initial data

Use a new, empty database for this first installation:

```sh
python src/manage.py migrate
python src/manage.py loaddata fixtures/locations/europe-2026-10-06.json.gz
python src/manage.py seed_games
python src/manage.py seed_users
python src/manage.py seed_events
python src/manage.py seed_registrations
```

Keep this order: events depend on games, locations, and players; registrations depend on events and players.

The fixed location fixture contains 43 countries, 948 administrative regions, and 57,945 cities. It includes only reference data. See [catalogue provenance and scope](../fixtures/locations/README.md).

**Do not load that fixture on top of an existing location catalogue.** Its primary keys belong to the supplied dataset. Loading it again is not an update procedure.

The demo seeds provide 123 games, 18 fictional player profiles, and 1,010 event templates. `horus_lupercal` is the public demo identity; the other seed profiles do not have usable login passwords. Events are dated relative to the seed execution date, using the application's Europe/Berlin timezone. The registration count depends on the windows open at the time of execution, so it is not a fixed installation assertion.

Create any optional local administrator **after** loading the seeds, so the administrator is not included in their organizer/participant selection:

```sh
python src/manage.py createsuperuser
```

Choose your own credentials. The initial demo seeds do not create a superuser.

Django Sites supplies the site identity used by account flows. Set the local site before trying registration. From the repository root with your virtual environment active, run:

```sh
python src/manage.py shell -c "from django.contrib.sites.models import Site; Site.objects.update_or_create(pk=1, defaults={'name': 'Tabula Belli', 'domain': 'localhost:8000'})"
```

Alternatively, edit Site ID 1 through the Sites section of Django Admin if you created a local administrator. Use a hostname and port, without `http://` or a path. If you access the application through another local address, use that address consistently and authorize its hostname in `ALLOWED_HOSTS`. If the development server is already running when you change the site, restart it to clear any cached site identity.

## 7. Start and check the application

```sh
python src/manage.py check
python src/manage.py runserver
```

Open **http://localhost:8000/**. Keep the terminal running. Stop the development server with Ctrl+C.

Check the following:

1. The homepage and event list load with styles.
2. Filters and event details work.
3. The login page can fill `horus_lupercal` / `TestPass123!`; submit the login to enter.
4. My Events and the profile page load. The shared demo profile and account settings are protected; event interaction remains available.
5. If you created an administrator, sign in at `http://localhost:8000/admin/`.

The health endpoint is `http://localhost:8000/health/`. Its success response confirms the application responds; it does not replace the checks above.

## 8. Try account verification and password recovery

With `DJANGO_ENV=development`, transactional emails are printed in the terminal running Django. There is no actual delivery to an inbox and no Resend key is required.

To try a new account:

1. Sign out of the shared demo account.
2. Register with a separate username and email address.
3. Read the verification email printed in the server terminal.
4. Open its confirmation link and complete the confirmation page.
5. Sign in with the new account.

Password recovery follows the same pattern: request a reset for your own local account, read the terminal email, and open its link. Recovery of the shared demo account is intentionally restricted.

The Contact page is independent of these emails. Its submit button stays disabled while `FORMSPREE_FORM_ID` is empty. To test contact delivery, configure your own Formspree form; do not reuse the portfolio owner's endpoint.

## 9. Run the tests

Django creates and removes a separate test database. The dedicated local database role needs permission to create it. In a PostgreSQL administration session, grant:

```sql
ALTER ROLE tabula_belli_local CREATEDB;
```

This is for a local test role; it is not a recommendation to expand production database permissions.

Run with `DEBUG=False`, keeping `DJANGO_ENV=development` so tests do not need production email credentials:

```sh
# Linux/macOS
DEBUG=False python src/manage.py test
```

```powershell
# Windows PowerShell
$env:DEBUG = 'False'
python src/manage.py test
Remove-Item Env:DEBUG
```

Additional checks:

```sh
python src/manage.py makemigrations --check --dry-run
python -m pip check
npm run build
```

Frontend interaction tests can also be run without sending network requests:

```sh
node --test scripts/tests/*.test.cjs
```

The installation and full Django test suite have been validated on Linux with PostgreSQL 17.11, Python 3.12 and Node.js 24.14.0. The Windows and macOS instructions are provided for convenience; those operating systems have not been separately validated.

Tests include PostgreSQL-specific transaction and concurrency behavior. Run them against a dedicated local server, never the published database.

## 10. Local maintenance and troubleshooting

To update persisted statuses after local events end, run:

```sh
python src/manage.py complete_past_events
```

You do not need to install a scheduler for local evaluation. Repeat the command when needed; normal browsing does not run the periodic event-completion job.

| Symptom | What to check |
| --- | --- |
| Missing database configuration | `.env` is in the repository root and `DB_NAME`, `DB_USER`, and `DB_PASSWORD` are set. |
| Connection refused or authentication failed | PostgreSQL is running; host, port, role, password, and database match `.env`. Check with `psql`. |
| Missing tables | Run migrations against the intended local database. |
| Missing games or locations | Load the fixed fixture once into empty location tables, then run the seeds in order. |
| Unstyled pages or missing frontend behavior | Run `npm ci` and `npm run build`, then reload the page. |
| Verification email not in your inbox | Development emails are printed in the server terminal. |
| A seed player's login fails | Only `horus_lupercal` has a usable public demo password. Create another account for your own identity. |
| Test database permission denied | Grant `CREATEDB` to the dedicated local test role. |
| Contact cannot be submitted | Expected when `FORMSPREE_FORM_ID` is empty. |
| Production email key required locally | Ensure `DJANGO_ENV=development`; an exported environment variable can override `.env`. |

For a completely fresh dataset, create a separate empty local database and repeat migrations and the initial-data steps. Do not treat the seed commands as a harmless refresh of visitor-created content: they can update existing records. `reset_demo` is an explicitly destructive operation and is unnecessary for first-time installation.

## Hosting your own instance

This guide covers local development. A production deployment needs its own secrets, PostgreSQL connection, allowed hosts, trusted origins, HTTPS/proxy configuration, built and collected static files, and application server.

Set up your own transactional email provider; the current production backend is Resend. Contact delivery requires your own Formspree endpoint. Schedule `complete_past_events` for event completion. Enable a recurring `reset_demo` only for an intentionally disposable demonstration dataset, with its safeguards configured.

The published portfolio's provider accounts, secrets, and private maintenance instructions are not required to run the code locally and are not distributed with the repository.
