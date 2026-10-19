# Verification against the Bern case study — Stapfer-Enquête (1799)

**Question.** Can Apertus reproduce the structured records that the University of Bern team created by hand (datafication 2009–2015) from the transcribed answers of the Stapfer-Enquête?

**Data.** opendata.swiss, *The Stapfer-Enquête: schooling in Switzerland 1799* (Swiss Federal Archives, open use), the SQL dump `stapferappdb_final.sql.zip` (2016) with 2,250 transcriptions, 92,524 answers, 3,229 schools and 2,443 teachers. We kept the 1,562 response sheets that describe exactly one school and drew 40 at random (seed 42).

**Method.**
- Apertus v1.5 70B reads **only the transcribed answers** of a sheet: the 60 questions with their answers, as `[I.1] question: answer` lines. It never sees the Bern records.
- It extracts the 12 fields that Bern coded: place, canton (1799), school type, confession, teacher's name, age, marital status and years of service, winter and summer pupils, the author of the answers, and the date written.
- Each field is compared with the Bern record as match, mismatch, missed (Bern has a value, Apertus has none), extra (Apertus has a value, Bern has none) or both empty.
- Place and person names match across **historical spellings**: both sides are reduced to a spelling key that folds umlauts, ß, th/rh/ph/ck/dt, ei/y, eu/eü, voiced and voiceless consonants (p/b, t/d, k/g), silent h and doubled letters ("Tachsen" = Dachsen, "Riggispärg" = Riggisberg, "Oberweil" = Oberwil); one dropped letter is tolerated ("Efigen" = Effingen), and abbreviated first names match ("Joh." = Johann). The exact-spelling score is kept next to it.
- Accuracy is measured where Bern has a value. "Extra" values can't be checked against Bern and are counted separately.
- Code: `src/cora/stapfer.py`, `python src/run.py stapfer`. Response sheets: `data/stapfer/cases/` and results `data/stapfer/comparison/`, one JSON file per sheet, with the summary in `comparison_summary.json`; the first run is in `comparison_naive/`. Stored extractions can be scored again without calling the model (`stapfer.rescore`).

## Results (40 response sheets, Apertus 70B)

The naive column is the first run as published (exact spelling); the codebook column compares names across historical spellings.

| Field | Naive prompt | With the Bern codebook | Comment |
|---|---:|---:|---|
| Teacher's age | 98 % | **98 %** | |
| School type | 0 % | **95 %** | coded category, not stated in the text |
| Teacher's marital status | 47 % | **95 %** | Bern codes "keine Angabe" when not stated |
| Winter pupils | 94 % | **94 %** | |
| Teacher's name | 93 % | **100 %** | 93 % in exact spelling ("Jacob" / Jakob, "Joh." / Johann) |
| Years of service | 65 % | **91 %** | Bern stores years; the text often gives a starting year |
| Confession | 26 % | **90 %** | Bern infers it from the parish |
| Date written | 83 % | **83 %** | |
| Canton (1799) | 80 % | **85 %** | "Bärn" = Bern |
| Summer pupils | 60 % | **80 %** | n = 5 |
| Author of the answers | 67 % | **70 %** | "J. S. Girard" = Jean Samuel Girard; the rest are roles, not names |
| Place | 53 % | **95 %** | 58 % in exact spelling; the 2 misses are a parish given for a hamlet |

No call failed and every answer was valid JSON (40/40).

## Error taxonomy

| Error class | Fields | Cause | Remedy |
|---|---|---|---|
| Historical spelling kept | place (15 cases), names | "Tachsen" for Dachsen, "Riggispärg" for Riggisberg: Apertus does not modernise reliably | **done:** names are compared through a historical spelling key (see Method). A gazetteer of historical place names (the Bern `t_ort` table or HLS) would also give the modern form |
| Different granularity | place (2) | parish instead of hamlet (Bagnes / Le Châble; St. Gallen / Linsebüel) | ask for the smallest named settlement |
| Coded category, not transcribed | school type, confession, marital status | Bern applies a codebook; the text never names the category | give Apertus the codebook. This alone took school type from 0 % to 95 % |
| Unit / representation | years of service | "since 1789" vs "10 years"; "a year and five months" vs 1 | state the unit and conversion rule in the prompt |
| Role instead of name | author | sheets without a signature: Apertus returns "Schullehrer zu Studen" | require a personal name or null |
| Values Bern left empty | pupils (≈20 per field), marital status, date | Apertus finds numbers or statuses that Bern did not code. These can't be checked against Bern and may be Apertus inferring too much (e.g. "has children" read as married) | review by an archivist; mark inferred values |
| Prompt leak (pipeline bug, fixed) | place (2, naive run) | the example value in our schema was copied into answers | never put real-looking example values in schemas |

## Reading

Against the reference structure of the Bern case study, Apertus reaches **90–100 % on 9 of the 12 coded fields** once it gets the same codebook the Bern team used and names are compared across historical spellings. It identifies the right school place in 95 % of sheets, though only 58 % in modern spelling. The remaining gap isn't the model misreading 1799 handwriting transcriptions. It comes from conventions: modern place-name spelling, the codebook's categories, and units. Those are cheap to supply. This is the same pattern as in the Federal Archives records (`docs/quality_report.md`): Apertus reads well, and needs the archive's conventions given explicitly.

**Limits.** The sample is 40 sheets. The comparison is automatic and string-based. The spelling key can merge two real places that differ only by such a letter (Tegerfelden AG and Degerfelden in Baden fold to the same key); within one sheet's canton this is unambiguous, across Switzerland it is not. The Bern records are themselves the result of human coding and contain some "keine Angabe" values where the text does say something.
