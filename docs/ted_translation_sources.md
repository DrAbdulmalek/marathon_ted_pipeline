# TED translation sources and ingestion policy

This document registers source references for the Marathon TED Pipeline. A source
being registered does not mean its data has already been downloaded, checked,
or uploaded to Telegram.

## 1. TED official subtitles

- Use the public TED talk page as the canonical source URL.
- The local adapter requests https://hls.ted.com/talks/{slug}/subtitles/{lang}/full.vtt.
- Keep English and Arabic in separate fields; never substitute English text for a
  missing Arabic subtitle.
- Preserve source URL, talk slug, language codes, fetch timestamp, and content hash
  in any dataset record.
- Deduplicate by canonical talk slug + source language + target language + content
  hash before publishing.
- Publish to the target Telegram channel only when the operator has configured a
  real target and explicitly enabled publishing. Do not commit API credentials,
  session files, or private channel identifiers.

## 2. ted2srt reference implementation

- Repository: https://github.com/rnons/ted2srt
- License: BSD-3-Clause (verify the upstream LICENSE before copying any upstream
  implementation code).
- The upstream project is a Haskell backend + PureScript frontend web application;
  its README requires Nix, PostgreSQL, and Redis for a local development setup. It
  is not a drop-in Python CLI or a documented public API.
- Marathon's ted2srt_py adapter is a separate local implementation. Do not claim
  that it runs or imports rnons/ted2srt; its role is to provide a small local
  subtitle adapter for the pipeline.

## 3. MuST-Cinema paper / dataset lead

- Paper: https://arxiv.org/abs/2002.10829
- Title: MuST-Cinema: a Speech-to-Subtitles corpus (Karakanta, Negri, Turchi; 2020).
- The paper describes aligned audio, transcription, and translation data derived
  from TED subtitles and preserves subtitle-break information.
- This citation is a research lead, not proof that an English-Arabic split is
  included or downloadable from the paper URL. Before adding any data to the
  English-Arabic training set, verify the dataset's language inventory, download
  source, license/terms, and exact split. If Arabic is absent, keep this entry as
  methodology/reference only and do not fabricate Arabic pairs.

## 4. Training-data evidence gate

Every harvested pair must include source_url, source_lang, target_lang,
retrieved_at, and sha256. Separate:
- official_subtitle: an official TED subtitle pair;
- human_reviewed: a pair reviewed by a human;
- machine_generated: a machine translation, never silently promoted to gold;
- uncertain: missing, misaligned, or otherwise unverified content.

A successful HTTP response or fluent-looking text does not by itself establish
translation correctness. Preserve raw subtitle files and provenance; publish a
dataset batch only after deduplication and review.
