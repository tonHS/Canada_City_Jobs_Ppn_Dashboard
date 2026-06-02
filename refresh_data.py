#!/usr/bin/env python3
"""
refresh_data.py
----------------
Pulls labour-force and population data for selected Canadian cities from
Statistics Canada's open data tables and writes a single `data.json` that the
dashboard reads. Designed to run unattended in GitHub Actions a few times a day;
it only changes data.json when StatCan publishes new figures.

Sources
  - Table 14-10-0459-01  Labour force characteristics by census metropolitan area,
                         three-month moving average, seasonally adjusted
                         (employment + unemployment rate)
  - Table 17-10-0148-01  Population estimates, July 1, by census metropolitan area
                         and census agglomeration
  - Iqaluit population: 2021 Census of Population (city / census subdivision),
                        as Iqaluit is not in the annual sub-provincial estimates.
"""

import io
import json
import zipfile
import datetime as dt

import requests
import pandas as pd

# ---------------------------------------------------------------------------
# Config — edit this list to add or remove cities.
#   emp_geo : exact GEO label in the labour table, or None if not published
#   pop_geo : exact GEO label in the population table, or None
#   pop_override / pop_year_override : use a fixed population (e.g. census count)
#   geo     : short description shown in the UI for population-only areas
# ---------------------------------------------------------------------------
CITIES = [
    {"name": "Toronto",         "emp_geo": "Toronto, Ontario",                          "pop_geo": "Toronto (CMA), Ontario",                          "geo": "CMA"},
    {"name": "Montréal",        "emp_geo": "Montréal, Quebec",                          "pop_geo": "Montréal (CMA), Quebec",                          "geo": "CMA"},
    {"name": "Vancouver",       "emp_geo": "Vancouver, British Columbia",               "pop_geo": "Vancouver (CMA), British Columbia",               "geo": "CMA"},
    {"name": "Calgary",         "emp_geo": "Calgary, Alberta",                          "pop_geo": "Calgary (CMA), Alberta",                          "geo": "CMA"},
    {"name": "Edmonton",        "emp_geo": "Edmonton, Alberta",                         "pop_geo": "Edmonton (CMA), Alberta",                         "geo": "CMA"},
    {"name": "Ottawa–Gatineau", "emp_geo": "Ottawa-Gatineau, Ontario/Quebec",          "pop_geo": "Ottawa - Gatineau (CMA), Ontario/Quebec",         "geo": "CMA"},
    {"name": "Winnipeg",        "emp_geo": "Winnipeg, Manitoba",                        "pop_geo": "Winnipeg (CMA), Manitoba",                        "geo": "CMA"},
    {"name": "Québec City",     "emp_geo": "Québec, Quebec",                            "pop_geo": "Québec (CMA), Quebec",                            "geo": "CMA"},
    {"name": "Hamilton",        "emp_geo": "Hamilton, Ontario",                         "pop_geo": "Hamilton (CMA), Ontario",                         "geo": "CMA"},
    {"name": "Halifax",         "emp_geo": "Halifax, Nova Scotia",                      "pop_geo": "Halifax (CMA), Nova Scotia",                      "geo": "CMA"},
    {"name": "Saskatoon",       "emp_geo": "Saskatoon, Saskatchewan",                   "pop_geo": "Saskatoon (CMA), Saskatchewan",                   "geo": "CMA"},
    {"name": "St. John's",      "emp_geo": "St. John's, Newfoundland and Labrador",     "pop_geo": "St. John's (CMA), Newfoundland and Labrador",     "geo": "CMA"},
    {"name": "Fredericton",     "emp_geo": "Fredericton, New Brunswick",                "pop_geo": "Fredericton (CMA), New Brunswick",                "geo": "CMA"},
    {"name": "Charlottetown",   "emp_geo": None,                                        "pop_geo": "Charlottetown (CA), Prince Edward Island",        "geo": "Census agglomeration"},
    {"name": "Yellowknife",     "emp_geo": None,                                        "pop_geo": "Yellowknife (CA), Northwest Territories",         "geo": "Census agglomeration · territorial capital"},
    {"name": "Whitehorse",      "emp_geo": None,                                        "pop_geo": "Whitehorse (CA), Yukon",                          "geo": "Census agglomeration · territorial capital"},
    {"name": "Iqaluit",         "emp_geo": None,                                        "pop_geo": None, "pop_override": 7429, "pop_year_override": 2021, "geo": "Census subdivision (city) · territorial capital"},
]

EMP_PID = "14100459"   # labour by CMA, 3-month moving average, seasonally adjusted
POP_PID = "17100148"   # population estimates by CMA / CA
TREND_MONTHS = 25      # months of unemployment-rate history to chart
CSV_URL = "https://www150.statcan.gc.ca/n1/tbl/csv/{pid}-eng.zip"


def fetch_table(pid: str) -> pd.DataFrame:
    """Download a StatCan full-table CSV (zipped) and return it as a DataFrame."""
    last_err = None
    for attempt in range(3):
        try:
            r = requests.get(CSV_URL.format(pid=pid), timeout=180)
            r.raise_for_status()
            z = zipfile.ZipFile(io.BytesIO(r.content))
            name = next(n for n in z.namelist() if n.endswith(f"{pid}.csv"))
            with z.open(name) as f:
                return pd.read_csv(f, low_memory=False)
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"  attempt {attempt + 1} for {pid} failed: {e}")
    raise RuntimeError(f"Could not download table {pid}: {last_err}")


def build() -> dict:
    print("Downloading labour table…")
    emp = fetch_table(EMP_PID)
    print("Downloading population table…")
    pop = fetch_table(POP_PID)

    months = sorted(emp["REF_DATE"].unique())[-TREND_MONTHS:]
    ef = emp[(emp["Statistics"] == "Estimate")
             & (emp["Data type"] == "Seasonally adjusted")
             & (emp["REF_DATE"].isin(months))]
    pop_year = int(pop["REF_DATE"].max())

    data = {
        "meta": {
            "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "latest_month": months[-1],
            "pop_year": pop_year,
            "months": months,
        },
        "cities": {},
    }

    for c in CITIES:
        eg, pg = c.get("emp_geo"), c.get("pop_geo")
        if eg:
            sub = ef[ef["GEO"] == eg]
            ur = (sub[sub["Labour force characteristics"] == "Unemployment rate"]
                  .set_index("REF_DATE")["VALUE"].reindex(months).tolist())
            em = (sub[sub["Labour force characteristics"] == "Employment"]
                  .set_index("REF_DATE")["VALUE"].reindex(months).tolist())
            labour = any(v is not None and pd.notna(v) for v in ur)
            if not labour:
                print(f"  WARNING: no labour data for {c['name']} (GEO '{eg}'); check the label.")
            ur = [None if (v is None or pd.isna(v)) else round(float(v), 1) for v in ur]
            em = [None if (v is None or pd.isna(v)) else round(float(v), 1) for v in em]
        else:
            ur, em, labour = [None] * len(months), None, False

        if c.get("pop_override") is not None:
            population, py = c["pop_override"], c["pop_year_override"]
        elif pg:
            pr = pop[(pop["GEO"] == pg) & (pop["REF_DATE"] == pop_year)
                     & (pop["Gender"] == "Total - gender") & (pop["Age group"] == "All ages")]
            population = int(pr["VALUE"].iloc[0]) if len(pr) else None
            py = pop_year
            if population is None:
                print(f"  WARNING: no population for {c['name']} (GEO '{pg}').")
        else:
            population, py = None, pop_year

        data["cities"][c["name"]] = {
            "unemp_rate": ur,
            "employment": em,
            "population": population,
            "pop_year": py,
            "labour": labour,
            "geo": c["geo"],
        }

    can = (ef[(ef["GEO"] == "Canada") & (ef["Labour force characteristics"] == "Unemployment rate")]
           .set_index("REF_DATE")["VALUE"].reindex(months))
    data["national"] = {"unemp_rate": [None if pd.isna(v) else round(float(v), 1) for v in can]}
    return data


# Minimum number of cities we expect to have labour data. The CITIES list has
# 13 CMAs with emp_geo set, so anything below this means StatCan labels drifted
# or the table layout changed.
MIN_LABOUR_CITIES = 12
# Refuse to publish if the latest labour month is older than this many days.
# StatCan releases monthly, so anything beyond ~75 days means the schedule is
# stalled or the table moved.
MAX_LATEST_MONTH_AGE_DAYS = 75


def validate(out: dict) -> None:
    """Raise ValueError if the generated dataset looks broken.

    Causes the workflow to exit non-zero so GitHub emails the repo owner and
    the previous data.json stays in the repo untouched.
    """
    problems = []

    n_lab = sum(1 for d in out["cities"].values() if d["labour"])
    if n_lab < MIN_LABOUR_CITIES:
        problems.append(f"only {n_lab} cities have labour data (expected ≥ {MIN_LABOUR_CITIES})")

    nat = out["national"]["unemp_rate"]
    if not any(v is not None for v in nat):
        problems.append("national unemployment series is entirely null")

    latest = out["meta"]["latest_month"]
    try:
        latest_dt = dt.datetime.strptime(latest, "%Y-%m").replace(tzinfo=dt.timezone.utc)
        age_days = (dt.datetime.now(dt.timezone.utc) - latest_dt).days
        if age_days > MAX_LATEST_MONTH_AGE_DAYS:
            problems.append(f"latest month {latest} is {age_days} days old (max {MAX_LATEST_MONTH_AGE_DAYS})")
    except ValueError:
        problems.append(f"latest_month '{latest}' is not parseable as YYYY-MM")

    missing_pop = [n for n, d in out["cities"].items() if d["population"] is None]
    if missing_pop:
        problems.append(f"missing population for: {', '.join(missing_pop)}")

    for name, d in out["cities"].items():
        if d["labour"] and lastVal_py(d["unemp_rate"]) is None:
            problems.append(f"{name}: labour=True but no recent unemp_rate value")

    if problems:
        raise ValueError("data.json failed validation:\n  - " + "\n  - ".join(problems))


def lastVal_py(seq):
    for v in reversed(seq):
        if v is not None:
            return v
    return None


if __name__ == "__main__":
    out = build()
    validate(out)
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    n_lab = sum(1 for d in out["cities"].values() if d["labour"])
    print(f"Wrote data.json — {len(out['cities'])} areas, {n_lab} with labour data, "
          f"labour month {out['meta']['latest_month']}, population year {out['meta']['pop_year']}.")
