# Permit source registry

Only sources with verified public machine-readable access are enabled. A public
application portal is not treated as permission for automated extraction.

| Source ID | Jurisdiction | Status | Authority / access note |
| --- | --- | --- | --- |
| `cincinnati-building-permits` | Cincinnati / Hamilton County, OH | Enabled | City of Cincinnati Open Data Socrata API, datasets `uhjb-xac9` (permits) and `vmk6-gy84` (contacts). |
| `louisville-metro-active-construction-permits` | Louisville / Jefferson County, KY | Enabled | Louisville Metro/LOJIC public ArcGIS FeatureServer. Active permits include contractor, project cost, location, status, work type, and issue date. |
| `boone-county-ky-permits` | Boone County, KY | Scaffold only | Official Building Department and Oracle permitting guidance found; no verified public bulk/API feed or automation terms. |
| `kenton-county-ky-permits` | Kenton County, KY participating jurisdictions | Scaffold only | PDS One Stop Shop uses an application portal. PDS directs records access through its Open Records process and requires commercial-purpose disclosure. |
| `campbell-county-ky-permits` | Campbell County, KY service area | Scaffold only | Official permit department and forms found; no verified public bulk/API feed or automation terms. County coverage is not equivalent to every incorporated city. |

Before enabling a scaffold, record the exact issuing jurisdictions, official
endpoint/export, permitted use, rate limits, update window, field mapping, and
contractor provenance. Add fixtures and adapter contract tests before adding it
to production ingestion.
