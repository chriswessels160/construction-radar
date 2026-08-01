# Construction Radar

Construction Radar publishes commercial permit opportunities to the existing
static dashboard. Ingestion is organized as independent source adapters that
emit a validated shared schema. Thirteen city/metro sources are configured,
including Cincinnati, Louisville, Columbus, and ten additional U.S. cities.
Boone, Kenton, and Campbell remain safe disabled scaffolds pending verified
public data access. Compatible ArcGIS sources use declarative field mappings,
bounded pagination, and per-source failure isolation rather than one-off fetch
implementations.

Run the tests with:

```text
python -m unittest discover -s tests -v
```

See `SOURCES.md` for source status and enablement requirements.
