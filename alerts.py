"""Email alerts are disabled until SMTP credentials are configured."""
import os, smtplib, logging
from email.message import EmailMessage
log=logging.getLogger("gamequest.alerts")
def send_new_job_alert(job):
    host=os.getenv("SMTP_HOST"); user=os.getenv("SMTP_USER"); password=os.getenv("SMTP_PASSWORD")
    recipient=os.getenv("ALERT_TO")
    if not all((host,user,password,recipient)):
        log.info("Email not configured; skipping alert for %s",job.title); return
    msg=EmailMessage()
    msg["Subject"]=f"New GameQuest job: {job.title}"
    msg["From"]=user; msg["To"]=recipient
    msg.set_content(f"New matching listing found (status unverified until checked):\n{job.title}\n{job.company}\n{job.location}\n{job.official_url}\nFirst seen: {job.first_seen_at}")
    try:
        with smtplib.SMTP(host,int(os.getenv("SMTP_PORT","587")),timeout=15) as server:
            server.starttls(); server.login(user,password); server.send_message(msg)
    except Exception: log.exception("Failed to send email alert")
