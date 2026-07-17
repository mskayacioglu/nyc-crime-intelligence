# NYPD Complaint Data Historic source provenance

The analytical pipeline uses the official NYC Open Data **NYPD Complaint Data
Historic** dataset.

| Field | Reviewed value |
| --- | --- |
| Dataset identifier | `qgea-i56i` |
| Publisher attribution | Police Department (NYPD) |
| Official dataset page | <https://data.cityofnewyork.us/Public-Safety/NYPD-Complaint-Data-Historic/qgea-i56i> |
| Official metadata API | <https://data.cityofnewyork.us/api/views/qgea-i56i> |
| Current CSV export endpoint | <https://data.cityofnewyork.us/api/views/qgea-i56i/rows.csv?accessType=DOWNLOAD> |
| Expected repository path | `data/raw/NYPD_Complaint_Data_Historic.csv` |
| Reviewed local byte size | `3,429,157,518` bytes |
| Reviewed local row count | `10,071,507` |
| Reviewed local SHA-256 | `759016def1c04aafaaeaa8e35c622d13abdd4af82a69f7b9e2b5549c08e47827` |
| Independent retrieval timestamp | Not recorded |

The raw CSV is intentionally ignored by Git and is never published to the
browser. To reproduce the checked-in analytical snapshot exactly, obtain an
export whose SHA-256 matches the reviewed value above and place it at the
expected path. A new portal export is a new source snapshot even when its file
name is unchanged; record its byte size, checksum, retrieval time, and review
date before rebuilding derived artifacts.

To retrieve the portal's current export from the repository root:

```bash
curl -fL 'https://data.cityofnewyork.us/api/views/qgea-i56i/rows.csv?accessType=DOWNLOAD' \
  -o data/raw/NYPD_Complaint_Data_Historic.csv
shasum -a 256 data/raw/NYPD_Complaint_Data_Historic.csv
```

This command retrieves the current portal snapshot; it is not expected to
recreate the reviewed historical bytes after the portal data changes.

The source retrieval timestamp cannot be reconstructed from the file's local
modification time and is therefore reported as unavailable. The cleaning
pipeline's `--as-of-date` is also a review parameter, not a source retrieval
timestamp. The published snapshot uses `--as-of-date 2026-07-04`; pass that
value for exact quality-flag reproduction or explicitly document an intentional
advance.

This dataset contains reported complaints. Reporting delays, revisions,
under-reporting, and classification changes can affect the records. Public
availability does not make complaint records causal truth and does not permit
person-level scoring, individual risk labels, or patrol, enforcement,
deployment, or intervention recommendations in this project.
