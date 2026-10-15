"""
Appointment Setter Dashboard (data from Google Sheets)
Local:   streamlit run app.py
Deploy:  see README.md
"""
import datetime as dt
import hmac

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

# =====================================================================
# CONFIG - edit this section
# =====================================================================
REFRESH_MINUTES = 10  # how often the dashboard re-reads the sheet

# Your Google Sheet and key file (the same ones your Jupyter notebook uses).
# Put the key file in the same folder as app.py.
SHEET_NAME = "Appointment Setter"
KEY_FILE = "lsw-marketing-b9a13bd21034.json"
MIN_DATE = dt.date(2025, 1, 1)
MAX_DATE = dt.date(2026, 9, 30)

# ---- Setter performance tab ------------------------------------------
# Worksheet names and the column headers to use from each.
LEADS_TAB = "leads_create"
LEADS_COLS = {
    "lead":   "leads_id",
    "date":   "marketing date",     # when the lead was created
    "setter": "mark_salesname",     # setter who created it
    "branch": "mbranch",            # department of the person who created it
}
APT_TAB = "apt_created"
APT_COLS = {
    "lead":   "leads_id",
    "date":   "first_created",       # when the appointment was first set up
    "setter": "apt salesname",       # setter who set it up
    "branch": "apt branch",          # department of the person who set it up
    "status": "final_status",        # "Set up" or "Cancelled"
    "order":  ["orders salesrepsname", "salesreps_name", "sales amount"],  # first one found; any value = order
}
CANCELLED_VALUES = ["cancelled", "canceled"]   # status values that count as cancelled (any case)
# Only leads and appointments made by this department count on the Setter performance tab.
SETTER_BRANCH = "Appointment Setters"

# ---- Phone calls tab --------------------------------------------------
CALLS_TAB = "calls"   # the appointment setters' GoTo calls (apt_call_res from the notebook)
CALL_COLS = {
    "date":      "Call Date",
    "time":      "Call Time",
    "hour":      "Hour",
    "weekday":   "Weekday",                 # Monday ... Sunday
    "duration":  "Duration [Milliseconds]",
    "direction": "Direction",               # Inbound / Outbound / Internal
    "result":    "Call Result",
    "person":    "participant_name",
}
# Call results that count as missed (customer not reached / caller not answered)
MISSED_RESULTS = ["Missed Call", "Sent to voicemail", "Hung up (in queue)",
                  "Hung up (on hold)", "Hung up (parked)"]

# ---- Sales vs setters tab ---------------------------------------------
ALL_TAB = "all company"
ALL_COLS = {
    "lead":        "leads_id",
    "lead_date":   "marketing date",       # when the lead was created
    "lead_by":     "mark_salesname",       # who created the lead
    "owner":       "leads_owner",          # the sales rep who owns the lead (Sales vs setters table)
    "lead_branch": "mbranch",              # their department
    "apt_by":      "apt salesname",        # who set up the appointment
    "apt_branch":  "apt branch",           # their department
    "apt_date":    "first_created",        # when the appointment was set up
    "status":      "final_status",         # "Set up" or "Cancelled"
    "order":       ["orders salesrepsname", "salesreps_name", "sales amount"],  # first one found; any value = order
}
# Each rep's branch in the By sales rep table comes from this column (optional).
# Values like "Andrew Higgins - Pasadena Team - Pasadena" are cut to the part after the last "-" ("Pasadena").
OFFICE_COL = "Regional Office"

# Region shown in the clicked lists on the Setter performance tab: Regional Office -> region.
# Offices not listed show no region. Edit freely.
REGION_OF_OFFICE = {
    "Arizona": "Desert", "Las Vegas": "Desert",
    "Orange County": "SoCal", "Pasadena": "SoCal", "Inland Empire": "SoCal", "San Diego": "SoCal",
    "Ventura/SB County": "SoCal", "Central Coast": "SoCal",
    "Bay Area": "NorCal", "Sacramento": "NorCal", "Fresno": "NorCal",
    "Austin": "Texas", "San Antonio": "Texas",
}
# Order amount shown in those lists: the first of these columns found in the sheet
ORDER_AMOUNT_COLS = ["sales amount", "IS amount"]

# Installs (optional columns in the all company tab)
INSTALL_COLS = {"amount": "IS amount", "rep": "IS reps"}   # installed system: sales amount + who sold it
CHART_MIN_LEADS = 5   # charts only show sales reps with at least this many leads
# Branches left out of the Sales vs setters tab completely (not in the list, not in any number).
# Leads with no creator (e.g. Web) and the appointment setters team are always left out too.
EXCLUDED_BRANCHES = ["CSR Staff", "National Sales Team", "Service Staff", "Commercial"]
# Link to a lead in the CRM. {lead} is replaced with the leads_id. Leave "" to hide the link column.
CRM_LEAD_URL = "https://www.mylifesourcewater.com/webcrm/expandedleads.php?leads_id={lead}"

# Used only to build demo data
SETTER_DEPT = "Appointment Setter"
EXCLUDE_REP_IDS = ["1261"]

# =====================================================================
# LOOK
# =====================================================================
INK, MUTED, BLUE, ORANGE, RULE = "#1B2230", "#5A6474", "#0E7A3C", "#8DC63F", "#D5DBE3"
# LifeSource CRM colors for the header, tabs and buttons
CRM_GREEN, CRM_GREEN_DARK, CRM_TAB, CRM_TAB_BORDER, CRM_RED = "#0E7A3C", "#0A5E2E", "#E2F2D6", "#A9CF95", "#C8102E"
KINDS, KIND_COLORS = ["Inbound", "Outbound", "Missed"], ["#0E7A3C", "#8DC63F", "#AEB8C6"]

st.set_page_config(page_title="Appointment Setter Dashboard", layout="wide")
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,400..800&display=swap');
.block-container {{ padding-top: 3.8rem; max-width: 1440px; }}
.dash, .dash * {{ font-family: 'Archivo', 'Helvetica Neue', Helvetica, sans-serif; font-variant-numeric: tabular-nums; }}
.topbar {{ background: {CRM_GREEN}; color: #FFFFFF; border-radius: 6px; padding: 22px 28px; margin-bottom: .6rem;
          border-bottom: 4px solid {CRM_RED};
          display: flex; align-items: baseline; gap: 14px; }}
.topbar h1 {{ margin: 0 !important; padding: 2px 0 !important; line-height: 1.2 !important; font-size: 30px;
             font-weight: 760; font-stretch: 115%; color: #FFFFFF; }}
.topbar > span {{ font-size: 13px; color: #D7EBCB; }}
.topbar h1 span {{ font-size: inherit; color: inherit; }}
.kpis {{ display: grid; background: #fff; border: 1px solid {RULE}; border-radius: 6px; margin: .4rem 0 1rem; }}
.kpi {{ padding: 18px 24px; border-left: 1px solid #E3E8EE; display: flex; flex-direction: column; gap: 6px; }}
.kpi:first-child {{ border-left: 0; }}
.kpi .l {{ font-size: 14px; color: {MUTED}; display: flex; align-items: center; gap: 8px; }}
.kpi .v {{ font-size: clamp(24px, 2.5vw, 36px); font-weight: 700; line-height: 1.05; color: {INK}; white-space: nowrap; }}
.kpi .sub {{ font-size: 14px; color: {MUTED}; }}
.kpi .sub b {{ color: {INK}; font-weight: 650; }}
.brk {{ display: grid; grid-template-columns: repeat(4, auto); justify-content: start; column-gap: 26px;
        row-gap: 2px; margin: 6px 0 4px; }}
.brk span {{ font-size: 13px; color: {MUTED}; }}
.brk b {{ font-size: 20px; font-weight: 700; color: {INK}; }}
.sw {{ width: 10px; height: 10px; border-radius: 2px; display: inline-block; }}
.hero {{ background: {CRM_GREEN_DARK}; color: #F3F5F8; border-radius: 6px; padding: 26px 30px; display: flex;
        flex-direction: column; gap: 6px; margin-bottom: 12px; }}
.hero .l {{ color: #AEB8C6; font-size: 15px; }}
.hero .v {{ font-size: 64px; font-weight: 760; font-stretch: 110%; line-height: 1; }}
.hero .s {{ color: #AEB8C6; font-size: 14px; }}
.cmp {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); background: #fff; border: 1px solid {RULE};
       border-radius: 6px; margin: .4rem 0 1rem; }}
.cmp > div {{ padding: 22px 30px; }}
.cmp > div + div {{ border-left: 1px solid #E3E8EE; }}
.cmp h3 {{ margin: 0 0 10px; padding: 0; font-size: 16px; font-weight: 700; color: {INK}; }}
.cmp .row {{ display: flex; gap: 48px; }}
.cmp .v {{ font-size: 48px; font-weight: 760; font-stretch: 110%; line-height: 1; color: {INK}; }}
.cmp .v.blue {{ color: {BLUE}; }}
.cmp .l {{ font-size: 14px; color: {MUTED}; margin-top: 4px; }}
/* Tabs styled like the CRM: light green tabs, dark green for the open one (works on old and new Streamlit) */
div[data-testid="stTabs"] [role="tablist"] {{ gap: 6px; border-bottom: 3px solid {CRM_GREEN}; }}
div[data-testid="stTabs"] [data-baseweb="tab-highlight"],
div[data-testid="stTabs"] [data-baseweb="tab-border"],
div[data-testid="stTabs"] .react-aria-SelectionIndicator {{ display: none; }}
div[data-testid="stTabs"] [role="tab"] {{ background: {CRM_TAB}; border: 1px solid {CRM_TAB_BORDER};
    border-bottom: none; border-radius: 8px 8px 0 0; padding: 10px 26px; margin: 0; }}
div[data-testid="stTabs"] [role="tab"] p {{ font-size: 16px; color: {INK}; }}
div[data-testid="stTabs"] [role="tab"]:hover {{ background: #D2EAC1; }}
div[data-testid="stTabs"] [role="tab"][aria-selected="true"] {{ background: {CRM_GREEN}; border-color: {CRM_GREEN}; }}
div[data-testid="stTabs"] [role="tab"][aria-selected="true"] p {{ color: #FFFFFF; font-weight: 600; }}
</style>
""", unsafe_allow_html=True)


def secret(key, default=None):
    try:
        return st.secrets[key]
    except Exception:
        return default


# =====================================================================
# PASSWORD (set APP_PASSWORD in secrets to turn it on)
# =====================================================================
def require_password():
    pw = secret("APP_PASSWORD")
    if not pw or st.session_state.get("authed"):
        return
    st.markdown('<div class="dash topbar"><h1>Appointment setting</h1></div>', unsafe_allow_html=True)
    entered = st.text_input("Password", type="password")
    if entered:
        if hmac.compare_digest(entered, str(pw)):
            st.session_state["authed"] = True
            st.rerun()
        st.error("That password isn't right. Try again.")
    st.stop()


require_password()
import json
from pathlib import Path

_key_path = Path(__file__).resolve().parent / KEY_FILE
SHEET_CFG = secret("gsheet") or {"name": SHEET_NAME}
KEY_INFO = secret("gcp_service_account")
if KEY_INFO is None and _key_path.exists():
    KEY_INFO = json.loads(_key_path.read_text(encoding="utf-8"))
DEMO_MODE = KEY_INFO is None


# =====================================================================
# DATA LOADING
# =====================================================================
@st.cache_data(ttl=REFRESH_MINUTES * 60, show_spinner="Reading the Google Sheet...")
def read_tabs():
    """Every worksheet in the sheet as {title: DataFrame of text}."""
    if DEMO_MODE:
        return demo_tabs(), dt.datetime.now()
    import gspread
    from google.oauth2.service_account import Credentials

    creds = Credentials.from_service_account_info(
        dict(KEY_INFO),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly",
                "https://www.googleapis.com/auth/drive.readonly"])
    client = gspread.authorize(creds)
    book = client.open_by_url(SHEET_CFG["url"]) if SHEET_CFG.get("url") else client.open(SHEET_CFG["name"])
    tabs = {}
    for ws in book.worksheets():
        rows = ws.get_all_values()
        if not rows:
            tabs[ws.title] = pd.DataFrame()
            continue
        header = [h.strip() for h in rows[0]]
        df = pd.DataFrame(rows[1:], columns=header)
        df = df.loc[:, [h != "" for h in header]]
        tabs[ws.title] = df[(df != "").any(axis=1)].reset_index(drop=True)
    return tabs, dt.datetime.now()


def missing_cols(df, needed):
    return [c for c in needed if c not in df.columns]


def text(s):
    s = s.astype(str).str.strip()
    return s.mask(s.str.lower().isin(["", "nan", "none", "null", "<na>"]), "")


def resolve_cols(df, cols):
    """Column names to use: a list means 'the first of these that exists in the sheet'."""
    out = {}
    for k, v in cols.items():
        if isinstance(v, list):
            out[k] = next((x for x in v if x in df.columns), v[0])
        else:
            out[k] = v
    return out


def to_dt(s):
    return pd.to_datetime(text(s).replace("", None), errors="coerce", format="mixed")


def setter_data(tabs):
    """Returns (leads, apts) for the Setter performance tab, or raises ValueError."""
    for tab, cols in ((LEADS_TAB, LEADS_COLS), (APT_TAB, APT_COLS)):
        if tab not in tabs:
            raise ValueError(f'There is no worksheet named "{tab}". Worksheets found: {list(tabs)}')
        if len(tabs[tab].columns) == 0:
            raise ValueError(f'The "{tab}" worksheet is empty. Re-run the notebook cell that writes it, '
                             f'then click Refresh now.')
        miss = missing_cols(tabs[tab], resolve_cols(tabs[tab], cols).values())
        if miss:
            raise ValueError(f'The "{tab}" worksheet is missing {miss}. Headers found: {list(tabs[tab].columns)}. '
                             f"Fix the headers in the sheet or the names in app.py.")
    l, a = tabs[LEADS_TAB], tabs[APT_TAB]
    A_COLS = resolve_cols(a, APT_COLS)
    # Keep only rows made by the appointment setters department
    l = l[text(l[LEADS_COLS["branch"]]).str.lower() == SETTER_BRANCH.lower()]
    a = a[text(a[A_COLS["branch"]]).str.lower() == SETTER_BRANCH.lower()]
    leads = pd.DataFrame({"lead": text(l[LEADS_COLS["lead"]]), "date": to_dt(l[LEADS_COLS["date"]]),
                          "setter": text(l[LEADS_COLS["setter"]])})
    status = text(a[A_COLS["status"]])
    apts = pd.DataFrame({
        "lead": text(a[A_COLS["lead"]]),
        "date": to_dt(a[A_COLS["date"]]),
        "setter": text(a[A_COLS["setter"]]),
        "status": np.where(status.str.lower().isin(CANCELLED_VALUES), "Cancelled", "Active"),
        "ordered": text(a[A_COLS["order"]]) != "",
    })
    extra = [c for c in ("path", "path_detail") if c in a.columns]
    for c in extra:
        apts[c] = text(a[c])
    for df, src in ((apts, a), (leads, l)):
        df["owner"] = clean_name(src[ALL_COLS["owner"]]) if ALL_COLS["owner"] in src.columns else ""
        df["office"] = clean_office(src[OFFICE_COL]) if OFFICE_COL in src.columns else ""
        amt_col = next((c_ for c_ in ORDER_AMOUNT_COLS if c_ in src.columns), None)
        df["amount"] = (pd.to_numeric(text(src[amt_col]).str.replace(r"[$,]", "", regex=True), errors="coerce")
                        if amt_col else np.nan)
    leads = leads[(leads.setter != "") & leads.date.notna()]
    apts = apts[(apts.setter != "") & apts.date.notna()]
    return leads, apts


def clean_name(col):
    """'Dori Priego - CDR' / 'Nathan Anderson-CDR' / '* House' -> 'Dori Priego' / 'Nathan Anderson' / 'House'.
    Hyphenated last names like 'Garcia-Cano' are kept."""
    return (text(col).str.replace(r"\s*(?:\s-|-\s|-(?=[A-Z]{2,}\b)).*$", "", regex=True)
            .str.replace(r"^\*\s*", "", regex=True).str.strip())


def clean_office(col):
    """'Nathalie Garcia- Sales Director Team - Customer Development' -> 'Customer Development'."""
    return text(col).str.rsplit("-", n=1).str[-1].str.strip()


def company_data(tabs):
    """One row per lead from the all company tab. Each lead belongs to the person who created it
    (mark_salesname / mbranch); its appointment, cancellation and order are counted for that person."""
    if ALL_TAB not in tabs:
        raise ValueError(f'There is no worksheet named "{ALL_TAB}". Worksheets found: {list(tabs)}')
    d = tabs[ALL_TAB]
    if d.empty and len(d.columns) == 0:
        raise ValueError(f'The "{ALL_TAB}" worksheet is empty. Re-run the notebook cell that writes it, '
                         f'then click Refresh now.')
    c = resolve_cols(d, ALL_COLS)
    miss = missing_cols(d, c.values())
    if miss:
        raise ValueError(f'The "{ALL_TAB}" worksheet is missing {miss}. Headers found: {list(d.columns)}. '
                         f"Fix the headers in the sheet or the names in app.py.")
    status = text(d[c["status"]])
    has_apt = (text(d[c["apt_by"]]) != "") | (status != "")
    cancelled = status.str.lower().isin(CANCELLED_VALUES)
    rows = pd.DataFrame({
        "lead": text(d[c["lead"]]),
        "date": to_dt(d[c["lead_date"]]),          # lead date (marketing date)
        # appointment date: first_created, or last_date when first_created is empty (e.g. cancelled only)
        "apt_date": to_dt(d[c["apt_date"]]).fillna(to_dt(d["last_date"]) if "last_date" in d.columns
                                                   else pd.Series(pd.NaT, index=d.index)),
        "person": clean_name(d[c["lead_by"]]),        # who created the lead
        "branch": text(d[c["lead_branch"]]),
        "owner": clean_name(d[c["owner"]]),           # who owns the lead
        "apt_by": clean_name(d[c["apt_by"]]),         # who set the appointment
        "apt_branch": text(d[c["apt_branch"]]),
        "owner_office": clean_office(d[OFFICE_COL]) if OFFICE_COL in d.columns else "",   # the owner's branch
        "active": has_apt & ~cancelled,
        "cancelled": has_apt & cancelled,
        "ordered": text(d[c["order"]]) != "",
        "status_text": status,
        # installs: IS amount has a value; IS reps = who sold the install
        "is_amount": (pd.to_numeric(text(d[INSTALL_COLS["amount"]]).str.replace(r"[$,]", "", regex=True), errors="coerce")
                      if INSTALL_COLS["amount"] in d.columns else pd.Series(np.nan, index=d.index)),
        "is_rep": clean_name(d[INSTALL_COLS["rep"]]) if INSTALL_COLS["rep"] in d.columns else "",
    })
    rows["installed"] = rows.is_amount.notna()
    no_owner = int((rows.person == "").sum())
    # Orders have no date of their own: use the appointment date, or the lead date if no appointment
    rows["order_date"] = rows.apt_date.fillna(rows.date)
    rows = rows[rows.date.notna() | rows.apt_date.notna()]
    return rows, no_owner



def clean(d):
    for k in ("leads", "appointments", "quotes", "orders"):
        d[k]["created_date"] = pd.to_datetime(d[k]["created_date"], errors="coerce", format="mixed")
        d[k] = d[k].dropna(subset=["created_date"])
        d[k]["leads_id"] = d[k]["leads_id"].astype(str).str.strip()
    d["reps"]["rep_id"] = d["reps"]["rep_id"].astype(str).str.strip()
    d["reps"]["rep_name"] = d["reps"]["rep_name"].astype(str).str.strip()
    d["reps"]["department"] = d["reps"]["department"].astype(str).str.strip()
    for k in ("leads", "appointments"):
        d[k]["created_by"] = d[k]["created_by"].astype(str).str.strip()
        d[k]["salesreps_id"] = d[k]["salesreps_id"].astype(str).str.strip()
    d["reps"] = d["reps"][~d["reps"]["rep_id"].isin(EXCLUDE_REP_IDS)]
    d["leads"] = d["leads"][~d["leads"]["salesreps_id"].isin(EXCLUDE_REP_IDS)]
    return d


def demo_crm():
    rng = np.random.default_rng(7)
    setters = ["Lisa Porras", "Fabio Davila", "Maya Chen", "Omar Reyes", "Jess Tran"]
    sales = ["Tom Brooks", "Ana Silva", "Raj Patel", "Kim Lee", "Dan Ortiz", "Sara Kim"]
    reps = pd.DataFrame({
        "rep_id": [str(100 + i) for i in range(11)],
        "rep_name": setters + sales,
        "department": [SETTER_DEPT] * 5 + ["Sales"] * 6,
    })
    setter_ids, sales_ids = reps.rep_id[:5].tolist(), reps.rep_id[5:].tolist()
    days = pd.date_range(MIN_DATE, MAX_DATE, freq="D")
    n = 7000
    is_setter = rng.random(n) < 0.7
    created_by = np.where(is_setter, rng.choice(setter_ids, n), rng.choice(sales_ids, n))
    assigned = np.where(is_setter, rng.choice(sales_ids, n), created_by)
    leads = pd.DataFrame({"leads_id": np.arange(n).astype(str), "created_date": rng.choice(days, n),
                          "created_by": created_by, "salesreps_id": assigned})
    apts = leads[rng.random(n) < np.where(is_setter, 0.45, 0.35)].copy()
    apts["apt_id"] = range(len(apts))
    apts["created_date"] += pd.to_timedelta(rng.integers(0, 5, len(apts)), unit="D")
    quotes = apts[rng.random(len(apts)) < 0.6][["leads_id", "created_date"]].copy()
    quotes["quote_id"] = range(len(quotes))
    quotes["created_date"] += pd.to_timedelta(rng.integers(1, 10, len(quotes)), unit="D")
    rate = np.where(quotes.leads_id.astype(int).map(lambda i: is_setter[i]), 0.38, 0.45)
    orders = quotes[rng.random(len(quotes)) < rate][["leads_id", "created_date"]].copy()
    orders["order_id"] = range(len(orders))
    orders["created_date"] += pd.to_timedelta(rng.integers(3, 20, len(orders)), unit="D")
    return clean({"reps": reps, "leads": leads, "appointments": apts, "quotes": quotes, "orders": orders})


def demo_calls(names):
    """Fake call log shaped like the calls worksheet."""
    rng = np.random.default_rng(3)
    n = 6000
    day = pd.Timestamp("2026-08-01") + pd.to_timedelta(rng.integers(0, 66, n), unit="D")
    hour = rng.choice(range(7, 18), n)
    direction = rng.choice(["Outbound", "Inbound", "Internal"], n, p=[0.63, 0.36, 0.01])
    result = np.where(direction == "Outbound",
                      rng.choice(["Ended successfully", "Missed Call"], n, p=[0.87, 0.13]),
                      rng.choice(["Dial plan call ended", "Ended successfully", "Sent to voicemail",
                                  "Hung up (on hold)"], n, p=[0.9, 0.04, 0.04, 0.02]))
    secs = np.where(result == "Missed Call", rng.integers(1, 20, n), rng.gamma(2, 90, n).astype(int) + 5)
    return pd.DataFrame({
        "Call Date": day.strftime("%Y-%m-%d"),
        "Call Time": [f"{h:02d}:{m:02d}:{x:02d}" for h, m, x in zip(hour, rng.integers(0, 60, n), rng.integers(0, 60, n))],
        "Hour": hour, "Weekday": day.day_name(), "Duration [Milliseconds]": secs * 1000, "Direction": direction,
        "Call Result": result, "participant_name": rng.choice(names, n),
    })


def to_seconds(x):
    if pd.isna(x):
        return 0.0
    if isinstance(x, dt.timedelta):
        return x.total_seconds()
    if isinstance(x, dt.time):
        return x.hour * 3600 + x.minute * 60 + x.second
    if isinstance(x, (int, float, np.number)):
        return float(x)
    s = str(x).strip()
    if ":" in s:
        try:
            parts = [float(p) for p in s.split(":")]
        except ValueError:
            return 0.0
        while len(parts) < 3:
            parts.insert(0, 0)
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    try:
        return float(s)
    except ValueError:
        return 0.0


def normalize_calls(raw):
    """Clean call log, or raises ValueError if columns are missing."""
    missing = [v for v in CALL_COLS.values() if v not in raw.columns]
    if missing:
        raise ValueError(f'The "{CALLS_TAB}" worksheet is missing {missing}. '
                         f"Headers found: {list(raw.columns)}. Fix the headers or CALL_COLS in app.py.")
    c = CALL_COLS
    result = text(raw[c["result"]])
    calls = pd.DataFrame({
        "datetime": to_dt(text(raw[c["date"]]) + " " + text(raw[c["time"]])),
        "person": text(raw[c["person"]]),
        "direction": text(raw[c["direction"]]).str.title(),
        "result": result,
        "missed": result.isin(MISSED_RESULTS),
        "duration_sec": pd.to_numeric(raw[c["duration"]], errors="coerce").fillna(0) / 1000,
        "hour": pd.to_numeric(raw[c["hour"]], errors="coerce"),
        "weekday": text(raw[c["weekday"]]).str.title() if c.get("weekday") in raw.columns else "",
    })
    calls["date"] = calls.datetime.dt.normalize()
    calls["weekday"] = calls.weekday.where(calls.weekday != "", calls.datetime.dt.day_name())
    return calls[calls.datetime.notna() & (calls.person != "")], raw


# =====================================================================
# HELPERS
# =====================================================================
def hms(sec):
    sec = int(sec or 0)
    return f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def mmss(sec):
    sec = int(sec or 0)
    return f"{sec // 60}:{sec % 60:02d}"


def in_range(df, start, end, col="created_date"):
    return df[(df[col] >= pd.Timestamp(start)) & (df[col] < pd.Timestamp(end) + pd.Timedelta(days=1))]


def pct(a, b):
    b = pd.Series(b, dtype=float).replace(0, np.nan)
    return (pd.Series(a, dtype=float) / b * 100).values


def fmt_pct(v):
    return "–" if pd.isna(v) else f"{v:.1f}%"


def period_picker(key, lo, hi):
    """Pick one or more months, or one or more Monday–Sunday weeks. Returns a list of (start, end)."""
    c1, c2 = st.columns([1, 2])
    view = c1.radio("Show by", ["Month", "Week", "All dates"], horizontal=True, key=f"{key}_view")
    if view == "All dates":
        c2.markdown(f'<div style="padding-top:30px;color:{MUTED}">{lo:%b %d, %Y} – {hi:%b %d, %Y}</div>',
                    unsafe_allow_html=True)
        return [(lo, hi)]
    if view == "Month":
        months = pd.period_range(lo, hi, freq="M")[::-1]                      # newest first
        options = {m.strftime("%B %Y"): (m.start_time.date(), m.end_time.date()) for m in months}
        label = "Months (pick one or more)"
    else:
        options = {}
        monday = hi - dt.timedelta(days=hi.weekday())                         # newest week first
        while monday + dt.timedelta(days=6) >= lo:
            sunday = monday + dt.timedelta(days=6)
            options[f"{monday:%b} {monday.day} – {sunday:%b} {sunday.day}, {sunday.year}"] = (monday, sunday)
            monday -= dt.timedelta(days=7)
        label = "Weeks, Monday – Sunday (pick one or more)"
    names = list(options)
    chosen = c2.multiselect(label, names, default=names[:1], key=f"{key}_{view}_multi",
                            placeholder="Pick one or more")
    if not chosen:
        c2.caption(f"Nothing picked, showing {names[0]}.")
        chosen = names[:1]
    return [(max(options[n][0], lo), min(options[n][1], hi)) for n in chosen]


QUICK_RANGES = ["All dates", "This month", "Last month", "Last 7 days", "Last 30 days"]


def date_picker(key, default_start, default_end, lo, hi):
    """Quick pick + separate From / To boxes (each opens a calendar and closes after one click)."""
    k_from, k_to, k_quick = f"{key}_from", f"{key}_to", f"{key}_quick"
    st.session_state.setdefault(k_from, default_start)
    st.session_state.setdefault(k_to, default_end)

    def apply_quick():
        q = st.session_state[k_quick]
        first = hi.replace(day=1)
        a, b = {
            "All dates": (lo, hi),
            "This month": (first, hi),
            "Last month": ((first - dt.timedelta(days=1)).replace(day=1), first - dt.timedelta(days=1)),
            "Last 7 days": (hi - dt.timedelta(days=6), hi),
            "Last 30 days": (hi - dt.timedelta(days=29), hi),
        }[q]
        st.session_state[k_from] = min(max(a, lo), hi)
        st.session_state[k_to] = max(min(b, hi), lo)

    c1, c2, c3 = st.columns([1.15, 1, 1])
    c1.selectbox("Quick pick", QUICK_RANGES, key=k_quick, on_change=apply_quick,
                 help=f"Based on the latest date in the sheet ({hi:%m/%d/%Y}).")
    s = c2.date_input("From", min_value=lo, max_value=hi, key=k_from, format="MM/DD/YYYY")
    e = c3.date_input("To", min_value=lo, max_value=hi, key=k_to, format="MM/DD/YYYY")
    if s > e:
        s, e = e, s
    return s, e


def checklist_filter(label, options, key, cols=3, default_off=()):
    """A compact button ("People: all 7") that opens a checklist with Select all / Clear all.
    Returns the checked options."""
    keys = {opt: f"{key}_{i}_{opt}" for i, opt in enumerate(options)}
    for opt, k in keys.items():
        st.session_state.setdefault(k, opt not in default_off)

    def set_all(value):
        for k in keys.values():
            st.session_state[k] = value

    on = [o for o, k in keys.items() if st.session_state[k]]
    off = [o for o in options if o not in on]
    if not off:
        summary = f"{label}: all {len(options)}"
    elif not on:
        summary = f"{label}: none selected"
    elif len(off) <= 2:
        summary = f"{label}: all except {', '.join(off)}"
    elif len(on) <= 2:
        summary = f"{label}: {', '.join(on)}"
    else:
        summary = f"{label}: {len(on)} of {len(options)}"

    st.markdown(f'<div style="font-size:14px;margin-bottom:6px">{label}</div>', unsafe_allow_html=True)
    with st.popover(summary, width="stretch"):
        b1, b2, _ = st.columns([1, 1, 2])
        b1.button("Select all", on_click=set_all, args=(True,), width="stretch", key=f"{key}_all")
        b2.button("Clear all", on_click=set_all, args=(False,), width="stretch", key=f"{key}_none")
        grid = st.columns(cols)
        for i, (opt, k) in enumerate(keys.items()):
            grid[i % cols].checkbox(opt, key=k)
    return [o for o, k in keys.items() if st.session_state[k]]


def kpi_strip(items, cols=None):
    """items: list of (label, value, swatch_color_or_None[, list of sub-lines])"""
    def cell(l, v, c, subs=()):
        sw = f"<span class=sw style=background:{c}></span>" if c else ""
        lines = "".join(f'<span class="sub">{x}</span>' for x in subs)
        return f'<div class="kpi"><span class="l">{sw}{l}</span><span class="v">{v}</span>{lines}</div>'
    cells = "".join(cell(*it) for it in items)
    st.markdown(f'<div class="dash kpis" style="grid-template-columns:{cols or f"repeat({len(items)},minmax(0,1fr))"}">'
                f'{cells}</div>', unsafe_allow_html=True)


def with_total(df, count_cols, ratio_specs):
    total = df[count_cols].sum().to_frame().T
    total.index = ["Total"]
    out = pd.concat([df, total])
    for name, num, den in ratio_specs:
        out[name] = pct(out[num], out[den])
    return out


COUNTS = ["Leads", "Appointments", "Quotes", "Orders"]
RATIOS = [("Apt / Leads", "Appointments", "Leads"), ("Order / Apt", "Orders", "Appointments")]


def demo_tabs():
    """Fake worksheets shaped like the real sheet."""
    crm = demo_crm()
    rng = np.random.default_rng(11)
    reps = crm["reps"]
    name_of = dict(zip(reps.rep_id, reps.rep_name))
    setters = set(reps.loc[reps.department == SETTER_DEPT, "rep_id"])
    l = crm["leads"][crm["leads"].created_by.isin(setters)]
    leads_create = pd.DataFrame({"leads_id": l.leads_id, "marketing date": l.created_date.dt.strftime("%Y-%m-%d"),
                                 "mark_salesname": l.created_by.map(name_of), "mbranch": "Appointment Setters"})
    a = crm["appointments"][crm["appointments"].created_by.isin(setters)]
    cancelled = rng.random(len(a)) < 0.18
    ordered = a.leads_id.isin(crm["orders"].leads_id) & ~cancelled
    apt_created = pd.DataFrame({
        "leads_id": a.leads_id, "apt salesname": a.created_by.map(name_of), "apt branch": "Appointment Setters",
        "first_created": a.created_date.dt.strftime("%Y-%m-%d %H:%M"),
        "final_status": np.where(cancelled, "Cancelled", "Set up"),
        "path": np.where(cancelled, "created > cancelled", "created"),
        "orders salesrepsname": np.where(ordered, a.salesreps_id.map(name_of), ""),
    })
    # all company: every lead, with who created it and who set its first appointment
    branch = lambda ids: np.where(pd.Series(ids).isin(setters), "Appointment Setters",
                                  pd.Series(ids).map(lambda i: ["Orange County", "Pasadena", "Arizona"][int(i) % 3]))
    first = crm["appointments"].sort_values("created_date").drop_duplicates("leads_id").set_index("leads_id")
    al = crm["leads"].set_index("leads_id")
    fa = first.reindex(al.index)
    has = fa.created_by.notna()
    canc = has & (rng.random(len(al)) < 0.18)
    ordd = has & ~canc & al.index.isin(crm["orders"].leads_id)
    all_company = pd.DataFrame({
        "leads_id": al.index,
        "marketing date": al.created_date.dt.strftime("%Y-%m-%d").values,
        "mark_salesname": al.created_by.map(name_of).values,
        "leads_owner": al.salesreps_id.map(name_of).fillna("").values + np.where(rng.random(len(al)) < 0.3, " - CDR", ""),
        "mbranch": branch(al.created_by.values),
        "apt salesname": np.where(has, fa.created_by.map(name_of), ""),
        "apt branch": np.where(has, branch(fa.created_by.fillna("0").values), ""),
        "first_created": np.where(has, fa.created_date.dt.strftime("%Y-%m-%d %H:%M"), ""),
        "final_status": np.where(~has, "", np.where(canc, "Cancelled", "Set up")),
        "orders salesrepsname": np.where(ordd, fa.salesreps_id.map(name_of), ""),
    })
    return {LEADS_TAB: leads_create, APT_TAB: apt_created, ALL_TAB: all_company}




# =====================================================================
# PAGE
# =====================================================================
try:
    tabs, loaded_at = read_tabs()
except Exception as err:
    st.error(f"Couldn't read the Google Sheet. {err}")
    st.caption("Check that the sheet is shared with the service account's email, and that the url in secrets is right.")
    st.stop()

st.markdown('<div class="dash topbar"><h1>Appointment setting</h1>'
            f'<span>{f"DEMO DATA: key file {KEY_FILE} not found next to app.py" if DEMO_MODE else ""}</span></div>',
            unsafe_allow_html=True)
r1, r2 = st.columns([5, 1])
r1.caption(f"Data read from the sheet at {loaded_at:%b %d, %I:%M %p}. "
           f"It refreshes every {REFRESH_MINUTES} minutes.")
if r2.button("Refresh now", width="stretch"):
    read_tabs.clear()
    st.rerun()

tab_calls, tab_setters, tab_sales = st.tabs(["Phone calls", "Setter performance", "Sales vs setters"])

# ---------------------------------------------------------------- TAB 1
with tab_calls:
    calls = raw_calls = None
    try:
        if DEMO_MODE:
            calls, raw_calls = normalize_calls(demo_calls(["Lisa Porras", "Fabio Davila", "Maya Chen", "Omar Reyes"]))
        elif CALLS_TAB not in tabs or len(tabs[CALLS_TAB].columns) == 0:
            st.info(f'Add a worksheet named "{CALLS_TAB}" with the appointment setters\' call data '
                    f"(apt_call_res from the notebook) to see call stats.")
        else:
            calls, raw_calls = normalize_calls(tabs[CALLS_TAB])
    except ValueError as err:
        st.error(str(err))

    if calls is not None and not calls.empty:
        lo, hi = calls.datetime.min().date(), calls.datetime.max().date()
        f1, f2 = st.columns([3, 2])
        with f1:
            periods = period_picker("calls_period", lo, hi)
        with f2:
            people = sorted(calls.person.unique())
            pick = checklist_filter("People", people, key="calls_people")
        in_period = pd.Series(False, index=calls.index)
        for a_, b_ in periods:
            in_period |= (calls.datetime >= pd.Timestamp(a_)) & (calls.datetime < pd.Timestamp(b_) + pd.Timedelta(days=1))
        mask = in_period & calls.person.isin(pick)
        c = calls[mask & calls.direction.isin(["Inbound", "Outbound"])]   # internal calls left out
        # Three separate groups, no overlap: answered inbound, connected outbound, missed (either way)
        c = c.assign(kind=np.where(c.missed, "Missed", c.direction))
        talked = c[c.kind != "Missed"]
        n_days = c.date.nunique()

        inb, outb = c[c.direction == "Inbound"], c[c.direction == "Outbound"]
        in_missed, out_missed = int(inb.missed.sum()), int(outb.missed.sum())
        in_ok, out_ok = inb[~inb.missed], outb[~outb.missed]          # connected calls only (for talk time)
        # Inbound and Outbound cards, each split into: answered, missed, voicemail, hung up (hold)
        hung = [r for r in MISSED_RESULTS if r.lower().startswith("hung up")]

        def breakdown(d, ok_label):
            n = lambda m: f"{int(m.sum()):,}"
            labels = [ok_label, "Missed", "Voicemail", "Hung up (hold)"]
            values = [n(~d.missed), n(d.result == "Missed Call"), n(d.result == "Sent to voicemail"), n(d.result.isin(hung))]
            return ('<div class="brk">' + "".join(f"<span>{l}</span>" for l in labels)
                    + "".join(f"<b>{v}</b>" for v in values) + "</div>")

        def talk(ok):
            return (f"talk time <b>{hms(ok.duration_sec.sum())}</b> · "
                    f"avg call <b>{mmss(ok.duration_sec.mean() if len(ok) else 0)}</b>")

        kpi_strip([
            ("Inbound calls", f"{len(inb):,}", BLUE, [breakdown(inb, "Answered"), talk(in_ok)]),
            ("Outbound calls", f"{len(outb):,}", ORANGE, [breakdown(outb, "Connected"), talk(out_ok)]),
            ("Avg calls / day", f"{len(talked) / n_days:,.0f}" if n_days else "0", None,
             [f"answered + connected ÷ {n_days} days"]),
        ], cols="minmax(0,2fr) minmax(0,2fr) minmax(0,1fr)")
        st.caption("Inbound calls and Outbound calls count every call in that direction. Each is split into: "
                   "Answered / Connected, Missed (Call Result = Missed Call), Voicemail (Sent to voicemail) and "
                   "Hung up (hold) (hung up on hold, in the queue or parked). "
                   "Talk time, avg call and Avg calls / day use only answered / connected calls.")

        g = c.groupby("person")
        by = lambda df: df.groupby("person").size()
        tbl = pd.DataFrame({
            "Inbound (all)": by(inb), "Inbound answered": by(inb[~inb.missed]), "Inbound missed": by(inb[inb.missed]),
            "Outbound (all)": by(outb), "Outbound connected": by(outb[~outb.missed]), "Outbound no answer": by(outb[outb.missed]),
        }).reindex(g.size().index).fillna(0).astype(int)
        tbl["Total calls"] = tbl["Inbound (all)"] + tbl["Outbound (all)"]      # every inbound + outbound call
        tbl["Avg calls / day"] = (len_t := talked.groupby("person").size().reindex(tbl.index).fillna(0)) / g.date.nunique()
        tbl["Talk time"] = talked.groupby("person").duration_sec.sum().reindex(tbl.index).fillna(0)
        tbl["Inbound time"] = talked[talked.kind == "Inbound"].groupby("person").duration_sec.sum().reindex(tbl.index).fillna(0)
        tbl["Outbound time"] = talked[talked.kind == "Outbound"].groupby("person").duration_sec.sum().reindex(tbl.index).fillna(0)
        tbl["Avg call"] = tbl["Talk time"] / len_t.replace(0, np.nan)
        tbl = tbl.sort_values("Avg calls / day", ascending=False)

        ROW1_H = max(420, 38 * (len(tbl) + 2) + 150)   # chart card and table card get the same height
        ROW2_H = 430
        left, right = st.columns([2, 3], gap="medium")
        with left:
            with st.container(border=True, height=ROW1_H):
                st.markdown("#### Calls by person (chart)")
                # One bar per person: Inbound + Outbound (connected calls), same numbers as the table
                pb = c.groupby(["person", "direction"]).size().rename("calls").reset_index()   # all calls, like Total calls
                pb["order"] = (pb.direction == "Outbound").astype(int)
                tot_pb = pb.groupby("person").calls.sum().rename("total").reset_index()
                y = alt.Y("person:N", sort=list(tbl.index), title=None, axis=alt.Axis(labelLimit=160))
                bar = alt.Chart(pb).mark_bar().encode(
                    y=y, x=alt.X("calls:Q", title="Calls"),
                    color=alt.Color("direction:N", title=None, legend=alt.Legend(orient="top"),
                                    scale=alt.Scale(domain=["Inbound", "Outbound"], range=[BLUE, ORANGE])),
                    order=alt.Order("order:Q"),
                    tooltip=["person", alt.Tooltip("direction:N", title="Direction"),
                             alt.Tooltip("calls:Q", format=",")])
                bar_labels = alt.Chart(tot_pb).mark_text(align="left", dx=5, fontSize=12, fontWeight="bold",
                                                         color=INK).encode(
                    y=y, x="total:Q", text=alt.Text("total:Q", format=","))
                st.altair_chart((bar + bar_labels).properties(height=ROW1_H - 190), width="stretch")
                st.caption("Bar = Total calls in the table: dark green = Inbound (all), light green = Outbound (all). "
                           "Hover for each part.")
        with right:
            with st.container(border=True, height=ROW1_H):
                st.markdown("#### Calls by person (table)")
                st.caption("Inbound (all) = answered + missed. Outbound (all) = connected + no answer. "
                           "Total calls = Inbound (all) + Outbound (all). Talk time, Avg call and Avg calls / day "
                           "use answered / connected calls only.")
                show = tbl.copy()
                tot = show.drop(columns=["Avg call", "Avg calls / day"]).sum()
                tot["Avg calls / day"] = len(talked) / n_days if n_days else np.nan
                tot["Avg call"] = tot["Talk time"] / len(talked) if len(talked) else np.nan
                show.loc["Total"] = tot[show.columns]
                for col in ("Inbound (all)", "Inbound answered", "Inbound missed", "Outbound (all)",
                            "Outbound connected", "Outbound no answer", "Total calls"):
                    show[col] = show[col].astype(int)
                for col in ("Talk time", "Inbound time", "Outbound time"):
                    show[col] = show[col].map(hms)
                show["Avg call"] = show["Avg call"].map(lambda v: "–" if pd.isna(v) else mmss(v))
                show.index.name = "Person"
                st.dataframe(show, height=38 * (len(show) + 1) + 4,
                             column_config={"Avg calls / day": st.column_config.NumberColumn(format="%.1f")})

        DIRS, DIR_COLORS = ["Inbound", "Outbound"], [BLUE, ORANGE]
        left, right = st.columns(2, gap="medium")
        with left:
            with st.container(border=True, height=ROW2_H):
                st.markdown("#### Average calls by weekday")
                WEEK = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                days_per_wd = talked.groupby("weekday").date.nunique()          # e.g. how many Mondays had calls
                wd = talked.groupby(["weekday", "direction"]).size().rename("total").reset_index()
                wd["days"] = wd.weekday.map(days_per_wd)
                wd["calls"] = (wd.total / wd.days).round(1)
                wd["order"] = (wd.direction == "Outbound").astype(int)
                wd_tot = wd.groupby("weekday").calls.sum().round(0).rename("sum").reset_index()
                x = alt.X("weekday:N", sort=WEEK, title=None, axis=alt.Axis(labelAngle=0, labelExpr="slice(datum.label, 0, 3)"))
                st.altair_chart((alt.Chart(wd).mark_bar().encode(
                    x=x, y=alt.Y("calls:Q", title="Avg calls per day"),
                    color=alt.Color("direction:N", title=None, legend=alt.Legend(orient="top"),
                                    scale=alt.Scale(domain=DIRS, range=DIR_COLORS)),
                    order=alt.Order("order:Q"),
                    tooltip=[alt.Tooltip("weekday:N", title="Weekday"), alt.Tooltip("direction:N", title="Direction"),
                             alt.Tooltip("calls:Q", title="Avg per day"), alt.Tooltip("total:Q", title="Total calls", format=","),
                             alt.Tooltip("days:Q", title="Days")])
                    + alt.Chart(wd_tot).mark_text(dy=-8, fontWeight="bold", color=INK).encode(
                        x=x, y="sum:Q", text=alt.Text("sum:Q", format=",.0f"))
                ).properties(height=270), width="stretch")
                st.caption("Each bar = average connected calls on that weekday "
                           "(e.g. all Monday calls ÷ number of Mondays with calls).")
        with right:
            with st.container(border=True, height=ROW2_H):
                st.markdown("#### Calls by hour of day")
                hourly = talked.groupby(["hour", "direction"]).size().rename("calls").reset_index()
                st.altair_chart(alt.Chart(hourly).mark_bar().encode(
                    x=alt.X("hour:O", title="Hour of day", axis=alt.Axis(labelAngle=0)),
                    y=alt.Y("calls:Q", title="Calls"),
                    color=alt.Color("direction:N", title=None, legend=alt.Legend(orient="top"),
                                    scale=alt.Scale(domain=DIRS, range=DIR_COLORS)),
                    tooltip=["hour", alt.Tooltip("direction:N", title="Direction"), "calls"],
                ).properties(height=270), width="stretch")
                st.caption("Each bar = connected calls that started in that hour (8 = 8:00–8:59), all days added up.")

        with st.container(border=True):
            st.markdown("#### Missed calls by hour of day")
            # Only Call Result = "Missed Call" (voicemail and hung up are left out), split inbound / outbound
            missed = c[c.result == "Missed Call"]
            if missed.empty:
                st.caption("No missed calls in this range.")
            else:
                mh = missed.groupby(["hour", "direction"]).size().rename("missed").reset_index()
                mh["order"] = (mh.direction == "Outbound").astype(int)
                totals = missed.groupby("hour").size().rename("total").reset_index()
                worst = totals.sort_values("total", ascending=False).head(3)
                bars = alt.Chart(mh).mark_bar(cornerRadiusTopLeft=2, cornerRadiusTopRight=2).encode(
                    x=alt.X("hour:O", title="Hour of day (8 = 8:00–8:59)", axis=alt.Axis(labelAngle=0)),
                    y=alt.Y("missed:Q", title="Missed calls"),
                    color=alt.Color("direction:N", title=None, legend=alt.Legend(orient="top"),
                                    sort=["Inbound", "Outbound"],
                                    scale=alt.Scale(domain=["Inbound", "Outbound"], range=[BLUE, "#C9DD8F"])),
                    order=alt.Order("order:Q"),
                    tooltip=[alt.Tooltip("hour:O", title="Hour"), alt.Tooltip("direction:N", title="Direction"),
                             alt.Tooltip("missed:Q", title="Missed calls")])
                labels = alt.Chart(totals).mark_text(dy=-8, fontSize=12, fontWeight="bold", color=INK).encode(
                    x="hour:O", y="total:Q", text="total:Q")
                st.altair_chart((bars + labels).properties(height=280), width="stretch")
                n_in, n_out = int((missed.direction == "Inbound").sum()), int((missed.direction == "Outbound").sum())
                st.caption(f"Each bar = calls with Call Result “Missed Call” in that hour: {n_in:,} inbound, "
                           f"{n_out:,} outbound in total. Voicemail and hung up calls are not included. "
                           "Most missed calls: " + ", ".join(f"{int(h)}:00 ({n})" for h, n in zip(worst.hour, worst.total)) + ".")


# ---------------------------------------------------------------- TAB 2
with tab_setters:
    try:
        s_leads, s_apts = setter_data(tabs)
    except ValueError as err:
        st.error(str(err))
        s_leads = None

    if s_leads is not None:
        all_dates = pd.concat([s_leads.date, s_apts.date])
        today = dt.date.today()
        # Date range = first to last date in the Google Sheet
        lo = all_dates.min().date() if len(all_dates) else today
        hi = all_dates.max().date() if len(all_dates) else today
        f1, f2 = st.columns([3, 2])
        with f1:
            s, e = date_picker(f"setter_range_{lo}_{hi}", lo, hi, lo, hi)
        with f2:
            names = sorted(set(s_leads.setter) | set(s_apts.setter))
            pick = checklist_filter("Setters", names, key="setter_pick")

        Ls = in_range(s_leads, s, e, "date");  Ls = Ls[Ls.setter.isin(pick)]
        As = in_range(s_apts, s, e, "date");   As = As[As.setter.isin(pick)]

        # Appointments = every appointment booked, cancelled ones included.
        # Cancelled is shown separately as the part of them that was cancelled.
        active = As
        t = pd.DataFrame(index=pick)
        t["Leads"] = Ls.groupby("setter").lead.nunique()
        t["Appointments"] = active.groupby("setter").lead.nunique()
        t["Cancelled"] = As[As.status == "Cancelled"].groupby("setter").lead.nunique()
        t["Orders"] = As[As.ordered].groupby("setter").lead.nunique()
        cols = ["Leads", "Appointments", "Cancelled", "Orders"]
        t = t.reindex(columns=cols).fillna(0).astype(int).sort_values(["Leads", "Appointments", "Orders"], ascending=False)
        t = with_total(t, cols, [("Apt / Leads", "Appointments", "Leads"),
                                 ("Order / Apt", "Orders", "Appointments")])
        t["Cancel rate"] = pct(t["Cancelled"], t["Appointments"])
        tot = t.loc["Total"]

        kpi_strip([
            ("Leads created", f"{int(tot.Leads):,}", INK),
            ("Appointments", f"{int(tot.Appointments):,}", BLUE),
            ("Cancelled", f"{int(tot.Cancelled):,}", "#AEB8C6"),
            ("Orders placed", f"{int(tot.Orders):,}", ORANGE),
        ])

        left, right = st.columns([2, 1], gap="medium")
        with left:
            with st.container(border=True):
                st.markdown("#### From lead to order")
                steps = [("Leads created", tot.Leads, INK, ""),
                         ("Appointments", tot.Appointments, BLUE, f"{fmt_pct(tot['Apt / Leads'])} of leads"),
                         ("Orders placed", tot.Orders, ORANGE, f"{fmt_pct(tot['Order / Apt'])} of appointments")]
                fun = pd.DataFrame({"stage": [f"{a}   {d}".strip() for a, b, c, d in steps],
                                    "value": [int(b) for a, b, c, d in steps],
                                    "color": [c for a, b, c, d in steps]})
                base = alt.Chart(fun).encode(y=alt.Y("stage:N", sort=None, title=None,
                                                     axis=alt.Axis(labelFontSize=13, labelLimit=300)))
                funnel = (base.mark_bar(cornerRadius=2, height=40).encode(
                              x=alt.X("value:Q", title=None, axis=None), color=alt.Color("color:N", scale=None))
                          + base.mark_text(align="left", dx=8, fontSize=18, fontWeight="bold", color=INK).encode(
                              x="value:Q", text=alt.Text("value:Q", format=",")))
                st.altair_chart(funnel.properties(height=200), width="stretch")
                st.caption(f"Appointments include the {int(tot.Cancelled):,} that were later cancelled "
                           f"({fmt_pct(tot['Cancel rate'])} of all appointments).")
        with right:
            st.markdown(
                f'<div class="dash hero"><span class="l">Apt / Leads</span>'
                f'<span class="v">{fmt_pct(tot["Apt / Leads"])}</span>'
                f'<span class="s">{int(tot.Appointments):,} appointments ÷ {int(tot.Leads):,} leads</span></div>'
                f'<div class="dash hero"><span class="l">Order / Apt</span>'
                f'<span class="v" style="color:#B7E08A">{fmt_pct(tot["Order / Apt"])}</span>'
                f'<span class="s">{int(tot.Orders):,} orders ÷ {int(tot.Appointments):,} appointments</span></div>',
                unsafe_allow_html=True)

        with st.container(border=True):
            st.markdown("#### By setter")
            t.index.name = "Setter"
            st.caption("Click a number in Appointments (or Leads, Cancelled, Orders) to list those leads, "
                       "with a link to each lead in the CRM, right below the table.")
            picked_s = st.dataframe(t, height=38 * (len(t) + 1) + 4, key="setter_table",
                                    on_select="rerun", selection_mode="single-cell", column_config={
                "Apt / Leads": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100),
                "Order / Apt": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100),
            }, column_order=["Leads", "Appointments", "Cancelled", "Orders", "Apt / Leads", "Order / Apt"])

            # ---- the leads behind the clicked number
            sources = {"Appointments": active, "Cancelled": As[As.status == "Cancelled"],
                       "Orders": As[As.ordered], "Leads": Ls}
            cells = picked_s.selection.cells if picked_s is not None and hasattr(picked_s, "selection") else []
            # Nothing clicked -> show every appointment for all setters (the Total row)
            row_pos, col = cells[0] if cells else (len(t) - 1, "Appointments")
            if True:
                who = t.index[row_pos]
                if col not in sources:
                    st.info(f"Click a number in one of these columns to see the leads: {', '.join(sources)}.")
                else:
                    src = sources[col]
                    hit = (src if who == "Total" else src[src.setter == who]).sort_values("date").drop_duplicates("lead", keep="last")
                    # Report layout: Day | Region | Rep | count | Link | Scheduled by | Order amount
                    region = (hit.office.map(REGION_OF_OFFICE).fillna("Other").where(hit.office != "", "Other")
                              if "office" in hit.columns else "Other")
                    rpt = pd.DataFrame({
                        "Day": hit.date.dt.normalize(),
                        "Region": region,
                        "Rep": hit.owner if "owner" in hit.columns else "",
                        "Appts scheduled" if col != "Leads" else "Leads": 1,
                        "Link": hit.lead.map(lambda i: CRM_LEAD_URL.format(lead=i)) if CRM_LEAD_URL else hit.lead,
                        "Scheduled by" if col != "Leads" else "Created by": hit.setter.str.split().str[0],
                        "Order amount": np.where(hit.ordered if "ordered" in hit.columns else False,
                                                 hit.amount, np.nan) if "amount" in hit.columns else np.nan,
                    })
                    if col == "Cancelled":
                        rpt.insert(rpt.columns.get_loc("Scheduled by") + 1, "Status", "Cancelled")
                    rpt = (rpt.assign(_r=rpt.Region.replace("Other", "~"))          # "Other" last in each day
                           .sort_values(["Day", "_r", "Rep"]).drop(columns="_r"))
                    # show each day / region only on the first row of its group, like a report
                    first_day = ~rpt.Day.duplicated()
                    first_reg = ~rpt.duplicated(["Day", "Region"])
                    rpt["Region"] = np.where(first_reg, rpt.Region, "")
                    rpt["Day"] = np.where(first_day, rpt.Day.dt.strftime("%m/%d/%Y"), "")
                    count_col = "Appts scheduled" if col != "Leads" else "Leads"
                    total = pd.DataFrame([{"Day": "", "Region": "", "Rep": "Total", count_col: int(rpt[count_col].sum()),
                                           "Link": "", "Order amount": rpt["Order amount"].sum(min_count=1)}])
                    rpt = pd.concat([rpt, total], ignore_index=True)
                    rpt["Order amount"] = rpt["Order amount"].map(lambda v: "" if pd.isna(v) else f"${v:,.0f}")
                    st.markdown(f"##### {'All setters' if who == 'Total' else who} · {col}: {len(hit):,} leads"
                                + ("" if cells else "  \n<span style='font-size:13px;color:#5A6474;font-weight:400'>Showing everything. Click a number in the table to narrow it down.</span>"), unsafe_allow_html=True)
                    cfg = {count_col: st.column_config.NumberColumn(format="%d")}
                    if CRM_LEAD_URL:
                        cfg["Link"] = st.column_config.LinkColumn("Links")
                    st.dataframe(rpt, hide_index=True, column_config=cfg,
                                 height=min(38 * (len(rpt) + 1) + 4, 460))
                    st.download_button("Download these leads", rpt.to_csv(index=False).encode("utf-8-sig"),
                                       file_name=f"{who.replace(' ', '_')}_{col}.csv", mime="text/csv",
                                       key="setter_clicked_dl")

        with st.container(border=True):
            h, m = st.columns([3, 2])
            h.markdown("#### Per month")
            metric = m.radio("Show", ["Leads", "Appointments", "Cancelled", "Orders"], index=1,
                             horizontal=True, key="trend_metric", label_visibility="collapsed")
            src = {"Leads": Ls, "Appointments": As, "Cancelled": As[As.status == "Cancelled"],
                   "Orders": As[As.ordered]}[metric]
            trend = src.groupby(src.date.dt.to_period("M")).lead.nunique().rename("count").reset_index()
            trend["month"] = trend.date.dt.to_timestamp()
            color = {"Orders": ORANGE, "Cancelled": "#8792A2", "Leads": INK}.get(metric, BLUE)
            bars = alt.Chart(trend).mark_bar(color=color, cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
                x=alt.X("yearmonth(month):O", title=None, axis=alt.Axis(format="%b %y", labelAngle=0)),
                y=alt.Y("count:Q", title=metric),
                tooltip=[alt.Tooltip("yearmonth(month):O", title="Month", format="%b %Y"), "count"])
            labels = bars.mark_text(dy=-8, fontSize=11, color=MUTED).encode(text="count:Q")
            st.altair_chart((bars + labels).properties(height=260), width="stretch")


# ---------------------------------------------------------------- TAB 3
with tab_sales:
    try:
        c_rows, no_owner = company_data(tabs)
    except ValueError as err:
        st.error(str(err))
        c_rows = None

    if c_rows is not None:
        all_dates = pd.concat([c_rows.date, c_rows.apt_date]).dropna()
        today = dt.date.today()
        # Date range = first to last date in the Google Sheet
        lo = all_dates.min().date() if len(all_dates) else today
        hi = all_dates.max().date() if len(all_dates) else today
        is_setter_branch = lambda b: b.str.lower() == SETTER_BRANCH.lower()
        NO_CREATOR = "Leads with no creator (Web, etc.)"
        sales_branches = sorted((set(c_rows.branch) | set(c_rows.owner_office)) - {"", SETTER_BRANCH})   # incl. Regional Offices
        excluded = {b.lower() for b in EXCLUDED_BRANCHES + [SETTER_BRANCH]}
        branch_options = [b for b in sales_branches if b.lower() not in excluded]   # excluded ones never appear
        f1, f2 = st.columns([3, 2])
        with f1:
            s, e = date_picker(f"sales_range_{lo}_{hi}", lo, hi, lo, hi)
        with f2:
            pick = checklist_filter("Branches", branch_options, key="brx")
        all_picked = set(pick) == set(branch_options)
        scope = "All listed branches" if all_picked else "Selected branches"

        R = c_rows
        start, end = pd.Timestamp(s), pd.Timestamp(e) + pd.Timedelta(days=1)
        within = lambda col: (R[col] >= start) & (R[col] < end)
        # Each count is UNIQUE leads_id, each filtered by its own date:
        R = R.assign(
            is_lead=within("date"),                               # lead created in range
            is_apt=R.active & within("apt_date"),                 # active appointment set in range
            is_cancel=R.cancelled & within("apt_date"),           # cancelled appointment set in range
            is_order=R.ordered & within("order_date"),            # order, by appointment date
            is_install=R.installed & within("order_date"),        # installed system, same date as the order
        )
        R = R[R.is_lead | R.is_apt | R.is_cancel | R.is_order | R.is_install]

        def installs(df):
            """(number of installed leads, total IS amount), each lead counted once."""
            sub = df[df.is_install].drop_duplicates("lead")
            return sub.lead.nunique(), float(sub.is_amount.sum())

        def metrics(D, by=None):
            """Unique leads, active appointments, cancelled and orders, overall or per `by` column."""
            def count(df, flag):
                sub = df[df[flag]]
                return sub.lead.nunique() if by is None else sub.groupby(by).lead.nunique()
            if by is None:
                n_inst, amt = installs(D)
                m = pd.Series({"Leads": count(D, "is_lead"),
                               "Appointments": D[D.is_apt | D.is_cancel].lead.nunique(),   # incl. cancelled
                               "Cancelled": count(D, "is_cancel"), "Orders": count(D, "is_order"),
                               "Installs": n_inst, "Installed $": amt}, dtype=float)
                m["Apt / Leads"] = m.Appointments / m.Leads * 100 if m.Leads else np.nan
                m["Order / Leads"] = m.Orders / m.Leads * 100 if m.Leads else np.nan
                return m
            m = pd.DataFrame({"Leads": count(D, "is_lead"),
                              "Appointments": D[D.is_apt | D.is_cancel].groupby(by).lead.nunique(),
                              "Cancelled": count(D, "is_cancel"), "Orders": count(D, "is_order")})
            m = m.reindex(D[by].unique()).fillna(0).astype(int)
            m["Apt / Leads"] = pct(m.Appointments, m.Leads)
            m["Order / Leads"] = pct(m.Orders, m.Leads)
            return m

        # The whole company: every lead (row) in the all company tab
        # Cards follow the branch filter (everything selected = the whole company)
        in_scope = R.branch.isin(pick)            # leads with no creator / excluded branches never count
        company = metrics(R[in_scope])

        # Totals for a group: leads by `lead_m`, appointments + cancelled by `apt_m`, orders by `order_m`
        def group_totals(lead_m, apt_m, order_m, inst_m):
            n_inst, amt = installs(R[inst_m])
            m = pd.Series({"Leads": R[R.is_lead & lead_m].lead.nunique(),
                           "Appointments": R[(R.is_apt | R.is_cancel) & apt_m].lead.nunique(),   # incl. cancelled
                           "Cancelled": R[R.is_cancel & apt_m].lead.nunique(),
                           "Orders": R[R.is_order & order_m].lead.nunique(),
                           "Installs": n_inst, "Installed $": amt}, dtype=float)
            m["Apt / Leads"] = m.Appointments / m.Leads * 100 if m.Leads else np.nan
            m["Order / Leads"] = m.Orders / m.Leads * 100 if m.Leads else np.nan
            return m

        # Everything in the rep table is counted on the leads each rep OWNS (leads_owner):
        # their leads, the appointments on those leads (whoever set them), how many of those the
        # setters department set up, and the orders / installs on those leads.
        R = R.assign(is_any_apt=R.is_apt | R.is_cancel,
                     is_setter_apt=(R.is_apt | R.is_cancel) & is_setter_branch(R.apt_branch))

        # Benchmark row: leads the appointment setters department created, counted the same way
        # Same rule as the Setter performance tab: leads the setters department CREATED,
        # and appointments (plus their orders / installs) the setters department SET UP
        setter_leads, setter_apts = is_setter_branch(R.branch), is_setter_branch(R.apt_branch)
        setters = group_totals(setter_leads, setter_apts, setter_apts, setter_apts)

        # Each rep's branch = their Regional Office (most common one on the leads they own)
        def mode_branch(df):
            df = df[(df.name != "") & (df.branch != "")]
            return df.groupby("name").branch.agg(lambda b: b.mode().iat[0]) if len(df) else pd.Series(dtype=str)
        office = mode_branch(R[["owner", "owner_office"]].set_axis(["name", "branch"], axis=1))
        other = mode_branch(pd.concat([R[["apt_by", "apt_branch"]].set_axis(["name", "branch"], axis=1),
                                       R[["person", "branch"]].set_axis(["name", "branch"], axis=1)]))
        rep_branch = office.combine_first(other)       # fallback only if there is no Regional Office
        # Each LEAD's branch = its Regional Office (fallback: the owner's usual branch).
        # The Branches filter picks leads by this, so a rep with leads in two offices shows up
        # under both, counting only the leads in the offices you picked.
        R = R.assign(lead_office=R.owner_office.where(R.owner_office != "", R.owner.map(rep_branch).fillna("")))
        in_pick = R.lead_office.isin(pick)       # excluded offices never count
        # Cards + "All listed branches" row: every lead whose Regional Office is in the Branches list
        in_scope = in_pick
        company = metrics(R[in_scope])
        # sales reps = leads owners, except people in the appointment setters department
        names = {n for n in set(R.owner) - {""} if rep_branch.get(n, "").lower() != SETTER_BRANCH.lower()}
        # A rep is a NAME + REGIONAL OFFICE: two people with the same name in different offices are
        # different reps. If a name appears in more than one office, its rows read "Name (Office)".
        multi = R[R.owner.isin(names) & (R.lead_office != "")].groupby("owner").lead_office.nunique()
        multi = set(multi[multi > 1].index)
        R = R.assign(rep=np.where(R.owner.isin(multi) & (R.lead_office != ""),
                                  R.owner + " (" + R.lead_office + ")", R.owner))
        own = R.owner.isin(names) & in_pick
        reps = sorted(set(R.loc[own, "rep"]))

        def per_rep(flag):
            return R[R[flag] & own].groupby("rep").lead.nunique()

        t = pd.DataFrame({"Leads": per_rep("is_lead"),
                          "All appointments": per_rep("is_any_apt"),
                          "Appointments": per_rep("is_any_apt"),
                          "Cancelled": per_rep("is_cancel"),
                          "Apts from setters": per_rep("is_setter_apt"),
                          "Orders": per_rep("is_order"),
                          "Installs": per_rep("is_install")}).reindex(reps).fillna(0).astype(int)
        inst_rows = R[R.is_install & own].drop_duplicates(["rep", "lead"])
        t["Installed $"] = inst_rows.groupby("rep").is_amount.sum().reindex(reps).fillna(0)
        t["Apt / Leads"] = pct(t.Appointments, t.Leads)
        t["Order / Leads"] = pct(t.Orders, t.Leads)
        # Branch column = the rep's Regional Office
        offices = (R[own & (R.lead_office != "")].drop_duplicates(["rep", "lead"])
                   .groupby("rep").lead_office.agg(lambda o: o.value_counts().index[0]))
        t.insert(0, "Branch", offices.reindex(reps).fillna(""))
        sales_tot = group_totals(own, own, own, own)
        t = t.sort_values(["Leads", "Appointments", "Orders"], ascending=False)
        t = t.rename(columns={"Appointments": "Set up (active)"})
        t = t[["Branch", "Leads", "All appointments", "Set up (active)", "Cancelled", "Apts from setters",
               "Orders", "Installs", "Installed $", "Apt / Leads", "Order / Leads"]]
        t.index.name = "Sales rep"

        kpi_strip([
            ("Leads", f"{int(company.Leads):,}", INK),
            ("Appointments", f"{int(company.Appointments):,}", BLUE),
            ("Cancelled", f"{int(company.Cancelled):,}", "#AEB8C6"),
            ("Orders", f"{int(company.Orders):,}", ORANGE),
            ("Installs", f"{int(company.Installs):,}", "#2E8B57"),
            ("Installed $", (f"${company['Installed $'] / 1e6:,.2f}M" if company['Installed $'] >= 1e6
                             else f"${company['Installed $']:,.0f}"), "#2E8B57"),
        ])

        st.markdown(f"""
        <div class="dash cmp">
          <div><h3>Apt / Leads</h3><div class="row">
            <div><div class="v">{fmt_pct(company['Apt / Leads'])}</div><div class="l">{scope}</div></div>
            <div><div class="v blue">{fmt_pct(setters['Apt / Leads'])}</div><div class="l">Appointment setters</div></div>
          </div></div>
          <div><h3>Order / Leads</h3><div class="row">
            <div><div class="v">{fmt_pct(company['Order / Leads'])}</div><div class="l">{scope}</div></div>
            <div><div class="v blue">{fmt_pct(setters['Order / Leads'])}</div><div class="l">Appointment setters</div></div>
          </div></div>
        </div>""", unsafe_allow_html=True)

        with st.container(border=True):
            st.markdown("#### By sales rep")
            st.caption(f"Two rows per sales rep ({ALL_COLS['owner']} + {OFFICE_COL}), both counted on the leads the rep owns: "
                       f"Set by sales = appointments not set by the appointment setters (the rep or other sales staff), "
                       f"plus orders on leads without an appointment. Set by setters = appointments the appointment "
                       f"setters department set up. Orders, installs and Installed $ follow the appointment's row. "
                       f"Share of appts = this row's appointments ÷ the rep's total appointments (both rows). "
                       f"Apt / Leads = all appointments (cancelled included) ÷ the rep's leads; "
                       f"Order / Apt = orders ÷ all appointments. Sorted by leads.")
            setter_row = is_setter_branch(R.apt_branch)
            SETBY = {"Set by sales": ~setter_row, "Set by setters": setter_row}

            def split_counts(mask):
                """Counts for one group of rows: appointments, set up, cancelled, orders, installs, $."""
                sub = R[mask]
                n_inst, amt = installs(sub)
                return {"All appointments": sub[sub.is_any_apt].lead.nunique(),
                        "Set up (active)": sub[sub.is_apt].lead.nunique(),
                        "Cancelled": sub[sub.is_cancel].lead.nunique(),
                        "Orders": sub[sub.is_order].lead.nunique(),
                        "Installs": n_inst, "Installed $": amt}

            rows, meta = [], []
            order = list(t.index)                                        # reps sorted by leads
            for who in ["All sales reps"] + order:          # totals first, then each rep
                base = own if who == "All sales reps" else own & (R.rep == who)
                n_leads = R[base & R.is_lead].lead.nunique()
                branch = "" if who == "All sales reps" else t.loc[who, "Branch"]
                for k, (label, cond) in enumerate(SETBY.items()):
                    c_ = split_counts(base & cond)
                    rows.append({"Branch": branch if k == 0 else "", "Sales rep": who if k == 0 else "",
                                 "Set by": label, "Leads": n_leads if k == 0 else np.nan, **c_,
                                 "Apt / Leads": c_["All appointments"] / n_leads * 100 if n_leads else np.nan,
                                 "Order / Apt": (c_["Orders"] / c_["All appointments"] * 100
                                                 if c_["All appointments"] else np.nan)})
                    meta.append((who, label))
            two = pd.DataFrame(rows)
            # Share of the rep's appointments: this row ÷ (set by sales + set by setters)
            pair_total = two.groupby(two.index // 2)["All appointments"].transform("sum")
            two.insert(two.columns.get_loc("All appointments") + 1, "Share of appts",
                       np.where(pair_total > 0, two["All appointments"] / pair_total * 100, np.nan))
            two["_pair_total"] = pair_total

            def row_style(row):
                who, label = meta[row.name]
                css = "background-color: #EEF6E8;" if label == "Set by setters" else ""
                if who == "All sales reps":
                    css += " font-weight: 700;"
                if label == "Set by sales":
                    css += f" border-top: 1px solid {CRM_TAB_BORDER};"
                return [css] * len(row)

            # Show numbers as text so empty cells stay empty (no "None")
            disp = two.copy()
            num = lambda v: "" if pd.isna(v) else f"{int(v):,}"
            for c_ in ["Leads", "All appointments", "Set up (active)", "Cancelled", "Orders", "Installs"]:
                disp[c_] = disp[c_].map(num)
            disp["Installed $"] = disp["Installed $"].map(lambda v: "" if pd.isna(v) else f"${v:,.0f}")
            for c_ in ["Apt / Leads", "Order / Apt"]:
                disp[c_] = disp[c_].map(lambda v: "" if pd.isna(v) else f"{v:.1f}%")
            disp["Share of appts"] = [
                "" if pd.isna(p_) else f"{p_:.1f}%  ({int(n_):,} of {int(tot_):,})"
                for p_, n_, tot_ in zip(two["Share of appts"], two["All appointments"], two["_pair_total"])]
            disp = disp.drop(columns="_pair_total")
            right = ["Leads", "All appointments", "Share of appts", "Set up (active)", "Cancelled", "Orders",
                     "Installs", "Installed $", "Apt / Leads", "Order / Apt"]
            styled = disp.style.apply(row_style, axis=1)
            st.caption("Click a number to list those leads, with a link to each lead in the CRM, right below the table.")
            picked = st.dataframe(styled, hide_index=True, key="rep_table", on_select="rerun",
                                  selection_mode="single-cell", height=min(36 * (len(two) + 1) + 4, 720),
                                  column_config={c_: st.column_config.TextColumn(c_, alignment="right") for c_ in right})
            st.download_button("Download CSV", disp.to_csv(index=False).encode("utf-8-sig"),
                               file_name=f"sales_vs_setters_{s:%Y%m%d}_{e:%Y%m%d}.csv", mime="text/csv")

            # ---- the leads behind the clicked number
            CLICK_FLAGS = {"Leads": "is_lead", "All appointments": "is_any_apt", "Set up (active)": "is_apt",
                           "Cancelled": "is_cancel", "Orders": "is_order", "Installs": "is_install"}
            cells = picked.selection.cells if picked is not None and hasattr(picked, "selection") else []
            if cells:
                row_pos, col = cells[0]
                who, label = meta[row_pos]
                if col not in CLICK_FLAGS:
                    st.info(f"Click a number in one of these columns to see the leads: {', '.join(CLICK_FLAGS)}.")
                else:
                    base = own if who == "All sales reps" else own & (R.rep == who)
                    if col != "Leads":
                        base = base & SETBY[label]
                    hit = R[R[CLICK_FLAGS[col]] & base].sort_values("apt_date").drop_duplicates("lead", keep="last")
                    leads_tbl = pd.DataFrame({
                        "Lead": (hit.lead.map(lambda i: CRM_LEAD_URL.format(lead=i)) if CRM_LEAD_URL else hit.lead),
                        "Sales rep (lead owner)": hit.rep,
                        "Appointment set by": hit.apt_by,
                        "Set by team": hit.apt_branch,
                        "Set up on": hit.apt_date.dt.strftime("%m/%d/%Y %H:%M").fillna(""),
                        "Status": np.where(hit.cancelled, "Cancelled", np.where(hit.active, "Set up", "")),
                        "Order / install amount": hit.is_amount.map(lambda v: "" if pd.isna(v) else f"${v:,.0f}"),
                    })
                    what = col if col == "Leads" else f"{col} · {label.lower()}"
                    st.markdown(f"##### {who} · {what}: {len(leads_tbl):,} leads")
                    cfg = ({"Lead": st.column_config.LinkColumn("Lead (click to open in CRM)",
                                                                display_text=r"leads_id=(\d+)")}
                           if CRM_LEAD_URL else {})
                    st.dataframe(leads_tbl, hide_index=True, column_config=cfg,
                                 height=min(38 * (len(leads_tbl) + 1) + 4, 420))
                    st.download_button("Download these leads", leads_tbl.to_csv(index=False).encode("utf-8-sig"),
                                       file_name=f"{who.replace(' ', '_')}_{col.replace(' ', '_')}.csv",
                                       mime="text/csv", key="clicked_leads_dl")
