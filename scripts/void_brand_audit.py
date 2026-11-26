#!/usr/bin/env python3
"""Audit user-facing VOID Music branding without removing upstream GPL attribution."""
from pathlib import Path
import hashlib
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

# Keep promotional entry points disabled, including old saved settings.
src = "app/src/main/kotlin/com/mochyy/mochymusic/"
check_file(src + "ui/screens/donate/DonatePrompt.kt", "fun DonatePromptScheduler(enabled: Boolean) = Unit", "No automatic donation prompts")
check_file(src + "ui/screens/donate/DonateSheet.kt", "fun PopupSheetState.showDonateSheet() = Unit", "No donation sheet")
check_file(src + "ui/screens/donate/SupportSheet.kt", "fun PopupSheetState.showSupportSheet() = Unit", "No support promotion")
check_file(src + "ui/screens/settings/devspace/DevSpaceData.kt", "maxAgeMs: Long = 60_000L) = Unit", "No repository telemetry")
check_file(src + "discord/PresenceActivity.kt", "PresenceButtonTarget.MOCHY -> com.mochyy.mochymusic.core.updater.DiscordUrl", "MARS presence link")
check_file(src + "core/updater/GithubUpdates.kt", 'Result.failure(IllegalStateException("Automatic updates are unavailable in this build"))', "No GitHub app update requests")
for relative, forbidden in {
    "ui/screens/donate/DonateSheet.kt": ("ko-fi.com/", "sociabuzz.com/", "buymeacoffee.com/"),
    "ui/screens/update/AboutSheet.kt": ("contributors = fetchContributors()", "stringResource(R.string.about_github)", "SectionHeader(stringResource(R.string.about_cool_contributors))"),
    "ui/screens/update/UpdateSheet.kt": ("label = stringResource(R.string.update_help_us)",),
    "ui/screens/settings/devspace/DeveloperSpaceScreen.kt": ("PlaygroundCard(stats =", "DevSpaceRepository.refresh("),
    "discord/PresenceSettings.kt": ("VOID Music on GitHub",),
}.items():
    source = (ROOT / (src + relative)).read_text(encoding="utf-8")
    for token in forbidden:
        if token in source:
            errors.append(f"Upstream promotional entry point {token!r} in {relative}")

check_file(src + "core/updater/GithubUpdates.kt", 'const val OwnerDiscordUrl = "https://discord.com/users/1472442073108971575"', "VOID owner URL")
check_file(src + "ui/screens/settings/devspace/DevProfiles.kt", "OwnerDiscordUrl", "Owner profile contact")
check_file(src + "ui/screens/update/AboutSheet.kt", "OwnerDiscordUrl", "About contact")
check_file(src + "modules/GitHubReleases.kt", "Found = Found.Unreachable", "No module release API")
# Permit only the immutable, project-owned logo PNG; no arbitrary GitHub artwork,
# API requests, repository redirects or user-supplied GitHub URLs.
logo_url = "https://raw.githubusercontent.com/voidcloit26-lab/Void-Music/2dae2d55e47ec04dab73ceca06e7ae7471106846/assets/discord/void_music.png"
logo_declaration = f'internal const val Logo = "{logo_url}"'
check_file(src + "discord/NativePresenceMapper.kt", logo_declaration, "Pinned VOID logo")
check_file(src + "discord/NativePresenceMapper.kt", "PresencePicture.Logo -> Logo", "Native VOID logo mapping")
logo_file = ROOT / "assets/discord/void_music.png"
if not logo_file.is_file():
    errors.append("Missing VOID logo PNG")
else:
    logo_bytes = logo_file.read_bytes()
    blob_header = f"blob {len(logo_bytes)}".encode("ascii") + bytes([0])
    if hashlib.sha1(blob_header + logo_bytes).hexdigest() != "48762d4d6427daed84d5c50137521357670d4a9a":
        errors.append("VOID logo PNG differs from the reviewed pinned asset")
mapper = (ROOT / (src + "discord/NativePresenceMapper.kt")).read_text(encoding="utf-8")
presence = (ROOT / (src + "discord/DiscordPresence.kt")).read_text(encoding="utf-8")
if mapper.count(logo_declaration) != 1:
    errors.append("Expected exactly one pinned VOID logo declaration")
remaining_mapper = mapper.replace(logo_declaration, "", 1).lower()
if any(host in source for source in (remaining_mapper, presence.lower()) for host in ("github.com", "githubusercontent.com")):
    errors.append("Unexpected GitHub artwork URL in native presence")
if (ROOT / ".github/FUNDING.yml").exists():
    errors.append("Upstream funding configuration present")

for helper in ("ui/screens/update/UpdateSheet.kt", "ui/screens/settings/devspace/DevStyle.kt"):
    check_file(src + helper, 'host.endsWith(".github.com")', "Block repository redirects")
about = (ROOT / (src + "ui/screens/update/AboutSheet.kt")).read_text(encoding="utf-8")
if "fetchContributors(" in about or re.search(r'https://github\\.com/[^"]+/LICENSE', about):
    errors.append("Legacy contributor lookup or repository license redirect")

if "https://github.com/" in about or "githubUser:" in about:
    errors.append("Unexpected GitHub profile/repository metadata in About")
for relative, forbidden in {
    "ui/screens/settings/ProfileScreen.kt": ('DeveloperCard(onClick = { navController.navigate("developer_space") })', 'DiscordCard(onClick = { context.openDevUrl(DiscordUrl) })'),
    "ui/screens/settings/integrations/IntegrationsScreen.kt": ('IntegrationPageSubtitle("VOID Community")',),
}.items():
    for token in forbidden:
        if token in (ROOT / (src + relative)).read_text(encoding="utf-8"):
            errors.append(f"Promotional navigation in {relative}: {token}")
check_file(src + "ui/screens/update/AboutSheet.kt", "View copyright & licenses", "Accessible legal attribution")
check_file(src + "guardian/GuardianActivationActivity.kt", "Legal & Privacy", "Pre-activation privacy notice")

print("VOID Music branding audit")
print(f"English resource checks: {len(list(english.glob('*.xml')))} files")
for warning in warnings[:10]:
    print("NOTICE:", warning)
for error in errors:
    print("ERROR:", error)
print(f"Result: {len(errors)} error(s), {len(warnings)} notice(s)")
sys.exit(1 if errors else 0)
