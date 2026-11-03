"""Network diagnostics run from the server: used by the assistant and by the admin Diagnostic tab."""
import json
import re

# What these two show (server load, addresses seen on the network) is not for every player
ADMIN_ONLY_TOOLS = {"check_server_health", "scan_local_network"}


def sanitize_host(host: str) -> bool:
    """Return True if host is a valid IPv4, IPv6, or domain name without injection characters."""
    if not host or not isinstance(host, str):
        return False
    # Only allow characters standard for domain names or IP addresses
    # (letters, numbers, dots, hyphens)
    # A leading hyphen would be read as an option by ping and traceroute
    return bool(re.match(r"^[a-zA-Z0-9][a-zA-Z0-9.-]*$", host))


def ping_host(args: dict) -> str:
    import subprocess
    host = args.get("host", "").strip()
    if not sanitize_host(host):
        return json.dumps({"error": f"Nom d'hôte ou IP invalide: '{host}'."}, ensure_ascii=False)
    
    count = args.get("count", 4)
    try:
        count = int(count)
        if count < 1: count = 1
        if count > 10: count = 10
    except:
        count = 4
        
    try:
        res = subprocess.run(
            ["ping", "-c", str(count), "-W", "2", host],
            capture_output=True, text=True, timeout=15
        )
        return json.dumps({
            "host": host,
            "success": res.returncode == 0,
            "stdout": res.stdout,
            "stderr": res.stderr
        }, ensure_ascii=False)
    except subprocess.TimeoutExpired:
        return json.dumps({"error": "Le test de ping a expiré (timeout)."}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"Erreur lors du ping: {str(e)}"}, ensure_ascii=False)


def traceroute_host(args: dict) -> str:
    import subprocess
    host = args.get("host", "").strip()
    if not sanitize_host(host):
        return json.dumps({"error": f"Nom d'hôte ou IP invalide: '{host}'."}, ensure_ascii=False)
        
    try:
        res = subprocess.run(
            ["traceroute", "-m", "15", "-q", "1", host],
            capture_output=True, text=True, timeout=20
        )
        return json.dumps({
            "host": host,
            "stdout": res.stdout,
            "stderr": res.stderr
        }, ensure_ascii=False)
    except subprocess.TimeoutExpired:
        return json.dumps({"error": "Le traceroute a expiré."}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"Erreur lors du traceroute: {str(e)}"}, ensure_ascii=False)


def dns_lookup(args: dict) -> str:
    import socket
    domain = args.get("domain", "").strip()
    if not sanitize_host(domain):
        return json.dumps({"error": f"Nom de domaine invalide: '{domain}'."}, ensure_ascii=False)
        
    try:
        name, aliases, addresses = socket.gethostbyname_ex(domain)
        return json.dumps({
            "domain": domain,
            "canonical_name": name,
            "aliases": aliases,
            "ips": addresses
        }, ensure_ascii=False)
    except Exception as e:
        import subprocess
        try:
            res = subprocess.run(
                ["nslookup", domain],
                capture_output=True, text=True, timeout=5
            )
            return json.dumps({
                "domain": domain,
                "stdout": res.stdout,
                "stderr": res.stderr
            }, ensure_ascii=False)
        except Exception as shell_err:
            return json.dumps({"error": f"Impossible de résoudre le domaine: {str(e)} (nslookup err: {str(shell_err)})"}, ensure_ascii=False)


def server_health() -> str:
    import shutil
    import os
    
    health = {}
    
    # 1. CPU load average
    try:
        if os.path.exists("/proc/loadavg"):
            with open("/proc/loadavg", "r") as f:
                load = f.read().strip().split()
                if len(load) >= 3:
                    health["cpu_load_1m"] = float(load[0])
                    health["cpu_load_5m"] = float(load[1])
                    health["cpu_load_15m"] = float(load[2])
        else:
            loadavg = os.getloadavg()
            health["cpu_load_1m"] = loadavg[0]
            health["cpu_load_5m"] = loadavg[1]
            health["cpu_load_15m"] = loadavg[2]
    except Exception as e:
        health["cpu_load_error"] = str(e)
        
    # 2. Memory RAM Info
    try:
        if os.path.exists("/proc/meminfo"):
            mem_total = 0
            mem_free = 0
            mem_available = 0
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        key = parts[0].replace(":", "")
                        val = int(parts[1])
                        if key == "MemTotal":
                            mem_total = val
                        elif key == "MemFree":
                            mem_free = val
                        elif key == "MemAvailable":
                            mem_available = val
            health["ram_total_mb"] = round(mem_total / 1024)
            health["ram_free_mb"] = round(mem_free / 1024)
            health["ram_available_mb"] = round(mem_available / 1024)
            health["ram_used_mb"] = round((mem_total - mem_available) / 1024) if mem_available else round((mem_total - mem_free) / 1024)
        else:
            health["ram_note"] = "Info de RAM non disponible via /proc/meminfo"
    except Exception as e:
        health["ram_error"] = str(e)
        
    # 3. Disk space
    try:
        total, used, free = shutil.disk_usage("/")
        health["disk_total_gb"] = round(total / (1024**3), 1)
        health["disk_used_gb"] = round(used / (1024**3), 1)
        health["disk_free_gb"] = round(free / (1024**3), 1)
        health["disk_use_percent"] = round((used / total) * 100, 1)
    except Exception as e:
        health["disk_error"] = str(e)
        
    return json.dumps(health, ensure_ascii=False)


def scan_arp_table() -> str:
    import os
    hosts = []
    try:
        if os.path.exists("/proc/net/arp"):
            with open("/proc/net/arp", "r") as f:
                lines = f.readlines()
                for line in lines[1:]:
                    parts = line.split()
                    if len(parts) >= 6:
                        ip = parts[0]
                        mac = parts[3]
                        device = parts[5]
                        if mac != "00:00:00:00:00:00":
                            hosts.append({
                                "ip": ip,
                                "mac": mac,
                                "interface": device
                            })
        else:
            import subprocess
            res = subprocess.run(["arp", "-a"], capture_output=True, text=True, timeout=5)
            for line in res.stdout.splitlines():
                if "at" in line:
                    parts = line.split()
                    try:
                        ip = parts[1].strip("()")
                        mac = parts[3]
                        hosts.append({"ip": ip, "mac": mac})
                    except:
                        pass
    except Exception as e:
        return json.dumps({"error": f"Erreur lors du scan réseau: {str(e)}"}, ensure_ascii=False)
        
    return json.dumps({
        "hosts": hosts,
        "count": len(hosts),
        "note": "Affiche les machines connectées découvertes dans la table ARP du serveur."
    }, ensure_ascii=False)
