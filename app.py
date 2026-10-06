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
    "order":  "orders salesrepsname",  # any value here = the customer placed an order
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
    "lead_branch": "mbranch",              # their department
    "apt_by":      "apt salesname",        # who set up the appointment
    "apt_branch":  "apt branch",           # their department
    "apt_date":    "first_created",        # when the appointment was set up
    "status":      "final_status",         # "Set up" or "Cancelled"
    "order":       "orders salesrepsname", # any value here = the customer placed an order
}
CHART_MIN_LEADS = 5   # charts only show sales reps with at least this many leads

# Used only to build demo data
SETTER_DEPT = "Appointment Setter"
EXCLUDE_REP_IDS = ["1261"]

# =====================================================================
# LOOK
# =====================================================================
INK, MUTED, BLUE, ORANGE, RULE = "#1B2230", "#5A6474", "#1F5FBF", "#E8913F", "#D5DBE3"
KINDS, KIND_COLORS = ["Inbound", "Outbound", "Missed"], ["#1F5FBF", "#E8913F", "#AEB8C6"]

st.set_page_config(page_title="Appointment Setter Dashboard", layout="wide")
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,400..800&display=swap');
.block-container {{ padding-top: 1.2rem; max-width: 1440px; }}
.dash, .dash * {{ font-family: 'Archivo', 'Helvetica Neue', Helvetica, sans-serif; font-variant-numeric: tabular-nums; }}
.topbar {{ background: {INK}; color: #F3F5F8; border-radius: 6px; padding: 22px 28px; margin-bottom: .6rem;
          display: flex; align-items: baseline; gap: 14px; }}
.topbar h1 {{ margin: 0; padding: 0; font-size: 30px; font-weight: 760; font-stretch: 115%; color: #F3F5F8; }}
.topbar span {{ font-size: 13px; color: #AEB8C6; }}
.kpis {{ display: grid; background: #fff; border: 1px solid {RULE}; border-radius: 6px; margin: .4rem 0 1rem; }}
.kpi {{ padding: 18px 24px; border-left: 1px solid #E3E8EE; display: flex; flex-direction: column; gap: 6px; }}
.kpi:first-child {{ border-left: 0; }}
.kpi .l {{ font-size: 14px; color: {MUTED}; display: flex; align-items: center; gap: 8px; }}
.kpi .v {{ font-size: 36px; font-weight: 700; line-height: 1.05; color: {INK}; }}
.kpi .sub {{ font-size: 14px; color: {MUTED}; }}
.kpi .sub b {{ color: {INK}; font-weight: 650; }}
.sw {{ width: 10px; height: 10px; border-radius: 2px; display: inline-block; }}
.hero {{ background: {INK}; color: #F3F5F8; border-radius: 6px; padding: 26px 30px; display: flex;
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
div[data-testid="stTabs"] button p {{ font-size: 16px; }}
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
        miss = missing_cols(tabs[tab], cols.values())
        if miss:
            raise ValueError(f'The "{tab}" worksheet is missing {miss}. Headers found: {list(tabs[tab].columns)}. '
                             f"Fix the headers in the sheet or the names in app.py.")
    l, a = tabs[LEADS_TAB], tabs[APT_TAB]
    # Keep only rows made by the appointment setters department
    l = l[text(l[LEADS_COLS["branch"]]).str.lower() == SETTER_BRANCH.lower()]
    a = a[text(a[APT_COLS["branch"]]).str.lower() == SETTER_BRANCH.lower()]
    leads = pd.DataFrame({"lead": text(l[LEADS_COLS["lead"]]), "date": to_dt(l[LEADS_COLS["date"]]),
                          "setter": text(l[LEADS_COLS["setter"]])})
    status = text(a[APT_COLS["status"]])
    apts = pd.DataFrame({
        "lead": text(a[APT_COLS["lead"]]),
        "date": to_dt(a[APT_COLS["date"]]),
        "setter": text(a[APT_COLS["setter"]]),
        "status": np.where(status.str.lower().isin(CANCELLED_VALUES), "Cancelled", "Active"),
        "ordered": text(a[APT_COLS["order"]]) != "",
    })
    extra = [c for c in ("path", "path_detail") if c in a.columns]
    for c in extra:
        apts[c] = text(a[c])
    leads = leads[(leads.setter != "") & leads.date.notna()]
    apts = apts[(apts.setter != "") & apts.date.notna()]
    return leads, apts


def company_data(tabs):
    """One row per lead from the all company tab. Each lead belongs to the person who created it
    (mark_salesname / mbranch); its appointment, cancellation and order are counted for that person."""
    if ALL_TAB not in tabs:
        raise ValueError(f'There is no worksheet named "{ALL_TAB}". Worksheets found: {list(tabs)}')
    d = tabs[ALL_TAB]
    if d.empty and len(d.columns) == 0:
        raise ValueError(f'The "{ALL_TAB}" worksheet is empty. Re-run the notebook cell that writes it, '
                         f'then click Refresh now.')
    miss = missing_cols(d, ALL_COLS.values())
    if miss:
        raise ValueError(f'The "{ALL_TAB}" worksheet is missing {miss}. Headers found: {list(d.columns)}. '
                         f"Fix the headers in the sheet or the names in app.py.")
    c = ALL_COLS
    status = text(d[c["status"]])
    has_apt = (text(d[c["apt_by"]]) != "") | (status != "")
    cancelled = status.str.lower().isin(CANCELLED_VALUES)
    rows = pd.DataFrame({
        "lead": text(d[c["lead"]]),
        "date": to_dt(d[c["lead_date"]]),          # lead date (marketing date)
        # appointment date: first_created, or last_date when first_created is empty (e.g. cancelled only)
        "apt_date": to_dt(d[c["apt_date"]]).fillna(to_dt(d["last_date"]) if "last_date" in d.columns
                                                   else pd.Series(pd.NaT, index=d.index)),
        "person": text(d[c["lead_by"]]),
        "branch": text(d[c["lead_branch"]]),
        "active": has_apt & ~cancelled,
        "cancelled": has_apt & cancelled,
        "ordered": text(d[c["order"]]) != "",
    })
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
        "Hour": hour, "Duration [Milliseconds]": secs * 1000, "Direction": direction,
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
    })
    calls["date"] = calls.datetime.dt.normalize()
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


def date_picker(key, default_start, default_end, lo, hi):
    val = st.date_input("Date range", (default_start, default_end), min_value=lo, max_value=hi,
                        key=key, format="MM/DD/YYYY")
    if not isinstance(val, (tuple, list)) or len(val) < 2:
        st.info("Pick an end date to finish the range.")
        st.stop()
    return val


def kpi_strip(items):
    """items: list of (label, value, swatch_color_or_None[, list of sub-lines])"""
    def cell(l, v, c, subs=()):
        sw = f"<span class=sw style=background:{c}></span>" if c else ""
        lines = "".join(f'<span class="sub">{x}</span>' for x in subs)
        return f'<div class="kpi"><span class="l">{sw}{l}</span><span class="v">{v}</span>{lines}</div>'
    cells = "".join(cell(*it) for it in items)
    st.markdown(f'<div class="dash kpis" style="grid-template-columns:repeat({len(items)},minmax(0,1fr))">'
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
        f1, f2 = st.columns([1, 2])
        with f1:
            s, e = date_picker(f"calls_range_{lo}_{hi}", lo, hi, lo, hi)   # first to last call in the sheet
        with f2:
            people = sorted(calls.person.unique())
            pick = st.multiselect("People", people, default=people, key="calls_people")
        mask = (calls.datetime >= pd.Timestamp(s)) & (calls.datetime < pd.Timestamp(e) + pd.Timedelta(days=1)) \
            & calls.person.isin(pick)
        c = calls[mask & calls.direction.isin(["Inbound", "Outbound"])]   # internal calls left out
        # Three separate groups, no overlap: answered inbound, connected outbound, missed (either way)
        c = c.assign(kind=np.where(c.missed, "Missed", c.direction))
        talked = c[c.kind != "Missed"]
        n_days = c.date.nunique()

        inb, outb = c[c.direction == "Inbound"], c[c.direction == "Outbound"]
        in_missed, out_missed = int(inb.missed.sum()), int(outb.missed.sum())
        kpi_strip([
            ("Inbound calls", f"{len(inb):,}", BLUE,
             [f"<b>{len(inb) - in_missed:,}</b> answered", f"<b>{in_missed:,}</b> missed ({fmt_pct(in_missed / len(inb) * 100 if len(inb) else np.nan)})"]),
            ("Outbound calls", f"{len(outb):,}", ORANGE,
             [f"<b>{len(outb) - out_missed:,}</b> connected", f"<b>{out_missed:,}</b> no answer ({fmt_pct(out_missed / len(outb) * 100 if len(outb) else np.nan)})"]),
            ("Avg calls / day", f"{len(talked) / n_days:,.0f}" if n_days else "0", None,
             [f"answered + connected calls", f"÷ {n_days} days with calls"]),
        ])
        st.caption("Inbound missed = no one answered, sent to voicemail, or the customer hung up while on hold / in the queue. "
                   "Outbound no answer = we called and the customer didn't pick up. "
                   "Dates default to the first and last call in the sheet.")

        g = c.groupby("person")
        by = lambda df: df.groupby("person").size()
        tbl = pd.DataFrame({
            "Inbound": by(inb), "Inbound missed": by(inb[inb.missed]),
            "Outbound": by(outb), "Outbound no answer": by(outb[outb.missed]),
        }).reindex(g.size().index).fillna(0).astype(int)
        tbl["Avg calls / day"] = (len_t := talked.groupby("person").size().reindex(tbl.index).fillna(0)) / g.date.nunique()
        tbl["Talk time"] = talked.groupby("person").duration_sec.sum().reindex(tbl.index).fillna(0)
        tbl["Inbound time"] = talked[talked.kind == "Inbound"].groupby("person").duration_sec.sum().reindex(tbl.index).fillna(0)
        tbl["Outbound time"] = talked[talked.kind == "Outbound"].groupby("person").duration_sec.sum().reindex(tbl.index).fillna(0)
        tbl["Avg call"] = tbl["Talk time"] / len_t.replace(0, np.nan)
        tbl = tbl.sort_values("Avg calls / day", ascending=False)

        with st.container(border=True):
            st.markdown("#### Calls by person (chart)")
            parts = ["Inbound answered", "Inbound missed", "Outbound connected", "Outbound no answer"]
            pc = c.assign(part=np.select(
                [(c.direction == "Inbound") & ~c.missed, c.direction == "Inbound", ~c.missed],
                parts[:3], parts[3]))
            bars = pc.groupby(["person", "part"]).size().rename("calls").reset_index()
            bars["order"] = bars.part.map({k: i for i, k in enumerate(parts)})
            totals = pc.groupby("person").size().rename("total").reset_index()
            chart = alt.Chart(bars).mark_bar().encode(
                y=alt.Y("person:N", sort=list(tbl.index), title=None, axis=alt.Axis(labelFontSize=13)),
                x=alt.X("calls:Q", title="Calls"),
                color=alt.Color("part:N", title=None, sort=parts, legend=alt.Legend(orient="top"),
                                scale=alt.Scale(domain=parts, range=[BLUE, "#9DBCEB", ORANGE, "#F5CFA8"])),
                order=alt.Order("order:Q"),
                tooltip=["person", alt.Tooltip("part:N", title="Type"), "calls"])
            labels = alt.Chart(totals).mark_text(align="left", dx=6, fontSize=12, fontWeight="bold", color=INK).encode(
                y=alt.Y("person:N", sort=list(tbl.index)), x="total:Q", text=alt.Text("total:Q", format=","))
            st.altair_chart((chart + labels).properties(height=max(220, 40 * len(tbl))), width="stretch")
            st.caption("Dark blue + light blue = all inbound calls; orange + light orange = all outbound calls. "
                       "The bars use the same numbers as the table below.")

        with st.container(border=True):
            st.markdown("#### Calls by person (table)")
            st.caption("Inbound and Outbound are all calls in that direction; the missed / no-answer columns are the part of them that didn't connect.")
            show = tbl.copy()
            tot = show.drop(columns=["Avg call", "Avg calls / day"]).sum()
            tot["Avg calls / day"] = len(talked) / n_days if n_days else np.nan
            tot["Avg call"] = tot["Talk time"] / len(talked) if len(talked) else np.nan
            show.loc["Total"] = tot[show.columns]
            for col in ("Inbound", "Inbound missed", "Outbound", "Outbound no answer"):
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
            with st.container(border=True):
                st.markdown("#### Calls per day")
                daily = c.groupby(["date", "direction"]).size().rename("calls").reset_index()
                st.altair_chart(alt.Chart(daily).mark_bar().encode(
                    x=alt.X("yearmonthdate(date):O", title=None, axis=alt.Axis(format="%b %d", labelAngle=-45)),
                    y=alt.Y("calls:Q", title="Calls"),
                    color=alt.Color("direction:N", title=None, legend=alt.Legend(orient="top"),
                                    scale=alt.Scale(domain=DIRS, range=DIR_COLORS)),
                    tooltip=[alt.Tooltip("yearmonthdate(date):O", title="Day", format="%a %b %d"),
                             alt.Tooltip("direction:N", title="Direction"), "calls"],
                ).properties(height=260), width="stretch")
        with right:
            with st.container(border=True):
                st.markdown("#### Calls by hour of day")
                hourly = c.groupby(["hour", "direction"]).size().rename("calls").reset_index()
                st.altair_chart(alt.Chart(hourly).mark_bar().encode(
                    x=alt.X("hour:O", title="Hour of day", axis=alt.Axis(labelAngle=0)),
                    y=alt.Y("calls:Q", title="Calls"),
                    color=alt.Color("direction:N", title=None, legend=alt.Legend(orient="top"),
                                    scale=alt.Scale(domain=DIRS, range=DIR_COLORS)),
                    tooltip=["hour", alt.Tooltip("direction:N", title="Direction"), "calls"],
                ).properties(height=260), width="stretch")

        with st.container(border=True):
            st.markdown("#### Missed calls by hour of day")
            missed = c[c.kind == "Missed"]
            if missed.empty:
                st.caption("No missed calls in this range.")
            else:
                mh = missed.groupby(["hour", "direction"]).size().rename("missed").reset_index()
                mh["type"] = mh.direction.map({"Inbound": "Customer called in, not answered",
                                               "Outbound": "We called out, customer didn't answer"})
                totals = missed.groupby("hour").size().rename("total").reset_index()
                worst = totals.sort_values("total", ascending=False).head(3)
                bars = alt.Chart(mh).mark_bar(cornerRadiusTopLeft=2, cornerRadiusTopRight=2).encode(
                    x=alt.X("hour:O", title="Hour of day (8 = 8:00–8:59)", axis=alt.Axis(labelAngle=0)),
                    y=alt.Y("missed:Q", title="Missed calls"),
                    color=alt.Color("type:N", title=None, legend=alt.Legend(orient="top", labelLimit=320),
                                    scale=alt.Scale(domain=["Customer called in, not answered",
                                                            "We called out, customer didn't answer"],
                                                    range=["#5A6474", "#AEB8C6"])),
                    tooltip=[alt.Tooltip("hour:O", title="Hour"), alt.Tooltip("type:N", title="Type"),
                             alt.Tooltip("missed:Q", title="Missed calls")])
                labels = alt.Chart(totals).mark_text(dy=-8, fontSize=12, fontWeight="bold", color=INK).encode(
                    x="hour:O", y="total:Q", text="total:Q")
                st.altair_chart((bars + labels).properties(height=280), width="stretch")
                st.caption("Each bar = how many calls were missed during that hour. "
                           "Most missed calls: " + ", ".join(f"{int(h)}:00 ({n})" for h, n in zip(worst.hour, worst.total)) + ".")

        with st.container(border=True):
            st.markdown(f"#### Call list ({len(c):,} calls)")
            st.caption("The calls for the dates and people picked above, as they are in the sheet.")
            raw_view = raw_calls.loc[c.index]
            st.download_button("Download CSV", raw_view.to_csv(index=False).encode("utf-8-sig"),
                               file_name=f"setter_calls_{s:%Y%m%d}_{e:%Y%m%d}.csv", mime="text/csv")
            st.dataframe(raw_view, hide_index=True, height=400)

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
        f1, f2 = st.columns([1, 2])
        with f1:
            s, e = date_picker(f"setter_range_{lo}_{hi}", lo, hi, lo, hi)
        with f2:
            names = sorted(set(s_leads.setter) | set(s_apts.setter))
            pick = st.multiselect("Setters", names, default=names, key="setter_pick")

        Ls = in_range(s_leads, s, e, "date");  Ls = Ls[Ls.setter.isin(pick)]
        As = in_range(s_apts, s, e, "date");   As = As[As.setter.isin(pick)]

        # Appointments = still active (not cancelled). Cancelled ones are counted separately
        # and are NOT included in Appointments or in the ratios.
        active = As[As.status == "Active"]
        t = pd.DataFrame(index=pick)
        t["Leads"] = Ls.groupby("setter").lead.nunique()
        t["Appointments"] = active.groupby("setter").lead.nunique()
        t["Cancelled"] = As[As.status == "Cancelled"].groupby("setter").lead.nunique()
        t["Orders"] = As[As.ordered].groupby("setter").lead.nunique()
        cols = ["Leads", "Appointments", "Cancelled", "Orders"]
        t = t.reindex(columns=cols).fillna(0).astype(int).sort_values(["Leads", "Appointments", "Orders"], ascending=False)
        t = with_total(t, cols, [("Apt / Leads", "Appointments", "Leads"),
                                 ("Order / Apt", "Orders", "Appointments")])
        t["Cancel rate"] = pct(t["Cancelled"], t["Appointments"] + t["Cancelled"])
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
                st.caption(f"{int(tot.Cancelled):,} cancelled appointments are left out of Appointments "
                           f"and the ratios ({fmt_pct(tot['Cancel rate'])} of everything booked).")
        with right:
            st.markdown(
                f'<div class="dash hero"><span class="l">Apt / Leads</span>'
                f'<span class="v">{fmt_pct(tot["Apt / Leads"])}</span>'
                f'<span class="s">{int(tot.Appointments):,} appointments ÷ {int(tot.Leads):,} leads</span></div>'
                f'<div class="dash hero"><span class="l">Order / Apt</span>'
                f'<span class="v" style="color:#F2A65E">{fmt_pct(tot["Order / Apt"])}</span>'
                f'<span class="s">{int(tot.Orders):,} orders ÷ {int(tot.Appointments):,} appointments</span></div>',
                unsafe_allow_html=True)

        with st.container(border=True):
            st.markdown("#### By setter")
            t.index.name = "Setter"
            st.dataframe(t, height=38 * (len(t) + 1) + 4, column_config={
                "Apt / Leads": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100),
                "Cancel rate": st.column_config.NumberColumn(format="%.1f%%"),
                "Order / Apt": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100),
            }, column_order=["Leads", "Appointments", "Cancelled", "Orders", "Apt / Leads", "Order / Apt", "Cancel rate"])

        with st.container(border=True):
            h, m = st.columns([3, 2])
            h.markdown("#### Per month")
            metric = m.radio("Show", ["Leads", "Appointments", "Cancelled", "Orders"], index=1,
                             horizontal=True, key="trend_metric", label_visibility="collapsed")
            src = {"Leads": Ls, "Appointments": As[As.status == "Active"], "Cancelled": As[As.status == "Cancelled"],
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

        with st.expander(f"Appointment list ({len(As):,})"):
            detail = As.sort_values("date", ascending=False).rename(columns={
                "lead": "Lead", "date": "Set up on", "setter": "Setter", "status": "Status",
                "ordered": "Ordered", "path": "Path", "path_detail": "Path detail"})
            st.dataframe(detail, hide_index=True)
            st.download_button("Download CSV", detail.to_csv(index=False).encode("utf-8-sig"),
                               file_name=f"appointments_{s:%Y%m%d}_{e:%Y%m%d}.csv", mime="text/csv")

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
        sales_branches = sorted(set(c_rows.branch) - {"", SETTER_BRANCH})
        f1, f2 = st.columns([1, 2])
        with f1:
            s, e = date_picker(f"sales_range_{lo}_{hi}", lo, hi, lo, hi)
        with f2:
            pick = st.multiselect("Branches", sales_branches, default=sales_branches, key="sales_branches")

        R = c_rows
        start, end = pd.Timestamp(s), pd.Timestamp(e) + pd.Timedelta(days=1)
        within = lambda col: (R[col] >= start) & (R[col] < end)
        # Each count is UNIQUE leads_id, each filtered by its own date:
        R = R.assign(
            is_lead=within("date"),                               # lead created in range
            is_apt=R.active & within("apt_date"),                 # active appointment set in range
            is_cancel=R.cancelled & within("apt_date"),           # cancelled appointment set in range
            is_order=R.ordered & within("order_date"),            # order, by appointment date
        )
        R = R[R.is_lead | R.is_apt | R.is_cancel | R.is_order]

        def metrics(D, by=None):
            """Unique leads, active appointments, cancelled and orders, overall or per `by` column."""
            def count(df, flag):
                sub = df[df[flag]]
                return sub.lead.nunique() if by is None else sub.groupby(by).lead.nunique()
            if by is None:
                m = pd.Series({"Leads": count(D, "is_lead"), "Appointments": count(D, "is_apt"),
                               "Cancelled": count(D, "is_cancel"), "Orders": count(D, "is_order")}, dtype=float)
                m["Apt / Leads"] = m.Appointments / m.Leads * 100 if m.Leads else np.nan
                m["Order / Leads"] = m.Orders / m.Leads * 100 if m.Leads else np.nan
                return m
            m = pd.DataFrame({"Leads": count(D, "is_lead"), "Appointments": count(D, "is_apt"),
                              "Cancelled": count(D, "is_cancel"), "Orders": count(D, "is_order")})
            m = m.reindex(D[by].unique()).fillna(0).astype(int)
            m["Apt / Leads"] = pct(m.Appointments, m.Leads)
            m["Order / Leads"] = pct(m.Orders, m.Leads)
            return m

        # The whole company: every lead (row) in the all company tab
        company = metrics(R)

        # Benchmark: leads created by the appointment setters department
        setters = metrics(R[is_setter_branch(R.branch)])

        # Sales reps: leads created by everyone else, in the chosen branches
        Rs = R[R.branch.isin(pick) & (R.person != "")]
        sales_tot = metrics(Rs)
        t = metrics(Rs, by="person")
        t.insert(0, "Branch", Rs.groupby("person").branch.agg(lambda b: b.mode().iat[0]).reindex(t.index))
        t["Apt / Leads vs setters"] = t["Apt / Leads"] - setters["Apt / Leads"]
        t["Order / Leads vs setters"] = t["Order / Leads"] - setters["Order / Leads"]
        t = t.sort_values(["Orders", "Appointments", "Leads"], ascending=False)
        t = t[["Branch", "Leads", "Appointments", "Cancelled", "Orders",
               "Apt / Leads", "Apt / Leads vs setters", "Order / Leads", "Order / Leads vs setters"]]
        t.index.name = "Sales rep"

        kpi_strip([
            ("Leads", f"{int(company.Leads):,}", INK),
            ("Appointments", f"{int(company.Appointments):,}", BLUE),
            ("Cancelled", f"{int(company.Cancelled):,}", "#AEB8C6"),
            ("Orders", f"{int(company.Orders):,}", ORANGE),
        ])

        st.markdown(f"""
        <div class="dash cmp">
          <div><h3>Apt / Leads</h3><div class="row">
            <div><div class="v">{fmt_pct(company['Apt / Leads'])}</div><div class="l">All company</div></div>
            <div><div class="v blue">{fmt_pct(setters['Apt / Leads'])}</div><div class="l">Appointment setters</div></div>
          </div></div>
          <div><h3>Order / Leads</h3><div class="row">
            <div><div class="v">{fmt_pct(company['Order / Leads'])}</div><div class="l">All company</div></div>
            <div><div class="v blue">{fmt_pct(setters['Order / Leads'])}</div><div class="l">Appointment setters</div></div>
          </div></div>
        </div>""", unsafe_allow_html=True)

        with st.container(border=True):
            st.markdown("#### By sales rep")
            st.caption(f"All numbers count unique leads_id. Leads by {ALL_COLS['lead_date']}, appointments and "
                       f"cancellations by {ALL_COLS['apt_date']}, orders by the appointment date. "
                       f"Each lead counts for the person who created it ({ALL_COLS['lead_by']}). "
                       f"Leads with no creator (e.g. Web leads) count in All company, but not in any rep's row.")
            st.caption(f"Sorted by orders. “vs setters” = the rep’s % minus the appointment setters’ %. "
                       f"Example: a rep with Apt / Leads 0.0% vs setters {fmt_pct(setters['Apt / Leads'])} shows "
                       f"▼ −{fmt_pct(setters['Apt / Leads'])}. ▲ blue = better than setters, ▼ orange = worse.")
            # Rows sorted by orders, then two summary rows like the design
            show = t.copy()
            summary = pd.DataFrame([
                {"Branch": "", **sales_tot.to_dict(),
                 "Apt / Leads vs setters": sales_tot["Apt / Leads"] - setters["Apt / Leads"],
                 "Order / Leads vs setters": sales_tot["Order / Leads"] - setters["Order / Leads"]},
                {"Branch": "", **setters.to_dict(),
                 "Apt / Leads vs setters": np.nan, "Order / Leads vs setters": np.nan},
                {"Branch": "", **company.to_dict(),
                 "Apt / Leads vs setters": company["Apt / Leads"] - setters["Apt / Leads"],
                 "Order / Leads vs setters": company["Order / Leads"] - setters["Order / Leads"]},
            ], index=["All sales reps", "Appointment setters", "All company"])
            show = pd.concat([show, summary[show.columns]])
            for col in ["Leads", "Appointments", "Cancelled", "Orders"]:
                show[col] = show[col].astype(int)
            show.index.name = "Sales rep"

            def fmt_diff(v):
                return "–" if pd.isna(v) else f"{'▲ +' if v >= 0 else '▼ −'}{abs(v):.1f}%"

            def diff_style(v):
                if pd.isna(v):
                    return ""
                return ("color: #16457F; background-color: #E3EDFB; font-weight: 600" if v >= 0
                        else "color: #8A3B06; background-color: #FCEBDD; font-weight: 600")

            def summary_rows(row):
                if row.name in ("All sales reps", "All company"):
                    return ["font-weight: 700; border-top: 2px solid #1B2230"] * len(row)
                if row.name == "Appointment setters":
                    return [f"color: {BLUE}; font-weight: 600"] * len(row)
                return [""] * len(row)

            # Put the setters' % in the header so the math is visible
            a_col = f"Apt / Leads vs setters ({fmt_pct(setters['Apt / Leads'])})"
            o_col = f"Order / Leads vs setters ({fmt_pct(setters['Order / Leads'])})"
            show = show.rename(columns={"Apt / Leads vs setters": a_col, "Order / Leads vs setters": o_col})
            diff_cols = [a_col, o_col]
            styled = (show.style
                      .format({**{c: "{:,.0f}" for c in ["Leads", "Appointments", "Cancelled", "Orders"]},
                               **{c: fmt_pct for c in ["Apt / Leads", "Order / Leads"]},
                               **{c: fmt_diff for c in diff_cols}})
                      .map(diff_style, subset=diff_cols)
                      .apply(summary_rows, axis=1))
            st.dataframe(styled, height=min(38 * (len(show) + 1) + 4, 680))
            st.download_button("Download CSV", t.to_csv().encode("utf-8-sig"),
                               file_name=f"sales_vs_setters_{s:%Y%m%d}_{e:%Y%m%d}.csv", mime="text/csv")

        def vs_chart(metric):
            d = t[t.Leads >= CHART_MIN_LEADS].reset_index()[["Sales rep", metric]].dropna()
            d = d.sort_values(metric, ascending=False).head(20)
            if d.empty:
                return None
            bars = alt.Chart(d).mark_bar(color=INK, cornerRadius=2).encode(
                y=alt.Y("Sales rep:N", sort=None, title=None, axis=alt.Axis(labelFontSize=12, labelLimit=220)),
                x=alt.X(f"{metric}:Q", title="%"),
                tooltip=["Sales rep", alt.Tooltip(f"{metric}:Q", format=".1f")])
            ref = pd.DataFrame({"v": [setters[metric]], "label": [f"Setters {fmt_pct(setters[metric])}"]})
            rule = alt.Chart(ref).mark_rule(color=BLUE, strokeWidth=2, strokeDash=[6, 4]).encode(x="v:Q")
            lab = alt.Chart(ref).mark_text(color=BLUE, align="left", dx=4, dy=-6, fontWeight="bold").encode(
                x="v:Q", y=alt.value(0), text="label:N")
            return (bars + rule + lab).properties(height=max(160, 30 * len(d)))

        left, right = st.columns(2, gap="medium")
        for col, metric in ((left, "Apt / Leads"), (right, "Order / Leads")):
            with col:
                with st.container(border=True):
                    st.markdown(f"#### {metric}: sales reps vs setters")
                    ch = vs_chart(metric)
                    if ch is None or pd.isna(setters[metric]):
                        st.caption(f"No sales rep has {CHART_MIN_LEADS}+ leads in this range.")
                    else:
                        st.altair_chart(ch, width="stretch")
                        st.caption(f"Reps with at least {CHART_MIN_LEADS} leads. Dashed line = appointment setters.")
