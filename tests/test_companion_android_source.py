import hashlib
import xml.etree.ElementTree as element_tree
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANDROID = ROOT / "companion/src-tauri/gen/android"
ATTRIBUTE = "{http://schemas.android.com/apk/res/android}"


def test_android_manifest_disables_backup_and_keeps_file_provider_private():
    manifest = element_tree.parse(ANDROID / "app/src/main/AndroidManifest.xml").getroot()
    application = manifest.find("application")
    assert application.get(ATTRIBUTE + "allowBackup") == "false"
    provider = application.find("provider")
    assert provider.get(ATTRIBUTE + "exported") == "false"
    assert provider.get(ATTRIBUTE + "grantUriPermissions") == "true"
    permissions = {node.get(ATTRIBUTE + "name") for node in manifest.findall("uses-permission")}
    assert permissions == {"android.permission.INTERNET", "com.termux.permission.RUN_COMMAND"}
    assert manifest.find('queries/package').get(ATTRIBUTE + 'name') == 'com.termux'


def test_android_gradle_wrapper_matches_published_distribution_and_bootstrap_checksums():
    wrapper = ANDROID / "gradle/wrapper"
    properties = dict(line.split("=", 1) for line in (wrapper / "gradle-wrapper.properties").read_text().splitlines()
                      if line and not line.startswith("#"))
    assert properties["distributionUrl"] == r"https\://services.gradle.org/distributions/gradle-9.6.1-bin.zip"
    assert properties["distributionSha256Sum"] == "9c0f7faeeb306cb14e4279a3e084ca6b596894089a0638e68a07c945a32c9e14"
    assert hashlib.sha256((wrapper / "gradle-wrapper.jar").read_bytes()).hexdigest() == "497c8c2a7e5031f6aa847f88104aa80a93532ec32ee17bdb8d1d2f67a194a9c7"


def test_android_launcher_assets_use_bifang_artwork_instead_of_the_template_icon():
    original = ROOT / "desktop/src-tauri/icons/android"
    resources = ANDROID / "app/src/main/res"
    assets = sorted(path for path in original.rglob("*") if path.is_file())
    assert assets
    for source in assets:
        destination = resources / source.relative_to(original)
        assert destination.read_bytes() == source.read_bytes()
