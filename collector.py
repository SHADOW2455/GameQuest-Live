"""Public ATS adapters for configured gaming-company career feeds.

Only configured employer boards are queried. Each adapter uses a public job-board
endpoint and preserves the employer/ATS application URL returned by that source.
This is not a universal jobs search API; companies on other ATS platforms need
additional adapters or direct official-career links.
"""
from __future__ import annotations
import os, requests, logging
from datetime import datetime, timezone
log = logging.getLogger("gamequest.collector")
TIMEOUT = 20
HEADERS = {"User-Agent": "GameQuestJobTracker/1.0 (public career-board reader)"}
COMPANY_NAMES = {
    "rockstargames": "Rockstar Games", "riotgamesup": "Riot Games — University Programs",
    "riotgamesinc": "Riot Games", "voodoo": "Voodoo", "moonactive": "Moon Active",
    "bloxd": "Bloxd", "good-job-games": "Good Job Games", "good_job_games": "Good Job Games",
    "ubisoft2": "Ubisoft", "intrepidstudios": "Intrepid Studios", "airlabinc": "Airlab / Playwing",
    "epicgames": "Epic Games", "electronicarts": "Electronic Arts", "ea": "Electronic Arts",
    "playstation": "PlayStation", "nintendo": "Nintendo", "take2games": "Take-Two Interactive",
    "zynga": "Zynga", "bandainamco": "Bandai Namco", "activision": "Activision",
    "blizzard": "Blizzard Entertainment", "king": "King", "supercell": "Supercell",
    "gameloft": "Gameloft", "cdprojektred": "CD PROJEKT RED", "remedy": "Remedy Entertainment",
    "larianstudios": "Larian Studios",
}
def company_name(slug: str) -> str:
    return COMPANY_NAMES.get(slug.lower(), slug.replace("-", " ").replace("_", " ").title())
def dt(value):
    if not value: return None
    try:
        if isinstance(value, (int, float)):
            # Some feeds use milliseconds since epoch.
            if value > 10_000_000_000: value = value / 1000
            return datetime.fromtimestamp(value, timezone.utc)
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception: return None
def _get(url, **kwargs):
    headers = dict(HEADERS); headers.update(kwargs.pop("headers", {}))
    response = requests.get(url, timeout=TIMEOUT, headers=headers, **kwargs)
    response.raise_for_status()
    return response

def greenhouse(slug):
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    jobs = _get(url).json().get("jobs", [])
    out = []
    for x in jobs:
        title = x.get("title", "")
        content = x.get("content", "") or ""
        loc = (x.get("location") or {}).get("name", "Not specified")
        blob = (title + " " + content + " " + loc).lower()
        out.append({"source": f"greenhouse:{slug}", "source_id": str(x["id"]), "company": company_name(slug),
            "title": title, "location": loc,
            "work_mode": "Remote" if "remote" in blob else ("Hybrid" if "hybrid" in blob else "On-site" if any(k in blob for k in ("on-site", "onsite", "office-based")) else "Unknown"),
            "experience": "Fresher" if any(k in blob for k in ("junior", "entry level", "entry-level", "intern", "trainee", "new grad", "graduate")) else "Experienced",
            "employment_type": "Internship" if "intern" in blob else ("Contract" if "contract" in blob else "Unknown"),
            "official_url": x.get("absolute_url") or f"https://job-boards.greenhouse.io/{slug}",
            "published_at": dt(x.get("updated_at")), "status": "Unverified", "description": content[:5000]})
    return out

def lever(slug):
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    rows = _get(url).json(); out = []
    for x in rows:
        title = x.get("text", "")
        desc = (x.get("descriptionPlain") or "") + " " + str(x.get("lists") or "")
        cats = x.get("categories") or {}; loc = cats.get("location") or "Not specified"
        blob = (title + " " + desc + " " + loc).lower()
        out.append({"source": f"lever:{slug}", "source_id": str(x["id"]), "company": company_name(slug),
            "title": title, "location": loc,
            "work_mode": "Remote" if "remote" in blob else ("Hybrid" if "hybrid" in blob else "On-site" if "on-site" in blob or "onsite" in blob else "Unknown"),
            "experience": "Fresher" if any(k in blob for k in ("junior", "entry level", "entry-level", "intern", "trainee", "new grad", "graduate")) else "Experienced",
            "employment_type": cats.get("commitment") or "Unknown", "official_url": x.get("hostedUrl") or x.get("applyUrl") or url,
            "published_at": dt(x.get("createdAt")), "status": "Unverified", "description": desc[:5000]})
    return out

def ashby(slug):
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"
    rows = _get(url).json().get("jobs", []); out = []
    for x in rows:
        title = x.get("title", "")
        desc = x.get("descriptionPlain") or x.get("descriptionHtml") or ""
        loc = x.get("location") or "Not specified"
        blob = (title + " " + desc + " " + str(loc)).lower()
        out.append({"source": f"ashby:{slug}", "source_id": str(x.get("id") or x.get("jobUrl")), "company": company_name(slug),
            "title": title, "location": loc,
            "work_mode": "Remote" if "remote" in blob else ("Hybrid" if "hybrid" in blob else "On-site" if "on-site" in blob or "onsite" in blob else "Unknown"),
            "experience": "Fresher" if any(k in blob for k in ("junior", "entry level", "entry-level", "intern", "trainee", "new grad", "graduate")) else "Experienced",
            "employment_type": x.get("employmentType") or ("Internship" if "intern" in blob else "Unknown"),
            "official_url": x.get("jobUrl") or url, "published_at": dt(x.get("publishedAt")),
            "status": "Unverified", "description": desc[:5000]})
    return out

def smartrecruiters(slug):
    # Public API supports offset/limit; continue through pages instead of silently
    # checking only the first 100 openings.
    out = []; offset = 0; limit = 100; max_pages = 20
    for _ in range(max_pages):
        url = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit={limit}&offset={offset}"
        data = _get(url).json(); rows = data.get("content", [])
        for x in rows:
            title = x.get("name", "")
            loc_obj = x.get("location") or {}
            loc = loc_obj.get("city") or ""
            if loc_obj.get("region"): loc += (", " if loc else "") + loc_obj["region"]
            if loc_obj.get("country"): loc += (", " if loc else "") + loc_obj["country"]
            loc = loc or "Not specified"
            ident = str(x.get("id", ""))
            blob = (title + " " + loc).lower()
            # The API posting page is the employer-hosted ATS application page.
            job_url = f"https://jobs.smartrecruiters.com/{slug}/{ident}"
            out.append({"source": f"smartrecruiters:{slug}", "source_id": ident, "company": company_name(slug),
                "title": title, "location": loc,
                "work_mode": "Remote" if "remote" in blob else ("Hybrid" if "hybrid" in blob else "On-site" if "on-site" in blob or "onsite" in blob else "Unknown"),
                "experience": "Fresher" if any(k in blob for k in ("junior", "entry level", "entry-level", "intern", "trainee", "new grad", "graduate")) else "Experienced",
                "employment_type": "Unknown", "official_url": job_url, "published_at": dt(x.get("releasedDate")),
                "status": "Unverified", "description": ""})
        if len(rows) < limit: break
        offset += len(rows)
    return out

PROVIDERS = {
    "greenhouse": ("GREENHOUSE_BOARDS", greenhouse),
    "lever": ("LEVER_BOARDS", lever),
    "ashby": ("ASHBY_BOARDS", ashby),
    "smartrecruiters": ("SMARTRECRUITERS_COMPANIES", smartrecruiters),
}
def collect_all_with_report():
    """Return (all jobs, one success/error report per configured source)."""
    out, reports, configured = [], [], 0
    for provider, (env_key, adapter) in PROVIDERS.items():
        slugs = [x.strip() for x in os.getenv(env_key, "").split(",") if x.strip()]
        for slug in slugs:
            configured += 1
            source = f"{provider}:{slug}"
            try:
                jobs = adapter(slug)
                out.extend(jobs)
                reports.append({"source": source, "result": "ok", "details": f"Feed request succeeded; {len(jobs)} current postings imported."})
                log.info("Source %s succeeded: %s postings", source, len(jobs))
            except Exception as e:
                detail = f"Feed request failed: {type(e).__name__}: {e}"[:500]
                reports.append({"source": source, "result": "error", "details": detail})
                log.exception("Source %s failed", source)
    if configured == 0:
        reports.append({"source": "configuration", "result": "warning", "details": "No feeds configured. Add valid public ATS board slugs to .env."})
    return out, reports

def collect_all():
    """Backwards-compatible job-only collector."""
    jobs, _ = collect_all_with_report()
    return jobs

def verify_job(source, source_id, company, url):
    """Verify a posting on its source board; request failures remain Unverified."""
    try:
        provider, slug = source.split(":", 1) if ":" in source else (source, company)
        if provider == "greenhouse":
            r = _get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
            ids = {str(x.get("id")) for x in r.json().get("jobs", [])}
            return {"status": "Open" if str(source_id) in ids else "Closed"}
        if provider == "lever":
            rows = _get(f"https://api.lever.co/v0/postings/{slug}?mode=json").json()
            ids = {str(x.get("id")) for x in rows if x.get("id") is not None}
            return {"status": "Open" if str(source_id) in ids else "Closed"}
        if provider == "ashby":
            rows = _get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}").json().get("jobs", [])
            ids = {str(x.get("id") or x.get("jobUrl")) for x in rows}
            return {"status": "Open" if str(source_id) in ids else "Closed"}
        if provider == "smartrecruiters":
            # The configured feed may paginate; search a bounded number of pages.
            offset = 0; limit = 100
            for _ in range(20):
                data = _get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit={limit}&offset={offset}").json()
                rows = data.get("content", [])
                if str(source_id) in {str(x.get("id")) for x in rows}:
                    return {"status": "Open"}
                if len(rows) < limit: return {"status": "Closed"}
                offset += len(rows)
            return {"status": "Unverified"}
    except Exception as e:
        log.warning("Verification failed for %s/%s: %s", source, source_id, e)
    return {"status": "Unverified"}
