# Roadmap: CoachLenz

## Milestones

- ✅ **v3.0 Core Platform** — Auth, roster, schedule, stats, dashboard, practice plans
- ✅ **v3.5 Film Room** — Video ingestion, AI play detection, frame-accurate tagging
- ✅ **v3.6 Scouting Engine** — Two-sided O/D/ST tendency engine, editable plays, PDF reports
- ✅ **v3.7 Detection Accuracy** — Denser frames, consecutive batches, accuracy benchmarking
- 🚧 **v3.8 Beta Readiness** — UATP compliance, stability hardening, beta polish (deadline: June 23, 2026)
- 📋 **v4.0 Scale** — Multi-sport expansion, video library, advanced analytics

## Phases

<details>
<summary>✅ Core Platform + Film Room + Scouting (Phases 1-9) — COMPLETE</summary>

### Phase 1: Auth & Org Foundation
**Goal:** Coach auth, organization multi-tenancy, onboarding flow
**Status:** Complete

### Phase 2: Roster & Schedule
**Goal:** Player management, game calendar, score tracking
**Status:** Complete

### Phase 3: Statistics & Dashboard
**Goal:** Season stats with AI analysis, top performers, team health summary
**Status:** Complete

### Phase 4: Practice Plans
**Goal:** AI-generated drill planning per sport/phase
**Status:** Complete

### Phase 5: Film Room — Ingest Pipeline
**Goal:** URL/upload → R2 → AI detection pipeline; YouTube + Hudl support
**Status:** Complete

### Phase 6: AI Play Detection
**Goal:** Frame extraction, Claude vision analysis, play tagging with timestamps
**Status:** Complete

### Phase 7: Scouting Engine
**Goal:** Two-sided O/D/ST tendency engine, editable play log, opponent report
**Status:** Complete

### Phase 8: Reports & PDF
**Goal:** AI tendency reports, printable PDF, structured {heading,body,insight_type} sections
**Status:** Complete

### Phase 9: Detection Accuracy
**Goal:** Denser frame extraction (5s/0.27 scene, cap 900), consecutive-frame batches, 8s dedup, accuracy benchmark tab
**Status:** Complete

</details>

### 🚧 v3.8 Beta Readiness (In Progress)

**Milestone Goal:** Ship a stable, trustworthy beta to coaches on June 23, 2026.

**Deadline:** 2026-06-23 (4 days)

#### Phase 10: UATP Compliance
**Goal:** All AI agents disclose identity, log every decision with reason + confidence, surface live status to user, support DRY_RUN mode, and escalate to human when confidence is low
**Depends on:** Phase 9
**Success Criteria:**
1. Every AI action logs: agent name, input, output, confidence (high/medium/low/unknown), timestamp to Supabase
2. Film room shows live agent status panel (not a silent spinner)
3. Low-confidence detections are flagged, not silently included
4. DRY_RUN mode simulates detection without writing to DB
5. Human escalation trigger fires when confidence < threshold
**Plans:** TBD

Plans:
- [ ] 10-01: UATP action logging + confidence flagging on ai_detect worker
- [ ] 10-02: Live status panel in film room UI
- [ ] 10-03: DRY_RUN mode + human escalation trigger

#### Phase 11: Beta Stability & Polish
**Goal:** Harden the most critical flows for beta, squash known edge-case bugs, ensure Railway deploy is clean
**Depends on:** Phase 10
**Success Criteria:**
1. Ingest → detect → report flow completes without error on 5 test videos
2. No silent failures — all errors surface to user with reason
3. Report PDF renders correctly for all sport types
4. Stripe billing flow completes without error (trial + paid)
5. Railway deploy produces clean health check on both services
**Plans:** TBD

Plans:
- [ ] 11-01: Error surface audit — silent failures become visible errors
- [ ] 11-02: E2E smoke test: ingest → detect → report → PDF across 3 sports
- [ ] 11-03: Billing flow verification + trial edge cases

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1-9 | v3.0–v3.7 | ✓ | Complete | 2026-06 |
| 10. UATP Compliance | v3.8 Beta | 0/3 | Not started | - |
| 11. Beta Stability | v3.8 Beta | 0/3 | Not started | - |
