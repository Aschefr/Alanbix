"""
Service d'auto-découverte réseau local (LAN) pour l'application mobile compagnon Alanbix.
- Répond aux requêtes UDP broadcast sur le port 42424
- Annonce optionnelle via mDNS / Zeroconf (_alanbix._tcp.local.) si disponible
- Fournit les métadonnées pour l'endpoint HTTP GET /api/system/discovery
"""
import asyncio
import json
import logging
import os
import socket
from typing import Optional

logger = logging.getLogger(__name__)

DISCOVERY_UDP_PORT = int(os.getenv("ALANBIX_DISCOVERY_UDP_PORT", "42424"))
APP_HTTP_PORT = int(os.getenv("PORT", "41481"))


def get_local_ip() -> str:
    """Détermine l'adresse IP locale principale du serveur sur le LAN."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.5)
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


def get_app_version() -> str:
    """Lit la version courante d'Alanbix depuis le fichier VERSION."""
    for path in ["VERSION", "../VERSION", "/app/VERSION", "/VERSION"]:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return f.read().strip()
            except Exception:
                pass
    return "1.20.0"


def get_discovery_payload(event_name: str = "Alanbix LAN") -> dict:
    """Construit la charge utile JSON d'identification du serveur Alanbix."""
    hostname = socket.gethostname()
    return {
        "app": "Alanbix",
        "id": "com.amifystudio.alanbix",
        "name": event_name or f"Alanbix ({hostname})",
        "hostname": hostname,
        "ip": get_local_ip(),
        "port": APP_HTTP_PORT,
        "version": get_app_version(),
        "status": "ok",
    }


class _AlanbixDiscoveryProtocol(asyncio.DatagramProtocol):
    """Protocole UDP répondant aux sondes de découverte LAN des clients mobiles."""

    def __init__(self):
        self.transport: Optional[asyncio.DatagramTransport] = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple) -> None:
        try:
            message = data.decode("utf-8", errors="ignore").strip().upper()
            if any(token in message for token in ("ALANBIX", "DISCOVER", "PING")):
                payload = json.dumps(get_discovery_payload()).encode("utf-8")
                if self.transport:
                    self.transport.sendto(payload, addr)
        except Exception as exc:
            logger.debug("Discovery UDP datagram error: %s", exc)


class DiscoveryManager:
    """Gère le cycle de vie du serveur UDP de découverte et de l'annonce mDNS."""

    def __init__(self) -> None:
        self._udp_transport: Optional[asyncio.DatagramTransport] = None
        self._zeroconf = None
        self._zc_info = None

    async def start(self) -> None:
        if os.getenv("DISABLE_LAN_DISCOVERY", "").lower() in ("1", "true", "yes"):
            return

        # 1. Démarrage de l'écouteur UDP broadcast
        try:
            loop = asyncio.get_running_loop()
            transport, _ = await loop.create_datagram_endpoint(
                _AlanbixDiscoveryProtocol,
                local_addr=("0.0.0.0", DISCOVERY_UDP_PORT),
                allow_broadcast=True,
            )
            self._udp_transport = transport  # type: ignore[assignment]
            logger.info("Alanbix LAN UDP discovery active on port %d", DISCOVERY_UDP_PORT)
        except Exception as exc:
            logger.debug("Could not bind Alanbix UDP discovery port %d: %s", DISCOVERY_UDP_PORT, exc)

        # 2. Annonce mDNS / Bonjour (_alanbix._tcp.local.) optionnelle
        try:
            from zeroconf import ServiceInfo
            from zeroconf.asyncio import AsyncZeroconf

            ip_str = get_local_ip()
            hostname = socket.gethostname()
            self._zc_info = ServiceInfo(
                "_alanbix._tcp.local.",
                f"Alanbix-{hostname}._alanbix._tcp.local.",
                addresses=[socket.inet_aton(ip_str)],
                port=APP_HTTP_PORT,
                properties={
                    "app": "Alanbix",
                    "version": get_app_version(),
                    "hostname": hostname,
                },
                server=f"{hostname}.local.",
            )
            self._zeroconf = AsyncZeroconf()
            await self._zeroconf.async_register_service(self._zc_info)
            logger.info("Alanbix mDNS service registered as _alanbix._tcp.local.")
        except ImportError:
            pass
        except Exception as exc:
            logger.debug("Alanbix mDNS registration skipped: %s", exc)

    async def stop(self) -> None:
        if self._udp_transport is not None:
            try:
                self._udp_transport.close()
            except Exception:
                pass
            self._udp_transport = None

        if self._zeroconf is not None:
            try:
                if self._zc_info is not None:
                    await self._zeroconf.async_unregister_service(self._zc_info)
                await self._zeroconf.async_close()
            except Exception:
                pass
            self._zeroconf = None
            self._zc_info = None


discovery_manager = DiscoveryManager()

