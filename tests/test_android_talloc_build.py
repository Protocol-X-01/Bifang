import hashlib
import io
import runpy
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BUILDER = runpy.run_path(str(ROOT / 'scripts/build-android-talloc.py'))


def archive_fixture(tmp_path, monkeypatch, member_name='talloc-2.5.0/talloc.c', link=None):
    archive = tmp_path / 'source.tar.gz'
    with tarfile.open(archive, 'w:gz') as stream:
        member = tarfile.TarInfo(member_name)
        if link is not None:
            member.type = tarfile.SYMTYPE
            member.linkname = link
            stream.addfile(member)
        else:
            member.size = 7
            stream.addfile(member, io.BytesIO(b'fixture'))
    monkeypatch.setitem(BUILDER['validate_source'].__globals__, 'SOURCE_SHA256',
                        hashlib.sha256(archive.read_bytes()).hexdigest())
    return archive


def test_pinned_source_digest_rejects_wrong_archive(tmp_path):
    archive = tmp_path / 'wrong.tar.gz'
    archive.write_bytes(b'not the reviewed source')
    with pytest.raises(ValueError, match='checksum'):
        BUILDER['validate_source'](archive)


def test_valid_source_members_are_accepted(tmp_path, monkeypatch):
    archive = archive_fixture(tmp_path, monkeypatch)
    BUILDER['validate_source'](archive)


@pytest.mark.parametrize('member', ['../outside', '/outside', 'talloc-2.5.0/../outside', 'other/file'])
def test_source_cannot_escape_its_pinned_directory(tmp_path, monkeypatch, member):
    archive = archive_fixture(tmp_path, monkeypatch, member_name=member)
    with pytest.raises(ValueError, match='member'):
        BUILDER['validate_source'](archive)


def test_source_links_are_rejected(tmp_path, monkeypatch):
    archive = archive_fixture(tmp_path, monkeypatch, link='../../outside')
    with pytest.raises(ValueError, match='member'):
        BUILDER['validate_source'](archive)


def test_existing_build_is_never_replaced(tmp_path):
    output = tmp_path / 'preserved'
    output.mkdir()
    marker = output / 'keep'
    marker.write_text('preserved')
    with pytest.raises(FileExistsError):
        BUILDER['build'](tmp_path / 'missing.tar.gz', tmp_path / 'missing-ndk', output)
    assert marker.read_text() == 'preserved'


def test_unreviewed_ndk_is_rejected_before_output_creation(tmp_path, monkeypatch):
    archive = archive_fixture(tmp_path, monkeypatch)
    ndk = tmp_path / 'ndk'
    ndk.mkdir()
    (ndk / 'source.properties').write_text('Pkg.Revision = 28.0.0\n')
    output = tmp_path / 'build'
    with pytest.raises(ValueError, match='NDK'):
        BUILDER['build'](archive, ndk, output)
    assert not output.exists()


def test_explicit_fill_retains_bounds_return_pointer_and_zero_length(tmp_path):
    compiler = shutil.which('cc')
    if compiler is None:
        pytest.skip('C compiler unavailable')
    harness = tmp_path / 'check.c'
    harness.write_text('''
#include <assert.h>
#include <stddef.h>
void *rep_memset_explicit(void *buffer, int value, size_t length);
int main(void) {
    unsigned char bytes[] = {7, 7, 7, 7, 7};
    assert(rep_memset_explicit(bytes + 1, 0, 3) == bytes + 1);
    assert(bytes[0] == 7 && bytes[4] == 7);
    assert(bytes[1] == 0 && bytes[2] == 0 && bytes[3] == 0);
    assert(rep_memset_explicit(bytes, 255, 0) == bytes);
    assert(bytes[0] == 7);
    rep_memset_explicit(bytes + 1, 0x1ff, 1);
    assert(bytes[1] == 255);
    return 0;
}
''')
    executable = tmp_path / 'check'
    subprocess.run([compiler, '-O3', '-Wall', '-Wextra', '-Werror', str(harness),
                    str(ROOT / 'scripts/android-talloc/replace.c'), '-o', str(executable)], check=True)
    subprocess.run([str(executable)], check=True, timeout=10)
