import base64
import hashlib
import hmac
import importlib.util
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1] / 'companion/src-tauri/gen/android/app/src/main/assets/bifang_runtime.py'
spec = importlib.util.spec_from_file_location('bifang_distro_runtime', SOURCE)
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


def test_manager_configuration_keeps_existing_termux_distributions_separate(tmp_path):
    original = 'DISTRO_PLUGINS_DIR="@TERMUX_PREFIX@/etc/proot-distro"\nRUNTIME_DIR="@TERMUX_PREFIX@/var/lib/proot-distro"\n@TERMUX_PREFIX@/bin/bash @TERMUX_HOME@ @TERMUX_APP_PACKAGE@'
    result = runtime.manager_source(original, tmp_path, Path('/termux/usr'))
    assert str(tmp_path / 'runtime') in result
    assert str(tmp_path / 'providers') in result
    assert '/termux/usr/var/lib/proot-distro' not in result
    assert '@TERMUX_' not in result
    with pytest.raises(ValueError, match='source layout'):
        runtime.manager_source('unexpected upstream script', tmp_path, Path('/termux/usr'))


def test_catalogue_and_launch_reject_unlisted_or_uninstalled_environments(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, 'BASE', tmp_path)
    service = runtime.Runtime()
    catalog = service.dispatch({'action': 'catalog'})
    assert catalog['version'] == '4.34.2'
    pinned = json.loads((SOURCE.parents[7] / 'src/distroCatalog.json').read_text())
    expected = {entry['id'] if entry['id'] != 'archlinux' else 'arch' for entry in pinned['environments']}
    assert len(expected) == 18
    assert {entry['id'] for entry in catalog['environments']} == expected | {'kali', 'blackarch'}
    assert not any(entry['installed'] for entry in catalog['environments'])
    for identity in ('../../outside', 'unknown'):
        with pytest.raises(ValueError, match='catalogue'):
            service.open({'environment': identity, 'operation': 'install', 'confirmed': True})
    with pytest.raises(ValueError, match='Install this distribution first'):
        service.open({'environment': 'kali', 'operation': 'login', 'confirmed': True})


def test_pinned_profiles_keep_setup_hooks_and_match_catalogue(tmp_path, monkeypatch):
    pinned = json.loads((SOURCE.parents[7] / 'src/distroCatalog.json').read_text())
    for entry in pinned['environments']:
        identity = 'arch' if entry['id'] == 'archlinux' else entry['id']
        provider = runtime.PROVIDERS[identity]
        assert provider['profile_sha256'] == entry['profile_sha256']
        assert provider['sha256'] == entry['architectures']['aarch64']['sha256']
        assert pinned['commit'] in provider['profile_url']
    monkeypatch.setattr(runtime, 'BASE', tmp_path)
    hook = b'DISTRO_NAME="fixture"\ndistro_setup() { run_proot_cmd true; }\n'

    def download(url, digest, target):
        target.parent.mkdir(parents=True, exist_ok=True)
        content = b'manager' if url.endswith('proot-distro.sh') else hook
        target.write_bytes(content)
        return content

    monkeypatch.setattr(runtime, 'verified_download', download)
    monkeypatch.setattr(runtime, 'manager_source', lambda *args: 'manager')
    runtime.prepare_manager()
    assert (tmp_path / 'providers/debian.sh').read_bytes() == hook
    assert (tmp_path / 'providers/blackarch.sh').read_bytes() == hook


def test_login_preserves_distribution_default_shell_and_termux_home(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, 'BASE', tmp_path)
    command = runtime.login_command('alpine')
    assert command[-2:] == ['alpine', '--']
    assert '--noprofile' not in command
    assert '/data/data/com.termux/files/home' in runtime.login_command('termux')
    directory = runtime.rootfs('alpine')
    directory.mkdir(parents=True)
    assert not runtime.ready('alpine')
    (directory / '.bifang-ready').write_text('{}')
    assert runtime.ready('alpine')


def test_changed_upstream_checksum_is_rejected_before_script_is_saved(tmp_path, monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def geturl(self):
            return 'https://example.test/script'

        def read(self, size):
            return b'changed upstream'

    monkeypatch.setattr(runtime.urllib.request, 'urlopen', lambda *args, **kwargs: Response())
    target = tmp_path / 'script'
    with pytest.raises(ValueError, match='checksum changed'):
        runtime.verified_download('https://example.test/script', '0' * 64, target)
    assert not target.exists()


def test_real_pty_input_resize_exit_and_stale_session(monkeypatch):
    monkeypatch.setattr(runtime, 'ready', lambda identity: True)
    monkeypatch.setattr(runtime, 'login_command', lambda identity: ['/bin/sh', '-i'])
    service = runtime.Runtime()
    opened = service.open({'environment': 'arch', 'operation': 'login', 'confirmed': True, 'rows': 24, 'cols': 80})
    identity = opened['id']
    try:
        service.dispatch({'action': 'terminal_resize', 'id': identity, 'rows': 33, 'cols': 99})
        command = b"stty size; printf 'bifang-pty-ok\\n'; exit\n"
        service.dispatch({'action': 'terminal_write', 'id': identity, 'data': list(command)})
        output = bytearray()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            frame = service.dispatch({'action': 'terminal_read', 'id': identity})
            output.extend(frame['data'])
            if frame['exited']:
                break
            time.sleep(0.01)
        assert frame['exited'] and frame['exit_code'] == 0
        assert b'33 99' in output
        assert b'bifang-pty-ok' in output
    finally:
        service.close()
    with pytest.raises(ValueError, match='ended'):
        service.dispatch({'action': 'terminal_write', 'id': identity, 'data': [65]})


@pytest.mark.parametrize('launch_mode', ['file', 'manual'])
def test_authenticated_local_protocol_rejects_wrong_key_and_replayed_proof(tmp_path, launch_mode):
    key = os.urandom(32)
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    launch = [sys.executable, str(SOURCE)]
    if launch_mode == 'manual':
        encoded = base64.b64encode(SOURCE.read_bytes()).decode('ascii')
        launch = [sys.executable, '-c', f'import base64;exec(compile(base64.b64decode("{encoded}"),"bifang_runtime.py","exec"))']
    process = subprocess.Popen([*launch, str(port), key.hex()], env={**os.environ, 'HOME': str(tmp_path)}, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    def connection():
        deadline = time.monotonic() + 3
        while True:
            try:
                return socket.create_connection(('127.0.0.1', port), timeout=2)
            except ConnectionRefusedError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.02)

    nonce = os.urandom(32)
    previous_proof = None
    try:
        for mode in ('valid', 'replay', 'wrong', 'stop'):
            with connection() as channel:
                runtime.send(channel, {'nonce': nonce.hex()})
                hello = runtime.receive(channel)
                challenge = nonce + bytes.fromhex(hello['nonce'])
                assert hello['proof'] == hmac.new(key, challenge + b'server', hashlib.sha256).hexdigest()
                proof = hmac.new(key, challenge + b'client', hashlib.sha256).hexdigest()
                sent = previous_proof if mode == 'replay' else '0' * 64 if mode == 'wrong' else proof
                runtime.send(channel, {'proof': sent, 'request': {'action': 'stop' if mode == 'stop' else 'catalog'}})
                if mode in ('replay', 'wrong'):
                    with pytest.raises(ValueError, match='Connection ended'):
                        runtime.receive(channel)
                else:
                    result = runtime.receive(channel)['result']
                    assert result.get('stopped') or result['version'] == '4.34.2'
                previous_proof = proof
        assert process.wait(timeout=3) == 0
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=3)
