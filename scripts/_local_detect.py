"""Run the LATEST detection code locally against prod film+DB, bypassing Railway entirely."""
import os, asyncio, json, uuid, tempfile, shutil, pathlib, ssl

# 1. env: R2 + Anthropic from captured file; dummy DB/secret so settings imports (engine unused)
for line in (pathlib.Path.home()/".cl_detect.env").read_text(encoding="utf-8", errors="ignore").splitlines():
    if "=" in line and not line.lstrip().startswith("#"):
        k, v = line.split("=", 1); os.environ[k] = v
os.environ["DATABASE_URL"] = "postgresql+asyncpg://u:p@localhost/x"
os.environ.setdefault("SECRET_KEY", "x"); os.environ.setdefault("FERNET_KEY", "x")

# 2. put a real ffmpeg on PATH (the code shells out to "ffmpeg")
import imageio_ffmpeg
_ffdir = tempfile.mkdtemp()
shutil.copy(imageio_ffmpeg.get_ffmpeg_exe(), os.path.join(_ffdir, "ffmpeg.exe"))
os.environ["PATH"] = _ffdir + os.pathsep + os.environ["PATH"]

import asyncpg
from backend.workers.worker_ai_detect import AiDetectWorker, CODE_VERSION, FRAMES_PER_BATCH
from backend.services.r2 import generate_presigned_download_url

PGURL = os.environ["DATABASE_PUBLIC_URL"]
GAME = "62aadc94-731c-474e-9bfa-29f148849323"

async def conn():
    try: return await asyncpg.connect(PGURL, timeout=30)
    except Exception: return await asyncpg.connect(PGURL, timeout=30, ssl=ssl._create_unverified_context())

async def main():
    print(f"LOCAL DETECTION — code_version={CODE_VERSION}", flush=True)
    c = await conn()
    g = await c.fetchrow("SELECT r2_key, sport, duration_seconds, organization_id FROM games WHERE id=$1", GAME)
    await c.close()
    sport = (g["sport"] or "football").lower()
    dur = float(g["duration_seconds"] or 0)
    print(f"game sport={sport} duration={dur/60:.1f}min", flush=True)

    url = generate_presigned_download_url(g["r2_key"], expires_in=7200)
    print("got presigned R2 url; extracting frames (parallel windows)...", flush=True)

    w = AiDetectWorker()
    with tempfile.TemporaryDirectory() as td:
        frames = await w._extract_windows(url, dur, td)
        print(f"\n*** FRAMES EXTRACTED: {len(frames)}  (old pipeline was 900; parallel target ~1360) ***", flush=True)
        print(f"    diag: {getattr(w,'_extract_diag',{})}", flush=True)
        if not frames:
            print("NO FRAMES — extraction failed locally too."); return

        batches = [frames[i:i+FRAMES_PER_BATCH] for i in range(0, len(frames), FRAMES_PER_BATCH)]
        all_plays = []
        for bi, b in enumerate(batches):
            try:
                plays = await w._analyze_batch(b, bi, len(batches), sport)
                all_plays.extend(plays)
            except Exception as e:
                print(f"  batch {bi} err: {str(e)[:120]}", flush=True)
            if bi % 20 == 0:
                print(f"  vision {bi}/{len(batches)} ... plays so far {len(all_plays)}", flush=True)

        deduped = w._deduplicate_plays(all_plays)
        if sport in ("football", "flag_football"):
            deduped = w._derive_from_sequence(deduped)
            deduped = w._derive_field_position(deduped)

    n = len(deduped) or 1
    def pct(k): return round(sum(1 for p in deduped if p.get(k) not in (None, "")) / n * 100, 1)
    print(f"\n===== LOCAL RESULT: total_plays={len(deduped)} (Railway was stuck at ~62) =====", flush=True)
    for k in ("down","distance","play_type","formation","result","field_position","yards_gained"):
        print(f"  {k:14}: {pct(k)}%", flush=True)

    # write to prod DB so it shows in the app
    DEEP = ("run_direction","run_concept","pass_concept","pass_depth","coverage_shell","pressure_type","play_description",
            "run_gap","target_area","motion_type","receiver_alignment","corner_technique","safety_rotation","pressure_gap",
            "linebacker_alignment","tempo","score_situation","is_play_action","screen_subtype","goal_line","blind_spot",
            "players","primary_player_jersey","yards_source","field_position_derived",
            "st_unit","kick_direction","kick_result","return_scheme","coverage_result","fg_distance_yds","snap_quality","block_attempt","st_fake")
    c = await conn()
    await c.execute("DELETE FROM events WHERE game_id=$1 AND (extra_data->>'auto_detected')='true'", GAME)
    rows = 0
    for p in deduped:
        side = (p.get("side") or "offense").lower().replace(" ", "_")
        if side not in ("offense","defense","special_teams","transition"): side = "offense"
        ed = {"auto_detected": True, "confidence": p.get("confidence", 0.8),
              "needs_review": p.get("confidence", 0.8) < 0.65,
              **{k: p[k] for k in DEEP if p.get(k) is not None}}
        await c.execute(
            "INSERT INTO events (id, game_id, organization_id, event_type, side, time_seconds, down, distance, field_position, "
            "formation, play_type, defensive_front, coverage, blitz, result, yards_gained, personnel, motion, extra_data, created_at) "
            "VALUES (gen_random_uuid(),$1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18::jsonb,now())",
            GAME, g["organization_id"], (p.get("event_type","shot") if sport=="basketball" else "play"), side,
            p.get("time_seconds"), p.get("down"), p.get("distance"), p.get("field_position"), p.get("formation"),
            p.get("play_type"), p.get("defensive_front"), p.get("coverage"), p.get("blitz"), p.get("result"),
            p.get("yards_gained"), p.get("personnel"), bool(p.get("motion", False)), json.dumps(ed))
        rows += 1
    await c.close()
    print(f"\nwrote {rows} plays to prod DB — now live in the app.", flush=True)

asyncio.run(main())
