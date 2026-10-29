import runpy
from pathlib import Path

import pytest

COLLECTOR = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/collect-release-notices.py"))


@pytest.mark.parametrize("package", ["libssl3", "libssl3t64"])
def test_openssl_notice_uses_existing_distribution_package_name(tmp_path, package):
    notice = tmp_path / package / "copyright"
    notice.parent.mkdir()
    notice.write_text("Synthetic distribution notice")
    assert COLLECTOR["distribution_notice_files"](tmp_path) == [(package, notice)]


def test_distribution_notices_do_not_claim_missing_or_nonfile_text(tmp_path):
    (tmp_path / "libssl3" / "copyright").mkdir(parents=True)
    unrelated = tmp_path / "unrelated" / "copyright"
    unrelated.parent.mkdir()
    unrelated.write_text("Not a selected runtime component")
    assert COLLECTOR["distribution_notice_files"](tmp_path) == []
