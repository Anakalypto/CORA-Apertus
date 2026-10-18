# Quality check of the Apertus output — 100 records of the Swiss Federal Archives

**Scope.** 100 item-level records drawn from the *Archive database of the Swiss Federal Archives* (opendata.swiss), classified by **Apertus v1.5 70B** (Keera Gateway → CSCS). Only fields of the original archive database were given to the model; additions made by LINDAS (ISIL holder, Wikimedia Commons links, access-rule vocabulary, dates on accession events) were excluded.

**Method.** Three layers:

1. **Automatic checks on all 100 records** (`src/cora/qc.py`): structure and schema, ISO dates, résumé length, grounding of every named entity in the source metadata, date consistency, agreement with explicit record fields, gazetteer comparison.
2. **Cross-model consistency**: the same prompt run with Apertus v1.5 8B.
3. **Manual review of 25 records** (every 4th record, all strata), field by field against the original metadata and its archive hierarchy (`data/manual_review.json`).

All figures are reproducible with `python src/run.py qc` and are shown live on the *Quality check* page of the demo.

## 1. Sample

| Stratum (by original `form` field) | Population | Drawn |
|---|---:|---:|
| Audiovisual (video, film, sound) | 215,956 | 40 |
| Still images (photographs, slides, plates …) | 6,949 | 30 |
| Other (parliamentary records, files …) | 40,218 | 30 |
| **All item-level records (`rico:Record`)** | **263,123** | **100** |

The draw is a stratified random sample with seed 42 over a sorted population, so it's reproducible. A uniform draw would have been about 82% TV news clips. Inside each stratum the fonds come out as they naturally occur: 32 Schweizer Fernsehen, 23 Landesverteidigung (WWI glass plates), 20 Nationalrat, 7 Filmwochenschau and others.

## 2. Headline results

| Metric | Result | Target / comment |
|---|---:|---|
| Records processed (valid JSON, schema respected) | **100 / 100** | 0 retries needed |
| Processed correctly (no structural or critical error) | **99 %** | challenge target ≥ 80 % |
| Structural errors | **1 %** | target < 5 % (one non-ISO date) |
| Résumés within 3 sentences | **100 %** | |
| Named entities literally present in the source | **92 %** | 377 entities |
| … counting translations (Nationalrat → National Council) | 100 % | all 30 misses were translations, not inventions |
| Creation date inside the record's own date range | **100 %** | |
| Creator agrees with the record's "author" field | 40 / 44 | the 4 misses keep the field label, e.g. "Produktion: TSI" |
| Publisher agrees with the record's "publisher" field | 28 / 28 | |
| Archival (accession) date correct | **24 %** | ⚠️ replaced by a rule (see §4) |
| Apertus' own coordinates within 25 km of the gazetteer | 94 % (median 1.8 km) | 51 coordinates given; one is 149 km off (Erstfeld) |
| Places located by the gazetteer | 83 % | country-level names deliberately not mapped |
| Agreement 70B vs 8B — document type | 80 % (κ = 0.74) | |
| Agreement 70B vs 8B — medium | 78 % (κ = 0.67) | |
| Agreement 70B vs 8B — source level | 100 % | all 100 records are primary sources |

**The automatic checks say the output is well-formed and grounded. They can't tell whether it is *right*.** The manual review measures that.

## 3. Manual review (25 records)

| Verdict | Records |
|---|---:|
| Correct | 8 |
| Minor errors only | 14 |
| Major errors | 3 |

That gives **88 % usable** and 12 % with a major error.

| Field | Correct |
|---|---:|
| Document type | 100 % |
| Source level | 100 % |
| Dates | 96 % |
| Places | 91 % |
| Title (normalized / translated) | 88 % |
| Personal-data assessment | 88 % |
| Creator / publisher | 80 % |
| Entities | 76 % |
| **Résumé** | **68 %** |

**Error taxonomy, most frequent first**

| Error | n | Example |
|---|---:|---|
| Unnamed group extracted as a person | 4 | "Offiziere", "Mann im Bademantel" listed as persons |
| Field label not stripped | 3 | creator = "Produktion: TSI" |
| Title not normalized | 2 | typo "Franktionsausflug", capitals "LOECHE / OPP.LIGNE…" kept |
| Wrong place role | 2 | Bern as "created" instead of "depicted" |
| Speculation in the résumé | 2 | "It likely depicts…", "contains the motion text and the debate" |
| Sensitive-data false positive | 2 | asylum *policy* debate flagged as sensitive personal data |
| Date semantics | 2 | debate date presented as submission date |
| Wrong author attribution (major) | 1 | Youth Session petition attributed to the speaker Maya Graf |
| Anachronistic creator (major) | 1 | Intelligence Service (founded 2010) as creator of a 1939–45 slide |
| Wrong term in translation (major) | 1 | *Postulat* translated as "motion" |
| Knowledge beyond the source | 1 | first names "Fredy" Bickel, "Hans-Peter" Friedländer added from world knowledge |
| Abbreviation not understood | 1 | "OPP." (opposition) missed, so the résumé misses the point of the report |
| Sensitive category missed | 1 | person on trial (Swissair case) not flagged |

**Reading.** Apertus is reliable on the *categorical* questions: type, medium, source level and dates. It's good at extracting entities and places from the dense German/French cataloguing prose. It's weakest where it has to **interpret archival conventions**: the roles in parliamentary records (*Sprecher* ≠ author), depositing agency ≠ creator, *Postulat* ≠ motion, and abbreviations of the TSR card catalogue. Résumés are fluent but sometimes over-claim what the record contains.

## 4. What the quality check changed in the pipeline

The QC ran in a loop with development. Three findings led to design changes.

**4.1 Preprocessing flags: from "always yes" to evidence-based.** Pass 1 asked Apertus directly whether each of the six preprocessing steps was needed. The answers carried no information:

| Preprocessing | Pass 1 (direct question) | Pass 2 (evidence-based + rules) |
|---|---:|---:|
| Transcription normalization | 99 % | 42 % |
| Structure extraction | 100 % | 43 % |
| Schema harmonization | 100 % | 69 % |
| Linked data & entity linking | 100 % | 100 % |
| Date & geolocation parsing | 100 % | 99 % |
| Anonymization verification | **0 %** | 12 % |

Pass 2 asks eleven concrete yes/no checks, each with a quoted piece of evidence, and derives the flags by fixed rules. Linking and date parsing really are needed almost everywhere: every record names entities and uses dotted dates.

**4.2 Apertus can't see mechanical problems → rule detectors.** Apertus' pass-2 answers compared with deterministic detectors:

| Check | Rule positive | Apertus positive | Apertus precision | Apertus recall |
|---|---:|---:|---:|---:|
| Labelled sub-fields ("Inhaltsangabe: … Sequenzbeschrieb: …") | 41 | 41 | 0.95 | 0.95 |
| Non-ISO dates ("1985.10.22") | 96 | 95 | 0.99 | 0.98 |
| Encoding damage ("T�l�vision … Gen�ve") | 38 | **0** | – | **0.00** |
| Packed role fields ("AutorIn: X: AUT\nProduktion: SF") | 39 | 14 | 0.36 | 0.13 |
| Capitalised / abbreviated title | 3 | 9 | 0.22 | 0.67 |

Apertus is excellent on structural patterns but blind to character-level damage: it silently reads through `�`. The final flag is therefore **Apertus OR rule**, and the evidence names which of the two fired.

**4.3 Accession date: rule over model.** Apertus filled `date_archived` correctly in only 24 % of records. It mostly left it empty even though the prompt explains that accession numbers are `YEAR/SERIAL`. The year is now derived from the accession number by rule; legacy holdings `1000/…` get no year. The override is recorded in the edit log.

**4.4 Coordinates: gazetteer over model.** Map points come from OpenStreetMap Nominatim. Apertus' coordinates are kept only for comparison: they are good (median error 1.8 km) but not safe, with Erstfeld 149 km off. One gazetteer error was found by hand ("Simplon region" was resolved inside the canton of Bern). Country-level names are not mapped, because a centroid of "USA" is not a place where a document was made.

## 5. Personal data and anonymization

65 % of records name natural persons, mostly politicians, journalists and presenters acting in public. 12 records are flagged for anonymization verification. About 7 of them are **topic-level false positives**: a parliamentary debate *about* asylum, health insurance or victim assistance, or the Intelligence Service as depositing agency. The real cases include:
- the kidnapping of a newborn, with a named person giving a statement (21811418)
- a record describing a private individual (30314032)
- a conviction under the anti-racism law (29668237)

One real case was missed in the manual review (the Swissair trial). **The flag is a triage aid for archivists, not an anonymization decision.**

## 6. Entity linking

107 of 178 persons and 68 of 100 organizations were linked to Wikidata. A link is accepted only on an exact label match, and for persons only when the Wikidata description denotes a person. Spot-check: the Swiss parliamentarians, Indira Gandhi, Franco, Karamanlis, Ulbricht and de Gaulle are all correct. One **cascade error** shows up: Apertus added the first name "Fredy" to the 1951 footballer *Bickel*, and the exact match then linked him to a present-day Swiss journalist of that name. Linking should also check life dates against the document date.

## 7. Cost and speed

| | Apertus 70B pass 1 | Apertus 70B pass 2 | Apertus 8B (comparison) |
|---|---:|---:|---:|
| Prompt tokens | 188,430 | 136,330 | 188,430 |
| Completion tokens | 87,235 | 37,003 | 83,171 |
| Mean latency per record | 22.7 s | 12.8 s | ≈ 6 s |

With 6 parallel requests, 100 records take about 6.5 min (pass 1) plus 2.5 min (pass 2). The 8B model is 4× faster and agrees with 70B on 80 % of document types. It's the candidate for an inexpensive on-premise run (≤ 8 GB VRAM when quantized), at a measurable cost in consistency.

## 8. Recommendations

1. **Strip field labels and normalize names by rule** before Apertus sees the record ("Produktion:", "AutorIn: … : AUT"). That removes the most frequent minor error.
2. **Give Apertus the cataloguing conventions**: *Sprecher* ≠ author, depositing agency ≠ creator, *Postulat/Motion/Interpellation*, TSR abbreviations (OPP., INT.). These caused all three major errors.
3. **Forbid world-knowledge completion of names** (or mark it as `inferred`) to prevent the Bickel-type cascade.
4. **Anonymization: distinguish topic from person.** Ask "is an *identifiable person* concerned by …" instead of "does the record concern …".
5. **Keep rules for mechanical facts** (encoding, dates, accession year) and keep Apertus for interpretation. That split is where each is strong.
6. **Scale-up check**: repeat the manual review on a fresh sample after applying 1–4. The measurement code is in place.
