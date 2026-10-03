# Final Project Report — Smart Speech Therapy AI

This report summarizes the upgrade pass performed against the existing
codebase in response to `MASTER-PROMPT.md`. It's written for whoever is
about to hand this project to a client or continue building on it: what was
actually built and verified, what remains a known limitation, and exactly
where to look for the detailed evidence.

**Companion document:** `docs/FINAL_UPGRADE_PLAN.md` is the stage-by-stage
build log with full technical detail on every change. This report is the
executive summary; that document is the paper trail.

---

## 1. Headline numbers

| | Before this pass | After this pass |
|---|---|---|
| Backend tests | 90 (88 passing, 2 skipped) | **142 (139 passing, 3 skipped)** |
| Disorders | 4, across 4 categories | **9, across 6 categories** |
| Exercises | 10 | **20** |
| Games | 2 types | **6 types** (4 new, including a real speech-based one) |
| Knowledge Base documents | 4 | **9** |
| Known dependency CVEs | ~80 (never audited before) | **2**, both documented with no available fix |
| Admin-reachable model info | none | **Model Registry**, Hub-verified |

Every number above was independently re-verified by running the actual
code in this session — not computed by inspection. See §7 for how.

---

## 2. What changed, by category

### Security (see Stage 6 in the upgrade plan for full detail)
- Found and fixed a real authorization bug: admins could approve/reject a
  patient's therapy plan, which the spec explicitly reserves for
  specialists. Fixed server-side; the frontend was then found to still
  show the (now-failing) buttons to admins and was fixed too.
- Found and fixed a real data-leak bug: unpublishing a Knowledge Base
  document didn't actually stop it from being used in RAG answers.
  Verified fixed with a live HTTP test (publish → retrievable → unpublish
  → gone → republish → retrievable again).
- Found and fixed a real upload-validation gap: files were only checked by
  filename extension, so a renamed arbitrary file would pass. Added actual
  magic-byte signature checking.
- Added a production boot guard that refuses to start the server with an
  insecure default `SECRET_KEY`, default admin password, or wildcard CORS
  — previously these would silently run in production.
- Ran a real dependency vulnerability audit (`pip-audit`), found ~80 known
  CVEs (several in the PDF-parsing and JWT libraries specifically), and
  upgraded everything that had a safe fix available, re-running the full
  test suite after every single upgrade. Two issues remain with no fix
  currently available upstream (`ecdsa`, and `python-jose`'s `pyasn1` pin)
  — documented explicitly in `requirements.txt` and the upgrade plan
  rather than hidden, with an honest assessment of the actual residual
  risk (low — this platform never exercises the vulnerable ECDSA code
  path) and a recommended follow-up (migrate off `python-jose` to
  `PyJWT`).
- Disabled `/docs`, `/redoc`, and `/openapi.json` in production; added
  baseline security response headers.

### RBAC / authorization hardening (Stage 2)
- Full authorization matrix from the spec now has explicit tests: USER and
  SPECIALIST cannot manage disorders/exercises/games/knowledge base; ADMIN
  can; only SPECIALIST can approve a therapy plan.
- Added a real `FIRST_SPECIALIST_EMAIL`/`FIRST_SPECIALIST_PASSWORD` seeded
  account, so the specialist-only approval flow is actually testable/usable
  out of the box instead of requiring manual account creation first.

### Knowledge Base admin workflow (Stage 2b)
- Documents now carry an honest ingestion `status`
  (UPLOADED/PROCESSING/INDEXED/FAILED) instead of silently vanishing on
  failure — a failed upload stays visible to an admin with a real failure
  reason, while its half-finished file/chunks are still cleaned up.
- Added document detail view, publish/unpublish, and search/filter
  endpoints that didn't exist before.

### AI result transparency (Stage 3)
- **Pronunciation analysis**: a new, honestly-labeled word-level
  comparison between a reference phrase and what the speech recognizer
  actually heard (Expected / Recognized / Mismatch / Confidence), built on
  Python's standard-library sequence alignment. Explicitly documented as a
  screening-level text comparison, not a phoneme-level clinical score —
  because no phoneme-level model could be genuinely evaluated from this
  build environment (see §6).
- **Unified Assessment Result**: one consistent JSON shape
  (`assessment_id, status, input_quality, transcription, fluency,
  stuttering, pronunciation, audio_features, visual_observations,
  evidence, models, limitations`) across audio/image/video assessments,
  with every populated section explicitly labeled `evidence_source:
  "audio" | "visual"` so the UI (and a specialist reading it) always knows
  where a claim came from.

### Content (Stage 4)
- 5 new disorders with the full required page structure (Overview,
  Characteristics, Speech Features, Assessment Considerations), filling
  two previously-missing categories (Speech Sound Disorders, Other
  Communication Areas). Original educational content — not claimed to
  cite specific peer-reviewed sources, consistent with "never fabricate
  medical citations."
- 10 new exercises (every new disorder has at least one linked exercise —
  verified by a dedicated test, not assumed).
- 5 new Knowledge Base reference documents, each verified to actually
  finish indexing (not just exist as a database row).
- 4 new, fully working game types — Sentence Builder, Memory Match, Sound
  Hunt, and **Picture Naming**, the last of which has a genuine
  speech-based answer path that runs a real recording through the
  platform's ASR pipeline and scores the transcript, not a fake/simulated
  "always correct" shortcut. (Scoped down from the spec's suggested 10
  game types to 6 real, fully-tested ones rather than rushing all 10 to a
  lower standard — see §6.)

### Model Registry + Hugging Face research (Stage 1)
- A mid-contribution setup change gave this session a Hugging Face MCP
  connector (read-only Hub search + a fixed set of Space tools — not
  network access for the backend itself). Used it to **verify, not guess**,
  every model this platform references: exact id, parameter count,
  license, and live Inference-Provider availability, checked against the
  real Hub API. One spec-suggested candidate (a stuttering-detection LoRA
  adapter) was found to not actually be usable as a drop-in API swap and
  was correctly not adopted, with the reasoning documented.
- Added an optional cross-encoder reranking pass for RAG (off by default),
  and a `GET /admin/models` endpoint exposing this registry to admins —
  now with a frontend tab to go with it.

### Frontend (Stage 5)
- New **Specialist Workspace** page — previously there was no frontend for
  a specialist to actually use the review endpoints the backend already
  had.
- Assessment page now has an optional reference-text field and renders the
  new pronunciation comparison.
- Admin Knowledge Base tab now shows real status/chunk counts and has
  working publish/unpublish buttons (previously missing entirely). New
  "AI Models" admin tab shows the model registry.
- `npx vite build` clean after every change; no new dependencies added.

---

## 3. What was explicitly NOT done, and why

Being honest about scope here matters more than appearing complete.

- **No model was benchmarked end-to-end** (WER/CER for ASR, retrieval
  quality for embeddings/reranking) **from this build environment**. The
  sandbox this was built in has no outbound network access to
  `huggingface.co`/`api-inference.huggingface.co`/`api.openai.com` — only
  package registries and `api.anthropic.com`. The Hugging Face MCP
  connector gave Claude (not the backend process) read access to the Hub
  API and a small fixed set of Space tools (none of which covered
  ASR/embeddings/audio-classification), so model *identity* could be
  verified, but not live inference quality. The code is written to call
  these models correctly and will work once deployed somewhere with real
  internet access and a real `HF_API_TOKEN` — this is a deployment-time
  step, documented clearly rather than silently assumed to already work.
- **Only 6 of the spec's ~10 suggested game types were built.** Building
  all 10 to the same real, server-authoritative, fully-tested standard
  used for the 6 that were built wasn't achievable in this pass without
  cutting corners on at least some of them. A smaller, fully-real set was
  chosen over a larger, partially-fake one.
- **Only 5 of the spec's suggested new disorders were added** (Cluttering,
  Developmental Language Disorder, Articulation Disorder, Dysphonia,
  Social Communication Difficulties), not the full list (e.g.
  Phonological Disorder, adult Apraxia, Language Delay, resonance
  disorders) — each one done properly (full page structure, linked
  exercise, KB document, all verified by tests) takes real time, and 5
  thorough ones were prioritized over a longer list of thinner ones.
- **Pronunciation analysis is word-level text comparison, not
  phoneme-level.** This is the spec's own documented fallback ("if a
  strong pretrained phoneme model is available, evaluate it; otherwise use
  a transparent alignment-based implementation") — no phoneme-alignment
  model or tool (e.g. a forced aligner) was available to genuinely
  evaluate from this environment.
- **ecdsa / pyasn1 CVEs remain unresolved** — no fixed release exists
  upstream in the version range `python-jose` requires. Real fix is
  migrating off `python-jose` to `PyJWT`, deliberately left as separate,
  careful follow-up work rather than rushed in alongside everything else
  (it touches every token the platform issues).
- **No real device/browser testing** was performed for mobile
  responsiveness or RTL rendering — verified at the CSS/logic level
  (existing `[dir="rtl"]` rules, logical layout primitives, no hardcoded
  directions) but not visually on an actual phone or Arabic-locale
  browser, since this environment has no browser automation tool.

---

## 4. Full list of new/changed files

**Backend**
- `app/services/model_registry.py` (new)
- `app/services/pronunciation_analysis.py` (new)
- `app/services/rate_limit.py` (pre-existing from an earlier session; unaffected)
- `app/services/assessment_service.py` (unified result builder, pronunciation integration)
- `app/services/knowledge_base_service.py` (reranking, active-document filtering fix)
- `app/services/hf_inference.py` (reranker call)
- `app/services/storage.py` (magic-byte validation)
- `app/api/v1/endpoints/admin.py` (`GET /admin/models`)
- `app/api/v1/endpoints/assessments.py` (`GET /pending-review`, `GET /{id}/result`, `reference_text`)
- `app/api/v1/endpoints/knowledge_base.py` (status workflow, publish/unpublish, detail view, search)
- `app/api/v1/endpoints/therapy.py` (SPECIALIST-only approval)
- `app/api/v1/endpoints/disorders.py` (rate limiting on AI extraction)
- `app/api/v1/endpoints/games.py` (audio-answer endpoint)
- `app/models/assessments.py` (`reference_text`)
- `app/models/knowledge_base.py` (`status`, `failure_reason`)
- `app/schemas/assessments.py`, `app/schemas/knowledge_base.py`, `app/schemas/games.py` (updated)
- `app/services/game_engine.py` (4 new game engines)
- `app/core/config.py` (`HF_RERANKER_MODEL`, `FIRST_SPECIALIST_*`)
- `app/main.py` (production config guard, security headers, docs disabling)
- `scripts/seed.py` (5 new disorders, 10 new exercises, 4 new games, 5 new KB docs, specialist account)
- `alembic/versions/c157ef0c6268_*.py`, `bba2e2b63f60_*.py` (new migrations)
- `requirements.txt` (security upgrades)
- 9 new/expanded test files (`test_model_registry.py`, `test_pronunciation_and_unified_result.py`,
  `test_seed_script.py`, expansions to `test_hardening.py`, `test_games.py`, `test_therapy.py`)

**Frontend**
- `src/pages/Specialist.jsx` (new)
- `src/pages/Plans.jsx` (admin-approval-button fix)
- `src/pages/Assessment.jsx` (reference text input, pronunciation panel)
- `src/pages/Admin.jsx` (Knowledge Base status/publish UI, new AI Models tab)
- `src/App.jsx`, `src/components/Layout.jsx`, `src/context/LangContext.jsx` (routing/nav/i18n for the new page)

**Docs**
- `docs/FINAL_UPGRADE_PLAN.md` (new — full build log)
- `docs/FINAL_PROJECT_REPORT.md` (this file)

---

## 5. How to verify this yourself

```bash
# Backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt --break-system-packages
cp .env.example .env   # set SECRET_KEY, DATABASE_URL=sqlite:///./dev.db for a quick run
alembic upgrade head
python scripts/seed.py
pytest -q               # expect: 139 passed, 3 skipped
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run build            # expect: clean build, no errors
npm run dev
```

The 3 skipped tests are environment-only (no internet to reach
`huggingface.co`/no `HF_API_TOKEN` configured in a sandboxed test run) —
they will run and pass in an environment with real credentials and
internet access.

---

## 6. Recommended next steps (not done here, flagged for follow-up)

1. Deploy somewhere with real internet access, set `HF_API_TOKEN`, and
   actually benchmark ASR (WER/CER on real Arabic + English recordings)
   and embedding/reranking retrieval quality — this was the single biggest
   thing this build environment could not do.
2. Migrate `python-jose` → `PyJWT` as an isolated, carefully-tested change
   (touches every issued token).
3. Expand the remaining spec-suggested disorders and game types,
   following the same pattern (full page structure / linked
   content / tests) established here.
4. Real device/browser QA pass for mobile responsiveness and Arabic RTL
   rendering.
5. Consider a dedicated phoneme-alignment pipeline (e.g. a forced aligner)
   if clinical-grade pronunciation scoring becomes a hard requirement —
   the current implementation is an honest, documented interim step, not
   a long-term ceiling.
