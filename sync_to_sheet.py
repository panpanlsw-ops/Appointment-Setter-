"""
sync_to_sheet.py - copy data from your CRM (or any DataFrame) into the dashboard's Google Sheet.

Run it from your Jupyter notebook, where getCrmData() already works:

    from sync_to_sheet import write_df
    write_df(df_reps, "reps")
    write_df(df_leads, "leads")
    ...

Needs:  pip install gspread google-auth pandas
The service account email must be an EDITOR on the sheet for this script
(the dashboard itself only needs Viewer).

This file is not used by the dashboard and does not need to be deployed.
"""
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

SHEET_URL = "https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID/edit"
KEY_FILE = "service_account.json"   # the JSON key you downloaded; never commit it
CHUNK = 5000                         # rows per request, keeps each call under Google's size limit

_book = None


def _open():
    global _book
    if _book is None:
        creds = Credentials.from_service_account_file(
            KEY_FILE, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        _book = gspread.authorize(creds).open_by_url(SHEET_URL)
    return _book


def write_df(df: pd.DataFrame, worksheet: str):
    """Replace everything in `worksheet` with `df` (headers in row 1)."""
    book = _open()
    try:
        ws = book.worksheet(worksheet)
    except gspread.WorksheetNotFound:
        ws = book.add_worksheet(worksheet, rows=1, cols=1)

    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            out[col] = out[col].dt.strftime("%Y-%m-%d %H:%M:%S").str.replace(" 00:00:00", "", regex=False)
    out = out.astype(object).where(out.notna(), "").astype(str)

    rows = [list(out.columns)] + out.values.tolist()
    ws.clear()
    ws.resize(rows=max(len(rows), 2), cols=max(len(out.columns), 1))
    for start in range(0, len(rows), CHUNK):
        part = rows[start:start + CHUNK]
        ws.update(values=part, range_name=f"A{start + 1}", value_input_option="USER_ENTERED")
    print(f'Wrote {len(out):,} rows to "{worksheet}".')


# ---------------------------------------------------------------------------
# Example: fill every worksheet the dashboard reads. Change the queries to
# your real tables, keep the column names after AS.
# ---------------------------------------------------------------------------
EXAMPLE_QUERIES = {
    "reps": """
        SELECT salesreps_id AS rep_id, name AS rep_name, department
        FROM CRM_salesreps
    """,
    "leads": """
        SELECT leads_id, created_date, created_by, salesreps_id
        FROM CRM_leads
        WHERE created_date >= '2025-01-01'
    """,
    "appointments": """
        SELECT apt_id, leads_id, created_date, created_by, salesreps_id
        FROM CRM_appointments
        WHERE created_date >= '2025-01-01'
    """,
    "quotes": """
        SELECT quote_id, leads_id, created_date
        FROM CRM_quotes
        WHERE created_date >= '2025-01-01'
    """,
    "orders": """
        SELECT order_id, leads_id, order_date AS created_date
        FROM CRM_orders
        WHERE order_date >= '2025-01-01'
    """,
}


def sync_all(get_data):
    """get_data = your getCrmData function from the notebook."""
    for worksheet, query in EXAMPLE_QUERIES.items():
        write_df(get_data(query), worksheet)


# In the notebook:
#   from sync_to_sheet import sync_all, write_df
#   sync_all(getCrmData)
#   write_df(pd.read_csv("goto_call_history.csv"), "calls")   # GoTo export
