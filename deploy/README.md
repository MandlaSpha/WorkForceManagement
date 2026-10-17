# Deploying the Workforce Management app

Hosting is undecided, so this is a portable container deployment: any host with Docker and the
Compose plugin. Nothing here is tied to a cloud.

## What runs

| Service | What it is |
|---|---|
| `db` | PostgreSQL 16, data in the `dbdata` volume |
| `valkey` | The job queue (no persistence: jobs are recorded in the database) |
| `migrate` | Runs once at start and applies database migrations |
| `api` | The Django API (gunicorn), port 8000 inside the network only |
| `worker` | Celery worker: forecasts, auto-schedule, report sending |
| `beat` | Celery scheduler: nightly audit check, report schedules, job clean-up |
| `web` | nginx: the built web app, and `/api` forwarded to the API. The only published port (`WEB_PORT`) |

## First start

1. `cp .env.example .env` and fill in **every** value. Generate the secret key and the database
   password randomly. `.env` is git-ignored; keep it out of version control and out of images.
2. `docker compose build` (the API image is built from the repository root).
3. `docker compose up -d`.
4. Create the first administrator: `docker compose exec api python manage.py createsuperuser`
   (then set their role to admin in the user list), or use the identity provider you configured.
5. Put a TLS terminator (your reverse proxy or load balancer) in front of `web`, forwarding
   `X-Forwarded-Proto`. Cookies are `Secure`, so the app only signs in over HTTPS.

Do **not** run `seed_demo` or `seed_demo_data` in production: they refuse to run unless
`DJANGO_DEBUG` is on, and they invent people.

## Backups

`docker compose --profile backup run --rm backup` writes a compressed dump to `BACKUP_DIR` and
deletes dumps older than `BACKUP_KEEP_DAYS`. Schedule it nightly from the host (cron or a systemd
timer). **Copy the dumps off the host**, to storage in South Africa (POPIA, NFR-03). Restore with the
command in `backup.sh`. Test a restore before you rely on it. The audit trail is in the database,
so it is in the dump; `manage.py audit_export` also writes a day's chain heads for storage you
cannot edit.

## Data residency

All data stays in the database volume and in the dumps you take. Nothing is sent to a third-party
service: the browser's telemetry is off by default, and outgoing mail goes only to the SMTP server
you name. Choose a host and backup storage inside South Africa.

## Upgrading

`git pull`, `docker compose build`, `docker compose up -d`. The `migrate` service applies new
migrations before the API restarts. Take a backup first.

## Not done here

Monitoring (a collector and dashboards), a hardened secrets store, high availability (one database,
one API), and TLS itself are the hosting platform's to provide once it is chosen.
