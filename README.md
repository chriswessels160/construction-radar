# Construction Radar

Construction Radar publishes commercial permit opportunities to the existing
static dashboard. Ingestion is organized as independent source adapters that
emit a validated shared schema. Thirteen city/metro sources are configured,
including Cincinnati, Louisville, Columbus, and ten additional U.S. cities.
Boone, Kenton, Campbell, Lexington-Fayette, Cuyahoga County, Bowling
Green-Warren County, Toledo, and Dayton remain safe disabled scaffolds pending
current, complete, and commercially usable public data access. Compatible ArcGIS sources use declarative field mappings,
bounded pagination, and per-source failure isolation rather than one-off fetch
implementations.

Run the tests with:

```text
python -m unittest discover -s tests -v
```

See `SOURCES.md` for source status and enablement requirements.

## Lead tools

The static dashboard includes three no-login sales tools:

- **Saved leads** are stored privately in the current browser and can be viewed as a dedicated watchlist.
- **Project comparison** shows up to three selected opportunities side by side.
- **CSV export** downloads the current filtered view, including contact role and source URL. When the saved-leads view is active, only the watchlist is exported.

Browser storage is intentionally the first version. A future account system can sync the same source-qualified project IDs across devices without changing permit records.
