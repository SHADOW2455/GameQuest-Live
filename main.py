from __future__ import annotations
import os, logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, String, DateTime, Boolean, Text, select, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session, sessionmaker
from pydantic import BaseModel, HttpUrl
from apscheduler.schedulers.background import BackgroundScheduler
from collector import collect_all_with_report, verify_job
from alerts import send_new_job_alert

logging.basicConfig(level=os.getenv("LOG_LEVEL","INFO"))
log=logging.getLogger("gamequest")
DATABASE_URL=os.getenv("DATABASE_URL","sqlite:///./gamequest.db")
connect_args={"check_same_thread":False} if DATABASE_URL.startswith("sqlite") else {}
engine=create_engine(DATABASE_URL,connect_args=connect_args,pool_pre_ping=True)
SessionLocal=sessionmaker(bind=engine,autoflush=False,expire_on_commit=False)

class Base(DeclarativeBase): pass
class Job(Base):
    __tablename__="jobs"
    id: Mapped[int]=mapped_column(primary_key=True)
    source: Mapped[str]=mapped_column(String(80),index=True)
    source_id: Mapped[str]=mapped_column(String(250),index=True)
    company: Mapped[str]=mapped_column(String(250),index=True)
    title: Mapped[str]=mapped_column(String(300),index=True)
    location: Mapped[str]=mapped_column(String(300),default="Not specified")
    work_mode: Mapped[str]=mapped_column(String(40),default="Unknown")
    experience: Mapped[str]=mapped_column(String(40),default="Unknown")
    employment_type: Mapped[str]=mapped_column(String(80),default="Unknown")
    official_url: Mapped[str]=mapped_column(Text)
    published_at: Mapped[Optional[datetime]]=mapped_column(DateTime(timezone=True),nullable=True)
    first_seen_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
    last_checked_at: Mapped[Optional[datetime]]=mapped_column(DateTime(timezone=True),nullable=True)
    status: Mapped[str]=mapped_column(String(30),default="Unverified")
    description: Mapped[str]=mapped_column(Text,default="")
    notified: Mapped[bool]=mapped_column(Boolean,default=False)
class SavedJob(Base):
    __tablename__="saved_jobs"
    id: Mapped[int]=mapped_column(primary_key=True)
    job_id: Mapped[int]=mapped_column(index=True)
    user_key: Mapped[str]=mapped_column(String(150),index=True)
    application_status: Mapped[str]=mapped_column(String(50),default="Saved")
    notes: Mapped[str]=mapped_column(Text,default="")
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc),onupdate=lambda:datetime.now(timezone.utc))
class SourceRun(Base):
    __tablename__="source_runs"
    id: Mapped[int]=mapped_column(primary_key=True)
    source: Mapped[str]=mapped_column(String(100))
    checked_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
    result: Mapped[str]=mapped_column(String(30))
    details: Mapped[str]=mapped_column(Text,default="")

def db():
    with SessionLocal() as s: yield s

class SaveRequest(BaseModel):
    user_key: str="local-user"
    application_status: str="Saved"
    notes: str=""

def now(): return datetime.now(timezone.utc)
def public(j):
    return {"id":j.id,"source":j.source,"company":j.company,"title":j.title,"location":j.location,
            "work_mode":j.work_mode,"experience":j.experience,"employment_type":j.employment_type,
            "official_url":j.official_url,"published_at":j.published_at,"first_seen_at":j.first_seen_at,
            "last_checked_at":j.last_checked_at,"status":j.status,"description":j.description[:700]}

def run_collection():
    jobs, reports = collect_all_with_report()
    added = 0
    updated = 0
    with SessionLocal() as s:
        for item in jobs:
            existing=s.scalar(select(Job).where(Job.source==item["source"],Job.source_id==item["source_id"]))
            if existing is None:
                item["first_seen_at"]=now()
                item.setdefault("status","Unverified")
                j=Job(**item); s.add(j); s.flush(); added += 1
                if not j.notified:
                    send_new_job_alert(j)
                    j.notified=True
            else:
                for k,v in item.items():
                    # Preserve a previously verified Open/Closed status during collection.
                    # The verifier (scheduled or manual) is responsible for changing status,
                    # not a fresh feed import which defaults every row to Unverified.
                    if k not in ("source", "source_id", "first_seen_at", "status"):
                        setattr(existing, k, v)
                updated += 1
        for report in reports:
            s.add(SourceRun(source=report["source"], result=report["result"], details=report["details"]))
        s.commit()
    summary={"configured_sources":len([r for r in reports if r["source"]!="configuration"]),
             "successful_sources":sum(1 for r in reports if r["result"]=="ok"),
             "failed_sources":sum(1 for r in reports if r["result"]=="error"),
             "jobs_fetched":len(jobs), "new_jobs":added, "updated_jobs":updated}
    log.info("Collection summary: %s", summary)
    return summary

def run_verification():
    with SessionLocal() as s:
        jobs=s.scalars(select(Job).where(Job.status!="Closed").limit(500)).all()
        for j in jobs:
            try:
                result=verify_job(j.source,j.source_id,j.company,j.official_url)
                j.status=result["status"]
                j.last_checked_at=now()
                s.add(SourceRun(source=j.source,result="ok",details=f"Status: {j.status}"))
            except Exception as e:
                j.status="Unverified"
                j.last_checked_at=now()
                s.add(SourceRun(source=j.source,result="error",details=str(e)[:500]))
        s.commit()

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    scheduler=BackgroundScheduler(timezone="UTC")
    if os.getenv("ENABLE_SCHEDULER","true").lower()=="true":
        scheduler.add_job(run_collection,"interval",minutes=int(os.getenv("COLLECT_INTERVAL_MINUTES","30")),id="collect",max_instances=1,coalesce=True)
        scheduler.add_job(run_verification,"interval",minutes=int(os.getenv("VERIFY_INTERVAL_MINUTES","60")),id="verify",max_instances=1,coalesce=True)
        scheduler.start()
    app.state.scheduler=scheduler
    yield
    if scheduler.running: scheduler.shutdown(wait=False)

app=FastAPI(title="GameQuest Jobs API",version="0.1.0",lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=os.getenv("CORS_ORIGINS","*").split(","),allow_methods=["*"],allow_headers=["*"])
@app.get("/api/health")
def health():
    return {"status":"ok","service":"GameQuest API","utc_time":now(),"scheduler_enabled":os.getenv("ENABLE_SCHEDULER","true").lower()=="true"}
@app.get("/api/jobs")
def list_jobs(q:str="",level:str="all",mode:str="all",status:str="all",limit:int=100,offset:int=0,s:Session=Depends(db)):
    stmt=select(Job)
    if q: stmt=stmt.where(func.lower(Job.title+" "+Job.company+" "+Job.description).contains(q.lower()))
    if level.lower()!="all": stmt=stmt.where(func.lower(Job.experience)==level.lower())
    if mode.lower()!="all": stmt=stmt.where(func.lower(Job.work_mode)==mode.lower())
    if status.lower()!="all": stmt=stmt.where(func.lower(Job.status)==status.lower())
    total=s.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows=s.scalars(stmt.order_by(Job.first_seen_at.desc()).limit(min(limit,250)).offset(offset)).all()
    return {"total":total,"items":[public(j) for j in rows]}
@app.get("/api/sources")
def sources(s:Session=Depends(db)):
    rows=s.scalars(select(SourceRun).order_by(SourceRun.checked_at.desc()).limit(50)).all()
    return [{"source":r.source,"checked_at":r.checked_at,"result":r.result,"details":r.details} for r in rows]
@app.post("/api/jobs/{job_id}/save")
def save_job(job_id:int,body:SaveRequest,s:Session=Depends(db)):
    if not s.get(Job,job_id): raise HTTPException(404,"Job not found")
    row=s.scalar(select(SavedJob).where(SavedJob.job_id==job_id,SavedJob.user_key==body.user_key))
    if row:
        row.application_status=body.application_status; row.notes=body.notes; row.updated_at=now()
    else:
        row=SavedJob(job_id=job_id,user_key=body.user_key,application_status=body.application_status,notes=body.notes);s.add(row)
    s.commit(); return {"ok":True,"saved_job_id":row.id}
@app.get("/api/saved")
def saved_jobs(user_key:str="local-user",s:Session=Depends(db)):
    rows=s.scalars(select(SavedJob).where(SavedJob.user_key==user_key).order_by(SavedJob.updated_at.desc())).all()
    return [{"job":public(s.get(Job,r.job_id)),"application_status":r.application_status,"notes":r.notes} for r in rows if s.get(Job,r.job_id)]
@app.post("/api/admin/run-collection")
def manual_collection(s:Session=Depends(db)):
    # Secure this endpoint with authentication before public production use.
    summary = run_collection()
    # Keep summary available both at top level (for the dashboard) and nested for API clients.
    return {"ok": True, "message": "Collection run completed; inspect /api/sources and logs.", **summary, "summary": summary}

@app.post("/api/admin/verify-job/{job_id}")
def manual_verify_single_job(job_id:int, s:Session=Depends(db)):
    """Immediately verify one saved listing against its configured public source."""
    job = s.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    result = verify_job(job.source, job.source_id, job.company, job.official_url)
    job.status = result.get("status", "Unverified")
    job.last_checked_at = now()
    s.add(SourceRun(
        source=job.source,
        result="ok" if job.status in ("Open", "Closed") else "error",
        details=f"Manual verification for job {job.id} ({job.company} — {job.title}): {job.status}"
    ))
    s.commit()
    return {
        "job_id": job.id,
        "company": job.company,
        "title": job.title,
        "status": job.status,
        "last_checked_at": job.last_checked_at,
        "official_url": job.official_url,
    }

app.mount("/",StaticFiles(directory="static",html=True),name="static")
