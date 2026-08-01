# Construction Radar

Construction Radar publishes commercial permit opportunities to the existing
static dashboard. Ingestion is organized as independent source adapters that
emit a validated shared schema. Cincinnati/Hamilton and Louisville/Jefferson
are enabled; Boone, Kenton, and Campbell are safe disabled scaffolds pending
verified public data access.

Run the tests with:

```text
python -m unittest discover -s tests -v
```

See `SOURCES.md` for source status and enablement requirements.
