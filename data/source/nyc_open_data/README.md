# NYC Police Precinct boundary source

This file documents the vendored precinct-boundary source. The separate
[NYPD Complaint Data Historic provenance note](nypd_complaint_data_historic.md)
records the identity, checksum, known timestamp gap, and reproduction limits of
the raw analytical source snapshot.

`police_precincts_y76i-bdw7_26b.geojson` is the unmodified bulk GeoJSON
export of New York City Department of City Planning's **Police Precincts**
dataset, NYC Open Data identifier `y76i-bdw7`, edition 26B (May 2026).

Retrieve the source from the official endpoint:

```bash
curl -fsSL 'https://data.cityofnewyork.us/api/geospatial/y76i-bdw7?method=export&format=GeoJSON' \
  -o 'Police Precincts.geojson'
shasum -a 256 'Police Precincts.geojson'
```

The expected source checksum is:

```text
5210830afa9d0875b7a7c769edfc4d2ebe984a9ab1e36f3b7fad8508828172aa
```

The adjacent provenance JSON records the publisher, dataset and metadata URLs,
retrieval time, original filename, size, checksum, native and export coordinate
references, schema, public-use assessment, disclaimer, and privacy review. The
spatial builder refuses a source whose bytes, schema, precinct coverage, or
privacy-relevant fields do not match those records.

Do not replace this file with the similarly named live ArcGIS FeatureServer
export. During the 2026-07-12 audit that endpoint returned only 77 features and
omitted precinct 123, while the versioned DCP 26B source and NYC Open Data
export both contained the authoritative 78-feature set.
