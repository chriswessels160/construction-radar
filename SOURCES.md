# Permit source registry

Only sources with verified public machine-readable access are enabled. A public
application portal is not treated as permission for automated extraction.

| Source ID | Jurisdiction | Status | Authority / access note |
| --- | --- | --- | --- |
| `cincinnati-building-permits` | Cincinnati / Hamilton County, OH | Enabled | City of Cincinnati Open Data Socrata API, datasets `uhjb-xac9` (permits) and `vmk6-gy84` (contacts). |
| `louisville-metro-active-construction-permits` | Louisville / Jefferson County, KY | Enabled | Louisville Metro/LOJIC public ArcGIS FeatureServer. Active permits include contractor, project cost, location, status, work type, and issue date. |
| `columbus-building-permits` | City of Columbus, OH | Enabled | City of Columbus Department of Building & Zoning Services public ArcGIS FeatureServer, updated nightly and dedicated to the public domain under CC0. The layer includes applicants but no verified contractor field; contractor remains `Unknown`. Columbus spans multiple counties and the layer omits county, so records use `jurisdiction: Columbus` and `county: Unknown` without guessing. |
| `cleveland-building-permits` | Cleveland, OH | Enabled | City of Cleveland Department of Building and Housing ArcGIS layer, updated weekly. |
| `detroit-building-permits` | Detroit, MI | Enabled | City of Detroit BSEED authoritative ArcGIS layer covering issued permits since 2019. |
| `austin-issued-building-permits` | Austin, TX | Enabled | City of Austin Development Services issued-permit ArcGIS layer. |
| `raleigh-building-permits` | Raleigh, NC | Enabled | Open Raleigh daily BLDS-aligned ArcGIS layer, including contractor fields. |
| `pasadena-active-building-permits` | Pasadena, CA | Enabled | City of Pasadena daily active-building-permit ArcGIS layer. Records lacking published valuation remain excluded by the opportunity filter. |
| `baltimore-building-permits` | Baltimore, MD | Enabled / isolated | City of Baltimore DHCD daily FeatureServer. Temporary server timeouts are isolated from every other source. |
| `beverly-hills-building-permits` | Beverly Hills, CA | Enabled / isolated | City of Beverly Hills nightly assessor permit export. Source HTTP/cache failures are isolated. |
| `las-vegas-building-permits` | Las Vegas, NV | Enabled | City of Las Vegas Office of GIS building-permit FeatureServer. |
| `washington-dc-building-permits` | Washington, DC | Enabled | District Department of Buildings/DC GIS current-year permit FeatureServer under CC BY 4.0. Records without published valuation remain excluded by the opportunity filter. |
| `tempe-building-permits` | Tempe, AZ | Enabled | City of Tempe weekly BLDS-aligned Building Safety permit FeatureServer under CC BY 4.0. |
| `boone-county-ky-permits` | Boone County, KY | Scaffold only | Official Building Department and Oracle permitting guidance found; no verified public bulk/API feed or automation terms. |
| `kenton-county-ky-permits` | Kenton County, KY participating jurisdictions | Scaffold only | PDS One Stop Shop uses an application portal. PDS directs records access through its Open Records process and requires commercial-purpose disclosure. |
| `campbell-county-ky-permits` | Campbell County, KY service area | Scaffold only | Official permit department and forms found; no verified public bulk/API feed or automation terms. County coverage is not equivalent to every incorporated city. |
| `lexington-fayette-ky-permits` | Lexington-Fayette County, KY | Scaffold only | The official development-records page links to AgencyCounter for public permit lookup, but no authoritative bulk/API feed or automated-access terms were verified. |
| `cuyahoga-county-high-value-construction` | Cuyahoga County, OH | Historical scaffold only | County Planning/Fiscal Office DeltaTrack is an official ArcGIS layer for new-construction permits of at least $1 million from 2012-2025. It is intentionally excluded from the current-opportunity feed. Cleveland's current city permit source is already enabled. |
| `bowling-green-warren-ky-permits` | Bowling Green-Warren County, KY | Inspection scaffold only | The official public GIS service exposes construction-inspection points, not permit opportunities, and omits the fields required to represent project value, address, and contractor truthfully. |
| `toledo-oh-building-permits` | Toledo, OH | Historical scaffold only | The official ArcGIS building-permit dataset covers 2018 through March 2023. It is too stale for the dashboard's current-opportunity window. |
| `dayton-oh-building-permits` | Dayton, OH | Permission required | Dayton's official system provides individual record-status search rather than a bulk feed, and its published notice requires prior written permission for commercial use. |

Before enabling a scaffold, record the exact issuing jurisdictions, official
endpoint/export, permitted use, rate limits, update window, field mapping, and
contractor provenance. Add fixtures and adapter contract tests before adding it
to production ingestion.

## Reusable ArcGIS sources

`ArcGISPermitConfig` declares source identity, jurisdiction, date field,
pagination, geometry behavior, and logical field mappings. The shared adapter
handles cutoff queries, pagination, geometry extraction, normalization,
contractor provenance, schema validation, source-qualified IDs, and a bounded
per-source record window. Applicant
fields are retained separately and are never promoted to contractor fields.
