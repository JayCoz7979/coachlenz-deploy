"""Single-camera film test: run detection + tendency engine on a LOCAL file. Usage: _local_film.py <video> <sport>"""
import os, sys, asyncio, json, re, subprocess, tempfile, shutil, pathlib
sys.path.insert(0, r"C:\Users\jason\coachlenz-deploy\.claude\worktrees\silly-curie-38af50")

for line in (pathlib.Path.home()/".cl_detect.env").read_text(encoding="utf-8", errors="ignore").splitlines():
    if "=" in line and not line.lstrip().startswith("#"):
        k, v = line.split("=", 1); os.environ[k] = v
os.environ["DATABASE_URL"] = "postgresql+asyncpg://u:p@localhost/x"
os.environ.setdefault("SECRET_KEY", "x"); os.environ.setdefault("FERNET_KEY", "x")

import imageio_ffmpeg
_ffdir = tempfile.mkdtemp(); FFMPEG = os.path.join(_ffdir, "ffmpeg.exe")
shutil.copy(imageio_ffmpeg.get_ffmpeg_exe(), FFMPEG)
os.environ["PATH"] = _ffdir + os.pathsep + os.environ["PATH"]

# local SSL is intercepted (Norton/VPN) -> Anthropic client skips cert verify for this one-off run
import anthropic, httpx
_o = anthropic.AsyncAnthropic
anthropic.AsyncAnthropic = lambda *a, **k: _o(*a, **{**k, "http_client": httpx.AsyncClient(verify=False, timeout=180)})

from types import SimpleNamespace as NS
from backend.workers.worker_ai_detect import AiDetectWorker, CODE_VERSION, FRAMES_PER_BATCH
from backend.services.tendency_engine.engine import run_tendency_engine

VIDEO = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\jason\tanner_ardmore.mp4"
SPORT = (sys.argv[2] if len(sys.argv) > 2 else "football").lower()

def duration_of(path):
    out = subprocess.run([FFMPEG, "-i", path], capture_output=True, text=True).stderr
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", out)
    return (int(m.group(1))*3600 + int(m.group(2))*60 + float(m.group(3))) if m else 0.0

def E(p):
    side = (p.get("side") or "offense").lower().replace(" ", "_")
    if side not in ("offense", "defense", "special_teams", "transition"): side = "offense"
    deep = {k: v for k, v in p.items() if v is not None}; deep["confidence"] = p.get("confidence", 0.8)
    return NS(event_type=p.get("event_type", "play"), side=side, down=p.get("down"), distance=p.get("distance"),
              field_position=p.get("field_position"), hash_position=p.get("hash_position"), formation=p.get("formation"),
              play_type=p.get("play_type"), personnel=p.get("personnel"), motion=bool(p.get("motion", False)),
              defensive_front=p.get("defensive_front"), coverage=p.get("coverage"), blitz=p.get("blitz"),
              result=p.get("result"), yards_gained=p.get("yards_gained"), time_seconds=p.get("time_seconds"), extra_data=deep)

async def main():
    print(f"SINGLE-CAMERA FILM TEST — sport={SPORT}, code_version={CODE_VERSION}\nfile: {VIDEO}", flush=True)
    dur = duration_of(VIDEO); print(f"duration: {dur/60:.1f} min", flush=True)
    w = AiDetectWorker()
    with tempfile.TemporaryDirectory() as td:
        frames = await w._extract_windows(VIDEO, dur, td)
        print(f"frames: {len(frames)}  diag={getattr(w,'_extract_diag',{})}", flush=True)
        batches = [frames[i:i+FRAMES_PER_BATCH] for i in range(0, len(frames), FRAMES_PER_BATCH)]
        plays = []
        for bi, b in enumerate(batches):
            try: plays.extend(await w._analyze_batch(b, bi, len(batches), SPORT))
            except Exception as e:
                if bi % 15 == 0: print(f"  b{bi} err {str(e)[:80]}", flush=True)
            if bi % 20 == 0: print(f"  vision {bi}/{len(batches)} plays={len(plays)}", flush=True)
        deduped = w._deduplicate_plays(plays)
        if SPORT in ("football", "flag_football"):
            deduped = w._derive_from_sequence(deduped); deduped = w._derive_field_position(deduped)

    events = [E(p) for p in deduped]
    n = len(events) or 1
    def fr(attr): return round(sum(1 for e in events if getattr(e, attr, None) not in (None, "")) / n * 100, 1)
    print(f"\n================ SINGLE-CAMERA TEST RESULT — {SPORT.upper()} ================", flush=True)
    print(f"plays detected: {len(events)}", flush=True)
    print("FILL RATES: " + " | ".join(f"{a} {fr(a)}%" for a in ("down","distance","play_type","formation","result","field_position","yards_gained")), flush=True)

    res = await run_tendency_engine(SPORT, events)
    dc = res.get("data_confidence", {})
    if SPORT in ("football", "flag_football"):
        off = res.get("offense", {}); deff = res.get("defense", {}); st = res.get("special_teams", {})
        rp = off.get("run_pass_ratio", {})
        print(f"\nOFFENSE: {off.get('total_plays')} plays | run {rp.get('run_pct')}% / pass {rp.get('pass_pct')}% | "
              f"top formations {list((off.get('top_formations') or {}).items())[:4]}", flush=True)
        print(f"   play types: {list((off.get('play_type_mix') or {}).items())[:6]}", flush=True)
        pst = off.get("pre_snap_tells") or []
        print(f"   pre-snap tells found: {len(pst)}" + (f" e.g. {pst[0]}" if pst else ""), flush=True)
        print(f"DEFENSE: {deff.get('total_plays')} plays | fronts {dict(list((deff.get('fronts') or {}).items())[:3]) if deff.get('fronts') else deff.get('top_fronts')} | "
              f"coverage {deff.get('top_coverages') or deff.get('coverages')}", flush=True)
        print(f"SPECIAL TEAMS: {st.get('total_plays')} plays | units {st.get('units')}", flush=True)
        fg = st.get("field_goals", {})
        if fg.get("attempts"): print(f"   FG {fg.get('made')}/{fg.get('attempts')} by_range {fg.get('by_range')}", flush=True)
        if (st.get('punts') or {}).get('count'): print(f"   punts {st['punts']}", flush=True)
        mt = off.get("micro_tells", {})
        print(f"\nPRE-SNAP MICRO-TELLS: read on {mt.get('plays_with_a_tell',0)} plays ({mt.get('coverage_pct',0)}% coverage)", flush=True)
        if mt.get("ol_tells_vs_run_pass"):
            for tell, vals in mt["ol_tells_vs_run_pass"].items():
                print(f"   {tell}: " + " | ".join(f"{v} -> run {d['run_pct']}%/pass {d['pass_pct']}% (n={d['count']})" for v, d in vals.items()), flush=True)
        if mt.get("key_tell_examples"):
            print("   examples: " + " || ".join(str(x) for x in mt["key_tell_examples"][:3]), flush=True)
        if mt.get("db_leverage") or mt.get("lb_depth_tells"):
            print(f"   DEF tells: db_leverage={mt.get('db_leverage')} lb_depth={mt.get('lb_depth_tells')} safety={mt.get('safety_depth_tells')}", flush=True)
    else:
        so = res.get("shooting_overview", {})
        if so.get("total_shots"): print(f"SHOOTING {so['overall_fg_pct']}% | 3PT {so['three_point']['fg_pct']}% | paint {so['paint']['fg_pct']}%", flush=True)
        print(f"top zones: {list((res.get('shot_zone_map',{}).get('zones') or {}).items())[:5]}", flush=True)
    print(f"\nCONFIDENCE: band={dc.get('confidence_band')}, blind spots flagged={dc.get('blind_spot_count')}, avg={dc.get('avg_confidence')}", flush=True)

asyncio.run(main())
