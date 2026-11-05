"""Takes the documentation screenshots from a demo server started with run.py.

    python scripts/docs_demo/capture.py fr            # all of them, into screenshots/fr/
    python scripts/docs_demo/capture.py en dashboard  # only one

Light theme, 1440x900 on desktop. Needs `pip install playwright pillow` and a browser
(`playwright install chromium`, or point CHROMIUM_PATH at an existing one).
"""
import io
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image
from playwright.sync_api import Error as PlaywrightError, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
PORTS = {"fr": 41590, "en": 41591}
PASSWORD = "demo-only-password"
DESKTOP = {"width": 1440, "height": 900}
PHONE = {"width": 412, "height": 892}


def token(base, name):
    data = urllib.parse.urlencode({"username": name, "password": PASSWORD}).encode()
    req = urllib.request.Request(base + "/token", data=data, headers={"Accept": "application/json"})
    return json.load(urllib.request.urlopen(req))["access_token"]


def api(base, tok, path):
    req = urllib.request.Request(base + path, headers={"Accept": "application/json", "Authorization": "Bearer " + tok})
    return json.load(urllib.request.urlopen(req))


class Shots:
    def __init__(self, browser, base, lang, only):
        self.browser, self.base, self.lang, self.only = browser, base, lang, only
        self.out = ROOT / "screenshots" / lang
        self.out.mkdir(parents=True, exist_ok=True)
        self.failed = []
        admin = token(base, "Admin")
        self.tournaments = {t["name"]: t["id"] for t in api(base, admin, "/tournaments")}
        self.users = {u["username"]: u["id"] for u in api(base, admin, "/room/users")}

    def page(self, user="PixelHunter", viewport=DESKTOP, storage=None):
        scale = 2 if viewport is PHONE else 1.5
        ctx = self.browser.new_context(viewport=viewport, device_scale_factor=scale, color_scheme="light",
                                       locale="fr-FR" if self.lang == "fr" else "en-US", has_touch=viewport is PHONE)
        values = {"alanbix_lang": self.lang, "alanbix_theme": "light", **(storage or {})}
        if user:
            values["alanbix_token"] = token(self.base, user)
        ctx.add_init_script("for (const [k, v] of Object.entries(%s)) localStorage.setItem(k, v);"
                            "sessionStorage.setItem('alanbix_notif_banner_dismissed', 'true');" % json.dumps(values))
        return ctx.new_page()

    def save(self, page, name, full_page=False):
        raw = page.screenshot(full_page=full_page, animations="disabled")
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        # 256 colours keep the interface sharp and divide the file size by about three
        img.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(self.out / f"{name}.png", optimize=True)
        print(name, f"{(self.out / f'{name}.png').stat().st_size // 1024} KB", page.url.replace(self.base, ""))

    def shot(self, name, path, user="PixelHunter", viewport=DESKTOP, storage=None, wait=1800, then=None, full_page=False):
        if self.only and name not in self.only:
            return
        page = self.page(user, viewport, storage)
        try:
            page.goto(self.base + path, wait_until="networkidle")
            page.wait_for_timeout(wait)
            if then:
                then(page)
                page.wait_for_timeout(700)
            self.save(page, name, full_page)
        except PlaywrightError as e:  # One failed shot must not lose the others; the summary lists it
            self.failed.append(name)
            print(name, "FAILED", str(e).splitlines()[0])
        page.context.close()


def zoom_at(page, x, y, ticks=3):
    page.mouse.move(x, y)
    for _ in range(ticks):
        page.mouse.wheel(0, -240)
        page.wait_for_timeout(120)


def run(s):
    t = s.tournaments
    fr = s.lang == "fr"
    admin_tab = lambda tab, sub=None: {"admin_tab": tab, **({"admin_subtab": sub} if sub else {})}
    tall = {"width": 1440, "height": 1200}

    def click_text(text, **kw):
        return lambda page: page.get_by_text(text, **kw).first.click()

    def scroll_to(selector):
        return lambda page: page.locator(selector).first.scroll_into_view_if_needed()

    def spectator(steps):
        def go(page):
            page.keyboard.press("Space")  # Pause, so the view does not move during the capture
            for _ in range(steps):
                page.keyboard.press("ArrowRight")
                page.wait_for_timeout(900)
        return go

    # Player pages
    s.shot("dashboard", "/dashboard")
    s.shot("info", "/dashboard/info", viewport=tall)
    s.shot("tournament_double_elim", f"/dashboard/tournaments/{t['Iron Arena Showdown']}", viewport=tall, then=lambda p: zoom_at(p, 900, 760, 2))
    s.shot("tournament_ffa", f"/dashboard/tournaments/{t['Neon Drift Grand Prix']}", viewport=tall, then=lambda p: zoom_at(p, 900, 760, 2))
    s.shot("tournament_round_robin", f"/dashboard/tournaments/{t['Goal Rush League']}", viewport=tall, then=lambda p: zoom_at(p, 900, 760, 2))
    s.shot("tournament_groups", f"/dashboard/tournaments/{t['Kart Frenzy Cup']}", viewport=tall, then=lambda p: zoom_at(p, 900, 760, 1))
    s.shot("tournament_teams", f"/dashboard/tournaments/{t['Rocket Duo']}", viewport=tall)
    s.shot("players", "/dashboard/players")
    s.shot("messages", f"/dashboard/players?chat={s.users['LaserCat']}")
    s.shot("notifications", "/dashboard/notifications")
    s.shot("profile", "/dashboard/profile")
    s.shot("room_plan", "/dashboard/map")
    s.shot("room_plan_zoom", "/dashboard/map", then=lambda p: zoom_at(p, 640, 430))
    s.shot("ai_assistant", "/dashboard/ai")
    s.shot("settings", "/dashboard/settings")

    # Projector
    s.shot("spectator_leaderboard", "/spectator", user="Admin", wait=2500, then=spectator(0))
    s.shot("spectator_map", "/spectator", user="Admin", wait=2500, then=spectator(2))
    s.shot("spectator_bracket", "/spectator", user="Admin", wait=2500, then=spectator(3))

    # Administration
    s.shot("admin_regie", "/dashboard/admin", user="Admin", storage=admin_tab("regie"))
    s.shot("admin_tournaments", "/dashboard/admin", user="Admin", storage=admin_tab("tournaments"))
    s.shot("admin_games", "/dashboard/admin", user="Admin", storage=admin_tab("tournaments"), then=scroll_to(".game-card"))
    s.shot("admin_players", "/dashboard/admin", user="Admin", storage=admin_tab("players"))
    s.shot("admin_settings", "/dashboard/admin", user="Admin", storage=admin_tab("settings", "general"))
    s.shot("admin_ai_settings", "/dashboard/admin", user="Admin", storage=admin_tab("settings", "ia"))
    s.shot("admin_knowledge", "/dashboard/admin", user="Admin", storage=admin_tab("settings", "ia"), then=scroll_to("#gi-knowledge"))
    s.shot("admin_danger_zone", "/dashboard/admin", user="Admin", storage=admin_tab("settings", "general"),
           then=lambda p: (p.locator("#gs-danger summary").click(), p.locator("#gs-danger").scroll_into_view_if_needed()))
    s.shot("admin_conversations", "/dashboard/admin", user="Admin", storage=admin_tab("conversations"),
           then=click_text("Le partage de fichiers ne répond pas" if fr else "The file share does not respond"))
    s.shot("admin_awards", "/dashboard/admin", user="Admin", storage=admin_tab("awards"))
    s.shot("admin_diagnostics", "/dashboard/admin", user="Admin", storage=admin_tab("diagnostics"))
    s.shot("admin_languages", "/dashboard/admin/languages", user="Admin")
    s.shot("room_plan_editor", "/dashboard/map", user="Admin",
           then=lambda p: p.locator("button.btn-secondary").filter(has_text="Éditer" if fr else "Edit").first.click())
    s.shot("setup", "/dashboard/setup", user="Admin", wait=3000, then=click_text("Jeux et tournois" if fr else "Games and tournaments"))

    # Phone
    s.shot("mobile_dashboard", "/dashboard", viewport=PHONE)
    s.shot("mobile_tournament", f"/dashboard/tournaments/{t['Iron Arena Showdown']}", viewport=PHONE)
    s.shot("mobile_messages", f"/dashboard/players?chat={s.users['LaserCat']}", viewport=PHONE, wait=2500)


def main(lang, *only):
    base = f"http://localhost:{PORTS[lang]}"
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None)
        shots = Shots(browser, base, lang, set(only))
        run(shots)
        browser.close()
    if shots.failed:
        raise SystemExit("Failed: " + ", ".join(shots.failed))


if __name__ == "__main__":
    main(*sys.argv[1:])
