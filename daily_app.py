"""
Daily performance dashboard for the sales reps.

It runs the main dashboard (app.py) in "daily only" mode, so it shows exactly the
Daily performance report and nothing else: no Phone calls, History or Sales vs setters tabs.
Any change to the Daily performance report in app.py shows up here automatically.

Deploy it on Streamlit Community Cloud as a SECOND app from the same GitHub repository,
with "Main file path" set to daily_app.py. It uses the same secrets as the main app.
"""
from pathlib import Path

APP = Path(__file__).with_name("app.py")
exec(compile(APP.read_text(encoding="utf-8"), str(APP), "exec"),
     {"__name__": "__main__", "__file__": str(APP), "DAILY_ONLY": True})
