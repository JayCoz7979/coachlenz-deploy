"""Run detection + the elite basketball tendency engine on a LOCAL game file. No Railway."""
import os, sys, asyncio, json, re, subprocess, tempfile, shutil, pathlib
sys.path.insert(0, r"C:\Users\jason\coachlenz-deploy\.claude\worktrees\silly-curie-38af50")

for line in (pathlib.Path.home()/".cl_detect.env").read_text(encoding="utf-8", errors="ignore").splitlines():
    if "=" in line and not line.lstrip().startswith("#"):
        k, v = line.split("=", 1); os.environ[k] = v
os.environ["DATABASE_URL"] = "postgresql+asyncpg://u:p@localhost/x"
os.environ.setdefault("SECRET_KEY", "x"); os.environ.setdefault("FERNET_KEY", "x")

import imageio_ffmpeg
_ffdir = tempfile.mkdtemp()
FFMPEG = os.path.join(_ffdir, "ffmpeg.exe")
shutil.copy(imageio_ffmpeg.get_ffmpeg_exe(), FFMPEG)
os.environ["PATH"] = _ffdir + os.pathsep + os.environ["PATH"]

# Local SSL is intercepted (Norton/VPN) → make the Anthropic client skip cert verify for this one-off run.
import anthropic, httpx
_orig_anthropic = anthropic.AsyncAnthropic
anthropic.AsyncAnthropic = lambda *a, **k: _orig_anthropic(*a, **{**k, "http_client": httpx.AsyncClient(verify=False, timeout=180)})

from types import SimpleNamespace as NS
from backend.workers.worker_ai_detect import AiDetectWorker, CODE_VERSION, FRAMES_PER_BATCH
from backend.services.tendency_engine.basketball import analyze_basketball

VIDEO = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\jason\auburn_duke.mp4"

def duration_of(path):
    out = subprocess.run([FFMPEG, "-i", path], capture_output=True, text=True).stderr
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", out)
    if not m: return 0.0
    h, mi, s = m.groups(); return int(h)*3600 + int(mi)*60 + float(s)

def E(p):
    return NS(event_type=p.get("event_type", "shot"), side=(p.get("side") or "offense"),
              result=p.get("result"), yards_gained=None, play_type=p.get("play_type"),
              extra_data={**p, "confidence": p.get("confidence", 0.8)})

async def main():
    print(f"LOCAL BASKETBALL — code_version={CODE_VERSION}\nfile: {VIDEO}", flush=True)
    dur = duration_of(VIDEO)
    print(f"duration: {dur/60:.1f} min", flush=True)
    w = AiDetectWorker()
    with tempfile.TemporaryDirectory() as td:
        frames = await w._extract_windows(VIDEO, dur, td)
        print(f"frames extracted: {len(frames)}  diag={getattr(w,'_extract_diag',{})}", flush=True)
        batches = [frames[i:i+FRAMES_PER_BATCH] for i in range(0, len(frames), FRAMES_PER_BATCH)]
        all_plays = []
        for bi, b in enumerate(batches):
            try:
                all_plays.extend(await w._analyze_batch(b, bi, len(batches), "basketball"))
            except Exception as e:
                print(f"  batch {bi} err {str(e)[:100]}", flush=True)
            if bi % 25 == 0:
                print(f"  vision {bi}/{len(batches)} events={len(all_plays)}", flush=True)
        deduped = w._deduplicate_plays(all_plays)

    events = [E(p) for p in deduped]
    r = analyze_basketball(events)

    def line(s): print(s, flush=True)
    line(f"\n================ ELITE BASKETBALL ANALYSIS — Auburn vs Duke ================")
    line(f"possessions/events detected: {r.get('total_plays')}  (offense {r.get('offense_plays')}, defense {r.get('defense_plays')})")
    so = r.get("shooting_overview", {})
    if so.get("total_shots"):
        line(f"\nSHOOTING: {so['total_made']}/{so['total_shots']} = {so['overall_fg_pct']}% FG | "
             f"3PT {so['three_point']['made']}/{so['three_point']['attempts']} ({so['three_point']['fg_pct']}%) | "
             f"paint {so['paint']['fg_pct']}% | mid {so['mid_range']['fg_pct']}%")
    sz = r.get("shot_zone_map", {})
    if sz.get("zones"):
        line(f"\nSHOT ZONES (hottest={sz.get('hottest_zone')}, most-used={sz.get('most_frequent_zone')}):")
        for z, v in list(sz["zones"].items())[:6]:
            line(f"   {z:18}: {v['attempts']:3} att, {v['fg_pct']}% FG, {v['pct_of_all_shots']}% of shots")
    pnr = r.get("pick_and_roll", {})
    if pnr.get("total_pnr"):
        line(f"\nPICK & ROLL: {pnr['total_pnr']} poss, roll {pnr['roll_pct']}%, FG {pnr['fg_pct']}%, pref {pnr.get('preferred_position')}")
    for key, label in [("isolation","ISOLATION"),("post_up","POST-UP"),("transition","TRANSITION"),("paint_and_drive","DRIVE/PAINT")]:
        b = r.get(key, {})
        if b and b.get("total") not in (0, None) or (b and any(b.values())):
            line(f"{label}: {json.dumps({k:v for k,v in b.items() if not isinstance(v,dict)})[:140]}")
    ds = r.get("defensive_scheme", {})
    if ds.get("total"):
        line(f"\nOPP DEFENSE: primary={ds.get('primary_scheme')}, man {ds.get('man_pct')}%, zone {ds.get('zone_pct')}%, press {ds.get('press_count')}")
    bsd = r.get("ball_screen_defense", {})
    if bsd.get("total"):
        line(f"BALL-SCREEN D: primary hedge={bsd.get('primary_hedge')}, dist={bsd.get('hedge_distribution')}")
    clutch = r.get("clutch", {})
    if clutch.get("clutch_possessions"):
        line(f"CLUTCH: {clutch['clutch_possessions']} poss, {clutch['fg_pct']}% FG, best action={clutch.get('best_clutch_action')}")
    dc = r.get("data_confidence", {})
    if dc:
        line(f"\nCONFIDENCE: band={dc.get('confidence_band')}, blind spots flagged={dc.get('blind_spot_count')}")

asyncio.run(main())
