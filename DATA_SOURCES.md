# Data sources and terms

The MIT License in this repository covers the original project software and
documentation. It does not relicense third-party source data, map tiles, or
other third-party material.

## NYPD complaint source

The raw **NYPD Complaint Data Historic** dataset is not included in this
repository or in its Git history. The cleaning and modeling code expects a
separately obtained local copy that remains ignored by Git.

Authoritative references:

- Dataset: [NYPD Complaint Data Historic](https://data.cityofnewyork.us/Public-Safety/NYPD-Complaint-Data-Historic/qgea-i56i)
- Dataset identifier: `qgea-i56i`
- Provider: Police Department (NYPD)
- [NYC Open Data FAQ](https://opendata.cityofnewyork.us/faq/)
- [NYC Open Data terms and disclaimer](https://opendata.cityofnewyork.us/overview/#termsofuse)
- [NYC Open Data Technical Standards Manual](https://opendata.cityofnewyork.us/wp-content/uploads/NYC_OpenData_TechnicalStandardsManual.pdf)

NYC Open Data states in its FAQ that Open Data has no use restrictions. The
Technical Standards Manual describes datasets on the portal as public
resources available without restriction or licensing requirements. Access and
use remain subject to the NYC.gov terms, privacy policy, any additional terms
from the providing agency, and the City's accuracy and fitness disclaimers.
No SPDX license identifier is assigned to this source by this project.

The exact reviewed local snapshot identity and its reproduction limits are in
[the complaint-source provenance note](data/source/nyc_open_data/nypd_complaint_data_historic.md).

## Precinct boundary source

The administrative precinct geometry comes from the New York City Department
of City Planning **Police Precincts** dataset, NYC Open Data identifier
`y76i-bdw7`. The vendored boundary file contains administrative geometry only;
it contains no complaint, person, address, or demographic records. It is not
covered by the project MIT License and remains subject to its documented NYC
Open Data source terms.

See [the precinct source provenance note](data/source/nyc_open_data/README.md)
and the adjacent provenance JSON for the source URL, checksum, retrieval time,
schema, disclaimers, and privacy review.

## Aggregate demonstration artifacts

The files under `dashboard/public/data/` are deterministic aggregate browser
artifacts, not a copy of the raw complaint dataset. They exclude complaint
identifiers, event rows, exact event coordinates, addresses, and victim or
suspect demographics. They are included only so the static dashboard can be
reviewed without distributing the raw source data. The project MIT License
does not grant additional rights in the underlying source data.
