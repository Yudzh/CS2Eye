"""Read-only real-data audit. Run with DEBUG=false .venv/bin/python scripts/check_map_strength_v35.py."""
import asyncio
import json
from datetime import date
from pathlib import Path
import httpx
from sqlalchemy import select
from cs2eye.db.session import AsyncSessionLocal, engine
from cs2eye.models.team import Team
from cs2eye.services.map_strength_v3_service import MapStrengthV3Service, sanity_check
from cs2eye.services.team_strength_v3_service import _json_safe

async def main():
    report={"as_of":str(date.today()),"teams":[],"temporary_roster":None}
    async with AsyncSessionLocal() as session:
        service=MapStrengthV3Service(session)
        async with httpx.AsyncClient(base_url="http://localhost:8000",timeout=180) as client:
            for tid in (3,1,6,9,2):
                team=await session.get(Team,tid)
                pool=await service.pool(tid)
                response=await client.get(f"/api/v1/analysis/teams/{tid}/maps",params={"aggregation_level":"current_roster","include_inactive_maps":"true"})
                response.raise_for_status()
                legacy={x["map_name"]:x["strength"]["map_strength_score"] for x in response.json()["maps"]}
                for item in pool["maps"]:
                    sanity_check(item)
                    item["legacy_score"]=legacy.get(item["map"])
                baseline_response=await client.get(f"/api/v1/teams/{tid}/strength-v3")
                baseline_response.raise_for_status()
                assert all(m["team_strength_v3"] == baseline_response.json()["score"] for m in pool["maps"])
                report["teams"].append({"id":tid,"name":team.name,"maps":pool["maps"]})
                print(team.name,len(pool["maps"]),"maps checked",flush=True)
            report["temporary_roster"]=await service.pool(3,tournament_id=7)
            sample=next(x for x in report["teams"][0]["maps"] if x["map"]=="nuke")
            response=await client.get("/api/v1/analysis/teams/3/maps-v3/nuke")
            response.raise_for_status()
            api=response.json()["map_strength_v3"]
            assert api["score"]==sample["score"] and api["delta_vs_team"]==sample["delta_vs_team"]
            manual=round(sum(c["score"]*c["effective_weight"] for c in sample["components"].values() if c["score"] is not None),2)
            assert manual==api["score"]
            report["manual"]={"team":"Vitality","map":"nuke","components":sample["components"],"score":manual,"api_score":api["score"],"team_strength":api["team_strength_v3"],"delta":api["delta_vs_team"]}
    out=Path("docs/MAP_STRENGTH_V35_REAL_DATA.json")
    out.write_text(json.dumps(_json_safe(report),ensure_ascii=False,indent=2,allow_nan=False)+"\n")
    print(out,flush=True)
    await engine.dispose()

if __name__=="__main__": asyncio.run(main())
