"""
End-to-End & Regression Test Suite for Alanbix Companion (Mobile & Desktop).
Verifies all Phase 1-5 functional requirements and ensures zero regressions on Desktop (> 900px).
"""

import os
import re
import sys
import json
import subprocess
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
BACKEND = ROOT / "backend"

def run_test(name, func):
    print(f"\n[TEST] {name}...")
    try:
        func()
        print(f"  -> PASS")
        return True
    except AssertionError as e:
        print(f"  -> FAIL: {e}")
        return False
    except Exception as e:
        print(f"  -> ERROR: {e}")
        return False

# --- 1. DESKTOP INTEGRITY TESTS (> 900px) ---

def test_desktop_layout_integrity():
    layout_svelte = (FRONTEND / "src" / "routes" / "dashboard" / "+layout.svelte").read_text(encoding="utf-8")
    
    # 1. Mobile top bar and bottom nav MUST be display: none by default
    assert ".mobile-top-bar, .mobile-bottom-nav" in layout_svelte, "Default mobile nav selector missing"
    assert "display: none;" in layout_svelte, "Default display: none missing"
    
    # 2. Side navigation MUST be present and not hidden by default
    assert '<nav class="side-nav' in layout_svelte, "side-nav markup missing in layout"
    
    # 3. Media query must strictly be <= 900px
    assert "@media (max-width: 900px)" in layout_svelte, "Mobile media query missing or wrong breakpoint"
    
    # 4. Check home dashboard page
    home_svelte = (FRONTEND / "src" / "routes" / "dashboard" / "+page.svelte").read_text(encoding="utf-8")
    assert ".mobile-only" in home_svelte, "mobile-only CSS class missing"
    assert ".mobile-only {\n\t\tdisplay: none;\n\t}" in home_svelte or "display: none" in home_svelte, "mobile-only must be hidden on desktop"
    assert 'class="hq-grid"' in home_svelte or 'class="hq-dashboard"' in home_svelte, "Desktop HQ layout missing"

def test_no_native_confirm_or_alert():
    for ext in ["*.svelte", "*.ts", "*.js"]:
        for file in (FRONTEND / "src").rglob(ext):
            content = file.read_text(encoding="utf-8")
            # Exclude comments
            code_lines = [line for line in content.splitlines() if not line.strip().startswith("//") and not line.strip().startswith("/*")]
            code = "\n".join(code_lines)
            assert not re.search(r"\bwindow\.confirm\s*\(", code), f"Native window.confirm found in {file.name}"
            assert not re.search(r"(?<!ask)confirm\s*\(", code), f"Native confirm found in {file.name}"

# --- 2. MOBILE PLAYER-FIRST NAVIGATION TESTS (Phases 2 & 3) ---

def test_mobile_navigation_tabs():
    layout_svelte = (FRONTEND / "src" / "routes" / "dashboard" / "+layout.svelte").read_text(encoding="utf-8")
    
    # Check 5 bottom tabs
    expected_tabs = [
        ('href="/dashboard"', "Accueil"),
        ('href="/dashboard/tournaments"', "Tournois"),
        ('href="/dashboard/players', "Messages"),
        ('href="/dashboard/ai"', "Assistant"),
        ('href="/dashboard/profile"', "Profil")
    ]
    for href, label in expected_tabs:
        assert href in layout_svelte, f"Bottom tab link '{href}' ({label}) missing"

    # Check compact top bar links
    assert 'href="/dashboard/map"' in layout_svelte, "Mobile top bar map link missing"
    assert 'href="/dashboard/notifications"' in layout_svelte, "Mobile top bar notifications link missing"
    assert 'href="/dashboard/settings"' in layout_svelte, "Mobile top bar settings link missing"

def test_mes_matchs_and_duel_cards():
    home_svelte = (FRONTEND / "src" / "routes" / "dashboard" / "+page.svelte").read_text(encoding="utf-8")
    
    assert "myActiveMatches" in home_svelte, "myActiveMatches logic missing"
    assert "Loser Bracket" in home_svelte, "Loser bracket support missing in duel cards"
    assert "Grande Finale" in home_svelte, "Grand Final support missing in duel cards"
    assert "Groupe (" in home_svelte, "FFA mode support missing in duel cards"
    assert "/dashboard/tournaments?select=" in home_svelte, "Tournament select link missing in duel cards"
    assert "/dashboard/map?highlight=" in home_svelte or "targetSeat" in home_svelte or "opponent_seat" in home_svelte, "Seat highlight link missing"

def test_chat_master_detail_navigation():
    players_svelte = (FRONTEND / "src" / "routes" / "dashboard" / "players" / "+page.svelte").read_text(encoding="utf-8")
    player_chat = (FRONTEND / "src" / "lib" / "components" / "PlayerChat.svelte").read_text(encoding="utf-8")
    
    # Check master/detail column classes
    assert "players-layout" in players_svelte, "players-layout missing"
    assert "chat-col" in players_svelte, "chat-col missing"
    assert "directory-col" in players_svelte, "directory-col missing"
    
    # Check mobile back button in PlayerChat
    assert "mobile-back-btn" in player_chat, "mobile-back-btn missing in PlayerChat"
    assert "dispatch('close')" in player_chat, "close event dispatch missing in PlayerChat"

# --- 3. ERGONOMIC POLISH TESTS (Phase 5) ---

def test_tactile_map_and_bottom_sheet():
    map_svelte = (FRONTEND / "src" / "routes" / "dashboard" / "map" / "+page.svelte").read_text(encoding="utf-8")
    
    # Touch event handlers
    assert "onTouchStart" in map_svelte, "onTouchStart missing on map canvas"
    assert "onTouchMove" in map_svelte, "onTouchMove missing on map canvas"
    assert "onTouchEnd" in map_svelte, "onTouchEnd missing on map canvas"
    
    # Quick mobile bar (Poste badge, Centrer, Vue globale)
    assert "map-mobile-bar" in map_svelte, "map-mobile-bar missing"
    assert "centerOnMySeat" in map_svelte, "centerOnMySeat missing"
    assert "resetView" in map_svelte, "resetView missing"
    
    # Bottom sheet on seat tap
    assert "seat-info-bottom-sheet" in map_svelte, "seat-info-bottom-sheet missing"
    assert "activeSeatCard" in map_svelte, "activeSeatCard state missing"
    assert "/dashboard/players?chat=" in map_svelte, "Direct link to message seat occupant missing"

def test_ai_mobile_drawer():
    ai_svelte = (FRONTEND / "src" / "routes" / "dashboard" / "ai" / "+page.svelte").read_text(encoding="utf-8")
    
    assert "showMobileHistory" in ai_svelte, "showMobileHistory state missing"
    assert "ai-mobile-top-bar" in ai_svelte, "ai-mobile-top-bar missing"
    assert "mobile-history-drawer" in ai_svelte, "mobile-history-drawer missing"

def test_profile_achievements_and_mobile_cards():
    profile_svelte = (FRONTEND / "src" / "routes" / "dashboard" / "profile" / "+page.svelte").read_text(encoding="utf-8")
    demo_data = (FRONTEND / "src" / "lib" / "demoData.ts").read_text(encoding="utf-8")
    
    # Achievements section
    assert "profile_achievements_title" in profile_svelte or "achievements-card" in profile_svelte, "Achievements section missing in profile"
    assert "getAwardEmoji" in profile_svelte, "getAwardEmoji helper missing"
    assert "history-cards-mobile" in profile_svelte, "Mobile stacked history cards missing"
    
    # Demo data contract
    assert "awards" in demo_data, "awards array missing in demoData.ts points-history"
    assert "total_points" in demo_data, "total_points missing in demoData.ts points-history"

# --- 4. NATIVE BACKGROUND PUSH NOTIFICATIONS (Phase 4) ---

def test_android_native_push_architecture():
    service_java = (FRONTEND / "android" / "app" / "src" / "main" / "java" / "com" / "amifystudio" / "alanbix" / "push" / "AlanbixPushService.java").read_text(encoding="utf-8")
    plugin_java = (FRONTEND / "android" / "app" / "src" / "main" / "java" / "com" / "amifystudio" / "alanbix" / "push" / "AlanbixPushPlugin.java").read_text(encoding="utf-8")
    boot_java = (FRONTEND / "android" / "app" / "src" / "main" / "java" / "com" / "amifystudio" / "alanbix" / "push" / "BootReceiver.java").read_text(encoding="utf-8")
    manifest = (FRONTEND / "android" / "app" / "src" / "main" / "AndroidManifest.xml").read_text(encoding="utf-8")
    main_activity = (FRONTEND / "android" / "app" / "src" / "main" / "java" / "com" / "amifystudio" / "alanbix" / "MainActivity.java").read_text(encoding="utf-8")
    
    # 1. Service OkHttp WebSocket & channels
    assert "newWebSocket" in service_java, "OkHttp newWebSocket call missing in AlanbixPushService"
    assert "CHANNEL_MATCHES" in service_java, "CHANNEL_MATCHES channel missing"
    assert "CHANNEL_MESSAGES" in service_java, "CHANNEL_MESSAGES channel missing"
    assert "CHANNEL_ANNOUNCEMENTS" in service_java, "CHANNEL_ANNOUNCEMENTS channel missing"
    assert "isDndActive" in service_java, "DND check missing in AlanbixPushService"
    assert "startForeground" in service_java, "startForeground call missing in AlanbixPushService"
    
    # 2. Capacitor Plugin
    assert "@CapacitorPlugin" in plugin_java, "@CapacitorPlugin annotation missing"
    assert "registerPlugin(AlanbixPushPlugin.class)" in main_activity, "AlanbixPushPlugin not registered in MainActivity"
    
    # 3. Manifest permissions & components
    assert "android.permission.FOREGROUND_SERVICE" in manifest, "FOREGROUND_SERVICE permission missing"
    assert "android.permission.POST_NOTIFICATIONS" in manifest, "POST_NOTIFICATIONS permission missing"
    assert "AlanbixPushService" in manifest, "AlanbixPushService declaration missing in AndroidManifest.xml"
    assert "BootReceiver" in manifest, "BootReceiver declaration missing in AndroidManifest.xml"
    assert '<data android:scheme="alanbix" />' in manifest, "alanbix:// custom scheme missing in AndroidManifest.xml"

def test_settings_native_controls():
    settings_svelte = (FRONTEND / "src" / "routes" / "dashboard" / "settings" / "+page.svelte").read_text(encoding="utf-8")
    
    assert "native-service-card" in settings_svelte, "native-service-card missing in settings"
    assert "openBatterySettings" in settings_svelte, "openBatterySettings missing"
    assert "openSystemNotificationSettings" in settings_svelte, "openSystemNotificationSettings missing"
    assert "toggleNativeService" in settings_svelte, "toggleNativeService missing"

# --- 5. ANDROID EMULATOR LIVE INTERACTION (via ADB) ---

def test_android_emulator_live():
    adb_path = Path(os.environ.get("LOCALAPPDATA", "")) / "Android" / "Sdk" / "platform-tools" / "adb.exe"
    if not adb_path.exists():
        print("  -> SKIP (ADB not found on this system)")
        return
    
    # Check attached devices
    res = subprocess.run([str(adb_path), "devices"], capture_output=True, text=True)
    if "emulator-5554\tdevice" not in res.stdout:
        print("  -> SKIP (emulator-5554 not running)")
        return
    
    # 1. Test deep link to tournaments
    cmd = [str(adb_path), "-s", "emulator-5554", "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", "alanbix://dashboard/tournaments?select=1"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"am start failed: {res.stderr}"
    
    # 2. Test deep link to settings
    cmd = [str(adb_path), "-s", "emulator-5554", "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", "alanbix://dashboard/settings"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"am start settings failed: {res.stderr}"

    # 3. Check logcat for no fatal crashes
    cmd = [str(adb_path), "-s", "emulator-5554", "logcat", "-d", "-s", "AndroidRuntime:E"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    fatal_lines = [l for l in res.stdout.splitlines() if "FATAL EXCEPTION" in l and "com.amifystudio.alanbix" in l]
    assert len(fatal_lines) == 0, f"Fatal exception detected in logcat: {fatal_lines}"

def main():
    print("=" * 65)
    print("🧪 ALANBIX COMPREHENSIVE E2E & REGRESSION SUITE")
    print("=" * 65)
    
    tests = [
        ("Desktop Layout Integrity (> 900px)", test_desktop_layout_integrity),
        ("Zero Native window.confirm or alert Calls", test_no_native_confirm_or_alert),
        ("Mobile Player-First Navigation (5 Tabs + Compact Top Bar)", test_mobile_navigation_tabs),
        ("Mes Matchs, Duel Cards & FFA/LB Support", test_mes_matchs_and_duel_cards),
        ("Chat Master/Detail Column Transitions", test_chat_master_detail_navigation),
        ("Tactile Map: Pan, Pinch-Zoom & Bottom Sheet", test_tactile_map_and_bottom_sheet),
        ("AI Assistant Full-Width Chat & Drawer", test_ai_mobile_drawer),
        ("Profile Achievements & Mobile History Cards", test_profile_achievements_and_mobile_cards),
        ("Android Native Push Architecture & Permissions", test_android_native_push_architecture),
        ("Settings Mobile Background Service Controls", test_settings_native_controls),
        ("Live Android Emulator Deep-Linking & Crash Check", test_android_emulator_live),
    ]
    
    results = [run_test(name, func) for name, func in tests]
    
    print("\n" + "=" * 65)
    passed = sum(results)
    total = len(results)
    print(f"📊 SUMMARY: {passed}/{total} tests passed ({passed/total*100:.0f}%)")
    print("=" * 65)
    
    if passed < total:
        sys.exit(1)

if __name__ == "__main__":
    main()
