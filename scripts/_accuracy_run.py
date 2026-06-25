"""Deploy parallel-windows extraction, hard scale 0->1 (kill old container), run clean detection, report diag + recall."""
import asyncio, os, json, uuid, ssl, urllib.request, pathlib
import asyncpg

ACCESS = json.loads(pathlib.Path.home().joinpath(".railway/config.json").read_text())["user"]["accessToken"]
EP = "https://backboard.railway.com/graphql/v2"; CTX = ssl._create_unverified_context()
SID = "b22e6603-01f9-4414-bd5d-2a12196d2b11"; ENV = "075a9754-2c65-4803-a599-e37794b630b7"
SHA = "79393bc4d0a9eff10203793be0687c023eee71e9"
GAME = uuid.UUID("62aadc94-731c-474e-9bfa-29f148849323")
URL = os.environ["DATABASE_PUBLIC_URL"]

def gql(q):
    import time as _t
    for _ in range(5):
        r = urllib.request.Request(EP, data=json.dumps({"query": q}).encode(),
            headers={"Authorization": f"Bearer {ACCESS}", "Content-Type": "application/json",
                     "Accept": "application/json", "User-Agent": "Mozilla/5.0 rlwy"})
        try:
            with urllib.request.urlopen(r, timeout=40, context=CTX) as x:
                d = json.loads(x.read().decode())
            if "errors" not in d: return d
        except Exception as e: d = {"_exc": repr(e)}
        _t.sleep(4)
    return d

def scale(n): return "errors" not in gql(f'mutation {{ serviceInstanceUpdate(serviceId:"{SID}", environmentId:"{ENV}", input:{{numReplicas:{n}}}) }}')

async def conn():
    try: return await asyncpg.connect(URL, timeout=30)
    except Exception: return await asyncpg.connect(URL, timeout=30, ssl=CTX)

async def main():
    gql(f'mutation {{ serviceConnect(id:"{SID}",input:{{repo:"JayCoz7979/coachlenz-deploy",branch:"main"}}){{id}} }}')
    dep = (gql(f'mutation {{ serviceInstanceDeployV2(serviceId:"{SID}",environmentId:"{ENV}",commitSha:"{SHA}") }}').get("data") or {}).get("serviceInstanceDeployV2")
    print("deploy_id:", dep, flush=True)
    for _ in range(40):
        st = (gql(f'query {{ deployment(id:"{dep}"){{status}} }}').get("data") or {}).get("deployment", {}).get("status")
        print("deploy:", st, flush=True)
        if st == "SUCCESS": break
        if st in ("FAILED","CRASHED","REMOVED"): print("DEPLOY FAILED"); return
        await asyncio.sleep(30)
    # hard kill old container, bring up only the new image
    print("scale -> 0:", scale(0), flush=True); await asyncio.sleep(80)
    up = False
    for a in range(6):
        up = scale(1); print(f"scale -> 1 ({a}): {up}", flush=True)
        if up: break
        await asyncio.sleep(10)
    if not up: gql(f'mutation {{ serviceInstanceRedeploy(serviceId:"{SID}", environmentId:"{ENV}") }}'); print("fallback redeploy", flush=True)
    print("waiting 170s for boot...", flush=True); await asyncio.sleep(170)

    c = await conn()
    g = await c.fetchrow("SELECT organization_id FROM games WHERE id=$1", GAME)
    await c.execute("DELETE FROM jobs WHERE job_type='ai_detect' AND payload->>'game_id'=$1 AND status IN ('queued','running')", str(GAME))
    await c.execute("UPDATE games SET status='ready' WHERE id=$1", GAME)
    await c.execute("DELETE FROM agent_logs WHERE game_id=$1", GAME)
    jid = uuid.uuid4()
    await c.execute("INSERT INTO jobs (id,organization_id,job_type,status,payload,attempts,created_at,updated_at) VALUES ($1,$2,'ai_detect','queued',$3::jsonb,0,now(),now())",
        jid, g["organization_id"], json.dumps({"game_id": str(GAME)}))
    print(f"enqueued {jid}", flush=True)
    await c.close()

    shown = False
    for i in range(170):
        await asyncio.sleep(40)
        c = await conn()
        fe = await c.fetchrow("SELECT detail FROM agent_logs WHERE game_id=$1 AND phase='frame_extraction' ORDER BY created_at DESC LIMIT 1", GAME)
        if fe and not shown:
            d = json.loads(fe['detail']) if isinstance(fe['detail'],str) else (fe['detail'] or {})
            print("\n*** EXTRACTION DIAG ***", flush=True)
            for k in ("code_version","method","windows_total","windows_ok","windows_failed","total_frames","frame_count","ffmpeg_err"):
                if k in d: print(f"    {k}: {d[k]}", flush=True)
            shown = True
        last = await c.fetchval("SELECT action FROM agent_logs WHERE game_id=$1 ORDER BY created_at DESC LIMIT 1", GAME)
        done = await c.fetchrow("SELECT action FROM agent_logs WHERE game_id=$1 AND phase='complete' ORDER BY created_at DESC LIMIT 1", GAME)
        await c.close()
        print(f"  [{i}] {last}", flush=True)
        if done:
            c = await conn()
            rows = await c.fetch("SELECT down,distance,field_position,formation,play_type,result,yards_gained FROM events WHERE game_id=$1 AND (extra_data->>'auto_detected')='true'", GAME)
            await c.close()
            n=len(rows) or 1
            def pct(k): return round(sum(1 for r in rows if r[k] not in (None,""))/n*100,1)
            print(f"\n===== RESULT: total_plays={len(rows)} (was 62, target 100+) =====", flush=True)
            for k in ("down","distance","play_type","formation","result","field_position","yards_gained"):
                print(f"  {k:14}: {pct(k)}%", flush=True)
            break

asyncio.run(main())
