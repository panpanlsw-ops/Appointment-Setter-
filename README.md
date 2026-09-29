# Appointment Setter Dashboard

A Streamlit dashboard that reads everything from one Google Sheet and refreshes every 10 minutes (plus a **Refresh now** button).

1. **Phone calls**: GoTo call history (inbound, outbound, talk time per person and per phone line), month to date by default.
2. **Setter performance**: leads, appointments, quotes and orders per setter, with Apt / Leads and Order / Apt (Jan 2025 – Sep 2026).
3. **Sales vs setters**: each sales rep's own results next to the appointments setters handed them.

## Files

```
app.py                            the dashboard
sync_to_sheet.py                  optional: copy CRM data from your notebook into the sheet
requirements.txt                  Python packages
.streamlit/config.toml            colors and theme
.streamlit/secrets.toml.example   template for the sheet link, Google key and password
.gitignore                        keeps secrets and key files out of GitHub
```

## 1. Set up the Google Sheet

Create one Google Sheet with these six worksheets (tab names must match exactly). Row 1 of each tab holds the headers; extra columns are fine.

| Worksheet      | Required headers                                                  |
|----------------|-------------------------------------------------------------------|
| `reps`         | `rep_id`, `rep_name`, `department`                                |
| `leads`        | `leads_id`, `created_date`, `created_by`, `salesreps_id`          |
| `appointments` | `apt_id`, `leads_id`, `created_date`, `created_by`, `salesreps_id`|
| `quotes`       | `quote_id`, `leads_id`, `created_date`                            |
| `orders`       | `order_id`, `leads_id`, `created_date`                            |
| `calls`        | the GoTo call history export, pasted as-is                        |

- `created_by` and `salesreps_id` must use the same ids as `rep_id` in `reps`.
- In `reps`, setters' `department` must be exactly `Appointment Setter` (or change `SETTER_DEPT` in `app.py`).
- For `calls`, set `GOTO_COLS` in `app.py` to the export's header names. If they're wrong, the dashboard shows the real ones.

To fill the sheet from your Jupyter notebook instead of by hand, use `sync_to_sheet.py`:

```python
from sync_to_sheet import sync_all, write_df
sync_all(getCrmData)                                       # reps, leads, appointments, quotes, orders
write_df(pd.read_csv("goto_call_history.csv"), "calls")   # GoTo export
```

## 2. Create a Google service account (one time)

This lets the dashboard read a private sheet.

1. Go to https://console.cloud.google.com and create a project (any name).
2. **APIs & Services → Library**: enable **Google Sheets API**.
3. **IAM & Admin → Service Accounts → Create service account**. No roles needed.
4. Open it → **Keys → Add key → JSON**. A `.json` file downloads. Keep it private and never put it on GitHub.
5. In your Google Sheet, click **Share** and add the service account's `client_email` (from the JSON). **Viewer** is enough for the dashboard; use **Editor** if you'll run `sync_to_sheet.py`.

## 3. Run it on your computer

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# fill in the sheet url and copy the fields from the JSON key into [gcp_service_account]
streamlit run app.py
```

Without the `[gsheet]` and `[gcp_service_account]` sections, the app runs on demo data.

## 4. Put it on GitHub

```bash
git init
git add .
git commit -m "Appointment setter dashboard"
git branch -M main
git remote add origin https://github.com/<your-account>/setter-dashboard.git
git push -u origin main
```

Make the repository **private**. Run `git status` before the first push and make sure `secrets.toml` and the `.json` key are not listed.

## 5. Deploy on Streamlit Community Cloud

1. Go to https://share.streamlit.io and sign in with GitHub.
2. Click **Create app**, choose the repository, branch `main`, main file `app.py`.
3. **Advanced settings → Secrets**: paste the contents of your `secrets.toml`.
4. Click **Deploy**.

Every push to `main` updates the app. New data in the sheet shows up within 10 minutes, or right away with **Refresh now**.

Set `APP_PASSWORD` in secrets so only people with the password can see the data.
