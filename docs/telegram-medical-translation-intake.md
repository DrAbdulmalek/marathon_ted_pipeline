# Telegram medical/translation source intake — orthopaedic bilingual scope

**Status: candidate registry only; no Telegram source is enabled by this document.**

## Goal
Screen the 68 user-supplied Telegram channel candidates for only:
1. English↔Arabic dictionaries, glossaries, terminology lists, and CAT-tool resources that directly help medical translation.
2. Truly bilingual English–Arabic books or documents, with priority to orthopaedic and joint surgery.
3. Orthopaedic/musculoskeletal surgery resources: trauma, arthroplasty, sports orthopaedics, spine, hand, foot/ankle, paediatric orthopaedics, implants, anatomy, rehabilitation, and closely relevant rheumatology.
4. Translation methods/tools that materially support the user's medical translation pipeline.

## Activation gate
- Entries in `config/telegram_source_candidates.json` are all `enabled: false` and `UNVERIFIED_CANDIDATE`.
- Do not add these candidates to live `telegram.source_channels`, start a Telethon client, scan message history, download files, or change live cursors until source identities/access and an explicit activation authorization are verified.
- Do not set `initial_sync: from_start`; the intended safe default remains `latest`. Existing SQLite ledger and per-channel cursors must be preserved.
- The repository is public. Never put Telegram API credentials, session files, private channel data, downloaded books, or copyrighted extracted content into Git.

## Intake classification
Each post/file is a candidate, not an accepted resource. Use title/caption/metadata only for preliminary triage; inspect actual contents before acceptance. A filename or channel description is not proof of language, content, or quality.

Required fields for each item:
- source channel identity and message ID; source URL and retrieval timestamp;
- original filename, MIME/type, file size, SHA-256 where possible;
- detected language(s), actual bilingual status, domain/topic, page count;
- content classification and reason for inclusion/exclusion;
- rights/licence evidence and permitted use; do not infer redistribution permission from public availability;
- extraction tool/version, OCR language, confidence/evidence, and validation state;
- deduplication identity and links to any related editions.

## Strict selection rules
- **Dictionary/glossary:** accept only English–Arabic or Arabic–English (or a clearly stated English–Arabic multi-language resource). Prioritize medical/orthopaedic terminology. Reject English-only/general-language dictionaries unless the item is a translation tool or method directly useful to the workflow.
- **Books:** accept as a bilingual book only if both English and Arabic are actually present in the same work in aligned or clearly corresponding content. Prioritize orthopaedic surgery and joint surgery. A monolingual orthopaedic reference may be retained only as a separately labelled *orthopaedic reference candidate* if it materially supports the user's requested specialty; never label it bilingual.
- **Specialty relevance:** orthopaedic surgery, trauma, joint replacement/arthroplasty, musculoskeletal anatomy, orthopaedic implants/instrumentation, sports orthopaedics, spine, hand, foot/ankle, paediatric orthopaedics, orthopaedic rehabilitation, and tightly related rheumatology.
- Exclude unrelated general books, unrelated medical specialties, pharmacology-only resources not relevant to orthopaedics, English-learning chatter, course advertisements, quizzes without reusable terminology/reference value, and duplicates.
- Keep the original file immutable. Store verbatim extraction separately from normalized text; never overwrite original OCR or silently normalize clinical terms.
- No item becomes trusted translation memory, glossary, training data, or publishable content until provenance, content, rights, and quality gates pass and human approval is recorded.

## Rights, privacy, and security
- Public Telegram availability is not a licence to redistribute or republish books.
- Prefer metadata/cataloguing and legally accessible open-licensed resources. If rights are unclear, quarantine; do not upload book files or substantial extracted text to public repositories, Hugging Face, CMS, or other external destinations.
- Do not ingest patient-identifiable material or private/sensitive clinical records from channels.
- Treat files, captions, links, archives, and documents as untrusted inputs; malware-scan and sandbox before opening. Never execute attachments/macros.
- Do not publish or forward source material automatically. Extraction, acceptance, training export, and publication are separate gates.

## Operational stages
1. `DISCOVERED`: user-supplied candidate only.
2. `IDENTITY_VERIFIED`: username/channel identity and access checked without historical backfill.
3. `RIGHTS_REVIEWED`: rights and permitted use recorded.
4. `NEW_MESSAGE_OBSERVED`: new message captured with source/message ID; dedupe ledger checked.
5. `QUARANTINED`: pending language/domain/rights/security review.
6. `EXTRACTED`: allowed extraction completed with original preserved and provenance.
7. `VALIDATED`: actual language pairing, specialty relevance, and OCR/translation quality checked.
8. `HUMAN_APPROVED`: eligible for a local research/translation knowledge base.
9. `EXPORT_APPROVED`: separate explicit approval for any external dataset, training, or publication.

Never skip stages. Keep forwarding, download, extraction, validation, approval, and publication counters separate.

## Known input anomalies
The user-supplied strings for EDLMedicos (`t.me/ed/medicos`), Naser's Medical Education (`t.me/NaserMedical Education`), Easy Pharmacology (`t.me/Pharma Topguide`), and طالب صيدلاني (`t.me/Pharma Yemen`) are not valid standard Telegram username URLs as written. They remain recorded exactly as supplied and must be manually resolved before activation. All remaining names/handles are also unverified until checked against Telegram.
