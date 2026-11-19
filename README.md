# BountyRadar

A self-hosted directory of public bug bounty programs, disclosure policies and audit contests. The initial catalog is empty. Refresh a public dataset in **Sources** to discover real programs. **Discover** supports search, filters, fit scoring and bookmarks. Open a program to inspect source evidence, original policy, normalized scope, changes and workspace downloads.

## Docker Compose

From the BountyRadar directory, with Python 3 and Docker Compose v2 installed:

```sh
python scripts/setup.py
docker compose up --build -d --wait
```

Visit [BountyRadar](http://127.0.0.1:8098). Sign in as **admin** with the generated password in `secrets/admin`. The setup command preserves existing credentials. Keep the deployment directory private. Add team members in **Settings**. The scheduler refreshes the YesWeHack public dataset daily by default. Change the selected feeds and interval in Sources. The API and worker share PostgreSQL. Redis queues tasks. Caddy publishes the loopback port. For remote access, terminate TLS at your reverse proxy and set `COOKIE_SECURE=1`. Change `RADAR_PORT` to avoid port conflicts.

Enable the optional isolated Agent Reach reader with `docker compose --profile research up -d --build`. Use its token from `secrets/reach`. Firecrawl accepts an existing cloud or self-hosted endpoint. Personal and shared provider keys are encrypted at rest. The master key must be backed up separately. [Provider and browsing configuration](docs/research.md).

## Windows local launch

From this directory:

```powershell
py -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
npm.cmd ci --prefix frontend
npm.cmd run build --prefix frontend
.venv/Scripts/python -m scripts.local
```

The Windows launcher binds to localhost and stores its database, initial admin password and encryption key in `%LOCALAPPDATA%/BountyRadar`. It uses SQLite and a background thread for local jobs. The Compose configuration is the multi-process deployment. Open [the local dashboard](http://127.0.0.1:8098).

## Working with data

The React dashboard calls FastAPI on the same origin. A refresh job selects a fixed-origin connector, validates the complete response and normalizes published assets while retaining their original text. A single database transaction stores the observations, snapshots and HTTP cache validators. The directory, change feed and exports read those stored records.

Each program has a stable platform and external identifier. Snapshots record the source, acquisition time, verification level, policy and scope. Observations track the last successful sighting per source. The selected snapshot favors official data, then manually reviewed imports, then secondary directories. Users, sessions, preferences, bookmarks, encrypted connections and job history share the same database.

- **Sources** lists automatic feeds, credentialed APIs and manual-import sources. The latest job identifies download, parse and authorization failures. [Source register and import example](docs/sources.md).
- **Changes** shows snapshot differences, original values, and verification level. Snapshot time, last observation and last official verification are distinct. Disappearance from a complete listing marks possible removal. Outages retain prior data.
- **Settings** lets each researcher weight program fit. Unknown factors contribute zero with a separate evidence coverage percentage. Scope size uses a capped linear scale at 50 rules. Recent scope changes use a 30-day window. The score expresses preference fit.
- **Connections** supports testing, changing and deleting credentials. Team connections require administrator access. **Research** accepts a program, model and optional reader, queues a bounded research job and stores a cited summary for review.
- **Export workspace** downloads Markdown, metadata, normalized scope and changelog together. JSON schemas are in `schemas/`. The authenticated REST interface is documented at [OpenAPI](http://127.0.0.1:8098/docs). Sign in through the dashboard and send the `radar_csrf` cookie value as `X-CSRF-Token` for mutations.

## Operations and checks

[Acceptance results and dashboard preview](docs/acceptance.md)

Run `python -m pip install pytest httpx`, then `python -m pytest`. Run `python -m scripts.verify_slice` with network access to validate fresh ingestion, persistence and all five exports against a real public source. The test uses a temporary database. Run the browser acceptance script in `frontend/tests/browser.mjs` with Playwright, a local origin, and a test account. Compose CI builds the images and checks service health.

Back up PostgreSQL with `sh scripts/backup.sh radar.dump`. Store master, admin and deployment secrets separately with restricted access. Restore into an empty installation before starting its API or workers: start only db, then run `docker compose exec -T db pg_restore -U radar -d radar < radar.dump`, restore the matching master key, and start the remaining services. For a local SQLite backup, stop the app and copy the state directory. Versioned schema migrations run during Compose API startup.

Data restrictions, partial coverage and authenticated connector verification are documented in the source register. Publishing a new snapshot never grants authorization to test an asset.

