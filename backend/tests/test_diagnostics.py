import json
import subprocess
from unittest.mock import patch

from app import ia_network
from app.auth import get_current_admin, get_current_user
from app.main import app

PING_OK = """PING 192.168.1.20 (192.168.1.20) 56(84) bytes of data.
64 bytes from 192.168.1.20: icmp_seq=1 ttl=63 time=17.2 ms

--- 192.168.1.20 ping statistics ---
4 packets transmitted, 3 received, 25% packet loss, time 3004ms
rtt min/avg/max/mdev = 1.000/17.230/30.000/0.000 ms
"""
PING_DEAD = """--- 192.168.1.99 ping statistics ---
4 packets transmitted, 0 received, 100% packet loss, time 3070ms
"""


def done(stdout, code=0):
    return subprocess.CompletedProcess([], code, stdout=stdout, stderr="")


def test_ping_is_summed_up():
    with patch("subprocess.run", return_value=done(PING_OK)):
        result = json.loads(ia_network.ping_host({"host": "192.168.1.20"}))
    assert result["success"] is True
    assert result["loss_percent"] == 25.0
    assert result["avg_ms"] == 17.23


def test_dead_host_has_no_average():
    with patch("subprocess.run", return_value=done(PING_DEAD, 1)):
        result = json.loads(ia_network.ping_host({"host": "192.168.1.99"}))
    assert result["success"] is False
    assert result["loss_percent"] == 100.0
    assert result["avg_ms"] is None


def test_server_state_counts_the_processor_cores(client):
    res = client.get("/diagnostics/server")
    assert res.status_code == 200
    assert res.json()["cpu_count"] >= 1


def test_run_ping_by_hand(client):
    with patch("subprocess.run", return_value=done(PING_OK)) as run:
        res = client.post("/diagnostics/run", json={"tool": "ping", "host": " 192.168.1.20 "})
    assert res.status_code == 200
    assert res.json()["avg_ms"] == 17.23
    assert run.call_args.args[0][-1] == "192.168.1.20"


def test_bad_address_and_unknown_test_are_refused(client):
    with patch("subprocess.run") as run:
        assert client.post("/diagnostics/run", json={"tool": "ping", "host": "-f"}).status_code == 400
        assert client.post("/diagnostics/run", json={"tool": "ping", "host": "a;reboot"}).status_code == 400
        assert client.post("/diagnostics/run", json={"tool": "rm", "host": "example.com"}).status_code == 400
    run.assert_not_called()


def test_for_admins_only(client):
    app.dependency_overrides.pop(get_current_admin)
    app.dependency_overrides.pop(get_current_user)
    assert client.get("/diagnostics/server").status_code == 401
    assert client.post("/diagnostics/run", json={"tool": "ping", "host": "example.com"}).status_code == 401
