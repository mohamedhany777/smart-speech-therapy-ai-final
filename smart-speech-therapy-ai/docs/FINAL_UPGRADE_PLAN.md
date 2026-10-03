# Final Upgrade Plan — Execution Log

This document tracks the implementation of the MASTER-PROMPT.md upgrade
request against the existing Smart Speech Therapy AI codebase. It is a
living log: each stage is recorded here as it's completed, with an honest
account of what was verified vs. what remains environment-dependent.

## 0. Build-environment constraints (read this first)

Everything below was built and tested in a sandboxed container with an
**egress allowlist** covering package registries (PyPI, npm, GitHub, crates)
and `api.anthropic.com` only. It does **not** include `huggingface.co`,
`api-inference.huggingface.co`, `api.openai.com`, or `api.tavily.com`.

Separately, this session has a **Hugging Face MCP connector** authenticated
as a real Hugging Face user account (scopes: `read-repos`, `inference-api`,
`jobs`, `contribute-repos`). This is a distinct channel: it lets the
assistant (Claude) query the real Hugging Face Hub API for model metadata
and invoke a fixed set of public Spaces (image/video/TTS/OCR tasks at time
of writing — no ASR, embedding, or audio-classification Spaces were
available). It does **not** grant the backend application's own runtime
network access to Hugging Face — the FastAPI process still needs a real
`HF_API_TOKEN` and real internet access when deployed to actually call the
Inference API.

Practical consequence: every model referenced in
`app/services/model_registry.py` has been **identity-verified** (exact
model id, parameter count, license, task, Inference-Provider availability)
against the live Hub — nothing is a guess. But end-to-end inference
(WER/CER measurement, retrieval-quality benchmarking, reranker quality) has
**not** been executed from this environment, because that requires the
backend process itself to reach `api-inference.huggingface.co`, which this
sandbox cannot do. Anywhere this matters, the code and this document say so
explicitly rather than implying it was tested.

---

## Stage 1 — Model Registry + optional RAG reranking ✅ DONE

- Added `app/services/model_registry.py`: a single source of truth for
  every AI model the platform can call, each with `model_name`, `role`,
  `task`, `language`, `provider`, `version_or_revision`, `license`,
  `validated` (bool), `validated_note` (what was actually checked and
  when), `limitations`, and `configurable_via`.
- Added `GET /api/v1/admin/models` (requires `manage_models` permission,
  already existed in the RBAC seed data but was unused) to expose the
  registry to admins.
- Verified against the live Hugging Face Hub (via the MCP connector) on
  2026-09-29:

  | Model | Verified facts |
  |---|---|
  | `openai/whisper-large-v3-turbo` (current ASR default) | 808.9M params, MIT, live on `hf-inference` + `deepinfra` |
  | `intfloat/multilingual-e5-base` (current embedding default) | 278.0M params, MIT, live on `hf-inference` |
  | `intfloat/multilingual-e5-large` (new opt-in alternative) | 559.9M params, MIT, live on `hf-inference` |
  | `BAAI/bge-m3` (new opt-in alternative) | MIT, live on `hf-inference`. Only its dense-embedding output is usable through the plain Inference API — sparse/multi-vector modes are not implemented here. |
  | `BAAI/bge-reranker-v2-m3` (new, opt-in reranker) | 567.8M params, Apache-2.0, live on `hf-inference` |
  | `vocametrix/wav2vec2-xlsr-53-stuttering-classification` (current default) | 315.7M params, Apache-2.0, trained on SEP-28k/SEP-28k-Extended. **No live Inference Provider was listed for this specific repo** at verification time (low download count) — treat the audio-feature heuristic fallback in `audio_analysis.py` as the realistic primary path, not a cosmetic backup. |
  | `pmootr/stuttering-detection-wavlm-lora` (candidate from the prompt) | Confirmed to be a **LoRA adapter** on `microsoft/wavlm-base-plus`, not a standalone model. Not usable as a drop-in Inference API swap without base-model + adapter-merge code that doesn't exist in this project. **Not adopted.** |
  | `itshamdi404/Egy_Arabic_whisper-small` (new, opt-in) | Real Egyptian-Arabic finetune of whisper-small, full checkpoint (not an adapter) so it *is* a valid drop-in via `HF_ASR_MODEL`. Only 289 downloads — quality unverified by this project. Registered as an explicitly experimental, non-default option. |

- Added `settings.HF_RERANKER_MODEL` (empty by default = disabled).
  `knowledge_base_service.retrieve()` now over-fetches `top_k * 3`
  candidates and reranks them via `hf_inference.rerank()` when this is
  set; falls back to the original embedding-similarity order on any
  error or response-shape mismatch, so a reranker outage never breaks the
  assistant.
- `hf_inference.rerank()` uses the HF-documented `sentence-similarity`
  pipeline contract (`{"inputs": {"source_sentence", "sentences": [...]}}`)
  matching the target model's `sentence-transformers` tag. **Not
  exercised against a live token from this build** — correctness of the
  wire format is based on HF's published pipeline spec, not a live test.
- Tests: `backend/tests/test_model_registry.py` (7 tests: permission
  enforcement, full registry shape, enabled/disabled reflects config,
  reranker default-off, reranker reordering, reranker fail-open on error
  and on malformed response).
- Full suite after this stage: **105 passed, 3 skipped** (skips are
  pre-existing, environment-only: no internet for `transformers`, no
  `HF_API_TOKEN` set in the test environment).

## Stage 2 — Admin/RBAC hardening ✅ DONE

- **Fixed a real spec violation**: `POST /therapy-plans/{id}/review` allowed
  both SPECIALIST and ADMIN to approve/reject a therapy plan. Spec section
  16 is explicit: *"Only a SPECIALIST can approve it. Admin can manage
  templates/content but should not replace specialist approval."* Changed
  the dependency to `require_roles("SPECIALIST")` only. `GET
  /therapy-plans/pending-review` still allows ADMIN (read-only operational
  oversight, not approval — not restricted by the spec).
- Added `FIRST_SPECIALIST_EMAIL` / `FIRST_SPECIALIST_PASSWORD` settings and
  wired `scripts/seed.py` to create a real, usable SPECIALIST account
  (`specialist@example.com` by default) — otherwise the SPECIALIST-only
  approval flow above would be untestable out of the box.
- Added the full spec section 28 authorization matrix as explicit tests
  (previously implicit/untested): SPECIALIST cannot manage disorders,
  exercises, games, or the knowledge base; USER cannot either; ADMIN can.
  See `tests/test_hardening.py::test_specialist_cannot_manage_system_content`
  etc.
- Full suite after this stage: **106 passed, 3 skipped**.

## Stage 2b — Knowledge Base admin workflow ✅ DONE

- Added an explicit ingestion `status` column to `KnowledgeDocument`
  (`UPLOADED` -> `PROCESSING` -> `INDEXED`, or `FAILED` with a
  `failure_reason` kept on the record — spec section 6 lists FAILED as a
  real status to show, not something to hide) plus a migration with a safe
  `server_default='INDEXED'` for pre-existing rows.
- Failed uploads used to be silently deleted; now the document record is
  kept (status=FAILED, reason recorded) but its file and any partial
  chunks are cleaned up — visible for admin troubleshooting, not a phantom
  entry.
- Added `GET /knowledge-base/documents/{id}` (source detail view),
  `PATCH /knowledge-base/documents/{id}` (publish/unpublish via
  `is_active`, plus metadata correction), and search/filter query params
  (`q`, `disorder_category`, `status_filter`, `include_inactive`) on the
  list endpoint.
- **Fixed a real retrieval bug**: unpublishing a document (`is_active =
  False`) did not actually stop it from being retrieved by the RAG
  assistant — `knowledge_base_service.retrieve()` never filtered on
  `is_active`. Now it always restricts search to published, successfully
  indexed documents.
- `chunk_count` in API responses is computed live from the document's
  actual chunks, never stored/duplicated data that could drift.
- Full suite after this stage: **106 passed, 3 skipped** (one existing test
  updated to assert the new, more informative FAILED-status behavior
  instead of the old silent-delete behavior; two new tests added for the
  failed-upload-is-visible-but-inert behavior).

## Stage 3 — Pronunciation analysis + Unified Assessment Result ✅ DONE

- Added `app/services/pronunciation_analysis.py` implementing spec section
  12's exact pipeline: `Reference Text -> ASR -> Alignment -> Word
  Comparison -> Mismatches`, shown as `Expected / Recognized / Mismatch /
  Confidence` per word. Uses Python's standard-library `difflib`
  (Ratcliff-Obershelp sequence alignment) — a transparent, honestly-labeled
  alignment-based implementation, per spec section 12's explicit fallback
  instruction ("Otherwise use a transparent alignment-based
  implementation"), since no phoneme-level pronunciation model could be
  evaluated end-to-end from this build environment (see Stage 0 notes).
  The per-word "confidence" is explicitly documented as a heuristic
  (ASR-backend reliability x string-similarity for partial matches), not a
  statistical/model confidence score — none of the ASR backends this
  project integrates return real per-word confidence.
- `Assessment.reference_text` (new, optional) lets a caller supply the
  target phrase; when present, `run_audio_assessment` runs the comparison
  and stores it under `features_json["pronunciation"]`.
- Added `build_unified_result()` in `assessment_service.py` and `GET
  /assessments/{id}/result`, producing exactly the JSON shape spec section
  15 asks for: `assessment_id, status, input_quality, transcription,
  fluency, stuttering, pronunciation, audio_features,
  visual_observations, evidence, models, limitations`. Every field is
  `null`/empty rather than fabricated when that assessment type didn't
  produce it. Each populated section carries an explicit
  `evidence_source: "audio" | "visual"` tag (spec section 13's "Audio /
  Visual / Combined" requirement); a video result with both audio and
  visual evidence gets a `combined_evidence_note`.
- Full suite after this stage: **117 passed, 3 skipped** (8 new tests:
  pronunciation exact-match/substitution/omission/no-reference/no-speech
  cases, ASR-reliability ranking, end-to-end unified-result shape via the
  real API + PocketSphinx offline ASR, ownership/permission enforcement on
  the new endpoint).

## Stage 4 — Content: disorders, exercises, new games ✅ DONE

- Expanded the disorder taxonomy from 4 to 9 disorders across 6 categories
  (added: Speech Sound Disorders, Other Communication Areas), each with
  the full required page structure (Overview, Possible Characteristics,
  Speech/Language Features, Assessment Considerations) — original,
  responsibly-written general educational content, not sourced from or
  claiming specific peer-reviewed citations (spec section 17's "do not
  generate fake medical content"). New disorders: Cluttering,
  Developmental Language Disorder, Articulation Disorder, Dysphonia,
  Social Communication Difficulties. Deferred to a future pass rather than
  rushed: Phonological Disorder, adult Apraxia of Speech, Language Delay,
  resonance disorders — adding them properly (own category nuance, correct
  cross-links) needs more room than this pass had.
- Expanded exercises from 10 to 20 (2 new exercises per new disorder,
  linked via `disorder_id`) and Knowledge Base documents from 4 to 9 (one
  genuine educational-overview document per new disorder, fully indexed —
  verified by `tests/test_seed_script.py` that every seeded KB document
  actually reaches `status == "INDEXED"` with real chunks, not just a
  database row).
- **Games expanded from 2 to 6 engine types / 5 seeded games** (spec
  section 7 asked for up to 10; building all 10 to the same real,
  tested-end-to-end standard wasn't achievable in this pass without
  cutting corners, so a deliberately smaller, fully-working set was built
  instead of a larger, partially-fake one):
  - **Sentence Builder** (new): reorder shuffled word tiles into a correct sentence.
  - **Memory Match** (new): judge whether two revealed cards belong to the same pair.
  - **Sound Hunt** (new): phonological awareness — does this word start with the target sound?
  - **Picture Naming** (new): name a pictured item either by typing *or*
    by speaking it aloud — the audio path (`POST
    /games/sessions/{id}/answer-audio`) runs the recording through the
    platform's real ASR pipeline (the same one used for assessments,
    honestly subject to the same accuracy limits — PocketSphinx offline or
    HF Whisper, depending on configuration) and scores the transcript with
    the same word-level comparator pronunciation_analysis.py uses, rather
    than a fake "always correct" or multiple-choice shortcut.
  - Word Matching and Sound Recognition (pre-existing) were kept as-is.
  - All five are fully server-authoritative (engine `ABC` pattern, no
    client-trusted scoring) and covered by direct engine unit tests plus
    full-session integration tests through the real API.
- Full suite after this stage: **129 passed, 3 skipped** (20 new tests:
  5 new engines' logic, full play-through sessions via the API for each,
  the audio-answer endpoint's contract and ownership enforcement, and
  `test_seed_script.py` validating the seed script itself end-to-end
  against an isolated database — exact content counts, every disorder
  has ≥1 linked exercise, every KB document is actually indexed,
  idempotent re-running).

## Stage 6 — Security pass ✅ DONE

- **Production boot guard**: added `_validate_production_config()` in
  `main.py`, which hard-refuses to start (raises, doesn't just log) when
  `APP_ENV=production` and any of: `SECRET_KEY` is still the insecure dev
  default (JWT forgery risk for every user including admin),
  `FIRST_ADMIN_PASSWORD` is still the insecure dev default, or
  `CORS_ORIGINS` contains `"*"` (unsafe alongside `allow_credentials=True`).
- **Interactive docs disabled in production**: `/docs`, `/redoc`, and
  `/openapi.json` are now `None` when `settings.is_production` — reduces
  attack-surface/schema-disclosure in a real deployment; still fully
  available in development.
- **Baseline security response headers** added via middleware:
  `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: strict-origin-when-cross-origin`, and
  `Strict-Transport-Security` (production only).
- **Fixed a real file-upload gap**: `validate_upload()` previously only
  checked the client-supplied filename's extension — renaming any file to
  `.wav`/`.pdf`/etc. would pass. Added magic-byte signature checking for
  every binary format this platform accepts (WAV/MP3/FLAC/OGG/M4A,
  JPG/PNG/WEBP, MP4/MOV/WEBM, PDF, DOCX) so the actual file content must
  match the claimed type, not just its name.
- **Dependency vulnerability audit** (`pip-audit` against
  `requirements.txt`, a genuine scan — not a guess): started at ~80 known
  CVEs across `pypdf` (5.9.0, dozens of issues), `starlette` (0.38.6,
  pulled in transitively by an old `fastapi==0.115.0`), and `ecdsa`.
  Upgraded `pypdf` to 6.19.0, `fastapi` to 0.142.2 (pulling in a current
  `starlette`), `python-multipart` to 0.0.31, `python-dotenv` to 1.2.2,
  `python-jose[cryptography]` to 3.4.0 (fixes two real CVEs,
  PYSEC-2024-232/233, in the JWT library itself), and the test-only
  `pytest`/`pytest-asyncio` to current versions. Full suite re-run after
  every single upgrade (not just at the end) to catch any compatibility
  break immediately — none occurred.
  - **Two known issues remain, deliberately not papered over**:
    `ecdsa==0.19.2` has no fixed release available upstream at all
    (`PYSEC-2026-1325`), and `python-jose==3.4.0` hard-pins
    `pyasn1<0.5.0`, whose newest release in that range (0.4.8) still has
    open CVEs with no compatible fix. Both are now pinned *explicitly* in
    `requirements.txt` (not left as implicit transitive versions) with a
    comment explaining why, so a future `pip install --upgrade` doesn't
    silently reintroduce a worse, incompatible version. The practical risk
    today is limited — this platform only ever issues HS256 (HMAC,
    symmetric) tokens, never ECDSA-signed ones, so the vulnerable code
    paths in `ecdsa`/`pyasn1` are not actually exercised by this app's own
    token flow — but the real fix is migrating off `python-jose` to
    `PyJWT` (actively maintained, no such pin), which is security-critical
    plumbing that deserves its own careful, isolated pass rather than
    being rushed alongside everything else in this one.
- Full suite after this stage: **137 passed, 3 skipped** (12 new tests:
  production-config guard rejecting bad secret/password/CORS and
  accepting good config, security headers present, docs disabled when
  production flag set, magic-byte rejection for spoofed audio/PDF
  uploads, genuine-file acceptance).

## Stage 5 — (next) UI/UX: specialist dashboard, admin polish, RTL checks

## Stage 5 — Frontend: specialist workspace, admin additions, result transparency ✅ DONE

- **Fixed a real consistency bug this upgrade itself introduced**:
  `Plans.jsx` still showed Approve/Reject buttons to ADMIN users after
  Stage 2 made `POST /therapy-plans/{id}/review` SPECIALIST-only — an admin
  clicking Approve would now silently get a 403. Split the page's logic
  into `canViewQueue` (SPECIALIST or ADMIN — oversight) vs. `canApprove`
  (SPECIALIST only), so an admin sees the queue read-only with an explicit
  note instead of a button that always fails.
- **Found and closed a real backend gap while building this**: there was
  no way for a specialist to discover *which* assessments needed review —
  `review_assessment` existed but nothing listed what was pending. Added
  `GET /assessments/pending-review` (mirroring the existing therapy-plans
  equivalent), registered before the `/{assessment_id}` dynamic route
  (otherwise FastAPI would 404 trying to parse "pending-review" as an id —
  covered by a regression test). Covered by 2 new backend tests.
- **New page**: `pages/Specialist.jsx` — a single workspace listing both
  the assessment review queue and the therapy-plan review queue, each
  completed-assessment card expandable to show the real AI findings
  (transcript with its evidence source, pronunciation accuracy against the
  reference text if one was given, limitations, and the supporting
  Knowledge Base evidence) before approving/rejecting — not just a bare
  "approve" button with no context. Wired into the router and the nav
  (visible to SPECIALIST only, since ADMIN already has its own oversight
  view in Plans.jsx).
- **Assessment page**: added an optional "what were you asked to say?"
  field (only shown for audio uploads) that is sent as `reference_text`,
  and a new `PronunciationPanel` that renders the word-by-word
  Expected/Recognized/Mismatch comparison from Stage 3's pronunciation
  analysis, using the existing design system's color tokens (not invented
  colors) and explicitly labeling the per-word confidence as a heuristic.
- **Admin page**: `KnowledgeBaseAdmin` now shows each document's real
  ingestion `status` (INDEXED/PROCESSING/FAILED, with the failure reason
  when applicable) and `chunk_count`, and has working Publish/Unpublish
  buttons wired to the new `PATCH` endpoint — previously there was no way
  to unpublish a document from the UI at all. Added a new "AI Models" tab
  (`ModelRegistryAdmin`) rendering Stage 1's model registry: every model,
  its verified metadata, honest limitations, and whether it's currently
  enabled given this deployment's configured credentials.
- RTL: the project already had real `[dir="rtl"]` CSS rules (not just
  string translation) before this pass; all new components reuse the
  existing `stack`/`row`/`row-between`/`card`/`badge` layout primitives and
  CSS custom-property color tokens rather than hardcoded directions or
  colors, so they inherit RTL support automatically rather than needing
  separate RTL-specific code.
- `npx vite build` run after every change in this stage — clean every
  time, no new warnings.
- Verified against a real running backend (not just "the build succeeded"):
  a full HTTP-level end-to-end script exercised every new/changed
  endpoint this stage and Stage 2-4 depend on — specialist/admin login,
  the model registry endpoint (and that SPECIALIST correctly gets 403 from
  it), a real audio assessment with `reference_text` producing a genuine
  (and honestly low — PocketSphinx misheard "apple" as "ah cool")
  pronunciation comparison, the new pending-review queue, the admin→403
  regression check on plan approval, and — most importantly — **publishing
  a Knowledge Base document, confirming it's retrievable, unpublishing it
  and confirming it immediately disappears from RAG answers, then
  republishing and confirming it reappears**, proving Stage 2b's retrieval
  fix works end-to-end over real HTTP, not just in a unit test.

## Stage 7 — (next) Final full-suite test + README + FINAL_PROJECT_REPORT.md
