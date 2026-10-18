# Quality check of the Apertus output — 100 records of the Swiss Federal Archives

**Scope.** 100 item-level records drawn from the *Archive database of the Swiss Federal Archives* (opendata.swiss), classified by **Apertus v1.5 70B** (Keera Gateway → CSCS). Only fields of the original archive database were given to the model; additions made by LINDAS (ISIL holder, Wikimedia Commons links, access-rule vocabulary, dates on accession events) were excluded.

**Method.** Three layers:

1. **Automatic checks on all 100 records** (`src/cora/qc.py`): structure and schema, ISO dates, résumé length, grounding of every named entity in the source metadata, date consistency, agreement with explicit record fields, gazetteer comparison.
2. **Cross-model consistency**: the same prompt run with Apertus v1.5 8B.
3. **Manual review of 25 records** (every 4th record, all strata), field by field against the original metadata and its archive hierarchy (`data/manual_review.json`).

All figures are reproducible with `python src/run.py qc` and are shown live on the *Quality check* page of the demo.

**Versions.** Sections 2–7 describe the first prompt version (v1). Section 9 re-measures everything after the fixes recommended in §8 (prompt v2): **0 major errors instead of 3, résumés correct 68 % → 92 %, creator/publisher 80 % → 100 %**. The demo and the dataset use v2. (The 70B-vs-8B comparison in §2 was not rerun and still refers to v1.)

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

## 9. v1 → v2: applying recommendations 1–4

Prompt versions: classify v1 → **v2**, audit v2 → **v3** (`PROMPT_VERSION` in `src/cora/export.py`). The v1 output is kept as `data/classified_v1.jsonl` (with `qc_report_v1.json`, `enriched_v1.jsonl`, `dataset_v1/`). The v2 output is the one the dataset and the demo now use. Same 100 records, same model (Apertus v1.5 70B), same temperature.

**What changed**

1. **Role labels parsed by rule** (`parse_roles`, `parse_speakers` in `src/cora/classify.py`). Apertus no longer sees `"AutorIn: Strub, Edi (AUT)\nProduktionsgesellschaft: SF"`. It gets `[{"name": "Edi Strub", "role": "author"}, {"name": "SF", "role": "production company"}]`. The parliamentary field `"Autor: Sprecher/Sprecherinnen: Graf, Maya;"`, which misleadingly starts with *Autor*, becomes `"speakers_in_debate": ["Maya Graf"]`. The rule detectors and the QC still read the original record.
2. **Archival conventions in the pass-1 prompt**:
   - *Sprecher* ≠ author; the author of a Motion/Postulat/Interpellation is the member named in the title; the Council is the creator of the recording.
   - The instruments are distinct terms.
   - A parliamentary date is the debate date.
   - The depositing agency or fonds is not the creator when it postdates the record.
   - TSR abbreviations: OPP., INT., DUPLEX.
   - Unnamed groups are not persons.
3. **No name completion**: names are copied exactly as written, never completed from world knowledge.
4. **Person-centred sensitivity** in the audit: "is an *identifiable person* concerned by …". A debate *about* asylum or health is explicitly a "no".

A first v2 run went backwards on one point. Once "Produktion" became a neutral `role: production`, Apertus put the *publisher* (SRG SSR) as creator in 14 of 44 records (creator agreement 30/44). One more sentence fixed it ("when the record has an author field, the creator comes from it … the publisher field gives the publisher, never the creator"). The figures below are from the second run. **Removing a label also removes the hint that the label carried. A structured input needs an explicit mapping rule.**

**Manual review: the same 25 records** (`data/manual_review_v2.json`)

| Verdict | v1 | v2 |
|---|---:|---:|
| Correct | 8 | **16** |
| Minor errors only | 14 | 9 |
| Major errors | 3 | **0** |

| Field | v1 | v2 |
|---|---:|---:|
| Document type | 100 % | 100 % |
| Source level | 100 % | 100 % |
| Dates | 96 % | **100 %** |
| Places | 91 % | **96 %** |
| Title (normalized / translated) | 88 % | **92 %** |
| Personal-data assessment | 88 % | **96 %** |
| Creator / publisher | 80 % | **100 %** |
| Entities | 76 % ¹ | **80 %** |
| **Résumé** | 68 % | **92 %** |

¹ Correction to the v1 review: the first names "Fredy" Bickel and "Hans-Peter" Friedländer (21681248) *are* in the record's `thema` field (`Personen: …`). The v1 verdict "knowledge beyond the source" was a reviewer error. Corrected, v1 entities would be 80 %, so on entities v2 shows **no measurable gain**. The published v1 file is left unchanged and the correction is recorded in `manual_review_v2.json`.

**All three major errors are fixed**:
- The Youth Session petition is no longer attributed to the speaker Maya Graf.
- The 2010 Intelligence Service is no longer the creator of a 1939–45 slide (creator now null, no sensitivity flag, no "likely").
- *Postulat* is kept as "postulate", the date is the debate date, and asylum policy is no longer flagged as sensitive.

Also fixed: the creator labels ("Produktion: TSI"), OPP. and Duplex, a place role (Bern), the speculative and over-claiming résumés, and the transcript/sound inconsistency.

**What did not improve**

| Remaining error (v2) | n | Comment |
|---|---:|---|
| Unnamed group as person | 4 | "Offiziere" ×2, "Mann im Bademantel", "Batallion 24". The prompt rule had **no effect**, so it needs a rule-based filter (no capitalised proper name → not a person). |
| Title not normalized | 2 | Capitalised TSR title and the typo "Franktionsausflug" are still kept, although title_en is right. |
| Sensitive category missed | 1 | Swissair trial: Apertus lists Vreni Spoerry as "defendant" in `persons` yet answers "no identifiable person concerned". |
| Résumé factual / unsupported | 2 | "22-minute" clip (1:47 clip on a 22:28 tape); "official transcript" for a video series. |
| Entity missed | 1 | Fulvio Pelli (gives a statement) dropped. |
| Wrong place role | 1 | Nicosia "depicted" instead of "mentioned". |

**Automatic checks, all 100 records**

| Metric | v1 | v2 |
|---|---:|---:|
| Processed correctly / structural errors | 99 % / 1 % | 99 % / 1 % |
| Creator or publisher still carrying a field label | 20 | **0** |
| Creator agrees with record "author" (label-insensitive check) | 40 / 44 | **44 / 44** |
| Named entities literally in the source | 92.0 % (377) | **96.1 %** (357) |
| Speculative résumés ("likely" …) | 1 | **0** |
| Records flagged for anonymization verification | 12 % | **3 %** |
| Sensitive category (identifiable person) | 11 % | 3 % |
| Private individual named | 1 % | **0 %** ⚠️ |
| Prompt tokens, pass 1 | 188,430 | 245,751 (+30 %, longer system prompt) |
| Mean latency per record, pass 1 | 22.7 s | 24.4 s |

**Anonymization: precision up, recall not.** Of the 12 v1 flags, 9 were topic-level false positives (asylum, health insurance, victim-assistance debates, the Intelligence Service, a cancer-research news item). v2 keeps 3 flags: the anti-racism-law conviction (29668237), the newborn kidnapping (21811418) and Indira Gandhi's detention (a public figure, defensible). The 1852 police record of a private individual (30314032, "Zürcher, Joseph — 18 Jahre alt, Beruf: Korber") **is now missed**: the private-individual check dropped from 1 % to 0 %. The Swissair trial is still missed. On the four real cases found by hand, recall is v1 3/4 → v2 2/4. The person-centred wording made Apertus more conservative across the board, not just on topics.

**Next steps**
- Filter unnamed groups out of `persons` by rule.
- Add a rule check: a person whose own role in `persons` names a proceeding ("defendant", "accused", "victim") should get sensitive_categories = true.
- Restore the private-individual question as a separate, unchanged check. Its v1 wording was not the source of the false positives.
- Repeat the review on a fresh sample (recommendation 6). These 25 records also guided the prompt changes, so the v2 numbers are optimistic.

## 10. Verification against the Bern case study (Stapfer-Enquête)

Apertus 70B read only the transcribed answers of 40 random Stapfer response sheets (1799) and extracted the 12 fields that the University of Bern team coded by hand. Given the Bern codebook, it reaches **90–98 % agreement on 8 of the 12 fields**: teacher's age 98 %, school type 95 %, marital status 95 %, winter pupils 94 %, teacher's name 93 %, years of service 91 %, confession 90 %. It identifies the right school place in 95 % of sheets, but only 58 % in modern spelling. Without the codebook, school type was 0 % and confession 26 %. Error classes: historical spelling kept, coded categories not stated in the text, unit conversion, role given instead of a name, and values Bern left empty. Details: [stapfer_verification.md](stapfer_verification.md).

## 11. Wikidata life-date check

Person links are now also checked against life dates. Birth and death years (P569/P570) are compared with the record's own date range: a link is **rejected** if the person was born after the document, and **flagged** if they died more than 50 years before it. On the 100 records, 102 links pass, 71 persons stay unlinked, and **2 links are rejected**. Both are errors found in review:

| Person in the record | Wrong Wikidata match | Reason |
|---|---|---|
| Bickel (1951 newsreel, Spain v Switzerland) | Fredy Bickel, Swiss journalist, Q1453340 | born 1965, after the document |
| Joseph Zürcher (1853 police record, private individual) | association football player, Q26972533 | born 1925, after the document |

The second case matters for privacy as well as accuracy: a private 19th-century individual had been linked to a 20th-century person. Rejected links are kept out of the dataset and recorded in `edit_log.jsonl` (actor `rule`).

## 12. Trust card and organization linking

Each record page now opens on a **trust card** with three bands:
- **Evidence:** the untouched archive fields, numbered E1…, with the portal link.
- **Context:** Wikidata, Wikipedia and HLS links for the linked persons and organizations, plus gazetteer places, numbered C…, each with its tier.
- **Imagination:** a 3–5 sentence Apertus narrative in which every sentence must footnote E or C items.

On the 100 records, the cards hold 108 narrative sentences, 36 HLS links and 131 Wikipedia links (`data/dataset/trust_cards.jsonl`). Apertus footnoted every sentence (0 "inferred"). That is a claim by the model, so an automatic support check measures how many of a sentence's words occur in the items it cites. **27 of 108 sentences are weakly supported** (under 20 %); these are mostly interpretive phrases ("politically significant"), and partly English sentences citing German evidence, where word overlap undercounts.

The card exposed bad organization links. "Bundesrat" was linked to the German Bundesrat, "Grüne Partei" to a generic concept, and the acronym "SRG" to an X-ray observatory. Organization linking now prefers Swiss items, rejects generic "type of …" items and items about another state, and accepts acronyms of four letters or fewer only when the item is described as Swiss. 36 of 81 organizations are linked. One known weakness remains: "Nationalrat" and "Bundesrat" resolve to the *position* items ("member of …") rather than the chambers.
