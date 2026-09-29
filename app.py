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
MIN_DATE = dt.date(2025, 1, 1)
MAX_DATE = dt.date(2026, 9, 30)
SETTER_DEPT = "Appointment Setter"   # value in the department column for setters
EXCLUDE_REP_IDS = ["1261"]           # reps to leave out everywhere

# Worksheet (tab) names in your Google Sheet, and the column headers each one must have.
# Row 1 of each worksheet = headers. Extra columns are fine and ignored.
SHEETS = {
    "reps":         ("reps",         ["rep_id", "rep_name", "department"]),
    "leads":        ("leads",        ["leads_id", "created_date", "created_by", "salesreps_id"]),
    "appointments": ("appointments", ["apt_id", "leads_id", "created_date", "created_by", "salesreps_id"]),
    "quotes":       ("quotes",       ["quote_id", "leads_id", "created_date"]),
    "orders":       ("orders",       ["order_id", "leads_id", "created_date"]),
    "calls":        ("calls",        None),   # GoTo call history, headers set in GOTO_COLS below
}
# created_by / salesreps_id must use the same ids as rep_id in the reps worksheet.

# Column headers in the "calls" worksheet (paste the GoTo call history export as-is).
# If they don't match, the app lists the real headers so you can fix these.
GOTO_COLS = {
    "datetime": "Date",
    "person": "User",
    "direction": "Direction",
    "duration": "Duration",
    "line": "Phone Number",   # set to None if you don't have a phone/line column
}

REFRESH_MINUTES = 10  # how often the dashboard re-reads the sheet

# =====================================================================
# LOOK
# =====================================================================
INK, MUTED, BLUE, ORANGE, RULE = "#1B2230", "#5A6474", "#1F5FBF", "#E8913F", "#D5DBE3"

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
SHEET_CFG = secret("gsheet")
DEMO_MODE = SHEET_CFG is None or secret("gcp_service_account") is None


# =====================================================================
# DATA LOADING
# =====================================================================
@st.cache_data(ttl=REFRESH_MINUTES * 60, show_spinner="Reading the Google Sheet...")
def load_data():
    if DEMO_MODE:
        d = demo_crm()
        d["calls_raw"] = None
        d["loaded_at"] = dt.datetime.now()
        return d
    import gspread
    from google.oauth2.service_account import Credentials

    creds = Credentials.from_service_account_info(
        dict(secret("gcp_service_account")),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    book = gspread.authorize(creds).open_by_url(SHEET_CFG["url"])
    names = {ws.title: ws for ws in book.worksheets()}

    data = {}
    for key, (ws_name, required) in SHEETS.items():
        if ws_name not in names:
            raise ValueError(f'The Google Sheet has no worksheet named "{ws_name}". '
                             f"Worksheets found: {list(names)}")
        rows = names[ws_name].get_all_values()
        if not rows:
            raise ValueError(f'The "{ws_name}" worksheet is empty. Row 1 must hold the column headers.')
        header = [h.strip() for h in rows[0]]
        df = pd.DataFrame(rows[1:], columns=header)
        df = df.loc[:, [h != "" for h in header]]
        df = df[(df != "").any(axis=1)]                       # drop blank rows
        if required:
            missing = [c for c in required if c not in df.columns]
            if missing:
                raise ValueError(f'The "{ws_name}" worksheet is missing these column headers: {missing}. '
                                 f"Headers found: {list(df.columns)}")
            df = df[required]
        data[key] = df
    calls_raw = data.pop("calls")
    d = clean(data)
    d["calls_raw"] = calls_raw
    d["loaded_at"] = dt.datetime.now()
    return d


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


def demo_goto(names):
    rng = np.random.default_rng(3)
    today = dt.date.today()
    start = pd.Timestamp(today.replace(day=1))
    n = 1800
    return pd.DataFrame({
        "datetime": start + pd.to_timedelta(rng.integers(0, max((today - start.date()).days, 1) * 86400, n), unit="s"),
        "person": rng.choice(names, n),
        "direction": rng.choice(["Inbound", "Outbound"], n, p=[0.45, 0.55]),
        "duration_sec": rng.gamma(2, 110, n).round(),
        "line": rng.choice(["Main line", "Direct line"], n),
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
    missing = [v for v in GOTO_COLS.values() if v and v not in raw.columns]
    if missing:
        st.error(f'The "calls" worksheet is missing these column headers: {missing}. '
                 f"Update GOTO_COLS in app.py. Headers found: {list(raw.columns)}")
        return None
    direction = raw[GOTO_COLS["direction"]].astype(str).str.strip().str.lower()
    return pd.DataFrame({
        "datetime": pd.to_datetime(raw[GOTO_COLS["datetime"]], errors="coerce", format="mixed"),
        "person": raw[GOTO_COLS["person"]].astype(str).str.strip(),
        "direction": np.select([direction.str.startswith("in"), direction.str.startswith("out")],
                               ["Inbound", "Outbound"], "Other"),
        "duration_sec": raw[GOTO_COLS["duration"]].map(to_seconds),
        "line": raw[GOTO_COLS["line"]].astype(str) if GOTO_COLS.get("line") else "All",
    })


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
    """items: list of (label, value, swatch_color_or_None)"""
    cells = "".join(
        f'<div class="kpi"><span class="l">'
        f'{f"<span class=sw style=background:{c}></span>" if c else ""}{l}</span>'
        f'<span class="v">{v}</span></div>'
        for l, v, c in items)
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


# =====================================================================
# DATA
# =====================================================================
try:
    crm = load_data()
except Exception as err:
    st.error(f"Couldn't read the Google Sheet. {err}")
    st.caption("Check that the sheet is shared with the service account's email, and that the url in secrets is right.")
    st.stop()
reps, leads, apts, quotes, orders = (crm[k] for k in ("reps", "leads", "appointments", "quotes", "orders"))
name_of = dict(zip(reps.rep_id, reps.rep_name))
setter_ids = set(reps.loc[reps.department == SETTER_DEPT, "rep_id"])
sales_ids = set(reps.loc[reps.department != SETTER_DEPT, "rep_id"])

# A lead is credited to whoever set its FIRST appointment; origin_rep = the sales rep who ran it.
origin = (apts.sort_values("created_date").drop_duplicates("leads_id")
          [["leads_id", "created_by", "salesreps_id"]]
          .rename(columns={"created_by": "origin", "salesreps_id": "origin_rep"}))
quotes_o = quotes.merge(origin, on="leads_id", how="inner")
orders_o = orders.merge(origin, on="leads_id", how="inner")

st.markdown('<div class="dash topbar"><h1>Appointment setting</h1>'
            f'<span>{"Demo data: add Google Sheet secrets to see real numbers" if DEMO_MODE else ""}</span></div>',
            unsafe_allow_html=True)
r1, r2 = st.columns([5, 1])
r1.caption(f"Data read from the sheet at {crm['loaded_at']:%b %d, %I:%M %p}. "
           f"It refreshes every {REFRESH_MINUTES} minutes.")
if r2.button("Refresh now", width="stretch"):
    load_data.clear()
    st.rerun()

tab_calls, tab_setters, tab_sales = st.tabs(["Phone calls", "Setter performance", "Sales vs setters"])

# ---------------------------------------------------------------- TAB 1
with tab_calls:
    if DEMO_MODE:
        calls = demo_goto([name_of[i] for i in sorted(setter_ids)])
    else:
        calls = normalize_calls(crm["calls_raw"])
        if calls is not None and calls.dropna(subset=["datetime"]).empty:
            st.info('The "calls" worksheet has no rows with a readable date yet.')
            calls = None

    if calls is not None:
        calls = calls.dropna(subset=["datetime"])
        today = dt.date.today()
        lo, hi = calls.datetime.min().date(), max(calls.datetime.max().date(), today)
        f1, f2 = st.columns([1, 2])
        with f1:
            s, e = date_picker("calls_range", max(today.replace(day=1), lo), min(today, hi), lo, hi)
        with f2:
            people = sorted(calls.person.unique())
            pick = st.multiselect("People", people, default=people, key="calls_people")
        c = in_range(calls, s, e, "datetime")
        c = c[c.person.isin(pick)]

        kpi_strip([
            ("Total calls", f"{len(c):,}", None),
            ("Inbound", f"{(c.direction == 'Inbound').sum():,}", BLUE),
            ("Outbound", f"{(c.direction == 'Outbound').sum():,}", ORANGE),
            ("Total talk time", hms(c.duration_sec.sum()), None),
            ("Average call", mmss(c.duration_sec.mean() if len(c) else 0), None),
        ])

        g = c.groupby(["person", "direction"]).agg(calls=("duration_sec", "size"),
                                                   secs=("duration_sec", "sum")).reset_index()
        tbl = pd.DataFrame(index=sorted(c.person.unique()))
        for d in ("Inbound", "Outbound"):
            sub = g[g.direction == d].set_index("person")
            tbl[d] = sub["calls"]
            tbl[f"{d} time"] = sub["secs"]
        tbl = tbl.fillna(0)
        tbl["Total"] = c.groupby("person").size()
        tbl["Total time"] = c.groupby("person").duration_sec.sum()
        tbl["Avg call"] = tbl["Total time"] / tbl["Total"]
        tbl = tbl.sort_values("Total", ascending=False)

        left, right = st.columns([2, 3], gap="medium")
        with left:
            with st.container(border=True):
                st.markdown("#### Calls by person")
                bars = g[g.direction.isin(["Inbound", "Outbound"])]
                chart = alt.Chart(bars).mark_bar(cornerRadius=2).encode(
                    y=alt.Y("person:N", sort=list(tbl.index), title=None),
                    x=alt.X("calls:Q", title="Calls"),
                    color=alt.Color("direction:N", title=None,
                                    scale=alt.Scale(domain=["Inbound", "Outbound"], range=[BLUE, ORANGE]),
                                    legend=alt.Legend(orient="top")),
                    order=alt.Order("direction:N"),
                    tooltip=["person", "direction", "calls"],
                ).properties(height=max(220, 44 * len(tbl)))
                st.altair_chart(chart, width="stretch")
        with right:
            with st.container(border=True):
                st.markdown("#### Calls and talk time by person")
                show = tbl[["Inbound", "Outbound", "Total", "Inbound time", "Outbound time", "Total time", "Avg call"]].copy()
                total = show[["Inbound", "Outbound", "Total", "Inbound time", "Outbound time", "Total time"]].sum()
                total["Avg call"] = total["Total time"] / total["Total"] if total["Total"] else 0
                show.loc["Total"] = total
                for col in ("Inbound", "Outbound", "Total"):
                    show[col] = show[col].astype(int)
                for col in ("Inbound time", "Outbound time", "Total time", "Avg call"):
                    show[col] = show[col].map(hms)
                st.dataframe(show, height=38 * (len(show) + 1) + 4)

        with st.container(border=True):
            st.markdown("#### By phone line")
            by_line = c.groupby(["person", "line"]).agg(Calls=("duration_sec", "size"),
                                                        secs=("duration_sec", "sum")).reset_index()
            by_line["Time"] = by_line.secs.map(hms)
            wide = by_line.pivot(index="person", columns="line", values=["Calls", "Time"])
            wide.columns = [f"{line} {m.lower()}" for m, line in wide.columns]
            wide = wide[sorted(wide.columns)].fillna("–")
            wide.index.name = "Person"
            st.dataframe(wide)

# ---------------------------------------------------------------- TAB 2
with tab_setters:
    f1, f2 = st.columns([1, 2])
    with f1:
        s, e = date_picker("setter_range", MIN_DATE, min(dt.date.today(), MAX_DATE), MIN_DATE, MAX_DATE)
    with f2:
        setter_names = sorted(name_of[i] for i in setter_ids)
        pick = st.multiselect("Setters", setter_names, default=setter_names, key="setter_pick")
    chosen = {i for i in setter_ids if name_of[i] in pick}

    L = in_range(leads, s, e);    L = L[L.created_by.isin(chosen)]
    A = in_range(apts, s, e);     A = A[A.created_by.isin(chosen)]
    Q = in_range(quotes_o, s, e); Q = Q[Q.origin.isin(chosen)]
    O = in_range(orders_o, s, e); O = O[O.origin.isin(chosen)]

    t = pd.DataFrame(index=sorted(chosen))
    t["Leads"] = L.groupby("created_by").size()
    t["Appointments"] = A.groupby("created_by").size()
    t["Quotes"] = Q.groupby("origin").size()
    t["Orders"] = O.groupby("origin").size()
    t = t.reindex(columns=COUNTS).fillna(0).astype(int)
    t.index = t.index.map(name_of)
    t = with_total(t.sort_values("Appointments", ascending=False), COUNTS, RATIOS)
    tot = t.loc["Total"]

    left, right = st.columns([2, 1], gap="medium")
    with left:
        with st.container(border=True):
            st.markdown("#### From first call to order")
            steps = [("Leads created", tot.Leads, ""),
                     ("Appointments", tot.Appointments, f"{fmt_pct(pct([tot.Appointments], [tot.Leads])[0])} booked"),
                     ("Quotes sent", tot.Quotes, f"{fmt_pct(pct([tot.Quotes], [tot.Appointments])[0])} quoted"),
                     ("Orders", tot.Orders, f"{fmt_pct(pct([tot.Orders], [tot.Quotes])[0])} ordered")]
            fun = pd.DataFrame({"stage": [f"{a}   {c}".strip() for a, b, c in steps],
                                "value": [int(b) for a, b, c in steps],
                                "color": [INK, BLUE, "#6FA6F2", ORANGE]})
            base = alt.Chart(fun).encode(y=alt.Y("stage:N", sort=None, title=None,
                                                 axis=alt.Axis(labelFontSize=13, labelLimit=260)))
            funnel = (base.mark_bar(cornerRadius=2, height=34).encode(
                          x=alt.X("value:Q", title=None, axis=None), color=alt.Color("color:N", scale=None))
                      + base.mark_text(align="left", dx=8, fontSize=18, fontWeight="bold", color=INK).encode(
                          x="value:Q", text=alt.Text("value:Q", format=",")))
            st.altair_chart(funnel.properties(height=230), width="stretch")
    with right:
        st.markdown(
            f'<div class="dash hero"><span class="l">Apt / Leads</span><span class="v">{fmt_pct(tot["Apt / Leads"])}</span>'
            f'<span class="s">{int(tot.Appointments):,} appointments from {int(tot.Leads):,} leads</span></div>'
            f'<div class="dash hero"><span class="l">Order / Apt</span>'
            f'<span class="v" style="color:#F2A65E">{fmt_pct(tot["Order / Apt"])}</span>'
            f'<span class="s">{int(tot.Orders):,} orders from {int(tot.Appointments):,} appointments</span></div>',
            unsafe_allow_html=True)

    with st.container(border=True):
        st.markdown("#### By setter")
        t.index.name = "Setter"
        st.dataframe(t, height=38 * (len(t) + 1) + 4, column_config={
            "Apt / Leads": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=60),
            "Order / Apt": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=30),
        })

    with st.container(border=True):
        h, m = st.columns([3, 2])
        h.markdown("#### Per month")
        metric = m.radio("Show", ["Leads", "Appointments", "Orders"], index=1, horizontal=True,
                         key="trend_metric", label_visibility="collapsed")
        src = {"Leads": L, "Appointments": A, "Orders": O}[metric]
        trend = src.groupby(src.created_date.dt.to_period("M")).size().rename("count").reset_index()
        trend["month"] = trend.created_date.dt.to_timestamp()
        col = alt.Chart(trend).mark_bar(color={"Orders": ORANGE}.get(metric, BLUE),
                                        cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
            x=alt.X("yearmonth(month):O", title=None, axis=alt.Axis(format="%b %y", labelAngle=0)),
            y=alt.Y("count:Q", title=metric),
            tooltip=[alt.Tooltip("yearmonth(month):O", title="Month", format="%b %Y"), "count"])
        labels = col.mark_text(dy=-8, fontSize=11, color=MUTED).encode(text="count:Q")
        st.altair_chart((col + labels).properties(height=260), width="stretch")

# ---------------------------------------------------------------- TAB 3
with tab_sales:
    f1, f2 = st.columns([1, 2])
    with f1:
        s, e = date_picker("sales_range", MIN_DATE, min(dt.date.today(), MAX_DATE), MIN_DATE, MAX_DATE)
    with f2:
        sales_names = sorted(name_of[i] for i in sales_ids)
        pick = st.multiselect("Sales reps", sales_names, default=sales_names, key="sales_pick")
    chosen = {i for i in sales_ids if name_of[i] in pick}
    Lr, Ar = in_range(leads, s, e), in_range(apts, s, e)
    Qr, Or = in_range(quotes_o, s, e), in_range(orders_o, s, e)

    # What the sales rep generated themselves
    own = pd.DataFrame(index=sorted(chosen))
    own["Leads"] = Lr[Lr.created_by.isin(chosen)].groupby("created_by").size()
    own["Appointments"] = Ar[Ar.created_by.isin(chosen)].groupby("created_by").size()
    own["Quotes"] = Qr[Qr.origin.isin(chosen)].groupby("origin").size()
    own["Orders"] = Or[Or.origin.isin(chosen)].groupby("origin").size()

    # What the setters handed to this sales rep
    fromset = pd.DataFrame(index=sorted(chosen))
    fromset["Leads"] = Lr[Lr.created_by.isin(setter_ids)].groupby("salesreps_id").size()
    fromset["Appointments"] = Ar[Ar.created_by.isin(setter_ids)].groupby("salesreps_id").size()
    fromset["Quotes"] = Qr[Qr.origin.isin(setter_ids)].groupby("origin_rep").size()
    fromset["Orders"] = Or[Or.origin.isin(setter_ids)].groupby("origin_rep").size()

    own = with_total(own.reindex(columns=COUNTS).fillna(0).astype(int), COUNTS, RATIOS)
    fromset = with_total(fromset.reindex(columns=COUNTS).fillna(0).astype(int), COUNTS, RATIOS)
    for df in (own, fromset):
        df.index = df.index.map(lambda i: name_of.get(i, i))

    st.markdown(f"""
    <div class="dash cmp">
      <div><h3>Apt / Leads</h3><div class="row">
        <div><div class="v">{fmt_pct(own.loc['Total', 'Apt / Leads'])}</div><div class="l">Sales reps’ own leads</div></div>
        <div><div class="v blue">{fmt_pct(fromset.loc['Total', 'Apt / Leads'])}</div><div class="l">Leads from setters</div></div>
      </div></div>
      <div><h3>Order / Apt</h3><div class="row">
        <div><div class="v">{fmt_pct(own.loc['Total', 'Order / Apt'])}</div><div class="l">Appointments they set</div></div>
        <div><div class="v blue">{fmt_pct(fromset.loc['Total', 'Order / Apt'])}</div><div class="l">Appointments from setters</div></div>
      </div></div>
    </div>""", unsafe_allow_html=True)

    def dumbbell(metric):
        d = pd.DataFrame({"rep": own.index, "Own": own[metric].values,
                          "From setters": fromset[metric].values})
        d = d[d.rep != "Total"]
        y = alt.Y("rep:N", sort=None, title=None, axis=alt.Axis(labelFontSize=13))
        rule = alt.Chart(d).mark_rule(color="#AEB8C6", strokeWidth=2).encode(
            y=y, x=alt.X("Own:Q", scale=alt.Scale(zero=False, padding=20), title="%"), x2="From setters:Q")
        pts = alt.Chart(d.melt("rep", var_name="source", value_name="pct")).mark_circle(size=170, opacity=1).encode(
            y=y, x="pct:Q",
            color=alt.Color("source:N", title=None, scale=alt.Scale(domain=["Own", "From setters"], range=[INK, BLUE]),
                            legend=alt.Legend(orient="top")),
            tooltip=["rep", "source", alt.Tooltip("pct:Q", format=".1f")])
        return (rule + pts).properties(height=max(200, 44 * len(d)))

    left, right = st.columns(2, gap="medium")
    with left:
        with st.container(border=True):
            st.markdown("#### Apt / Leads by sales rep")
            st.altair_chart(dumbbell("Apt / Leads"), width="stretch")
    with right:
        with st.container(border=True):
            st.markdown("#### Order / Apt by sales rep")
            st.altair_chart(dumbbell("Order / Apt"), width="stretch")

    with st.container(border=True):
        st.markdown("#### Side by side")
        both = pd.concat({"Own": own, "From setters": fromset}, axis=1)
        both.columns = [f"{a}: {b}" for a, b in both.columns]
        both.index.name = "Sales rep"
        st.dataframe(both, height=38 * (len(both) + 1) + 4,
                     column_config={c: st.column_config.NumberColumn(format="%.1f%%") for c in both.columns if "/" in c})
