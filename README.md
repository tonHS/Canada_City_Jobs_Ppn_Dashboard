# Canadian Cities — Labour & Population Dashboard

A static dashboard showing unemployment, employment, and population for major
Canadian Census Metropolitan Areas / Census Agglomerations, built on Statistics
Canada open data. It refreshes itself automatically: a GitHub Action re-pulls
StatCan every few hours and commits a fresh `data.json`, and Vercel redeploys on
each commit.

# Verification and Disclaimer

This is AI-generated with spot-check verification against external data sources. This spot-check verification process discovered no errors and since the dashboard does little analysis of its own but simply displays the numbers, it seems reasonable to deem this dashboard and its dynamic data updates reliable. However, to be clear, please do not use these numbers or anything in this dashboard for any material purposes without checking them yourself. 

## How it works

```
refresh_data.py  ──(GitHub Action, every 6h)──▶  data.json  ──▶  index.html (static, on Vercel)
```

- **`index.html`** — the dashboard. Loads `data.json` at runtime. No build step.
- **`data.json`** — the generated dataset (committed; ships with current data).
- **`refresh_data.py`** — downloads StatCan tables and rewrites `data.json`.
- **`.github/workflows/refresh.yml`** — the schedule that runs the script and commits.

The browser can't call StatCan directly (no cross-origin access), which is why a
scheduled job produces `data.json` instead of fetching live in the page.

## Quick deploy checklist

1. **Create a GitHub repo** and add these files, keeping the
   `.github/workflows/refresh.yml` path intact. Push to GitHub.
2. **Enable the Action to commit:** repo **Settings → Actions → General →
   Workflow permissions →** select **“Read and write permissions” → Save.**
3. **Connect to Vercel:** vercel.com → **Add New → Project →** import the repo.
   Framework preset **Other**, no build command, output directory = repo root.
   **Deploy.**
4. **Kick off the first refresh (optional):** GitHub **Actions** tab → **Refresh
   StatCan data → Run workflow.** It then runs every 6 hours on its own.

That's it. New StatCan releases appear on the site within hours, with no manual work.

## Editing the city list

Open `refresh_data.py` and edit the `CITIES` list. Each entry needs the exact
`GEO` label from the StatCan tables. Cities without a monthly Labour Force
Survey figure (e.g. smaller capitals) use `emp_geo: None` and show population
only.

## Run locally

```bash
pip install -r requirements.txt
python refresh_data.py            # regenerates data.json
python -m http.server 8000        # then open http://localhost:8000
```

Open it over `http://` (not a `file://` path) so the page can fetch `data.json`.

## Data sources

- **Employment & unemployment rate** — Statistics Canada, Table 14-10-0459-01
  (Labour force characteristics by census metropolitan area, three-month moving
  average, seasonally adjusted).
- **Population** — Statistics Canada, Table 17-10-0148-01 (Population estimates,
  July 1, by census metropolitan area and census agglomeration).
- **Iqaluit population** — Statistics Canada, 2021 Census of Population (Iqaluit,
  City — census subdivision); Iqaluit is not in the annual sub-provincial estimates.

Charlottetown, Yellowknife, Whitehorse and Iqaluit are not covered by the
monthly Labour Force Survey at this geography, so they appear with population only.

Statistics Canada data is used under the
[Statistics Canada Open Licence](https://www.statcan.gc.ca/en/reference/licence).
