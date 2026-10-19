# Verification of the 10,000-record mixed batch

10,000 records of the Swiss Federal Archives, drawn by `src/cora/mixed.py` over three source tiers (primary by form; secondary and tertiary from archival evidence: title conventions and form), the three form types and five eras of the beginning date, none of them already in `data/`. Processed by `src/batch_run.sh` with the per-feature models of `src/config.toml` (classify/audit: Apertus v1.5 8B, source level: 70B). Timings in `data/batch10k/timing.tsv`, full per-record checks in `data/batch10k/qc_report.json`.

## Findings

- **Ready for the website.** 98.6 % of the records pass every automatic check (target ≥ 80 %), 0.9 % have a structural error (target < 5 %); creation dates fall inside the record's own range in 99.3 % of the cases. 2 records got no valid answer from either model and are left out.
- **Source level.** Registers and indexes (tertiary) and press clippings (secondary) are recognised in 95-97 % of the cases. The low agreement on the 'history' and 'obituary' pools is mostly the evidence label being wrong, not Apertus: these title patterns also catch department dossiers about congresses, correspondence about a Festschrift and parliamentary eulogies, which Apertus correctly calls primary (manual review: source level right in 92 % of the sample).
- **Known inconsistency (also in the demo set).** TV news and newsreels are split between primary and secondary: the source-level pass applies the press convention (`press_convention = "secondary"`) to broadcast news only part of the time (1,133 of 2,248 in this batch; 27 of 41 in the demo). A rule that fixes broadcast news to one level would remove it.
- **Archiving date.** Apertus matches the accession-number rule in only 27.8 % of the records; the export always uses the rule (conflict policy in `export.py`), so this does not reach the site.
- **Manual review.** Major errors in 4 of 66 records: a misread institution (German BND for the Swiss intelligence service), an invented first name, a grant request read as the book it funds and a police card with the archive as creator. Most minor errors are document type / medium on non-standard items (posters, typed communiqués, tables of contents).

## Draw

| Tier / type | pre1900 | 1900-1939 | 1940-1969 | 1970-1999 | 2000+ | Total |
|---|---:|---:|---:|---:|---:|---:|
| primary/audiovisual | – | 83 (of 83) | 584 (of 64,387) | 584 (of 90,675) | 583 (of 60,187) | 1,834 |
| primary/other | 366 (of 397) | 366 (of 1,876) | 367 (of 3,780) | 367 (of 8,110) | 367 (of 25,547) | 1,833 |
| primary/still_image | 278 (of 278) | 904 (of 5,633) | 388 (of 388) | 263 (of 263) | – | 1,833 |
| secondary/secondary_history | 64 (of 64) | 197 (of 197) | 364 (of 402) | 365 (of 569) | 213 (of 213) | 1,203 |
| secondary/secondary_obituary | 8 (of 8) | 48 (of 48) | 88 (of 88) | 66 (of 66) | 83 (of 83) | 293 |
| secondary/secondary_press | 65 (of 65) | 284 (of 504) | 285 (of 2,393) | 285 (of 2,069) | 285 (of 504) | 1,204 |
| tertiary/tertiary_index | 170 (of 170) | 174 (of 174) | 485 (of 578) | 486 (of 1,515) | 485 (of 717) | 1,800 |

Cells with fewer records than their share are taken in full; the rest goes to the other cells of the type.

## Automatic checks (qc.py)

| Check | This batch | Demo (300) |
|---|---:|---:|
| Records without structural or critical error | 98.6 % | 99.3 % |
| Structural errors | 0.9 % | 0.0 % |
| Critical errors | 0.6 % | 0.7 % |
| Résumé ≤ 3 sentences | 99.9 % | 100.0 % |
| Named entities found in the record | 98.7 % | 99.4 % |
| … strict match | 88.6 % | 95.7 % |
| Creation date inside the record's date range | 99.3 % | 98.2 % |
| Archiving date = accession rule | 27.8 % | 53.7 % |
| Places located by the gazetteer | 71.7 % | 77.3 % |
| Creator / publisher agreement with the record | 2010/2171 / 1455/1457 | 44/44 / 28/28 |

Critical errors: date_created_outside_record_range 45, created_after_archived 11, no_output 2

Structural errors: enum 65, resume_4_sentences 9, non_iso 8, type 4, no_output 2

Warnings: date_archived_mismatch 7218, source_level_secondary_mismatch 1397, repaired:iso 664, ungrounded_entities 351, geo_conflict_over_50km 351, repaired:control_chars 243, source_level_tertiary_mismatch 219, resume_speculative 28, source_level_primary_mismatch 14, date_created_outside_record_range 1

## By tier and era

| Tier | Era | n | OK | Critical | Date in range | Source level = evidence |
|---|---|---:|---:|---:|---:|---:|
| primary | pre1900 | 644 | 97.0 % | 0.3 % | 99.5 % | – |
| primary | 1900-1939 | 1,353 | 99.2 % | 0.1 % | 99.8 % | – |
| primary | 1940-1969 | 1,339 | 99.8 % | 0.1 % | 99.8 % | – |
| primary | 1970-1999 | 1,214 | 99.8 % | 0.1 % | 99.9 % | – |
| primary | 2000+ | 950 | 98.9 % | 1.1 % | 100.0 % | – |
| secondary | pre1900 | 137 | 96.4 % | 0.0 % | 100.0 % | 78.1 % |
| secondary | 1900-1939 | 529 | 97.0 % | 0.8 % | 98.8 % | 72.2 % |
| secondary | 1940-1969 | 737 | 97.6 % | 0.7 % | 98.8 % | 65.9 % |
| secondary | 1970-1999 | 716 | 97.5 % | 0.7 % | 99.2 % | 63.6 % |
| secondary | 2000+ | 581 | 98.1 % | 0.3 % | 99.3 % | 63.0 % |
| tertiary | pre1900 | 170 | 98.8 % | 1.2 % | 98.7 % | 97.1 % |
| tertiary | 1900-1939 | 174 | 94.3 % | 5.7 % | 90.7 % | 97.1 % |
| tertiary | 1940-1969 | 485 | 97.7 % | 1.9 % | 94.9 % | 95.3 % |
| tertiary | 1970-1999 | 486 | 99.2 % | 0.6 % | 94.0 % | 96.9 % |
| tertiary | 2000+ | 485 | 99.6 % | 0.2 % | 93.8 % | 98.1 % |

## Source level

Against the level set from archival evidence (secondary and tertiary tiers, n = 4,498): **78.7 %** agree (demo: 84.5 %).

| Evidence → Apertus | n |
|---|---:|
| secondary->primary | 815 |
| secondary->secondary | 1,795 |
| secondary->tertiary | 88 |
| tertiary->primary | 57 |
| tertiary->tertiary | 1,743 |

| Stratum | n | Agreement | Apertus said |
|---|---:|---:|---|
| secondary_history | 1,202 | 42.6 % | primary 655, secondary 512, tertiary 35 |
| secondary_obituary | 293 | 49.5 % | secondary 145, tertiary 6, primary 142 |
| secondary_press | 1,203 | 94.6 % | secondary 1138, primary 18, tertiary 47 |
| tertiary_index | 1,800 | 96.8 % | tertiary 1743, primary 57 |

Primary tier (no evidence label; mostly item-level film, photo and text records): Apertus says primary 4,161, secondary 1,278, tertiary 61.

## Distribution

Document types: photograph 1,991, TV news report 1,608, press article 1,170, finding aid / inventory 1,152, report 690, newsreel 640, register / index 511, administrative file 511, parliamentary record 438, publication / book 402, minutes / protocol 219, speech 180, correspondence 178, map / plan 104, other 74

## Manual review

Two records per tier x type x era cell (66 records from 33 cells, seed 7, src/verify_batch.py sample); each Apertus field compared with the original record fields and the first three hierarchy levels. 'unverified' = not checkable from the record and excluded from accuracy. 'major_errors' = an error that changes what a user would conclude about the record (wrong institution, invented person, wrong kind of document). Archival creators (the fonds creator) count as correct. The source level is judged on the record, not on the evidence pool it was drawn from.

Verdicts: correct 35, minor_errors 27, major_errors 4

| Field | Accuracy | Errors |
|---|---:|---:|
| creator_publisher | 95.5 % | 3 |
| dates | 95.4 % | 3 |
| document_type | 87.9 % | 8 |
| entities | 93.9 % | 4 |
| personal_data | 97.0 % | 2 |
| places | 97.0 % | 2 |
| resume | 84.6 % | 10 |
| source_level | 92.4 % | 5 |
| title | 95.5 % | 3 |

Error types: medium_wrong 3, source_level_press_convention_inconsistent 2, entities_incomplete 2, wrong_language 2, encoding_damage_introduced 2, document_type_report_for_file 2, false_date_precision 2, resume_speculative 2, holder_added_as_organization 1, wrong_abbreviation_expansion 1, wrong_institution 1, personal_data_missed 1, place_not_in_record 1, poster_typed_as_newsreel 1, document_type_inconsistent 1, holder_as_creator 1, birth_date_as_document_date 1, sensitivity_missed 1, creator_too_generic 1, canton_of_person_as_place 1, origin_read_as_location 1, historical_notice_as_primary 1, grant_request_read_as_book 1, edition_date_as_content_date 1, invented_person 1, press_as_tertiary 1, mistranslation 1, holder_detail_in_resume 1, date_range_changed 1, document_type_report_for_index 1, document_type_file_for_index 1

Notes on the major errors:

- `33010972` (primary/other/1900-1939): Résumé attributes the photo to the 'Bundesnachrichtendienst' (Germany's BND); the record is from the Swiss Nachrichtendienst des Bundes collection.
- `31216030` (primary/other/pre1900): Police description card: creator given as the Federal Archives, résumé calls the birth date the document date, police record not marked sensitive.
- `32214431` (secondary/secondary_history/2000+): Pro Helvetia grant-request placeholder read as the published book itself (author as creator).
- `4541759` (secondary/secondary_obituary/1900-1939): Invents 'Theo Bratschi (Luzern)'; the fonds is Robert Bratschi's.

## Cost

23,239,804 prompt + 7,592,045 completion tokens for classification, 5.9 s per record (12 parallel requests), 6 JSON retries.

| Stage (incl. re-runs) | Minutes |
|---|---:|
| classify | 83 |
| audit | 35 |
| level | 54 |
| repair | 0 |
| enrich | 58 |
| qc | 0 |
| export | 0 |
