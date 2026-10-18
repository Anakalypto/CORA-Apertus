# Ethical impact assessment

## Data and licence
- **Source**: *Archive database of the Swiss Federal Archives*, published on opendata.swiss under "open use" terms. The current version is served by LINDAS. We use its public SPARQL endpoint for 100 records instead of crawling the online search portal, as the challenge rules require. The 1.4 GB bulk dump was not used, because its download rate (~50 KB/s) made it impractical.
- **Only original fields** of the archive database are used: title, dates, reference codes, hierarchy, the detail data elements and accession numbers. Additions made by LINDAS are excluded.
- **Original values are preserved** in every output record (`source.original`). Every change is written to `data/dataset/edit_log.jsonl` with the actor (rule / apertus / gazetteer) and the reason.
- Third-party data: OpenStreetMap Nominatim (ODbL, attribution in the UI; 1 request/s, cached) and Wikidata (CC0). Institution favicons are trademarks of their owners and are used only to identify institutions on the map.

## Privacy
- 65 % of the sampled records name natural persons. Almost all are public figures acting publicly (parliamentarians, Federal Councillors, journalists, presenters). All sampled records are freely accessible in the archive; no records under a protection period were processed.
- Records that concern identifiable persons in sensitive contexts (criminal proceedings, health, asylum, intelligence) are flagged for **anonymization verification** with quoted evidence. The flag is a triage aid: the QC shows about 40 % precision (topic-level false positives) and at least one miss. A human archivist must decide, under the Federal Act on Archiving (BGA) and the Data Protection Act (DSG).
- The pipeline **does not anonymize or redact** anything automatically, and it does not create new personal data. Wikidata links are added only for exact matches with a person-type description. The QC documents a mis-link caused by a name the model completed from world knowledge.
- The API key is read from `.env`, which is git-ignored.

## Generated content
- Everything Apertus writes is labelled as generated: résumés, Q&A answers, trust-card narratives and consultation tags. The trust card keeps the generated **Imagination** band visually separate from **Evidence** (the record) and **Context** (reference works).
- Q&A and narratives must cite record IDs or evidence items sentence by sentence. Uncited or weakly supported sentences are marked, not hidden.
- Wikidata person links are checked against life dates. A link to someone born after the document is rejected; this caught the link of a private 1853 individual to a 20th-century footballer. Organization links reject other-state homonyms and ambiguous acronyms.
- Nothing about living private persons is inferred or linked: links require an exact match to a public-figure description and pass the life-date check, and the anonymization flag is person-centred.

## Additional sources
- Stapfer-Enquête (opendata.swiss, open use). Its subjects are 1799 teachers and pupils, all long dead. Only the transcribed answers are sent to the model.
- Federal consultations 1960–1991 (opendata.swiss, open use) and Swissvotes (Année politique suisse, CC BY 4.0, attribution on the page).
- swisstopo "Journey through time" tiles (© swisstopo, attribution on the map).

## Counterfactuals and parliament data
- The 1959/1971 estimate is a model output with a stated error (±9.7 points), not a historical fact. Apertus' counterfactual party positions are labelled as imagination and checked against the record. The page notes that both votes were cast by men only.
- Council members are public office holders; their names and terms come from parlament.ch open data. Wikipedia links require a Swiss-politician description and a plausible birth year.

## Bias
- **Collection bias.** 82 % of the item-level records are TV news clips (Schweizer Fernsehen and TSR). A uniform sample would reproduce that, so we stratify by medium and document the strata. Fonds coverage follows what was itemized, not what is historically important.
- **Language bias.** Cataloguing is mostly German, with French and Italian minorities. Apertus is multilingual, but the outputs are written in English (configurable). Translations can lose meaning: *Postulat* became "motion".
- **Model knowledge bias.** Apertus sometimes completes names or facts from world knowledge, which favours well-known people. We measure this through the entity-grounding check and flag it as an error class.
- **Source-level classification.** All 100 sampled records are primary sources. The classifier was not tested on secondary or tertiary material in this sample.

## Transparency and sovereignty
- Apertus v1.5 is an open model with open training data, run on Swiss infrastructure (CSCS through the Keera Gateway). It can also run on-premise: the code only needs an OpenAI-compatible endpoint.
- Every field carries its provenance (record / derived / apertus / gazetteer / wikidata). Prompts are versioned in `src/cora/classify.py`, and the QC with its manual review is published together with the dataset.
- The front end needs no external scripts at runtime (Leaflet is vendored). Map tiles come from OpenStreetMap, or from swisstopo in Switzerland.

## Apertus Charter alignment
The design follows the Charter's principles: the model's assertions are kept separate from the archival record, uncertainty and errors are measured and published, and decisions about personal data stay with human archivists.
