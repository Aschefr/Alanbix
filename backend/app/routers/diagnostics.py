"""Network tests and server state, run by hand by an admin. Same code as the assistant's tools."""
import json

from fastapi import APIRouter, Depends, HTTPException

from .. import auth, ia_network

router = APIRouter(prefix="/diagnostics", tags=["Diagnostics"], dependencies=[Depends(auth.get_current_admin)])


# Plain def: FastAPI runs these in a thread, so a slow traceroute does not hold up the server
@router.get("/server")
def server_state():
    return json.loads(ia_network.server_health())


@router.post("/run")
def run_test(body: dict):
    tool, host = body.get("tool"), (body.get("host") or "").strip()
    if not ia_network.sanitize_host(host):
        raise HTTPException(status_code=400, detail="Invalid address")
    if tool == "ping":
        return json.loads(ia_network.ping_host({"host": host, "count": 4}))
    if tool == "traceroute":
        return json.loads(ia_network.traceroute_host({"host": host}))
    if tool == "dns":
        return json.loads(ia_network.dns_lookup({"domain": host}))
    raise HTTPException(status_code=400, detail="Unknown test")
