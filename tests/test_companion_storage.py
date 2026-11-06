"""Shared-storage policy with real synthetic links; no Android device or downloads."""
import errno
import importlib.util
import json
import os
import time
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1] / 'companion/src-tauri/gen/android/app/src/main/assets/bifang_runtime.py'
spec = importlib.util.spec_from_file_location('bifang_storage_runtime', SOURCE)
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


@pytest.fixture
def storage(tmp_path, monkeypatch):
    home, shared = (tmp_path / name for name in ('home', 'shared'))
    base = home / '.local/share/bifang-distros'
    (home / 'storage').mkdir(parents=True)
    shared.mkdir()
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setattr(runtime, 'STORAGE_ROOT', shared)
    monkeypatch.setattr(runtime, 'BASE', base)
    for name, folder in runtime.STORAGE_FOLDERS.items():
        target = shared / folder
        target.mkdir(exist_ok=True)
        (home / 'storage' / name).symlink_to(target, target_is_directory=True)
    runtime.rootfs('debian').mkdir(parents=True)
    return home, shared


def test_status_is_read_only_and_login_does_not_implicitly_share(storage, monkeypatch):
    home, shared = storage
    monkeypatch.setattr(runtime.subprocess, 'run', lambda *args, **kwargs: pytest.fail('No storage setup command is allowed'))
    before = sorted(str(p) for p in home.parent.rglob('*'))
    result = runtime.Runtime().dispatch({'action': 'storage_status'})
    assert result['state'] == 'ready'
    assert result['aliases']['downloads'] == str(shared / 'Download')
    assert '--bind' not in runtime.login_command('debian')
    assert sorted(str(p) for p in home.parent.rglob('*')) == before


def test_status_does_not_create_storage_or_public_folders(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path))
    result = runtime.storage_status()
    assert result['state'] == 'unavailable' and result['aliases'] == {}
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('identity,guest_home', [('debian', '/root'), ('termux', '/data/data/com.termux/files/home')])
def test_opted_in_isolated_login_binds_each_approved_folder(storage, identity, guest_home):
    home, shared = storage
    runtime.rootfs(identity).mkdir(parents=True, exist_ok=True)
    command = runtime.login_command(identity, shared_storage=True)
    assert '--isolated' in command
    assert command[-2:] == [identity, '--']
    assert command[command.index('--work-dir') + 1] == guest_home
    binds = [command[i + 1] for i, value in enumerate(command) if value == '--bind']
    assert f'{shared}:/sdcard' in binds
    assert f'{shared / "Download"}:{guest_home}/storage/downloads' in binds
    assert len(binds) == len(runtime.STORAGE_FOLDERS) + 1
    assert not any(str(home) in bind for bind in binds)


def test_denial_and_revocation_remove_all_new_login_binds(storage, monkeypatch):
    assert '--bind' in runtime.login_command('debian', shared_storage=True)
    monkeypatch.setattr(runtime.os, 'access', lambda *_: False)
    assert runtime.storage_status()['aliases'] == {}
    assert runtime.storage_status()['state'] == 'unavailable'
    assert '--bind' not in runtime.login_command('debian', shared_storage=True)


def test_only_accessible_known_aliases_are_exported(storage, monkeypatch):
    home, shared = storage
    monkeypatch.setattr(runtime.os, 'access', lambda path, *_: path == shared / 'Download')
    (home / 'storage' / 'private').symlink_to(home)
    command = runtime.login_command('debian', shared_storage=True)
    binds = [command[i + 1] for i, arg in enumerate(command) if arg == '--bind']
    assert binds == [f'{shared / "Download"}:/root/storage/downloads']
    assert runtime.storage_status()['state'] == 'partial'


@pytest.mark.parametrize('attack', ['private_alias', 'public_target_redirect', 'storage_redirect', 'dangling_alias', 'alias_loop'])
def test_unsafe_or_broken_links_never_export_private_home(storage, attack):
    home, shared = storage
    private = home / '.ssh'
    private.mkdir()
    (private / 'keep').write_text('synthetic')
    link = home / 'storage/downloads'
    if attack == 'storage_redirect':
        (home / 'storage').rename(home / 'previous-storage')
        (home / 'storage').symlink_to(home / 'previous-storage')
    elif attack == 'public_target_redirect':
        (shared / 'Download').rmdir()
        (shared / 'Download').symlink_to(private)
    else:
        link.unlink()
        link.symlink_to(private if attack == 'private_alias' else home / 'missing' if attack == 'dangling_alias' else link)
    report = runtime.storage_status()
    assert 'downloads' not in report['aliases']
    binds = runtime.storage_bindings('debian')
    assert not any(str(private) in bind or str(home / 'storage') in bind for bind in binds)
    assert (private / 'keep').read_text() == 'synthetic'


def test_existing_guest_files_directories_and_links_are_preserved(storage):
    home, shared = storage
    guest = runtime.rootfs('debian')
    target = guest / 'root/storage'
    target.mkdir(parents=True)
    (target / 'downloads').write_text('keep file')
    (target / 'documents').mkdir()
    (target / 'documents/keep').write_text('keep directory')
    (target / 'music').symlink_to(home)
    (guest / 'sdcard').symlink_to('/storage/emulated/0')
    binds = runtime.storage_bindings('debian')
    assert f'{shared}:/mnt/bifang-shared' in binds
    assert not any(bind.endswith(('/storage/downloads', '/storage/documents', '/storage/music', ':/sdcard')) for bind in binds)
    assert (target / 'downloads').read_text() == 'keep file'
    assert (target / 'documents/keep').read_text() == 'keep directory'
    assert os.readlink(target / 'music') == str(home)
    assert os.readlink(guest / 'sdcard') == '/storage/emulated/0'


def test_linked_guest_storage_is_not_followed(storage):
    home, _ = storage
    guest = runtime.rootfs('debian')
    (guest / 'root').mkdir()
    (guest / 'root/storage').symlink_to(home)
    binds = runtime.storage_bindings('debian')
    assert all('/root/storage/' not in value for value in binds)
    assert not (home / 'downloads').exists()


def test_linked_rootfs_cannot_receive_mount_placeholders(storage, capsys):
    home, _ = storage
    guest = runtime.rootfs('alpine')
    guest.symlink_to(home)
    command = runtime.login_command('alpine', shared_storage=True)
    assert '--isolated' in command and '--bind' not in command
    assert 'distribution storage is linked or unavailable' in capsys.readouterr().out
    assert not (home / 'root').exists()


def test_linked_runtime_parent_cannot_write_into_private_home(storage, capsys):
    home, _ = storage
    parent = runtime.BASE / 'runtime'
    parent.rename(runtime.BASE / 'previous-runtime')
    private = home / '.ssh'
    (private / 'installed-rootfs/debian').mkdir(parents=True)
    parent.symlink_to(private)
    command = runtime.login_command('debian', shared_storage=True)
    assert '--isolated' in command and '--bind' not in command
    assert 'distribution storage is linked or unavailable' in capsys.readouterr().out
    assert not (private / 'installed-rootfs/debian/root').exists()


@pytest.mark.parametrize('linked', ['rootfs', 'runtime'])
def test_linked_storage_still_opens_isolated_shell_without_binds_or_rootfs_writes(storage, monkeypatch, capfd, linked):
    home, _ = storage
    guest = runtime.rootfs('debian')
    if linked == 'rootfs':
        guest.rename(home / 'guest')
        guest.symlink_to(home / 'guest')
    else:
        parent = runtime.BASE / 'runtime'
        parent.rename(home / 'private-runtime')
        parent.symlink_to(home / 'private-runtime')
    (guest / '.bifang-ready').write_text('{}')
    prefix = home / 'prefix'
    (prefix / 'bin').mkdir(parents=True)
    (prefix / 'bin/bash').symlink_to('/bin/sh')
    (runtime.BASE / 'proot-distro-v4').write_text(
        'printf \'%s\\n\' "$@" > "$HOME/linked-launch"\n'
        'IFS= read -r line\n'
        'printf \'linked-shell-input:%s\\n\' "$line"\n'
    )
    monkeypatch.setattr(runtime, 'PREFIX', prefix)
    before = sorted(str(path.relative_to(guest)) for path in guest.rglob('*'))
    service = runtime.Runtime()
    with capfd.disabled():
        opened = service.open({'environment': 'debian', 'operation': 'login', 'confirmed': True,
                               'shared_storage': True, 'rows': 24, 'cols': 80})
    try:
        service.dispatch({'action': 'terminal_write', 'id': opened['id'], 'data': list(b'ping\n')})
        output = bytearray()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            frame = service.dispatch({'action': 'terminal_read', 'id': opened['id']})
            output.extend(frame['data'])
            if frame['exited']:
                break
            time.sleep(0.01)
        assert frame['exited'] and frame['exit_code'] == 0
        assert b'linked-shell-input:ping' in output
        assert b'distribution storage is linked or unavailable' in output
        arguments = (home / 'linked-launch').read_text().splitlines()
        assert '--isolated' in arguments and '--bind' not in arguments
        assert sorted(str(path.relative_to(guest)) for path in guest.rglob('*')) == before
    finally:
        service.close()


@pytest.mark.parametrize('approved', [False, True])
def test_terminal_open_carries_explicit_storage_opt_in_into_real_pty(storage, monkeypatch, approved):
    home, _ = storage
    record = home / 'launch.json'

    def login(identity, command=None, shared_storage=False):
        record.write_text(json.dumps({'identity': identity, 'shared_storage': shared_storage}))
        return ['/bin/sh', '-c', 'printf storage-launch-ok']

    monkeypatch.setattr(runtime, 'ready', lambda _: True)
    monkeypatch.setattr(runtime, 'login_command', login)
    service = runtime.Runtime()
    opened = service.open({'environment': 'debian', 'operation': 'login', 'confirmed': True,
                           'shared_storage': approved, 'rows': 24, 'cols': 80})
    try:
        output = bytearray()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            frame = service.dispatch({'action': 'terminal_read', 'id': opened['id']})
            output.extend(frame['data'])
            if frame['exited']:
                break
            time.sleep(0.01)
        assert frame['exited'] and frame['exit_code'] == 0
        assert b'storage-launch-ok' in output
        assert json.loads(record.read_text()) == {'identity': 'debian', 'shared_storage': approved}
    finally:
        service.close()


@pytest.mark.parametrize('operation,error_type,error_number,target', [
    ('is_symlink', PermissionError, errno.EACCES, 'root/storage/downloads'),
    ('iterdir', PermissionError, errno.EACCES, 'root/storage/downloads'),
    ('mkdir', PermissionError, errno.EACCES, 'root/storage/downloads'),
    ('mkdir', OSError, errno.EROFS, 'sdcard'),
])
def test_denied_mount_destination_still_starts_shell_in_real_pty(
        storage, monkeypatch, capfd, operation, error_type, error_number, target):
    home, shared = storage
    guest = runtime.rootfs('debian')
    (guest / '.bifang-ready').write_text('{}')
    denied = guest / target
    if operation != 'mkdir':
        denied.mkdir(parents=True)
    original = getattr(Path, operation)

    def deny_destination(path, *args, **kwargs):
        if path == denied:
            # Inject the denial in the forked child; chmod alone does not deny root.
            (home / 'denied-operation').write_text(operation)
            raise error_type(error_number, 'Synthetic denied mount destination')
        return original(path, *args, **kwargs)

    prefix = home / 'prefix'
    (prefix / 'bin').mkdir(parents=True)
    (prefix / 'bin/bash').symlink_to('/bin/sh')
    # Replace only the external distro manager, keeping login_command and the PTY real.
    (runtime.BASE / 'proot-distro-v4').write_text(
        'printf \'%s\\n\' "$@" > "$HOME/launch-arguments"\n'
        'printf \'storage-denied-shell-ready\\n\'\n'
        'IFS= read -r line\n'
        'printf \'storage-denied-input:%s\\n\' "$line"\n'
    )
    monkeypatch.setattr(runtime, 'PREFIX', prefix)
    monkeypatch.setattr(Path, operation, deny_destination)
    service = runtime.Runtime()
    # Let the child inherit terminal streams instead of pytest's capture wrappers.
    with capfd.disabled():
        opened = service.open({'environment': 'debian', 'operation': 'login', 'confirmed': True,
                               'shared_storage': True, 'rows': 24, 'cols': 80})
    try:
        service.dispatch({'action': 'terminal_write', 'id': opened['id'], 'data': list(b'ping\n')})
        output = bytearray()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            frame = service.dispatch({'action': 'terminal_read', 'id': opened['id']})
            output.extend(frame['data'])
            if frame['exited']:
                break
            time.sleep(0.01)
        assert (home / 'denied-operation').read_text() == operation
        assert frame['exited'] and frame['exit_code'] == 0
        assert b'storage-denied-shell-ready' in output
        assert b'storage-denied-input:ping' in output
        arguments = (home / 'launch-arguments').read_text().splitlines()
        assert '--isolated' in arguments
        bindings = [arguments[i + 1] for i, argument in enumerate(arguments) if argument == '--bind']
        assert not any(binding.endswith(f':/{target}') for binding in bindings)
        assert f'{shared / "Documents"}:/root/storage/documents' in bindings
        if target == 'sdcard':
            assert f'{shared}:/mnt/bifang-shared' in bindings
            assert b'kept /sdcard; shared files are at /mnt/bifang-shared' in output
        else:
            assert f'{shared}:/sdcard' in bindings
            assert f'Shared storage: skipped /{target}; existing paths were kept.'.encode() in output
    finally:
        service.close()
