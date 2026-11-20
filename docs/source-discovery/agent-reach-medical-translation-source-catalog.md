# Agent-Reach-assisted medical and translation source discovery

**Review date:** 2026-10-11  
**Status:** Discovery catalog / human review required. Not an ingestion allowlist.  
**Scope:** English↔Arabic medical translation, terminology, orthopaedics, clinical references, parallel corpora, and source leads for the Telegram marathon.

## Decision

Use [Agent-Reach](https://github.com/Panniantong/Agent-Reach) as an **optional research workstation tool**, not as a runtime dependency of this pipeline.

Agent-Reach is an installer/router for upstream tools (for example, Jina Reader, Exa search, GitHub CLI, YouTube tooling and RSS parsing). It is not itself a vetted medical database, translation memory, source-license registry, or guaranteed extraction API. Its backends may need cookies, a browser session, or proxy configuration. Do not put cookies, browser profiles, API keys, or other credentials in this repository.

The current Telegram monitor in `src/channel_monitor.py` accepts configured Telegram source channels. Its visible processing paths handle PDF/EPUB documents, TED links, and short text messages. It does **not** currently ingest arbitrary websites, RSS feeds, PubMed queries, YouTube transcripts, or Agent-Reach output as structured translation assets. Therefore this catalog does not change `telegram.source_channels` and does not enable any new live ingestion.

## Candidate source register

The priorities below refer to **research value**, not permission to copy or redistribute the content. Confirm the terms for each specific document, dataset version, and third-party item before bulk download, translation, training, or redistribution.

| ID | Source | Best use | Access / discovery path | Reuse gate | Initial priority |
|---|---|---|---|---|---|
| TR-01 | [TICO-19 Translation Initiative for COVID-19](https://tico-19.github.io/) | EN↔AR parallel sentences, COVID terminology, translation-memory and MT evaluation leads | Download the published TMX, terminology files, and benchmark from the project pages | The project states its published content is CC0; retain provenance and verify each artifact/version and its metadata | P0 — first dataset to evaluate |
| TR-02 | [WHO EMRO Unified Medical Dictionary and Arabic MeSH](https://www.emro.who.int/home-page/information-resources/) | Arabic↔English medical terms; terminology validation and query expansion | Search the EMRO information resources / Unified Medical Dictionary / Arabic MeSH | Public search access is not blanket permission for bulk export; confirm dataset/API terms before copying records | P0 — terminology lead |
| MED-01 | [WHO IRIS](https://iris.who.int/) | Bilingual WHO reports, guidelines, health terminology, parallel document candidates | Search for Arabic and English editions of the same title; retain edition/language metadata | WHO says many post-2016 publications use CC BY-NC-SA 3.0 IGO, but check the notice on each publication; non-commercial and share-alike conditions may apply | P0 — document-pair discovery |
| MED-02 | [WHO EMRO e-Library / IDR](https://www.emro.who.int/e-library/front-page/index.html) | Arabic/English regional health publications, public-health terminology, Syria/EMR-relevant material | Search by subject, title, year, language, and publication type | Check the specific publication's copyright notice and any third-party content | P0 — regional relevance |
| MED-03 | [NCBI Bookshelf](https://www.ncbi.nlm.nih.gov/books/) | Full-text medical books, clinical reference documents, textbooks and glossary candidates | Search by specialty; inspect each book's copyright/permissions section before intake | Bookshelf is a host, not a single-license corpus. US government works may be public domain; other titles retain their own rights. Intake only titles with suitable rights | P0 — licensed-book intake |
| MED-04 | [PubMed](https://pubmed.ncbi.nlm.nih.gov/) and [NCBI E-utilities](https://www.ncbi.nlm.nih.gov/books/NBK25501/) | Literature discovery, abstracts/metadata, identifying open-access full text and bilingual article pairs | Search with specialty terms and language filters; use E-utilities for compliant structured retrieval | Treat metadata and abstracts separately from full text. Abstracts may be copyrighted; follow NCBI terms and request-rate guidance. Do not turn PubMed into a bulk parallel-text corpus by default | P0 — evidence discovery |
| MED-05 | [Europe PMC](https://europepmc.org/) | Biomedical literature, open-access full text, metadata and links to full-text sources | Prefer records explicitly marked open access; retain source license and PMCID/DOI | Reuse only according to each article's stated license; open access does not always mean unrestricted reuse | P1 — open-access article leads |
| MED-06 | [European Medicines Agency](https://www.ema.europa.eu/) | Medicine product information, regulatory terminology, assessment reports, multilingual regulatory documents | Search public documents and matching language versions | EMA's legal notice permits reuse of its own material with attribution in many cases, but excludes third-party content; check the document's rights notice | P1 — drug/regulatory terminology |
| MED-07 | [MedlinePlus](https://medlineplus.gov/) | Patient-friendly terminology and health-topic language; English/Spanish material is more extensive than Arabic | Use as a terminology/reading-level reference and link resolver | Only selected sections are public domain; other material is licensed. Do not bulk-ingest the entire site or assume all content is reusable | P1 — patient-facing language |
| MED-08 | [Global Index Medicus](https://www.globalindexmedicus.net/) and [WHO EMRO IMEMR](https://www.emro.who.int/e-library/databases/bibliographic-databases.html) | Regional medical literature, Arabic-language journals and local terminology | Discover citations, then follow each journal/article's own full-text and license information | Indexing/abstracting does not confer rights to copy article text | P1 — Arabic/region-specific leads |
| MED-09 | [ClinicalTrials.gov](https://clinicaltrials.gov/) | Standardized clinical terms, outcomes, eligibility criteria and study metadata | Query condition/intervention terms; use public records to find terminology | Use the site's data-use terms and avoid importing submitted documents or third-party attachments without checking rights | P1 — structured clinical vocabulary |
| MED-10 | [ICD-11 API](https://icd.who.int/icdapi) | Disease classification concepts, official identifiers, terminology lookup and multilingual concept discovery | Register for API access if needed; record concept URI, release, language, and API version | WHO states ICD-11 is CC BY-ND 3.0 IGO; translation/crosswalk activities can require separate written agreement. Treat as lookup/reference until intended reuse is cleared | P1 — terminology lookup, rights-gated |
| TR-03 | [Wikidata lexicographical data](https://www.wikidata.org/wiki/Wikidata:Lexicographical_data/en) | Multilingual word/sense leads and candidate terminology cross-checks | Query lexemes/senses and keep entity IDs and provenance | Verify the applicable Wikidata data license and individual external references; community data is not automatically medically validated | P2 — supplementary only |
| TR-04 | [OPUS](https://opus.nlpl.eu/) | Parallel corpora and translation memories for model evaluation or training | Search for medical, EU, EMEA, GNOME, and other potentially relevant corpus collections; inspect each corpus card | OPUS is an umbrella for datasets with different licenses. Do not apply one license assumption to all corpora; assess every corpus separately | P1 — corpus-by-corpus review |
| TR-05 | [GitHub](https://github.com/) | Medical terminology projects, bilingual dictionaries, OCR/evaluation sets, dataset cards, reproducible extraction scripts | Search repositories and releases through GitHub CLI or Agent-Reach's GitHub channel | Check repository license, dataset license, upstream attribution, and whether data files have separate terms; a public repository is not automatically reusable | P1 — tool/data discovery |
| TR-06 | [YouTube](https://www.youtube.com/) and relevant professional/academic channels | Orthopaedic lectures, medical terminology in context, conference talks and educational videos | Use Agent-Reach/yt-dlp only where permitted; prefer official university, society, or publisher channels | Video/transcript copyright and platform terms apply. Do not bulk download, translate, or republish without a suitable basis; save URLs/metadata first | P2 — curated leads |
| TR-07 | [RSS feeds](https://www.rssboard.org/) from selected journals, agencies and terminology projects | Incremental discovery of new papers, guidelines, releases, and glossary updates | Use feed URLs with feedparser after each publisher's feed terms are checked | RSS is a discovery mechanism, not a reuse license. Store metadata and source links by default | P1 — update monitoring |

## Agent-Reach research workflow

1. Install and test Agent-Reach in a dedicated local environment, not inside this repository. Start with its safe/dry-run mode and inspect the proposed changes before installing system-level packages.
2. Run `agent-reach doctor` and record which channels are actually working. Do not infer that every advertised backend is configured.
3. Search first for primary/authoritative sources: WHO/WHO EMRO, NCBI, Europe PMC, EMA, ClinicalTrials.gov, official specialty societies, and original dataset repositories.
4. Use social/video sources (Reddit, X, YouTube, Bilibili, etc.) to discover leads and expert explanations—not as sole evidence for clinical recommendations or as automatically reusable training data.
5. For every candidate, record the exact landing URL, title, publisher/owner, language(s), document/version date, access date, format, license/terms URL, third-party rights notes, and intended use.
6. Prefer source metadata and links over copying full pages. For each document, determine whether the intended action is (a) link/index only, (b) local research reading, (c) extraction of terminology, (d) creation of parallel sentence pairs, (e) model training, or (f) redistribution. These have different rights implications.
7. Deduplicate by canonical URL plus content hash where permitted. Preserve original text separately from normalized text; never silently replace the source wording.
8. Queue candidates for human review. A source is not approved for the translation knowledge base or model training until the license/reuse gate and medical-quality gate have both passed.

## Suggested search queries

### English↔Arabic medical terminology
- `"English Arabic" medical terminology dataset license`
- `Arabic MeSH medical terminology download`
- `"Unified Medical Dictionary" WHO EMRO Arabic English`
- `site:who.int Arabic English glossary health terminology`
- `site:ema.europa.eu Arabic English medicine terminology`

### Orthopaedics
- `orthopaedic surgery glossary English Arabic`
- `musculoskeletal terminology Arabic English guideline`
- `site:aofoundation.org orthopaedic reference licensing`
- `site:pubmed.ncbi.nlm.nih.gov orthopaedic surgery Arabic English`
- `fracture classification terminology Arabic English`

### Parallel corpora and translation memories
- `medical English Arabic TMX CC0`
- `Arabic English medical parallel corpus license`
- `site:opus.nlpl.eu medical Arabic English`
- `site:tico-19.github.io Arabic TMX terminology`
- `health translation memory Arabic English public license`

### Books and clinical guidelines
- `site:ncbi.nlm.nih.gov/books orthopaedics copyright permissions`
- `site:iris.who.int Arabic English guideline`
- `site:emro.who.int Arabic English clinical guideline`
- `site:europepmc.org/articles PMC orthopaedic open access`

## Marathon integration boundary

- **Do not** append web URLs, YouTube links, RSS feeds, or unverified Telegram channels to `telegram.source_channels`; that setting accepts Telegram entities, not arbitrary web sources.
- **Do not** change the active `config/config.yaml`, the live SQLite ingestion ledger, or the Telegram target channel as part of source discovery.
- First collect and approve source URLs/rights in this catalog or a separate reviewed source manifest. Then add only authorized Telegram channel usernames/IDs to a separately reviewed configuration change.
- For PDFs/EPUBs that pass the rights check, use the existing medical-translation intake path where appropriate; its README says it performs SHA-256 deduplication and extracts terms, sentence pairs, and rule candidates. Do not commit whole copyrighted books into the knowledge-base repository.
- Before any historical Telegram backfill, explicitly review `initial_sync`, the existing ledger, and duplicate risk. Source discovery must not trigger a live marathon run.

## Evidence and limitations

- This is a curated starting register, not an exhaustive search of every medical or translation resource.
- Searchability, public access, and a page's presence on a reputable site do not by themselves establish permission to scrape, translate, train on, or redistribute it.
- The legal notes above are high-level triage only. The license/terms attached to the specific artifact control.
- Agent-Reach itself has **not been installed or run by this documentation change**; this file records the recommended use and the first authoritative source leads. Channel health and actual retrieval must be verified in the user's chosen local environment.
