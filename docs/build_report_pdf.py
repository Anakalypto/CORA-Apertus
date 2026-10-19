"""Build RedPandas_Report.pdf (the submission's technical report, max. 6 pages without references).

The figures come from the measured runs in this repository:
  docs/quality_report.md            100-record demo (70B), manual review, scale run, 200 secondary/tertiary units
  docs/model_comparison.md          Apertus v1.5 70B vs 8B on every AI feature (data/model_eval/*.json)
  docs/batch10k_verification.md     10,000-record mixed batch and its manual review
  docs/stapfer_verification.md      verification against the University of Bern datafication

Run:  python docs/build_report_pdf.py      (needs reportlab; writes RedPandas_Report.pdf at the repository root)
"""
from pathlib import Path

from reportlab.graphics.charts.barcharts import HorizontalBarChart
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "RedPandas_Report.pdf"
DEMO_VIDEO = "link to be added"          # put the video URL here before the final build
REPO = "https://github.com/Anakalypto/CORA-Apertus"

# Fonts with the glyphs the text needs (→, ≥, ≤, κ, é, ü); Arial on Windows, DejaVu elsewhere.
FONT_DIRS = [Path("C:/Windows/Fonts"), Path("/usr/share/fonts/truetype/dejavu"), Path("/Library/Fonts")]
for reg, bold, ital, fam in (("arial.ttf", "arialbd.ttf", "ariali.ttf", "Body"), ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans-Oblique.ttf", "Body")):
    d = next((d for d in FONT_DIRS if (d / reg).exists()), None)
    if d:
        pdfmetrics.registerFont(TTFont(fam, str(d / reg)))
        pdfmetrics.registerFont(TTFont(fam + "-B", str(d / bold)))
        pdfmetrics.registerFont(TTFont(fam + "-I", str(d / ital)))
        pdfmetrics.registerFontFamily(fam, normal=fam, bold=fam + "-B", italic=fam + "-I", boldItalic=fam + "-B")
        break

RED, INK, GREY, PAPER, LINE = colors.HexColor("#B4161B"), colors.HexColor("#1D1D1D"), colors.HexColor("#5C5C5C"), colors.HexColor("#F5F2EC"), colors.HexColor("#D8D2C8")
S = {
    "title": ParagraphStyle("title", fontName="Body-B", fontSize=19, leading=23, textColor=INK, spaceAfter=3),
    "sub": ParagraphStyle("sub", fontName="Body", fontSize=10.5, leading=14, textColor=GREY, spaceAfter=2),
    "h1": ParagraphStyle("h1", fontName="Body-B", fontSize=12.5, leading=16, textColor=RED, spaceBefore=9, spaceAfter=3),
    "h2": ParagraphStyle("h2", fontName="Body-B", fontSize=10.2, leading=13, textColor=INK, spaceBefore=6, spaceAfter=2),
    "p": ParagraphStyle("p", fontName="Body", fontSize=9.2, leading=12.2, textColor=INK, spaceAfter=4, alignment=TA_LEFT),
    "li": ParagraphStyle("li", fontName="Body", fontSize=9.2, leading=12.0, textColor=INK, leftIndent=11, bulletIndent=2, spaceAfter=1.5),
    "cell": ParagraphStyle("cell", fontName="Body", fontSize=8.1, leading=10.2, textColor=INK),
    "cellb": ParagraphStyle("cellb", fontName="Body-B", fontSize=8.1, leading=10.2, textColor=INK),
    "cap": ParagraphStyle("cap", fontName="Body-I", fontSize=7.8, leading=10, textColor=GREY, spaceBefore=2, spaceAfter=5),
    "ref": ParagraphStyle("ref", fontName="Body", fontSize=8.4, leading=11, textColor=INK, leftIndent=12, firstLineIndent=-12, spaceAfter=2),
}

story = []
P = lambda t, s="p": story.append(Paragraph(t, S[s]))
H1 = lambda t: P(t, "h1")
H2 = lambda t: P(t, "h2")


def bullets(items):
    for t in items:
        story.append(Paragraph(t, S["li"], bulletText="•"))


def table(rows, widths, caption=None, head=True, align_right=()):
    data = [[Paragraph(str(c), S["cellb" if (head and i == 0) else "cell"]) for c in r] for i, r in enumerate(rows)]
    t = Table(data, colWidths=[w * cm for w in widths], repeatRows=1 if head else 0)
    st = [("GRID", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("TOPPADDING", (0, 0), (-1, -1), 2.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
          ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
    if head:
        st.append(("BACKGROUND", (0, 0), (-1, 0), PAPER))
    t.setStyle(TableStyle(st))
    block = [t] + ([Paragraph(caption, S["cap"])] if caption else [Spacer(1, 5)])
    story.append(KeepTogether(block))


def level_chart():
    """Source-level agreement with the archival evidence label, 10,000-record batch, by stratum."""
    d = Drawing(17 * cm, 3.6 * cm)
    c = HorizontalBarChart()
    c.x, c.y, c.width, c.height = 5.4 * cm, 0.55 * cm, 10.6 * cm, 2.8 * cm
    vals = [96.8, 94.6, 49.5, 42.6]
    c.data = [vals]
    c.categoryAxis.categoryNames = ["Registers / indexes (tertiary)", "Press clippings (secondary)", "Obituaries (secondary)", "Histories, studies (secondary)"]
    c.categoryAxis.labels.fontName, c.categoryAxis.labels.fontSize = "Body", 7.6
    c.categoryAxis.labels.dx = -4
    c.valueAxis.valueMin, c.valueAxis.valueMax, c.valueAxis.valueStep = 0, 100, 25
    c.valueAxis.labels.fontName, c.valueAxis.labels.fontSize = "Body", 7
    c.valueAxis.labelTextFormat = "%d %%"
    c.bars[0].fillColor = RED
    c.bars[0].strokeColor = None
    c.barWidth = 9
    c.barLabelFormat = "%.1f %%"
    c.barLabels.fontName, c.barLabels.fontSize, c.barLabels.dx = "Body-B", 7.4, 16
    c.categoryAxis.strokeColor = c.valueAxis.strokeColor = LINE
    d.add(c)
    d.add(String(5.4 * cm, 3.42 * cm, "Apertus = evidence label (n = 4,498 secondary and tertiary records)", fontName="Body", fontSize=7.4, fillColor=GREY))
    return d


def on_page(canv, doc):
    canv.saveState()
    canv.setFont("Body", 7.5)
    canv.setFillColor(GREY)
    canv.drawString(2 * cm, 1.2 * cm, "CORA · Red Pandas · Hack Apertus Liebefeld 2026")
    canv.drawRightString(A4[0] - 2 * cm, 1.2 * cm, str(doc.page))
    canv.setStrokeColor(RED)
    canv.setLineWidth(1.4)
    canv.line(2 * cm, A4[1] - 1.45 * cm, A4[0] - 2 * cm, A4[1] - 1.45 * cm)
    canv.restoreState()


# ------------------------------------------------------------------------------------------------ content
P("CORA: deciphering the Swiss Federal Archives with Apertus", "title")
P("Technical report · <b>Red Pandas</b>: Giovanni Yazbeck, Alfredo Pio Yazbeck · University of Bern challenge "
  "<i>Deciphering Archives with Apertus</i>, Hack Apertus Liebefeld", "sub")
P(f'Code and data: <font color="#B4161B">{REPO}</font> · Demo video: {DEMO_VIDEO} · Licence: Apache-2.0', "sub")

H1("1. Summary")
P("The Archive database of the Swiss Federal Archives describes 263,123 item-level documents in dense German, French "
  "and Italian cataloguing prose. It is rich but not AI-ready: encoding damage, labelled sub-fields packed into free text, "
  "dotted dates, author fields that mix roles, and no source typing or geography. <b>CORA</b> turns each record into "
  "AI-ready, provenance-tracked metadata with <b>Apertus v1.5</b>: a résumé of at most three sentences, document type and medium, "
  "a primary/secondary/tertiary source level with its rationale, Gallica/Dublin-Core-style metadata, persons, organisations and "
  "places, the preprocessing the record needs, and the document's story on a map. Rules, a gazetteer and Wikidata check and complete "
  "the model, and every field records where it came from. The output is browsable in a Gallica-inspired site with cited Q&amp;A.")
table([
    ["Measurement", "Result"],
    ["100-record demo (70B): records without structural or critical error", "<b>99 %</b> (target ≥ 80 %); 1 % structural errors (target &lt; 5 %)"],
    ["Manual review, 25 demo records", "<b>88 % usable</b> (32 % fully correct, 56 % minor errors), 12 % with a major error"],
    ["10,000-record mixed batch (8B + 70B per feature)", "<b>98.6 %</b> pass every automatic check; 0.9 % structural errors"],
    ["Manual review, 66 batch records (all tiers, types, eras)", "<b>62 / 66 without a major error</b>; 35 fully correct, 27 minor"],
    ["Verification against the Bern datafication (Stapfer-Enquête 1799)", "<b>90–100 %</b> agreement on 9 of 12 hand-coded fields"],
    ["Scale run, Apertus 8B", "<b>1,000 records in 48 min</b> (target 2 h); 0.4 % structural errors after repair"],
    ["Apertus 8B vs 70B", "8B as good for parsing and Q&amp;A at 3× the speed; 70B needed for the source level"],
], [8.6, 8.4], "Table 1. Headline results. Sources: docs/quality_report.md, docs/batch10k_verification.md, docs/stapfer_verification.md, docs/model_comparison.md.")
P("<b>Our current open problem is the source level.</b> The referral of records to primary, secondary and tertiary sources, "
  "both in the reference labels we built from the archive and in how Apertus is asked to decide, has to be reconsidered (§5).")

H1("2. System")
P("The pipeline reads only the original archive-database fields (via LINDAS SPARQL, or the opendata.swiss bulk dump) and runs in "
  "independent stages, each reading the previous stage's file, so any stage can be rerun alone.")
table([
    ["Stage", "What happens", "Model / tool"],
    ["sample, fetch", "Stratified random sample (seed 42) of rico:Record units; original fields only", "LINDAS SPARQL"],
    ["classify", "Pass 1: résumé, type, medium, metadata, entities, story events (strict JSON schema, controlled vocabularies)", "Apertus 8B"],
    ["audit", "Pass 2: eleven yes/no checks, each with quoted evidence; preprocessing flags derived by rule, OR-ed with deterministic detectors", "Apertus 8B + rules"],
    ["level", "Pass 3: primary / secondary / tertiary with rationale; press convention configurable", "Apertus 70B"],
    ["repair, enrich", "ISO dates, control characters; gazetteer, Wikidata links with life-date check, story trail to Bern", "rules, Nominatim, Wikidata"],
    ["qc, export", "Automatic checks, edit log, JSONL/CSV/TSV + JSON schema, SQLite search index", "rules"],
], [2.3, 11.2, 3.5], "Table 2. Pipeline. Each field carries its provenance: record, derived, apertus, gazetteer or wikidata; conflicts are settled by fixed, logged rules "
   "(e.g. the accession year always comes from the accession number, coordinates always from the gazetteer).")
P("<b>Use of Apertus.</b> Apertus v1.5 runs on CSCS through the Keera gateway (OpenAI-compatible; <i>LLM_NAME</i>, <i>LLM_BASE_URL</i>, "
  "<i>LLM_API_KEY</i>), temperature 0.1, JSON mode, up to 3 retries with the parse error fed back. Each feature runs on the model that won "
  "the head-to-head comparison (§3.3), configurable per feature in <i>src/config.toml</i>. Prompts carry strict grounding rules "
  "(never invent names, dates or places) and archival definitions. Asking the model directly for the six preprocessing flags returned “yes” for "
  "nearly every record; replacing it with evidence-quoting checks (pass 2) made the flags informative.")
P("<b>Applications on the dataset.</b> <i>Ask the archive</i> answers only from retrieved records (BM25 / SQLite index) and cites every "
  "sentence; citations to records that were not retrieved are dropped. A read-only <b>MCP server</b> exposes search, record and Q&amp;A. "
  "Record pages show a <b>trust card</b> separating evidence (original fields) from context (Wikidata, Wikipedia, HLS). Further views: "
  "federal consultations 1960–1991 linked to Swissvotes, Parliament since 1848, a backtested referendum model, and <b>Swiss Tales</b>: "
  "a timeline of Swiss history with the archive units of each year, and <i>Oral tradition</i>, a cited, explicitly imagined year in the life "
  "of an ancestor from the 1799 Stapfer survey, censuses and the Federal Gazette, where Apertus also checks whether the place of origin existed "
  "and belonged to the Confederation in that year.")

H1("3. Evaluation")
H2("3.1 Quality of the classification")
P("<b>Demo, 100 records (70B).</b> All 100 outputs were valid JSON with no retry; 99 % have no structural or critical error; résumés are "
  "within three sentences in 100 %; 92 % of the 377 named entities occur literally in the record and all 30 others are translations "
  "(Nationalrat → National Council), not inventions; creation dates fall inside the record's own range in 100 %. Apertus is weak on the "
  "accession date (24 % right), so a rule replaced it.")
P("<b>Manual review.</b> On 25 demo records, 88 % are usable. All three major errors come from archival conventions the model does not know: "
  "speaker ≠ author, depositing agency ≠ creator, <i>Postulat</i> ≠ motion. On the 10,000-record batch we reviewed two records per "
  "tier × type × era cell (66 records):")
table([
    ["Field", "Title", "Creator / publisher", "Dates", "Entities", "Places", "Personal data", "Document type", "Résumé", "Source level"],
    ["Accuracy", "95.5 %", "95.5 %", "95.4 %", "93.9 %", "97.0 %", "97.0 %", "87.9 %", "84.6 %", "92.4 %"],
], [1.6, 1.3, 1.9, 1.3, 1.5, 1.3, 1.6, 1.7, 1.5, 1.7], "Table 3. Field accuracy in the manual review of the 10,000-record batch (66 records). "
   "The four major errors: a misread institution (German BND for the Swiss intelligence service), an invented first name, a grant request read as the book it funds, "
   "and a police card with the archive as creator.")

H2("3.2 Verification against the Bern case study")
P("Apertus 70B read only the transcribed answers of random Stapfer-Enquête response sheets (1799) and extracted the 12 fields that the "
  "University of Bern team coded by hand. With the Bern codebook in the prompt and names compared across historical spellings "
  "(“Tachsen” = Dachsen), agreement is 98 % on the teacher's age, 100 % on the teacher's name, 95 % on school type, marital status and place, "
  "94 % on winter pupils, 91 % on years of service and 90 % on confession. The naive prompt reached 0 % on school type and 26 % on confession: "
  "Bern's coded categories are conventions, and giving the model the codebook is what closes the gap. Remaining errors are mostly historical "
  "spellings and roles given instead of names.")

H2("3.3 Apertus 8B vs 70B")
P("Every AI feature was run on both models with identical inputs, prompts, post-processing and scoring. Where a reference exists we score "
  "against it; otherwise we only compare the two models.")
table([
    ["Feature (reference)", "70B", "8B", "Choice"],
    ["Parsing, 200 new records (automatic checks)", "98.5 % pass", "<b>100 %</b> pass", "8B"],
    ["&nbsp;&nbsp;– creator = record's author field", "86.6 %", "<b>95.1 %</b>", ""],
    ["Stapfer extraction, 100 sheets (Bern hand coding)", "<b>84.5 %</b>", "80.8 %; 8 % unusable", "70B"],
    ["Source level, 29 adjudicated records", "<b>62 %</b>", "55 %", "70B"],
    ["&nbsp;&nbsp;– secondary sources recognised (n = 120)", "<b>70 %</b>", "28 %", ""],
    ["&nbsp;&nbsp;– tertiary sources recognised (n = 110)", "<b>93.6 %</b>", "77.3 %", ""],
    ["Ask the archive, 24 questions: right record cited / unanswerable refused", "100 % / 8 of 8", "100 % / 8 of 8 (1 flag missing)", "8B"],
    ["“See more” explanations, 30 records: unsourced sentences", "<b>2.5 %</b>", "29.3 %", "70B"],
    ["Consultation tagging, 100 procedures: off-list topics", "<b>3</b>", "18", "70B"],
    ["What-if party positions, 40 real votes (naive baseline 71.7 %)", "65.0 %", "61.4 %", "neither beats the baseline"],
    ["Mean seconds per call (parsing / audit / level / Q&amp;A)", "16.5 / 6.9 / 3.3 / 2.4", "<b>5.7 / 2.4 / 0.9 / 0.8</b>", "8B ≈ 3× faster"],
], [8.0, 2.6, 3.6, 2.8], "Table 4. Apertus v1.5 70B vs 8B (docs/model_comparison.md, data/model_eval/). Several references are small (29 levels, 24 questions): "
   "differences of a few points are within noise.")
P("<b>Reading.</b> 8B is enough for the passes a reader meets on every record (parsing, audit, Q&amp;A) and is about three times faster, "
  "which matters for an archive that wants to host the model on a single GPU. 70B is still worth it where judgement or long, messy input "
  "dominate: the source level (8B misses most secondary sources), long transcriptions (8B copies them into its evidence field and breaks "
  "the JSON), and explanations that must stay sourced. Rules close several 8B gaps cheaply: mechanical detectors, a topic synonym map, and "
  "mapping “yes / free vote” to codes. Neither model beats a naive baseline on predicting party positions, so the what-if view stays "
  "labelled as imagination, not as a forecast.")

H2("3.4 Scale and cost")
table([
    ["Run", "Records", "Wall-clock", "Errors"],
    ["Demo, Apertus 70B", "100", "≈ 9 min (325k prompt + 124k completion tokens)", "1 % structural"],
    ["Scale run, Apertus 8B, 12 parallel requests", "1,000", "<b>48 min</b>: model 15 min, throttled geocoding 32 min", "6.0 % → 0.4 % after rule repair"],
    ["Mixed batch, 8B (classify, audit) + 70B (level)", "10,000", "classify 83, level 54, audit 35, enrich 58 min (23.2M + 7.6M tokens)", "0.9 % structural, 0.6 % critical"],
], [5.6, 1.6, 6.6, 3.2], "Table 5. Throughput. Two-thirds of the 1,000-record run is the public geocoder's 1 request/s limit; a self-hosted Nominatim removes it.")
P("The 10,000-record batch was drawn over three source tiers (primary by form; secondary and tertiary from archival evidence: title "
  "conventions and form), three form types and five eras, none already in the demo. 98.6 % pass every automatic check, creation dates fall "
  "inside the record's range in 99.3 %, and 98.7 % of named entities are found in the record.")

H1("4. Deployment and sovereignty")
bullets([
    "<b>On-premise and sovereign cloud.</b> The only runtime dependency is an OpenAI-compatible Apertus endpoint: the CSCS one, or Apertus "
    "weights served with vLLM on the archive's own hardware (8B fits on one GPU). Python (pandas, FastAPI) and a static front end with vendored MapLibre.",
    "<b>Air-gapped.</b> Serve Apertus locally, self-host Nominatim or ship the enrichment cache, serve swisstopo tiles locally and load records "
    "from the opendata.swiss bulk dump instead of LINDAS. Once built, the demo data runs offline except for map tiles.",
    "<b>Transparency.</b> Every value shows its provenance; every Apertus answer that a reader sees is cited or marked as imagined; raw outputs "
    "of both models are kept for audit.",
])

story.append(KeepTogether([  # heading, introduction and figure stay on one page
    Paragraph("5. Current problem: the source level must be reconsidered", S["h1"]),
    Paragraph("Primary, secondary and tertiary seem simple, but in an administrative archive they are not, and this is where our results are least solid. "
              "Two things need to be reconsidered: <b>how the datasets refer records to a level</b> (our reference labels) and <b>how Apertus is asked to decide</b>.", S["p"]),
    level_chart(),
    Paragraph("Figure 1. Source level in the 10,000-record batch: agreement of Apertus (70B) with the level implied by archival evidence. "
              "Overall 78.7 %, but very uneven by stratum.", S["cap"])]))
bullets([
    "<b>The reference labels are unreliable.</b> We derived secondary and tertiary labels from title conventions and form (“Register”, "
    "“Verzeichnis”, “Studie”, clipping dossiers). On 200 such units Apertus agreed only 39.5 % of the time, yet when we adjudicated 30 "
    "disagreements by hand, <b>Apertus was right in 19, the label in 4</b>, and 6 were defensible both ways. A “Verzeichnis” in a federal "
    "archive is mostly a primary list of firms, material or persons, not a finding aid; a “Studie” is often a contemporary planning study.",
    "<b>The same holds at scale.</b> In the batch, registers and press clippings agree 95–97 %, but “history” and “obituary” titles only "
    "43–50 %: those patterns also catch department dossiers about congresses, correspondence about a Festschrift and parliamentary eulogies, "
    "which Apertus correctly calls primary. Judged record by record in the manual review, the level is right in 92 %.",
    "<b>Conventions are inconsistent.</b> Press is secondary as a second-hand account, but historians use it as a primary source for public "
    "discourse. Our press convention was applied to broadcast news only part of the time (1,133 of 2,248 TV news and newsreel records in the batch).",
    "<b>Model gaps remain.</b> 70B recognises 70 % of secondary sources (8B: 28 %), misses some true indexes, and once called a published 1881 "
    "treatise primary because it was “written at the time”.",
])
P("<b>What we will change.</b> (1) Replace keyword labels with a gold set adjudicated by archivists, stratified like the batch. "
  "(2) Give the prompt explicit archival definitions: <i>tertiary</i> = a finding aid, index or register that points to other records; "
  "a list of persons, goods or places is primary; <i>secondary</i> = an account made after the events by someone not involved. "
  "(3) Separate the level from the genre: a press/broadcast flag, with one documented convention applied by rule to all news, "
  "and the level shown as relative to the research question. (4) Report the level with its rationale and confidence and let users correct it "
  "through the edit log. (5) Fine-tune 8B on the adjudicated set if 70B remains necessary.")

H1("6. Limitations and ethics")
bullets([
    "<b>Content accuracy.</b> The weakest fields are the résumé (84.6 % in the batch review) and document type on non-standard items (posters, "
    "typed communiqués). Apertus sometimes adds first names from world knowledge; a Wikidata life-date check catches wrong links.",
    "<b>Blind spots covered by rules.</b> Apertus does not notice encoding damage (recall 0 of 38) and rarely fills the accession date; "
    "8B writes more non-ISO dates and sometimes control characters in place of accents. Deterministic detectors and repairs handle these.",
    "<b>Personal data.</b> The anonymisation flag has about 40 % precision (it confuses sensitive topics with sensitive persons): a triage aid, "
    "not a decision. Nothing personal is added beyond Wikidata links to public figures; Oral tradition keeps family stories in the browser "
    "and only uses archive units older than 1950. See docs/ethics_impact_assessment.md.",
    "<b>Small references.</b> Manual reviews were done by our team on 25 + 66 records; archivists of the Federal Archives should repeat them on a larger sample.",
])

H1("7. Reproducibility")
P("<font face='Courier' size='8'>pip install -r requirements.txt; cp .env.example .env (set LLM_API_KEY); python src/run.py all; "
  "python src/run.py serve</font>. Each stage can be rerun alone (<i>python src/run.py qc</i>); the 10,000-record batch is "
  "<i>src/batch_run.sh</i>, the model comparison <i>src/eval_features.py</i>, the Bern verification <i>python src/run.py stapfer</i>. "
  "Sample seeds are fixed (42, 1000, 7); model temperature is 0.1, so reruns vary slightly. Python 3.12, Apertus v1.5 on vLLM, LINDAS data of 2026-01-08. "
  "A demonstration notebook is in notebooks/demo.ipynb.")

story.append(PageBreak())
H1("References")
for r in [
    "Swiss Federal Archives. <i>Archive database of the Swiss Federal Archives</i>. opendata.swiss, via LINDAS (dataset ais), 2026. Open use.",
    "Swiss Federal Archives. <i>The Stapfer-Enquête: schooling in Switzerland 1799</i> (SQL dump stapferappdb_final). opendata.swiss; University of Bern datafication, stapferenquete.ch.",
    "Swiss Federal Archives. <i>Federal consultations 1960–1991</i>. opendata.swiss. Open use.",
    "Swiss AI Initiative. <i>Apertus v1.5</i> model family (8B, 70B). huggingface.co/swiss-ai.",
    "Année politique suisse, University of Bern. <i>Swissvotes dataset</i>. CC BY 4.0.",
    "Swiss Parliament. parlament.ch OData service. Federal Statistical Office, PX-Web and population census 1850–2000.",
    "Historical Dictionary of Switzerland (HLS/DHS/DSS). hls-dhs-dss.ch.",
    "Wikidata (CC0); Wikipedia (CC BY-SA); Wikimedia Commons and the ETH Library image archive (E-Pics).",
    "OpenStreetMap contributors, Nominatim (ODbL); swisstopo geodata and historical maps; MapLibre GL JS.",
    "International Council on Archives. <i>Records in Contexts – Ontology (RiC-O)</i>.",
    "Bibliothèque nationale de France. <i>Gallica</i> (interface inspiration).",
    "Repository documents: docs/quality_report.md, docs/model_comparison.md, docs/batch10k_verification.md, docs/stapfer_verification.md, docs/ethics_impact_assessment.md.",
]:
    P(r, "ref")

doc = SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm, bottomMargin=1.8 * cm,
                        title="CORA — Technical report (Red Pandas)", author="Giovanni Yazbeck, Alfredo Pio Yazbeck",
                        subject="Hack Apertus Liebefeld — Deciphering Archives with Apertus")
doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
print(f"wrote {OUT}")
