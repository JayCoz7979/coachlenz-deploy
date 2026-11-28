"""
Tenant isolation for report generation and every route that takes a game, session,
report, or job id.

The HTTP sweep runs inside the SQLite integration harness (test_api_integration),
which is the repo's supported app-level DB test. SQLite has no report_type check,
so same-org live_game coverage here is app-level only. The Postgres check that
allows live_game lives in PR #296.

Cross-org responses are 404, never 403, so a miss does not confirm the id exists.
"""
import uuid

import pytest

from backend.routers.reports import REPORT_TYPES
from backend.workers.worker_reports import GAME_NOT_IN_ORG

pytestmark = pytest.mark.unit

# Unique strings so a leaked play note cannot hide inside an unrelated 404 body.
OURS = "xq-our-note-7f3a"
THEIRS = "xq-rival-note-7f3a"


def test_cross_org_failure_message_is_non_sensitive():
    assert "\u2014" not in GAME_NOT_IN_ORG
    low = GAME_NOT_IN_ORG.lower()
    for leak in ("jersey", "organization", "tenant", "secret", "note"):
        assert leak not in low
    assert "not found" in low


async def run(ac, tok, ids, check):
    """Called by the integration harness with its live client and helpers.

    Do not import test_api_integration from here. Running that module as a
    script loads it as __main__, and a second import would delete the SQLite
    file out from under the session and read an empty id map.
    """
    from datetime import datetime
    from sqlalchemy import select, func

    from backend.models.base import AsyncSessionLocal
    from backend.models.organization import Organization
    from backend.models.user import User
    from backend.models.game import Game
    from backend.models.event import Event
    from backend.models.report import TendencyReport
    from backend.models.job import Job
    from backend.models.clip import Clip
    from backend.services.auth import hash_password, create_access_token
    from backend.services.encryption import decrypt_json
    from backend.workers.worker_reports import ReportsWorker, ReportInputError
    import backend.workers.worker_reports as wr
    import backend.services.live_game_report as live_rep

    A = tok("reviewer")  # org A owner: tenancy, not a missing permission
    member = tok("analyst")

    async with AsyncSessionLocal() as db:
        org_b = Organization(name="Isolation Rival", slug=f"iso-{uuid.uuid4().hex[:8]}", is_trial=False)
        db.add(org_b)
        await db.flush()
        user_b = User(
            organization_id=org_b.id, name="Rival Owner",
            email=f"iso-{uuid.uuid4().hex[:6]}@rival.com",
            hashed_password=hash_password("x"), role="owner",
        )
        game_b = Game(
            id=uuid.uuid4(), organization_id=org_b.id, title="Rival Live",
            sport="football", status="live", opponent="Eagles",
        )
        game_a = Game(
            id=uuid.uuid4(), organization_id=uuid.UUID(ids["org"]), title="Our Film",
            sport="football", status="ready",
        )
        live_a = Game(
            id=uuid.uuid4(), organization_id=uuid.UUID(ids["org"]), title="Our Live",
            sport="football", status="live", opponent="Hawks",
        )
        db.add_all([user_b, game_b, game_a, live_a])
        await db.flush()
        ev_b = Event(
            id=uuid.uuid4(), game_id=game_b.id, organization_id=org_b.id,
            event_type="play", side="offense", player="77", coach_note=THEIRS,
            is_highlight=True,
        )
        ev_a = Event(
            id=uuid.uuid4(), game_id=game_a.id, organization_id=uuid.UUID(ids["org"]),
            event_type="play", side="offense", player="12", coach_note=OURS,
            is_highlight=True,
        )
        ev_live = Event(
            id=uuid.uuid4(), game_id=live_a.id, organization_id=uuid.UUID(ids["org"]),
            event_type="play", side="offense", player="12", coach_note=OURS,
        )
        # Two more plays so the same-org POST /live/report control clears the
        # 3-play minimum from #296 (0-2 plays is a 422 with no row).
        ev_live_more = [
            Event(
                id=uuid.uuid4(), game_id=live_a.id, organization_id=uuid.UUID(ids["org"]),
                event_type="play", side="offense", player="12",
            )
            for _ in range(2)
        ]
        # Mis-stamped: another org's note sitting on OUR game id. The worker must
        # drop it because the event query filters organization_id, not just game_id.
        ev_mis = Event(
            id=uuid.uuid4(), game_id=game_a.id, organization_id=org_b.id,
            event_type="play", side="offense", player="77", coach_note=THEIRS,
            is_highlight=True,
        )
        report_b = TendencyReport(
            id=uuid.uuid4(), organization_id=org_b.id, game_ids=[str(game_b.id)],
            sport="football", report_type="opponent", title="Rival Secret Report",
            generated_at=datetime.utcnow(),
            share_token="rival-share-token",
        )
        job_b = Job(
            id=uuid.uuid4(), organization_id=org_b.id, job_type="report",
            status="queued", payload={"report_id": "rival-job"},
        )
        clip_b = Clip(
            id=uuid.uuid4(), organization_id=org_b.id, game_id=game_b.id,
            title="Rival Clip", start_time=0, end_time=5, created_by=user_b.id,
        )
        db.add_all([ev_b, ev_a, ev_live, *ev_live_more, ev_mis, report_b, job_b, clip_b])
        await db.commit()
        B = {
            "org": str(org_b.id), "user": str(user_b.id), "game": str(game_b.id),
            "event": str(ev_b.id), "report": str(report_b.id), "job": str(job_b.id),
            "clip": str(clip_b.id),
        }
        A_GAME = str(game_a.id)
        A_LIVE = str(live_a.id)
        MIS = str(ev_mis.id)

    tok_b = {"Authorization": f"Bearer {create_access_token(B['user'], B['org'])}"}
    missing = str(uuid.uuid4())

    async def n_rows():
        async with AsyncSessionLocal() as db:
            reports = (await db.execute(select(func.count()).select_from(TendencyReport))).scalar()
            jobs = (await db.execute(select(func.count()).select_from(Job))).scalar()
            return reports, jobs

    async def probe(name, method, url, *, json=None, params=None, headers=None, expect=404):
        kwargs = {"headers": headers or A}
        if json is not None:
            kwargs["json"] = json
        if params is not None:
            kwargs["params"] = params
        r = await getattr(ac, method)(url, **kwargs)
        leaked = THEIRS in r.text or "Rival Secret Report" in r.text
        check(f"xorg {name} -> {expect}, no rival payload", r.status_code == expect and not leaked)
        return r

    # ── POST /reports: the reported hole ────────────────────────────────────
    before = await n_rows()
    r = await probe(
        "POST /reports member, rival live session",
        "post", "/reports",
        json={"title": "Stolen", "sport": "football", "game_ids": [B["game"]], "report_type": "opponent"},
        headers=member,
    )
    check("xorg POST /reports detail is Game not found", r.json().get("detail") == "Game not found")
    after = await n_rows()
    check("xorg POST /reports created no report and no job", after == before)

    r = await probe(
        "POST /reports mixed own + rival game",
        "post", "/reports",
        json={"title": "Mixed", "sport": "football", "game_ids": [A_GAME, B["game"]]},
        headers=member,
    )
    check("xorg mixed POST created no row", (await n_rows()) == after)

    r = await probe(
        "POST /reports unknown id",
        "post", "/reports",
        json={"title": "Missing", "sport": "football", "game_ids": [missing]},
        headers=member,
    )
    r = await probe(
        "POST /reports malformed id",
        "post", "/reports",
        json={"title": "Bad", "sport": "football", "game_ids": ["not-a-uuid"]},
        headers=member,
    )
    check("xorg malformed id is 404 not 500", r.status_code == 404)

    # Platform admin is not exempt on this route (no prior cross-org grant here).
    async with AsyncSessionLocal() as db:
        org_p = Organization(
            name="Platform", slug=f"plat-{uuid.uuid4().hex[:8]}",
            is_trial=False, admin_level="platform",
        )
        db.add(org_p)
        await db.flush()
        user_p = User(
            organization_id=org_p.id, name="Platform Admin",
            email=f"plat-{uuid.uuid4().hex[:6]}@x.com",
            hashed_password=hash_password("x"), role="owner",
        )
        db.add(user_p)
        await db.commit()
        tok_p = {"Authorization": f"Bearer {create_access_token(str(user_p.id), str(org_p.id))}"}
    await probe(
        "POST /reports platform admin, rival game",
        "post", "/reports",
        json={"title": "Admin Stolen", "sport": "football", "game_ids": [B["game"]]},
        headers=tok_p,
    )

    reports_before_type, _ = await n_rows()
    r = await ac.post(
        "/reports",
        json={"title": "Bad Type", "sport": "football", "game_ids": [A_GAME], "report_type": "not_a_type"},
        headers=member,
    )
    reports_after_type, _ = await n_rows()
    check(
        "unknown report_type -> 422 and no row",
        r.status_code == 422 and THEIRS not in r.text and reports_after_type == reports_before_type,
    )

    # $7 paywall (Stage 2 QA H1): an unpaid org cannot queue a live_game report
    # through POST /reports either. 403 with the paywall code, nothing written.
    reports_before_pay, jobs_before_pay = await n_rows()
    r = await ac.post(
        "/reports",
        json={"title": "Unpaid live", "sport": "football", "game_ids": [A_LIVE], "report_type": "live_game"},
        headers=member,
    )
    check(
        "unpaid POST /reports live_game -> 403 paywall, no row, no job",
        r.status_code == 403
        and (r.json().get("detail") or {}).get("code") == "live_tracker_payment_required"
        and await n_rows() == (reports_before_pay, jobs_before_pay),
    )
    async with AsyncSessionLocal() as db:
        org_a = await db.get(Organization, uuid.UUID(ids["org"]))
        org_a.live_tracker_purchased_at = datetime.utcnow()
        await db.commit()

    # Same-org creates, one per report type the product accepts.
    created = {}
    for rtype in REPORT_TYPES:
        gid = A_LIVE if rtype == "live_game" else A_GAME
        r = await ac.post(
            "/reports",
            json={"title": f"Same {rtype}", "sport": "football", "game_ids": [gid], "report_type": rtype},
            headers=member,
        )
        ok = r.status_code == 200 and bool(r.json().get("id"))
        check(f"same-org POST /reports {rtype} -> 200", ok)
        if ok:
            created[rtype] = r.json()["id"]
    r = await ac.post(
        "/reports",
        json={"title": "Dup", "sport": "football", "game_ids": [A_GAME, A_GAME]},
        headers=member,
    )
    check("same-org duplicate game id still queues", r.status_code == 200)
    r = await ac.post(
        "/reports",
        json={"title": "Empty", "sport": "football", "game_ids": []},
        headers=member,
    )
    check("same-org empty game_ids still queues", r.status_code == 200)
    empty_id = r.json().get("id") if r.status_code == 200 else None

    # ── Worker: cross-org job inserted directly, and same-org still runs ────
    async with AsyncSessionLocal() as db:
        planted = TendencyReport(
            id=uuid.uuid4(), organization_id=uuid.UUID(ids["org"]),
            game_ids=[B["game"]], sport="football", report_type="opponent",
            title="Planted cross org",
        )
        db.add(planted)
        await db.commit()
        planted_id = str(planted.id)

    seen = []

    real_engine = wr.run_tendency_engine

    async def spy_engine(sport, events):
        seen.append([(getattr(e, "player", None), getattr(e, "coach_note", None)) for e in events])
        try:
            return await real_engine(sport, events)
        except Exception:
            return {
                "total_plays": len(events), "offense_plays": 0, "defense_plays": 0,
                "special_teams_plays": 0, "data_confidence": {},
            }

    async def spy_prose(**kwargs):
        return [{"heading": "H", "insight_type": "tendency", "body": "ok"}]

    async def spy_live(**kwargs):
        evs = kwargs.get("events") or []
        seen.append([(getattr(e, "player", None), getattr(e, "coach_note", None)) for e in evs])
        return [{"heading": "H", "insight_type": "tendency", "body": "ok"}]

    async def no_adj(db, organization_id, sport):
        return []

    orig_adj = wr.learning_loop.active_adjustments_for
    orig_live = live_rep.generate_live_game_sections
    orig_prose = wr.generate_prose_sections
    wr.run_tendency_engine = spy_engine
    wr.generate_prose_sections = spy_prose
    live_rep.generate_live_game_sections = spy_live
    wr.learning_loop.active_adjustments_for = no_adj
    try:
        seen.clear()
        try:
            await ReportsWorker().handle({"report_id": planted_id})
            refused = False
        except ReportInputError as e:
            refused = str(e) == GAME_NOT_IN_ORG and THEIRS not in str(e) and OURS not in str(e)
        check("worker refuses a direct-inserted cross-org job", refused and not seen)
        async with AsyncSessionLocal() as db:
            planted_row = await db.get(TendencyReport, uuid.UUID(planted_id))
            rival_ev = await db.get(Event, uuid.UUID(B["event"]))
            check(
                "worker marked the planted report failed without writing a summary",
                planted_row is not None and planted_row.generated_at is None
                and planted_row.summary_json is None
                and planted_row.error_reason == GAME_NOT_IN_ORG
                and THEIRS not in (planted_row.error_reason or ""),
            )
            check("rival play note unchanged", rival_ev is not None and rival_ev.coach_note == THEIRS)

        for rtype, rid in created.items():
            seen.clear()
            await ReportsWorker().handle({"report_id": rid})
            flat = [pair for batch in seen for pair in batch]
            notes = [n for _p, n in flat]
            check(
                f"worker same-org {rtype} uses only this org's plays",
                OURS in notes and THEIRS not in notes and ("12", OURS) in flat,
            )
            async with AsyncSessionLocal() as db:
                row = await db.get(TendencyReport, uuid.UUID(rid))
                summary = decrypt_json(row.summary_json) if row and row.summary_json else {}
                blob = str(summary)
                check(
                    f"worker same-org {rtype} finished without the rival note",
                    row is not None and row.generated_at is not None and row.error_reason is None
                    and THEIRS not in blob and (rtype == "live_game" or OURS in blob),
                )

        if empty_id:
            seen.clear()
            await ReportsWorker().handle({"report_id": empty_id})
            notes = [n for batch in seen for _p, n in batch if n]
            async with AsyncSessionLocal() as db:
                row = await db.get(TendencyReport, uuid.UUID(empty_id))
            check(
                "worker same-org empty game_ids still finishes",
                row is not None and row.generated_at is not None and not notes,
            )
    finally:
        wr.run_tendency_engine = real_engine
        wr.generate_prose_sections = orig_prose
        wr.learning_loop.active_adjustments_for = orig_adj
        live_rep.generate_live_game_sections = orig_live

    # ── One probe per other route that takes an id ──────────────────────────
    g, e, rp, j, c = B["game"], B["event"], B["report"], B["job"], B["clip"]
    archive = str(uuid.uuid4())

    await probe("GET /reports list hides rival", "get", "/reports", expect=200)
    r = await ac.get("/reports", headers=A)
    check("GET /reports omits rival id", rp not in [x.get("id") for x in r.json()])

    await probe("GET /reports/{id}", "get", f"/reports/{rp}")
    await probe("POST /reports/{id}/retry", "post", f"/reports/{rp}/retry")
    await probe("GET /reports/{id}/export", "get", f"/reports/{rp}/export", params={"format": "coordinator"})
    await probe("GET /reports/{id}/export/csv", "get", f"/reports/{rp}/export/csv")
    await probe("POST /reports/{id}/share", "post", f"/reports/{rp}/share")
    await probe("DELETE /reports/{id}/share", "delete", f"/reports/{rp}/share")
    await probe("DELETE /reports/{id}", "delete", f"/reports/{rp}")
    await probe("GET /reports/{id}/chat", "get", f"/reports/{rp}/chat")
    await probe("POST /reports/{id}/chat", "post", f"/reports/{rp}/chat", json={"question": "what is the note?"})
    await probe(
        "GET /reports/{id}/share/{bad token}",
        "get", f"/reports/{rp}/share/not-the-token", headers={},
    )

    await probe("GET /jobs list hides rival", "get", "/jobs", expect=200)
    r = await ac.get("/jobs", headers=A)
    check("GET /jobs omits rival id", j not in [x.get("id") for x in r.json()])
    await probe("GET /jobs/{id}", "get", f"/jobs/{j}")
    await probe("GET /ingest/job/{id}", "get", f"/ingest/job/{j}")

    await probe("GET /live/sessions hides rival", "get", "/live/sessions", expect=200)
    r = await ac.get("/live/sessions", headers=A)
    ids_listed = [s.get("session_id") for s in (r.json().get("sessions") or [])]
    check("GET /live/sessions omits rival id", g not in ids_listed)
    await probe("GET /live/session/{id}", "get", f"/live/session/{g}")
    await probe("POST /live/plays", "post", "/live/plays", json={"session_id": g, "plays": []})
    await probe("POST /live/report", "post", "/live/report", json={"session_id": g, "scope": "full"})
    await probe("PATCH /live/play/{id}", "patch", f"/live/play/{e}", json={"note": "pwn"})
    await probe("DELETE /live/play/{id}", "delete", f"/live/play/{e}")
    await probe("POST /live/play/{id}/flag", "post", f"/live/play/{e}/flag", json={"is_coaching_point": True})

    await probe("GET /games/{id}", "get", f"/games/{g}")
    await probe("PATCH /games/{id}", "patch", f"/games/{g}", json={"title": "PWNED"})
    await probe("GET /games/{id}/accuracy", "get", f"/games/{g}/accuracy")
    await probe("POST /games/{id}/rederive-downs", "post", f"/games/{g}/rederive-downs")
    await probe("GET /games/{id}/tendencies", "get", f"/games/{g}/tendencies")
    await probe("GET /games/{id}/coverage", "get", f"/games/{g}/coverage")
    await probe("POST /games/{id}/auto-detect", "post", f"/games/{g}/auto-detect")
    await probe("GET /games/{id}/auto-detect/status", "get", f"/games/{g}/auto-detect/status")
    await probe("GET /games/{id}/players", "get", f"/games/{g}/players")
    await probe("GET /games/{id}/agent-log", "get", f"/games/{g}/agent-log")
    await probe("GET /games/{id}/runs", "get", f"/games/{g}/runs")
    await probe("POST /games/{id}/runs/{archive}/restore", "post", f"/games/{g}/runs/{archive}/restore")
    await probe("DELETE /games/{id}/runs/{archive}", "delete", f"/games/{g}/runs/{archive}")

    await probe("GET /events?game_id", "get", "/events", params={"game_id": g}, expect=200)
    r = await ac.get("/events", params={"game_id": g}, headers=A)
    check("GET /events rival game is empty", r.status_code == 200 and r.json() == [])
    await probe("POST /events", "post", "/events", json={"game_id": g, "event_type": "play"})
    await probe(
        "POST /events/bulk", "post", "/events/bulk",
        json=[{"game_id": g, "event_type": "play"}],
    )
    await probe("PATCH /events/{id}", "patch", f"/events/{e}", json={"coach_note": "pwn"})
    await probe("DELETE /events/{id}", "delete", f"/events/{e}")
    await probe("GET /events/enrich-template", "get", "/events/enrich-template", params={"game_id": g})
    await probe(
        "POST /events/enrich-csv", "post", "/events/enrich-csv",
        json={"game_id": g, "csv_text": "event_id,down\n"},
    )

    await probe("GET /grades/game/{id}", "get", f"/grades/game/{g}")
    await probe("GET /grades/game/{id}/sheet", "get", f"/grades/game/{g}/sheet")
    await probe("GET /grades/game/{id}/export", "get", f"/grades/game/{g}/export")
    await probe("GET /grades/game/{id}/annotations", "get", f"/grades/game/{g}/annotations")
    await probe(
        "POST /grades/annotations", "post", "/grades/annotations",
        json={"game_id": g, "event_id": e, "note": "pwn"},
    )

    await probe("GET /rosters/resolve/game/{id}", "get", f"/rosters/resolve/game/{g}")

    await probe("GET /clips?game_id", "get", "/clips", params={"game_id": g}, expect=200)
    r = await ac.get("/clips", params={"game_id": g}, headers=A)
    listed = r.json() if r.status_code == 200 else []
    check(
        "GET /clips rival game has no rival clip",
        r.status_code == 200 and c not in [x.get("id") for x in listed] and THEIRS not in r.text,
    )
    await probe("POST /clips", "post", "/clips", json={"game_id": g, "start_time": 0, "end_time": 1})
    await probe("GET /clips/{id}", "get", f"/clips/{c}")
    await probe("DELETE /clips/{id}", "delete", f"/clips/{c}")

    await probe(
        "POST /upload/presign", "post", "/upload/presign",
        json={"game_id": g, "file_name": "x.mp4"},
    )
    await probe("POST /upload/complete", "post", "/upload/complete", params={"game_id": g})

    await probe("GET /scout/{session}/analysis", "get", f"/scout/{g}/analysis")
    await probe("POST /scout/manual", "post", "/scout/manual", json={"session_id": g})
    await probe("POST /scout/csv", "post", "/scout/csv", json={"session_id": g, "csv_text": "jersey\n1\n"})
    await probe("POST /scout/analyze", "post", "/scout/analyze", json={"session_id": g})
    await probe("POST /scout/review", "post", "/scout/review", json={"session_id": g, "decision": "reviewed"})
    await probe("GET /scout/football/{session}/analysis", "get", f"/scout/football/{g}/analysis")
    await probe("POST /scout/football/plays", "post", "/scout/football/plays", json={"session_id": g, "plays": []})
    await probe(
        "POST /scout/football/csv", "post", "/scout/football/csv",
        json={"session_id": g, "csv_text": "jersey\n1\n"},
    )
    await probe("POST /scout/football/analyze", "post", "/scout/football/analyze", json={"session_id": g})
    await probe(
        "POST /scout/football/review", "post", "/scout/football/review",
        json={"session_id": g, "decision": "reviewed"},
    )

    # /admin/* is platform-admin cross-org by design. A non-admin gets 404 and
    # learns nothing. A platform admin can still set the quality-gate count.
    await probe("PUT /admin/detection-quality/{id}/true-count non-admin", "put",
                f"/admin/detection-quality/{g}/true-count", json={"true_count": 10})
    await probe("PUT /admin/detection-quality/{id}/true-shots non-admin", "put",
                f"/admin/detection-quality/{g}/true-shots", json={"true_shot_count": 4})
    r = await ac.put(
        f"/admin/detection-quality/{g}/true-count",
        json={"true_count": 40}, headers=tok_p,
    )
    check("platform admin detection-quality true-count still cross-org", r.status_code == 200)
    r = await ac.put(
        f"/admin/detection-quality/{g}/true-count",
        json={"true_count": None}, headers=tok_p,
    )
    check("platform admin can clear the count again", r.status_code == 200)

    # Positive controls: org B still reads its own session, and the note is there.
    r = await ac.get(f"/live/session/{g}", headers=tok_b)
    check(
        "rival owner still reads own live session",
        r.status_code == 200 and THEIRS in r.text and r.json().get("session_id") == g,
    )
    r = await ac.get(f"/reports/{rp}", headers=tok_b)
    check("rival owner still reads own report", r.status_code == 200)
    r = await ac.get(f"/jobs/{j}", headers=tok_b)
    check("rival owner still reads own job", r.status_code == 200)
    r = await ac.post(
        "/live/report",
        json={"session_id": A_LIVE, "scope": "full"}, headers=member,
    )
    check("same-org POST /live/report still queues", r.status_code == 200 and bool(r.json().get("report_id")))

    # Hostile probes must not have changed the rival play.
    async with AsyncSessionLocal() as db:
        rival_ev = await db.get(Event, uuid.UUID(B["event"]))
        mis = await db.get(Event, uuid.UUID(MIS))
        game = await db.get(Game, uuid.UUID(g))
        check("rival play intact after the sweep", rival_ev is not None and rival_ev.coach_note == THEIRS)
        check("mis-stamped row still not merged into our film", mis is not None and mis.coach_note == THEIRS)
        check("rival game title intact", game is not None and game.title == "Rival Live")
        check("admin count was cleared", game is not None and not game.true_play_count)
