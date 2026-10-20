"""
daily_email.py - email the "Appointments scheduled by day" table every day.

It reads the "daily performance" tab of the Google Sheet (same data as the dashboard),
builds the table (Day | Regional office | Rep | Appts scheduled | Links | Scheduled by | Total)
and emails it as a normal HTML table, plus a CSV attachment.

Runs on GitHub Actions every morning (see .github/workflows/daily_email.yml), or by hand:
    python daily_email.py              # yesterday (Los Angeles time)
    python daily_email.py 2026-10-13   # a specific day

Settings come from environment variables (GitHub: Settings > Secrets and variables > Actions):
    GOOGLE_KEY_JSON   the whole service account JSON key (same one the dashboard uses)
    SHEET_NAME        e.g. Appointment Setter
    SMTP_HOST         e.g. smtp.office365.com  (Outlook / Microsoft 365)  or  smtp.gmail.com
    SMTP_PORT         587
    SMTP_USER         the email account that sends the report
    SMTP_PASSWORD     its password (Gmail: an "app password")
    EMAIL_TO          who gets it, comma separated, e.g. sales@company.com,manager@company.com
"""
import io
import json
import os
import smtplib
import sys
from datetime import datetime, timedelta
from email.message import EmailMessage
from zoneinfo import ZoneInfo

import pandas as pd

TAB_NAMES = ["daily performance", "daily_performance", "daily"]
COLS = {"lead": "leads_id", "date": "date_created", "setter": "apt_set_names",
        "branch": "branch_name", "owner": "leads_owner", "office": "Regional Office"}
SETTER_BRANCH = "Appointment Setters"
CRM_LEAD_URL = "https://www.mylifesourcewater.com/webcrm/expandedleads.php?leads_id={lead}"
TZ = ZoneInfo("America/Los_Angeles")


def text(col):
    s = col.astype(str).str.strip()
    return s.mask(s.str.lower().isin(["", "nan", "none", "null", "<na>"]), "")


def clean_name(col):
    return (text(col).str.replace(r"\s*(?:\s-|-\s|-(?=[A-Z]{2,}\b)).*$", "", regex=True)
            .str.replace(r"^\*\s*", "", regex=True).str.strip())


def clean_office(col):
    return text(col).str.rsplit("-", n=1).str[-1].str.strip()


def read_daily_tab():
    import gspread
    from google.oauth2.service_account import Credentials
    creds = Credentials.from_service_account_info(
        json.loads(os.environ["GOOGLE_KEY_JSON"]),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly",
                "https://www.googleapis.com/auth/drive.readonly"])
    book = gspread.authorize(creds).open(os.environ.get("SHEET_NAME", "Appointment Setter"))
    ws = next((w for w in book.worksheets() if w.title.strip().lower() in TAB_NAMES), None)
    if ws is None:
        raise SystemExit('No worksheet named "daily performance" in the Google Sheet.')
    rows = ws.get_all_values()
    return pd.DataFrame(rows[1:], columns=[h.strip() for h in rows[0]])


def build_report(raw, day):
    """The same table as the dashboard, for one day."""
    d = pd.DataFrame({
        "lead": text(raw[COLS["lead"]]),
        "when": pd.to_datetime(text(raw[COLS["date"]]).replace("", None), errors="coerce", format="mixed"),
        "setter": clean_name(raw[COLS["setter"]]),
        "branch": text(raw[COLS["branch"]]) if COLS["branch"] in raw.columns else SETTER_BRANCH,
        "owner": clean_name(raw[COLS["owner"]]),
        "office": clean_office(raw[COLS["office"]]),
    })
    d = d[(d.lead != "") & d.when.notna() & (d.branch.str.lower() == SETTER_BRANCH.lower())]
    d = d[d.when.dt.date == day].sort_values("when").drop_duplicates("lead")     # count by leads_id
    d = d.assign(_off=d.office.replace("", "~")).sort_values(["_off", "owner", "when"])
    rows, last_office = [], None
    for i, (_, r) in enumerate(d.iterrows()):
        rows.append({"Day": f"{day:%m/%d/%Y}" if i == 0 else "",
                     "Regional office": r.office if r.office != last_office else "",
                     "Rep": r.owner, "Appts scheduled": 1,
                     "Links": CRM_LEAD_URL.format(lead=r.lead),
                     "Scheduled by": r.setter.split()[0] if r.setter else ""})
        last_office = r.office
    rows.append({"Day": "", "Regional office": "", "Rep": "Total", "Appts scheduled": len(d),
                 "Links": "", "Scheduled by": ""})
    return pd.DataFrame(rows)


def to_html(report, day):
    head = "".join(f'<th style="background:#0E7A3C;color:#fff;padding:6px 10px;text-align:left">{c}</th>'
                   for c in report.columns)
    body = ""
    for _, r in report.iterrows():
        total = r["Rep"] == "Total"
        style = "font-weight:bold;background:#E2F2D6;" if total else ""
        cells = ""
        for c in report.columns:
            v = r[c]
            if c == "Links" and v:
                v = f'<a href="{v}">{v}</a>'
            align = "right" if c == "Appts scheduled" else "left"
            cells += f'<td style="padding:5px 10px;border-bottom:1px solid #ddd;text-align:{align};{style}">{v}</td>'
        body += f"<tr>{cells}</tr>"
    n = int(report.iloc[-1]["Appts scheduled"])
    return f"""<div style="font-family:Arial,sans-serif;font-size:14px;color:#1B2230">
<p>Hi team,</p>
<p>The appointment setters scheduled <b>{n}</b> appointment{'s' if n != 1 else ''} on <b>{day:%A, %B %d, %Y}</b>.</p>
<table style="border-collapse:collapse;font-size:13px">{f'<tr>{head}</tr>'}{body}</table>
<p style="color:#5A6474;font-size:12px">Sent automatically from the Appointment setting dashboard.</p></div>"""


def send(report, day):
    msg = EmailMessage()
    msg["Subject"] = f"Appointments scheduled – {day:%m/%d/%Y} ({int(report.iloc[-1]['Appts scheduled'])})"
    msg["From"] = os.environ["SMTP_USER"]
    msg["To"] = os.environ["EMAIL_TO"]
    msg.set_content(report.to_string(index=False))                 # plain-text fallback
    msg.add_alternative(to_html(report, day), subtype="html")
    buf = io.StringIO(); report.to_csv(buf, index=False)
    msg.add_attachment(buf.getvalue().encode("utf-8-sig"), maintype="text", subtype="csv",
                       filename=f"appointments_scheduled_{day:%Y%m%d}.csv")
    with smtplib.SMTP(os.environ.get("SMTP_HOST", "smtp.office365.com"), int(os.environ.get("SMTP_PORT", "587"))) as s:
        s.starttls()
        s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        s.send_message(msg)


if __name__ == "__main__":
    day = (datetime.fromisoformat(sys.argv[1]).date() if len(sys.argv) > 1
           else (datetime.now(TZ) - timedelta(days=1)).date())       # yesterday, Los Angeles time
    report = build_report(read_daily_tab(), day)
    send(report, day)
    print(f"Sent {len(report) - 1} appointments for {day} to {os.environ['EMAIL_TO']}")
