# GameQuest Professional — FastAPI + PostgreSQL-ready starter

This is a runnable backend starter, not a fully live global job index. The website's Refresh button now triggers the collection endpoint and then reloads the dashboard; the scheduled worker also collects at the configured interval. It includes a responsive UI, a FastAPI API, SQLAlchemy models, a scheduled collector, starter Greenhouse/Lever public board adapters, status fields/timestamps, local-browser saved/applied controls, source-run history, and optional SMTP alerts.

## 1. Run locally on Windows

Install Python 3.11+ from https://www.python.org/downloads/ and enable **Add Python to PATH** during installation.

1. Extract the ZIP into a folder, for example `C:\GameQuest_Professional`.
2. Open that folder in File Explorer.
3. Click the address bar, type `cmd`, and press Enter.
4. Run:

```bat
py -m venv .venv
.venv\Scripts\activate
py -m pip install -r requirements.txt
copy .env.example .env
uvicorn main:app --reload
```

5. Open http://127.0.0.1:8000 in Chrome.
6. API docs: http://127.0.0.1:8000/docs
7. Health: http://127.0.0.1:8000/api/health

SQLite is used locally by default. The scheduler runs collection and verification at configured intervals, but **no employer boards are configured by default**, so no job records are expected until you add board slugs.

## 2. Official employer career pages (what the user asked for)

The dashboard includes direct official careers links, including Rockstar Games:
- Rockstar Games openings: https://www.rockstargames.com/careers/openings
- Ubisoft: https://www.ubisoft.com/en-us/company/careers
- Electronic Arts: https://www.ea.com/careers
- Riot Games: https://www.riotgames.com/en/work-with-us/jobs
- Epic Games: https://www.epicgames.com/site/careers/jobs
- PlayStation: https://www.playstation.com/en-us/corporate/playstation-careers/
- Nintendo: https://careers.nintendo.com/job-openings/
- Take-Two Interactive: https://careers.take2games.com/

The links are direct official career pages, not third-party search results. To import listings into the dashboard, a supported ATS adapter must be configured for each employer. Rockstar's official Greenhouse board slug is `rockstargames`; it is included in `.env.example` as a starting source. Other companies may use different ATS providers and need separate adapters. Direct links remain useful even if an employer has no supported feed.

## 3. Configure sources

The starter adapters use public board endpoints for Greenhouse and Lever. They are not global search APIs; each requires a specific company/board slug. Configure only sources you have identified and checked for permitted use.

Edit `.env` (the example now includes `GREENHOUSE_BOARDS=rockstargames`):
- `GREENHOUSE_BOARDS=rockstargames,anotherverifiedslug`
- `LEVER_BOARDS=companyslug1,companyslug2`

The collector searches titles/descriptions for game QA/testing keywords. This keyword matching can miss unusual job titles and can include false positives; refine it as coverage grows. Add additional permitted source adapters for other ATS providers and official employer sites.

## 4. Email alerts

Set SMTP provider values in `.env`: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, and `ALERT_TO`. Use a provider/app password; never commit secrets. Email sends only for newly discovered records. Configure a proper transactional email provider for production and test deliverability.

## 5. Production deployment architecture

Recommended:
- Web/API: Render web service (or equivalent)
- Database: managed PostgreSQL (e.g. Supabase or Render PostgreSQL)
- Scheduler: a dedicated worker or scheduled job rather than relying on a web instance that may sleep/restart
- Secrets: provider environment variables, never frontend files or Git
- Alerts: transactional email provider
- Authentication: implement user accounts before allowing public users to save private applications
- Monitoring: logs, source-health dashboard, retries, rate limits, feed failure alerts

Set `DATABASE_URL` to your managed PostgreSQL connection string. If your provider gives `postgres://`, normalize it to a supported SQLAlchemy URL such as `postgresql+psycopg://...` if required by your environment.

For a simple Render deployment:
1. Push the folder to a GitHub repository.
2. Create a Render **Web Service** from the repository.
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Set environment variables in the host dashboard.
6. Provision PostgreSQL and set `DATABASE_URL`.
7. For robust scheduling, deploy a separate worker with `ENABLE_SCHEDULER=true`, and set the web service to `ENABLE_SCHEDULER=false` to prevent duplicate schedulers.
8. Do not expose `/api/admin/run-collection` publicly without authentication; add admin authorization before production.

## 6. Important limitations and correctness notes

- **Coverage is not worldwide-complete.** Only configured board slugs are searched; no universal API contains every gaming job.
- **Near-real-time depends on source update/poll interval.** Default collection interval is 30 minutes, but employer feeds may update later or impose limits.
- **Status verifier is intentionally conservative and currently returns `Unverified` for ATS jobs.** Before treating this as production-ready, implement exact source-specific status verification that positively checks requisition IDs on a complete current board. Do not mark Closed merely because a request timed out, returned a CAPTCHA, or an adapter failed.
- **Experience/work mode are heuristic labels.** Remote/hybrid/on-site and fresher/experienced should ideally be parsed from structured source fields; ambiguous cases should be Unknown.
- **Official links** are taken from ATS-hosted job URLs when the source provides them. Always confirm the employer and application page.
- **Saved/application status** is local browser storage in this starter, not yet synced to a secure user account. API endpoints use a placeholder `user_key`; add authentication and authorization before multi-user/public use.
- **No 100% error-free or instant service guarantee is realistic.** Add tests, source-specific contracts, observability, retries, alerting, and manual review.
- Respect the terms of each job board and employer website. Prefer official APIs/feeds; do not bypass access controls or CAPTCHAs.

## 7. Recommended next engineering tasks

1. Add automated tests for source adapters and duplicate handling.
2. Store exact ATS board slug separately from company display name.
3. Implement source-specific verification using full feed snapshots, with `Open`, `Closed`, `Unverified` and evidence fields.
4. Persist user accounts and application records in PostgreSQL.
5. Add pagination and source configuration UI.
6. Add a proper notification preferences table and alert deduplication.
7. Add monitoring for stale sources and ingestion failures.

## Expanded company coverage and status verification

The dashboard includes official career-page links for multiple major publishers and studios, including Rockstar, Ubisoft, EA, Riot, Epic, PlayStation/Sony, Nintendo, Take-Two, Zynga, Bandai Namco, Blizzard, Activision/King, Xbox/Microsoft Gaming, Valve, CD PROJEKT RED, Supercell, Gameloft, Remedy, Larian, and Sledgehammer. These links are direct employer career portals; a link does not mean that the employer's listings are already ingested into the database.

The collector supports public board APIs for Greenhouse, Lever, Ashby, and SmartRecruiters. Set verified slugs in `.env`:
- `GREENHOUSE_BOARDS=rockstargames`
- `LEVER_BOARDS=verified-slug`
- `ASHBY_BOARDS=verified-board-name`
- `SMARTRECRUITERS_COMPANIES=verified-company-id`

Do not assume a company's brand name is its ATS slug. Add a slug only after confirming its official board/API. The project verifies Greenhouse, Lever, and Ashby listings against the current public feed; SmartRecruiters missing items remain `Unverified` to avoid falsely marking a job closed when pagination may hide it. Failed feed requests stay `Unverified`. An official careers portal without one of these public feed formats needs a dedicated, site-specific adapter; this package does not claim to scrape every employer.

For production, secure `/api/admin/run-collection` with authentication, use PostgreSQL, add monitoring/backups, and review each source's terms and rate limits. SMTP alerts require valid credentials. No credentials are needed for the local demo.
