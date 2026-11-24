#!/usr/bin/env python3
"""Audit user-facing VOID Music branding without removing upstream GPL attribution."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
errors = []
warnings = []

def check_file(path: str, expected: str, label: str) -> None:
    file = ROOT / path
    if not file.is_file():
        errors.append(f"{label}: missing {path}")
        return
    if expected not in file.read_text(encoding="utf-8"):
        errors.append(f"{label}: expected {expected!r} in {path}")

check_file("app/src/debug/res/values/app_name.xml", ">VOID Music</string>", "Debug launcher name")
check_file("app/src/main/res/values/app_name.xml", ">VOID Music</string>", "Main launcher name")
check_file("app/src/main/kotlin/com/mochyy/mochymusic/core/updater/GithubUpdates.kt", 'const val DiscordUrl = "https://discord.gg/marscm"', "MARS Discord URL")
check_file("app/src/main/res/values/updater_strings.xml", '<string name="developer_name">VOID</string>', "Developer identity")
check_file("app/src/main/kotlin/com/mochyy/mochymusic/ui/screens/settings/ProfileScreen.kt", 'GiantTextState("VOID"', "Profile heading")
check_file("app/src/main/kotlin/com/mochyy/mochymusic/ui/screens/recap/RecapStory.kt", 'GiantTextState("VOID"', "Recap heading")
check_file("app/src/main/kotlin/com/mochyy/mochymusic/modules/browser/ModuleFeed.kt", 'const val FeedUrl = ""', "Independent store configuration")
check_file("app/build.gradle.kts", 'applicationId = "online.voidbot.music"', "App ID")
check_file("VOID_MUSIC_ATTRIBUTION.md", "Mochy Music", "Upstream GPL attribution")

english = ROOT / "app/src/main/res/values"
text_resource = re.compile(r"<(?:string|item)\b[^>]*>([\s\S]*?)</(?:string|item)>")
brand = re.compile(r"\bmochy\b", flags=re.IGNORECASE)
allowed = ("original mochy", "mochy backups", "mochy-preserve")
for path in sorted(english.glob("*.xml")):
    contents = path.read_text(encoding="utf-8")
    for match in text_resource.finditer(contents):
        value = match.group(1)
        # Styles and resource aliases are implementation identifiers, not app-facing text.
        # In particular @style/Theme.mochy must not be treated as visible branding.
        if value.strip().startswith("@"):
            continue
        if not brand.search(value):
            continue
        line = contents.count("\n", 0, match.start()) + 1
        if any(word in value.lower() for word in allowed):
            warnings.append(f"Legal attribution or legacy storage naming: {path.name}:{line}")
        else:
            errors.append(f"Visible Mochy brand in {path.name}:{line}: {value[:95]!r}")

kotlin_cases = {
    "app/src/main/kotlin/com/mochyy/mochymusic/ui/screens/update/UpdateSheet.kt": (
        'text = "MOCHY', 'Text("Mochy"',
    ),
    "app/src/main/kotlin/com/mochyy/mochymusic/discord/PresenceText.kt": ('AppName = "Mochy"',),
    "app/src/main/kotlin/com/mochyy/mochymusic/discord/PresenceSettings.kt": (
        '"Mochy logo"', '"Mochy on GitHub"', '"Open Mochy"',
    ),
    "app/src/main/kotlin/com/mochyy/mochymusic/ui/screens/settings/integrations/discord/DiscordScreen.kt": ('hint = "Mochy"',),
    "app/src/main/kotlin/com/mochyy/mochymusic/ui/screens/settings/ProfileScreen.kt": ('GiantTextState("MOCHY"', 'R.drawable.mochy_discord'),
    "app/src/main/kotlin/com/mochyy/mochymusic/ui/screens/recap/RecapStory.kt": ('slideIn("MOCHY"', 'GiantTextState("MOCHY"'),
}
for relative, forbidden in kotlin_cases.items():
    content = (ROOT / relative).read_text(encoding="utf-8")
    for token in forbidden:
        if token in content:
            errors.append(f"Hardcoded former UI name {token!r} in {relative}")

locale_files = list((ROOT / "app/src/main/res").glob("values-*/*.xml"))
unmigrated = sum(bool(brand.search(p.read_text(encoding="utf-8"))) for p in locale_files)
if unmigrated:
    warnings.append(f"{unmigrated} translated resource files still contain legacy strings/identifiers; locale review required")

print("VOID Music branding audit")
print(f"English resource checks: {len(list(english.glob('*.xml')))} files")
for warning in warnings[:10]:
    print("NOTICE:", warning)
for error in errors:
    print("ERROR:", error)
print(f"Result: {len(errors)} error(s), {len(warnings)} notice(s)")
sys.exit(1 if errors else 0)
