# Prepared Vercel deployment

Deployment is intentionally **not published**. The stored CLI login was invalid; the user requested preparation only.

The static Nuxt frontend and the read-only FastAPI function can live in one Vercel project. Heavy data acquisition and training run locally. Runtime has no external API dependency and does not require the NASA/Earthdata secrets.

## Deploy when ready

From the repository root, using a valid Vercel account:

```bash
vercel login
vercel
```

Inspect the preview. Once explicitly ready to publish production:

```bash
vercel --prod
```

Use the repository root as the Vercel root directory and preserve the checked-in `vercel.json` overrides. Runtime Node major is set to 24; the current Nuxt build needs Node 24.15+ or a compatible version. Use Python 3.11+.

## How routing and packaging work

- Build command: `npm --prefix frontend ci && npm --prefix frontend run generate`.
- Static directory: `frontend/.output/public`.
- Python entrypoint: `api/index.py`, importing `backend.app:app`.
- `/api/*` rewrite: `/api/index.py`.
- Production requirements: FastAPI, numpy, scipy, uvicorn. pandas/sklearn/shapely are offline analysis dependencies.
- Required prepared assets: observations.npz, events.json.gz, analysis.json.gz, california.geojson, map-context.geojson. Seasonal outliers additionally require activity_daily.npz, activity_metadata.json, activity_diagnostics.json, activity_events.npz and activity_events.json. Event preparation is offline; runtime uses numpy/scipy and no Shapely.
- `.vercelignore` excludes `.env`, raw data, full working CSV/JSON, models, tests, and development folders. No key is embedded in the prepared data.

Vercel's current FastAPI documentation supports Python functions and a 500 MB Python bundle. The prepared data is approximately10 MB. A cloud build has **not** been tested because no deployment was requested; verify the first preview before relying on it for the submission.

## Post-deploy smoke checks

1. `/api/health` returns `status: ok` and 1,169,069 observations.
2. `/api/catalog` includes scientific metadata and local map geography.
3. Full-state calendar shows25 years; September 2020 has125,290 reference observations.
4. July 2024 shows an unavailable harmonized month with outage context.
5. Changing region updates raw counts, calendar and map.
6. ML pane shows the ratio baseline chosen on validation and actual held-out scores.
7. Extreme-fire pane showsp = .005 for the full-state/full-period bootstrap and no bootstrap p for an interactive subset.
8. CSV/SVG/JSON downloads work and require no viewer login.

References: https://vercel.com/docs/frameworks/backend/fastapi and https://vercel.com/docs/frameworks/full-stack/nuxt

