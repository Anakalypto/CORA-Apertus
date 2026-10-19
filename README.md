# Hack Apertus Liebefeld — Deciphering Archives with Apertus, `team name`

Template repository for [Hack Apertus](https://hackapertus.ch/) submissions.
Every project keeps the same layout, so organizers and judges find the same
things in the same place.

There are 3 challenges to pick from:
1. Bern Economic Development Agency: Research & Expertise Navigator
2. OpenParlData: Topic classification for Swiss parliaments with Apertus
3. University of Bern: Deciphering Archives with Apertus

**CORA** turns records of the Swiss Federal Archives into AI-ready, provenance-tracked metadata with Apertus v1.5.
For each document Apertus writes a résumé of at most 3 sentences (can be turned off) and decides whether it is a primary, secondary or tertiary source and of which type.
It also completes Gallica-style metadata (creator, publisher, commissioner, dates of creation, publication, update and archiving, place in the archive),
assesses the preprocessing the record needs (transcription normalization, structure extraction, schema harmonization,
entity linking, date/geo parsing, anonymization verification) and traces the document's story on a map. Rules, a gazetteer
and Wikidata check and complete what the model says, and every field records where it came from. The demo covers 100 random documents and is browsable
in a Gallica-inspired interface, together with a published quality check of the Apertus output.

### Quick start

```bash
python -m venv .venv && .venv/Scripts/activate   # Windows; or: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                              # set LLM_API_KEY
python src/run.py serve                           # demo on http://127.0.0.1:8000 (prebuilt data in data/)
python src/run.py all                             # rebuild everything from scratch (~15 min)
```

| What | Where |
|---|---|
| Pipeline code (Python) | `src/cora/`, CLI `src/run.py`, settings `src/config.toml` |
| REST API (FastAPI, OpenAPI docs at `/docs`) | `src/cora/api.py` |
| Gallica-style front end (JS + MapLibre GL) | `src/site/` |
| AI-ready dataset (JSONL / CSV / TSV), schema, edit log | `data/dataset/` |
| Quality check of the Apertus output | `docs/quality_report.md`, `data/qc_report.json` |
| Ethical impact assessment | `docs/ethics_impact_assessment.md` |
| Demonstration notebook | `notebooks/demo.ipynb` |
| Verification against the Bern Stapfer-Enquête datafication | `docs/stapfer_verification.md`, `python src/run.py stapfer` |
| Ask the archive (cited Q&A) and read-only MCP server | `/api/ask`, `src/mcp_server.py`, `docs/api.md` |
| Trust card (Evidence / Context / Imagination) | record pages, `python src/run.py narrative` |
| Map time slider on swisstopo historical maps | *Map* page |
| Federal consultations 1960–1991 with procedure chains | *Consultations* page, `python src/run.py consultations` |
| Parliament since 1848 and every federal vote: party-cue estimate, related votes and "what if voted in year Y" (Apertus), e.g. women's suffrage 1971 vs 1959 | *Parliament & votes* page, `/api/votes` |
| Subject of secondary/tertiary records: Wikipedia article, primary dossiers of the Federal Archives, news for current issues (Apertus-selected) | record pages, `/api/records/{id}/topic` |
| 1,000-record scale run (Apertus 8B, timed) | `src/scale_run.sh`, `data/scale1000/` |

Submissions must use the v1.5 Apertus model family.
The submission must comply with the [HackApertus T&C](https://hackapertus.ch/terms-and-conditions).

## 🎯 The Challenge

University of Bern: **Deciphering Archives with Apertus** — [challenge page](https://app.notion.com/p/hackapertus/University-of-Bern-0a7b4fec112a820a9a1181bc0b5d4d52)

## 🔧 Resources & Tools

Check our resources & tools page for detailed information:
[https://hackapertus.notion.site/liebefeld-resources-tools](https://hackapertus.notion.site/liebefeld-resources-tools)

| Models           | URL                                      |
|------------------|------------------------------------------|
| Apertus v1.5 8B  | [huggingface.co/swiss-ai/Apertus-v1.5-8B](https://huggingface.co/swiss-ai/Apertus-v1.5-8B)  |
| Apertus v1.5 70B | [huggingface.co/swiss-ai/Apertus-v1.5-70B](https://huggingface.co/swiss-ai/Apertus-v1.5-70B) |

## The structure

Keep the files and directories as shown below — don't rename or move them.

| Path | What it is |
| --- | --- |
| `README.md` | The challenge description and submission requirements |
| `technical_report.md` | The deeper write-up: architecture, evaluation, limitations |
| `LICENSE` | Apache-2.0 |
| `src/` | Your code |

## Environment

- Include instructions for running the project in your technical report.
- Use the following environment variables:
```
LLM_NAME — name and version of the model
LLM_BASE_URL — endpoint base URL
LLM_API_KEY — your API key
```

## 📦 Submission Requirements & Deliverables

The submission must:
1. follow the template repo and include all prerequisite files and definitions
2. run end-to-end when judges try to run it

### Git repo (URL)
- Create your repo from this template (**Use this template**).
- Keep the layout as it is: don't rename or move its files.
- Set the repo to PUBLIC (Settings --> Collaborators --> Manage Visibility)
- Submit the URL of YOUR Git repo.

### Technical Report (pdf)
- Update [technical_report.md](technical_report.md) in this repository with all the details for your submission.
- Upload a pdf of your technical report to the root of the repo, named as `TeamName_Report.pdf`.
- Format: pdf, max. 6 pages w/o references
- Submit the pdf of the technical report.

### Demo video (URL)
- Max. 2 min demo video of your prototype
- Add the link to the **Demo** field at the top of [technical_report.md](technical_report.md)
- Submit the URL of the video.

## ⚖️ Judging Criteria

Each challenge has its own criteria, listed in its challenge description.

The main jury scores every submission on 6 dimensions (relevant for Top 6 teams):
1. **Purposeful use of AI**
2. **Technical rigour**
3. **Value, cost & scalability**
4. **Sovereign deployability**
5. **Implementation feasibility**
6. **Pitch & presentation**

Each dimension is scored from 0 to 5.

## Getting started

1. Click **Use this template** to create your own repository.

## License

All Hack Apertus projects are open-sourced. Please check our Terms & Conditions for specific licensing details (6. What you build is open source): https://hackapertus.ch/terms-and-conditions

## Support

### FAQ
💡 https://hackapertus.ch/faq

### Contact

💬 In case you have questions, join the conversation on Discord. Alternatively, send an email to “hello@hackapertus.ch”.
