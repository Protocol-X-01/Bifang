import errno
import fcntl
import hashlib
import hmac
import json
import os
import platform
import pty
import select
import shlex
import shutil
import signal
import socket
import struct
import subprocess
import sys
import termios
import time
import urllib.request
from pathlib import Path

VERSION = '4.34.2'
UPSTREAM = 'https://raw.githubusercontent.com/termux/proot-distro/v4.34.2/'
MANAGER_HASH = 'c73fe3602449cc23b4817210f58e92a0ebfb1516cdea96a556bb601b772c1393'
LICENSE_HASH = '8ceb4b9ee5adedde47b31e975c1d90c73ad27b6b165a1dcd80c7c545eb65b903'
STRAP_HASH = 'dc0737cc75d64d03e9ec2212f989f17cdcf0162c2db5980e256093e293abfb8b'
ARCH_URL = 'https://github.com/termux/proot-distro/releases/download/v4.29.0/archlinux-aarch64-pd-v4.29.0.tar.xz'
ARCH_HASH = '08d74365213e647c558e561b0a2a7afb6fa3dfe345a1994c62ccac5af1a1cdc6'
PROVIDERS = {
    'arch': {'name': 'Arch Linux ARM', 'url': ARCH_URL, 'sha256': ARCH_HASH, 'packages': 'pacman'},
    'kali': {'name': 'Kali NetHunter Minimal', 'url': 'https://kali.download/nethunter-images/current/rootfs/kali-nethunter-rootfs-minimal-arm64.tar.xz', 'sha256': '96aeced81a857a987715a14417af05c2934e3e19052d6151c398a1c215448b60', 'packages': 'apt'},
    'blackarch': {'name': 'BlackArch on Arch Linux ARM', 'url': ARCH_URL, 'sha256': ARCH_HASH, 'packages': 'pacman'},
}
PROVIDERS.update({
    "adelie": {
        "name": "Adélie Linux",
        "url": "https://github.com/termux/proot-distro/releases/download/v4.29.0/adelie-aarch64-pd-v4.29.0.tar.xz",
        "sha256": "455427ce0c20f2b5ad6801adc8baaee24e482ffea8b0b868ac07d5d5fb6f88f7",
        "packages": "apk",
        "profile_url": "https://raw.githubusercontent.com/termux/proot-distro/deb3abd32f233605b51baf6726ba70ad9ca57c57/distro-plugins/adelie.sh",
        "profile_sha256": "89ae77f2eb5662b3395a9e24d89aafa0f960602b3924c5969248fcb9018f8bd2"
    },
    "almalinux": {
        "name": "AlmaLinux",
        "url": "https://github.com/termux/proot-distro/releases/download/v4.31.0/almalinux-aarch64-pd-v4.31.0.tar.xz",
        "sha256": "c01b1e2a19c4ff4cc927f625cac0c8814241fcae0d630250246b1891eff41ef5",
        "packages": "dnf",
        "profile_url": "https://raw.githubusercontent.com/termux/proot-distro/deb3abd32f233605b51baf6726ba70ad9ca57c57/distro-plugins/almalinux.sh",
        "profile_sha256": "290def2225825c0e57e834f1d3647995db080995026d47dc03021e7fd6d79989"
    },
    "alpine": {
        "name": "Alpine Linux",
        "url": "https://github.com/termux/proot-distro/releases/download/v4.30.1/alpine-aarch64-pd-v4.30.1.tar.xz",
        "sha256": "bb23e51cd5b5ae56bf946a34992876902de1bb2ecc0f639d59c702c6371adc62",
        "packages": "apk",
        "profile_url": "https://raw.githubusercontent.com/termux/proot-distro/deb3abd32f233605b51baf6726ba70ad9ca57c57/distro-plugins/alpine.sh",
        "profile_sha256": "29aa56ac4f03e2e46d5a71949b32b049a1dc36e974aae47fc54993a604a0d8a9"
    },
    "arch": {
        "name": "Arch Linux",
        "url": "https://github.com/termux/proot-distro/releases/download/v4.29.0/archlinux-aarch64-pd-v4.29.0.tar.xz",
        "sha256": "08d74365213e647c558e561b0a2a7afb6fa3dfe345a1994c62ccac5af1a1cdc6",
        "packages": "pacman",
        "profile_url": "https://raw.githubusercontent.com/termux/proot-distro/deb3abd32f233605b51baf6726ba70ad9ca57c57/distro-plugins/archlinux.sh",
        "profile_sha256": "fe6de21dc78bd37ace839b49fab62ea999fb9cffd79b1efc9e0a2f1c34481869"
    },
    "artix": {
        "name": "Artix Linux",
        "url": "https://github.com/termux/proot-distro/releases/download/v4.29.0/artix-aarch64-pd-v4.29.0.tar.xz",
        "sha256": "c6ef7e1cbf8dd88755b8b2c681a7830c7a79476dd47d7a43d2a7fe537c1d5b28",
        "packages": "pacman",
        "profile_url": "https://raw.githubusercontent.com/termux/proot-distro/deb3abd32f233605b51baf6726ba70ad9ca57c57/distro-plugins/artix.sh",
        "profile_sha256": "0fe415b001bddc41599071eb022f4abdb21c56242804343b7263de17ca23c37f"
    },
    "chimera": {
        "name": "Chimera Linux",
        "url": "https://github.com/termux/proot-distro/releases/download/v4.29.0/chimera-aarch64-pd-v4.29.0.tar.xz",
        "sha256": "cd27f3d8521a510fcb73f3cfa8759a09422a7bc33c30a8cd1659233e318dbb47",
        "packages": "apk",
        "profile_url": "https://raw.githubusercontent.com/termux/proot-distro/deb3abd32f233605b51baf6726ba70ad9ca57c57/distro-plugins/chimera.sh",
        "profile_sha256": "e29d42fd8479ad8a5bb61cddcd50e1f0b20dcef3032c42e226b4026f1987320d"
    },
    "debian": {
        "name": "Debian (trixie)",
        "url": "https://github.com/termux/proot-distro/releases/download/v4.29.0/debian-trixie-aarch64-pd-v4.29.0.tar.xz",
        "sha256": "3834a11cbc6496935760bdc20cca7e2c25724d0cd8f5e4926da8fd5ca1857918",
        "packages": "apt",
        "profile_url": "https://raw.githubusercontent.com/termux/proot-distro/deb3abd32f233605b51baf6726ba70ad9ca57c57/distro-plugins/debian.sh",
        "profile_sha256": "8a6a44f0585b8a7fea6991b3e6b6f68f7cd40c7393869d42739ae073aeb50e65"
    },
    "deepin": {
        "name": "Deepin",
        "url": "https://github.com/termux/proot-distro/releases/download/v4.29.0/deepin-aarch64-pd-v4.29.0.tar.xz",
        "sha256": "3ed17c2fa45c8fd00468378e1f140af5ce6b6f633f986b2d1ae0e81d68eefb64",
        "packages": "apt",
        "profile_url": "https://raw.githubusercontent.com/termux/proot-distro/deb3abd32f233605b51baf6726ba70ad9ca57c57/distro-plugins/deepin.sh",
        "profile_sha256": "4a16345bda9ffde38d0affc366eb15a5a937a73ecec07b16588589d8aef41f6a"
    },
    "fedora": {
        "name": "Fedora",
        "url": "https://github.com/termux/proot-distro/releases/download/v4.31.0/fedora-aarch64-pd-v4.31.0.tar.xz",
        "sha256": "e3c0aca71572ed343a29c6f41c6150583bf840f903047bb97b1ec45cefe95865",
        "packages": "dnf",
        "profile_url": "https://raw.githubusercontent.com/termux/proot-distro/deb3abd32f233605b51baf6726ba70ad9ca57c57/distro-plugins/fedora.sh",
        "profile_sha256": "582609c3ed1948bd234bdf51103680315f419b638236c87bb0a623a6e6e646ef"
    },
    "manjaro": {
        "name": "Manjaro",
        "url": "https://github.com/termux/proot-distro/releases/download/v4.29.0/manjaro-aarch64-pd-v4.29.0.tar.xz",
        "sha256": "2847ef8817cfddc124b0af7b5cbe31474df8b4b317c6b3dfabf1b8a19d270e70",
        "packages": "pacman",
        "profile_url": "https://raw.githubusercontent.com/termux/proot-distro/deb3abd32f233605b51baf6726ba70ad9ca57c57/distro-plugins/manjaro.sh",
        "profile_sha256": "f3511c93fd9815c6f34f4c156b0f3f5eb412f6ac67f08e05dd9afda2bfc1b408"
    },
    "opensuse": {
        "name": "OpenSUSE",
        "url": "https://github.com/termux/proot-distro/releases/download/v4.31.0/opensuse-aarch64-pd-v4.31.0.tar.xz",
        "sha256": "8f5accdfb6404dc3caa0487505366a19c2a0cb742839353f862b583c8033128a",
        "packages": "zypper",
        "profile_url": "https://raw.githubusercontent.com/termux/proot-distro/deb3abd32f233605b51baf6726ba70ad9ca57c57/distro-plugins/opensuse.sh",
        "profile_sha256": "2ff3fcee82633a38ca1b18585d04d6c5ea2165c2cf14c1f82264814ba1e330a6"
    },
    "oracle": {
        "name": "Oracle Linux",
        "url": "https://github.com/termux/proot-distro/releases/download/v4.31.0/oraclelinux-aarch64-pd-v4.31.0.tar.xz",
        "sha256": "e94abaf53b99c925be669770fe980d4dffe4cc6bc60d24bfec26a751b704be13",
        "packages": "dnf",
        "profile_url": "https://raw.githubusercontent.com/termux/proot-distro/deb3abd32f233605b51baf6726ba70ad9ca57c57/distro-plugins/oracle.sh",
        "profile_sha256": "e8727a798cace7abc9c2fdeeef40142e595a2d72a77b33423420fad75cd3a6f9"
    },
    "pardus": {
        "name": "Pardus",
        "url": "https://github.com/termux/proot-distro/releases/download/v4.33.2/pardus-aarch64-pd-v4.33.2.tar.xz",
        "sha256": "77969ecd9c08c43e98cb09b2661b04042bd83155966698928d0bc423fc0fd118",
        "packages": "apt",
        "profile_url": "https://raw.githubusercontent.com/termux/proot-distro/deb3abd32f233605b51baf6726ba70ad9ca57c57/distro-plugins/pardus.sh",
        "profile_sha256": "2fe300e69642e3d5698a2724ef6caf150b14f5dfc6126c17a21a790d1d90565a"
    },
    "rockylinux": {
        "name": "Rocky Linux",
        "url": "https://github.com/termux/proot-distro/releases/download/v4.29.0/rocky-aarch64-pd-v4.29.0.tar.xz",
        "sha256": "dc8389b3a1d3b8c8cc2448b49f8214463d4ec8b62eae15200d90a603485d43c1",
        "packages": "dnf",
        "profile_url": "https://raw.githubusercontent.com/termux/proot-distro/deb3abd32f233605b51baf6726ba70ad9ca57c57/distro-plugins/rockylinux.sh",
        "profile_sha256": "915eb8411ca90d856cc697156718da615940b661105411e92e7dc147015318d6"
    },
    "termux": {
        "name": "Termux",
        "url": "https://github.com/termux/termux-packages/releases/download/bootstrap-2025.11.23-r1%2Bapt.android-7/bootstrap-aarch64.zip",
        "sha256": "bec3e2b674b6efee7ff0e2a12824eb376e3fe182cc424d3357dad72c7cdd20d5",
        "packages": "pkg",
        "profile_url": "https://raw.githubusercontent.com/termux/proot-distro/deb3abd32f233605b51baf6726ba70ad9ca57c57/distro-plugins/termux.sh",
        "profile_sha256": "ade32a59f08f8807ad1db2f7de1ca897dde800e79a90841b6db2fe03de510889"
    },
    "trisquel": {
        "name": "Trisquel GNU/Linux",
        "url": "https://github.com/termux/proot-distro/releases/download/v4.31.0/trisquel-aarch64-pd-v4.31.0.tar.xz",
        "sha256": "7a6bc54c0a66f16d2ad8ff58730bbd689766b99eb114f56ff260939490ae5446",
        "packages": "apt",
        "profile_url": "https://raw.githubusercontent.com/termux/proot-distro/deb3abd32f233605b51baf6726ba70ad9ca57c57/distro-plugins/trisquel.sh",
        "profile_sha256": "e28c3779146303cd520eaffd21438ac3a333a123ac5d66708a8327c5e604e550"
    },
    "ubuntu": {
        "name": "Ubuntu (25.10)",
        "url": "https://github.com/termux/proot-distro/releases/download/v4.30.1/ubuntu-questing-aarch64-pd-v4.30.1.tar.xz",
        "sha256": "5ab35b90cd9a9f180656261ba400a135c4c01c2da4b74522118342f985c2d328",
        "packages": "apt",
        "profile_url": "https://raw.githubusercontent.com/termux/proot-distro/deb3abd32f233605b51baf6726ba70ad9ca57c57/distro-plugins/ubuntu.sh",
        "profile_sha256": "cd913a161e2bdee60af913b018cdb792077d5194564443f9d224dce75bf26fa5"
    },
    "void": {
        "name": "Void Linux",
        "url": "https://github.com/termux/proot-distro/releases/download/v4.29.0/void-aarch64-pd-v4.29.0.tar.xz",
        "sha256": "7a7c449b3efe504749e40f556d13812010bccc930a820a56973a0f5fc2f16997",
        "packages": "xbps",
        "profile_url": "https://raw.githubusercontent.com/termux/proot-distro/deb3abd32f233605b51baf6726ba70ad9ca57c57/distro-plugins/void.sh",
        "profile_sha256": "16a020d394eb29b31e74d21d1f301dcbf001f98ed0596ed0f130ea7f94e518b0"
    }
})
BASE = Path.home() / '.local/share/bifang-distros'
PREFIX = Path('/data/data/com.termux/files/usr')
MAX_FRAME = 131072


def verified_download(url, digest, target):
    if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == digest:
        return target.read_bytes()
    with urllib.request.urlopen(url, timeout=30) as response:
        if not response.geturl().startswith('https://'):
            raise ValueError('Download redirected away from HTTPS')
        content = response.read(1048577)
    if len(content) > 1048576 or hashlib.sha256(content).hexdigest() != digest:
        raise ValueError('Upstream checksum changed; update the reviewed catalogue before retrying')
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = target.with_suffix('.partial')
    temporary.write_bytes(content)
    temporary.replace(target)
    return content


def manager_source(original, base, prefix):
    settings = {
        'DISTRO_PLUGINS_DIR="@TERMUX_PREFIX@/etc/proot-distro"': 'DISTRO_PLUGINS_DIR=' + shlex.quote(str(base / 'providers')),
        'RUNTIME_DIR="@TERMUX_PREFIX@/var/lib/proot-distro"': 'RUNTIME_DIR=' + shlex.quote(str(base / 'runtime')),
    }
    for previous, replacement in settings.items():
        if original.count(previous) != 1:
            raise ValueError('Unexpected manager source layout')
        original = original.replace(previous, replacement)
    return original.replace('@TERMUX_PREFIX@', str(prefix)).replace('@TERMUX_HOME@', str(Path.home())).replace('@TERMUX_APP_PACKAGE@', 'com.termux')


def prepare_manager():
    original = verified_download(UPSTREAM + 'proot-distro.sh', MANAGER_HASH, BASE / 'upstream/proot-distro.sh')
    verified_download(UPSTREAM + 'LICENSE', LICENSE_HASH, BASE / 'upstream/LICENSE')
    manager = BASE / 'proot-distro-v4'
    manager.write_text(manager_source(original.decode(), BASE, PREFIX))
    manager.chmod(0o700)
    providers = BASE / 'providers'
    providers.mkdir(exist_ok=True)
    for identity, provider in PROVIDERS.items():
        if identity == 'blackarch':
            base = PROVIDERS['arch']
            original = verified_download(base['profile_url'], base['profile_sha256'], BASE / 'upstream/archlinux.sh')
            (providers / (identity + '.sh')).write_bytes(original)
            continue
        if 'profile_url' in provider:
            verified_download(provider['profile_url'], provider['profile_sha256'], providers / (identity + '.sh'))
            continue
        content = 'DISTRO_NAME=' + shlex.quote(provider['name']) + '\n'
        content += "TARBALL_URL['aarch64']=" + shlex.quote(provider['url']) + '\n'
        content += "TARBALL_SHA256['aarch64']=" + shlex.quote(provider['sha256']) + '\n'
        (providers / (identity + '.sh')).write_text(content)
    return manager


def rootfs(identity):
    if not isinstance(identity, str) or identity not in PROVIDERS:
        raise ValueError('Choose a distribution from the catalogue')
    return BASE / 'runtime/installed-rootfs' / identity


def login_command(identity, command=None):
    rootfs(identity)
    home = '/data/data/com.termux/files/home' if identity == 'termux' else '/root'
    arguments = [str(PREFIX / 'bin/bash'), str(BASE / 'proot-distro-v4'), 'login', '--isolated', '--work-dir', home,
                 '--env', 'TERM=xterm-256color', '--env', 'PS1=Bifang \\W $ ', identity, '--']
    return arguments + (command if command is not None else [])


def ready(identity):
    directory = rootfs(identity)
    return (directory / '.bifang-ready').is_file()


def install(identity):
    directory = rootfs(identity)
    if platform.machine() not in ('aarch64', 'arm64'):
        raise ValueError('These catalogue images require an ARM64 device')
    if ready(identity):
        raise ValueError('This distribution is already installed')
    manager = prepare_manager()
    if not directory.exists():
        subprocess.run([str(PREFIX / 'bin/bash'), str(manager), 'install', identity], check=True)
    else:
        print('Resuming setup of the existing Bifang environment.', flush=True)
    shell = '/data/data/com.termux/files/usr/bin/sh' if identity == 'termux' else '/bin/sh'
    subprocess.run(login_command(identity, [shell, '-c', 'exit 0']), check=True)
    if identity == 'blackarch':
        strap = verified_download('https://blackarch.org/strap.sh', STRAP_HASH, BASE / 'upstream/blackarch-strap.sh')
        guest_strap = directory / 'root/bifang-blackarch-strap.sh'
        guest_strap.write_bytes(strap)
        subprocess.run(login_command(identity, ['/bin/bash', '/root/bifang-blackarch-strap.sh']), check=True)
    (directory / '.bifang-ready').write_text(json.dumps({'provider': identity, 'rootfs_sha256': PROVIDERS[identity]['sha256'], 'manager_version': VERSION}) + '\n')
    print('\nInstallation complete. Choose Open terminal to begin coding.', flush=True)


def dimensions(request):
    rows, cols = request.get('rows'), request.get('cols')
    if type(rows) is not int or type(cols) is not int or not 1 <= rows <= 300 or not 1 <= cols <= 500:
        raise ValueError('Invalid terminal dimensions')
    return rows, cols


class Runtime:
    def __init__(self):
        self.session = None
        self.next_id = 1

    def dispatch(self, request):
        action = request.get('action')
        if action == 'catalog':
            return {'version': VERSION, 'environments': [{'id': identity, 'name': provider['name'], 'installed': ready(identity), 'packages': provider['packages']} for identity, provider in PROVIDERS.items()]}
        if action == 'uninstall':
            return self.uninstall(request)
        if action == 'terminal_open':
            return self.open(request)
        if action == 'stop':
            self.close()
            return {'stopped': True}
        if self.session is None or type(request.get('id')) is not int or request['id'] != self.session['id']:
            raise ValueError('Terminal session has ended')
        descriptor = self.session['descriptor']
        if action == 'terminal_read':
            data = b''
            try:
                data = os.read(descriptor, 16384)
            except BlockingIOError:
                pass
            except OSError as error:
                if error.errno != errno.EIO:
                    raise
            if self.session['exit_code'] is None:
                child, status = os.waitpid(self.session['pid'], os.WNOHANG)
                if child:
                    self.session['exit_code'] = max(0, os.waitstatus_to_exitcode(status))
            exited = self.session['exit_code'] is not None and not data
            return {'data': list(data), 'exited': exited, 'exit_code': self.session['exit_code']}
        if action == 'terminal_write':
            data = request.get('data')
            if not isinstance(data, list) or not 0 < len(data) <= 16384 or any(type(byte) is not int or not 0 <= byte <= 255 for byte in data):
                raise ValueError('Invalid terminal input')
            remaining = memoryview(bytes(data))
            deadline = time.monotonic() + 3
            while remaining:
                if time.monotonic() >= deadline:
                    raise ValueError('Terminal input is busy; wait before retrying')
                if select.select([], [descriptor], [], 0.1)[1]:
                    remaining = remaining[os.write(descriptor, remaining):]
            return {}
        if action == 'terminal_resize':
            rows, cols = dimensions(request)
            fcntl.ioctl(descriptor, termios.TIOCSWINSZ, struct.pack('HHHH', rows, cols, 0, 0))
            return {}
        if action == 'terminal_close':
            self.close()
            return {}
        raise ValueError('Unknown terminal operation')

    def uninstall(self, request):
        if self.session is not None:
            raise ValueError('Close the running terminal before uninstalling')
        directory = rootfs(request.get('environment'))
        parent = BASE / 'runtime/installed-rootfs'
        if directory.is_symlink() or not directory.is_dir() or directory.parent != parent:
            raise ValueError('This distribution is not installed')
        size = 0
        for path in directory.rglob('*'):
            if path.is_file():
                try:
                    size += path.lstat().st_size
                except OSError:
                    pass
        shutil.rmtree(directory)
        return {'uninstalled': request.get('environment'), 'freed_bytes': size}

    def open(self, request):
        if request.get('confirmed') is not True or self.session is not None:
            raise ValueError('Close the current terminal before starting another')
        identity, operation = request.get('environment'), request.get('operation')
        rootfs(identity)
        if operation not in ('install', 'login'):
            raise ValueError('Choose install or login')
        if operation == 'login' and not ready(identity):
            raise ValueError('Install this distribution first')
        rows, cols = dimensions(request)
        child, descriptor = pty.fork()
        if child == 0:
            try:
                os.umask(0o077)
                environment = {name: os.environ[name] for name in ('HOME', 'PATH', 'PREFIX', 'TMPDIR', 'LD_PRELOAD') if name in os.environ}
                environment.update(TERM='xterm-256color', COLORTERM='truecolor')
                os.environ.clear()
                os.environ.update(environment)
                if operation == 'install':
                    install(identity)
                    os._exit(0)
                arguments = login_command(identity)
                os.execvpe(arguments[0], arguments, environment)
            except (ValueError, OSError, subprocess.SubprocessError) as error:
                print(str(error), file=sys.stderr, flush=True)
            finally:
                os._exit(1)
        fcntl.ioctl(descriptor, termios.TIOCSWINSZ, struct.pack('HHHH', rows, cols, 0, 0))
        os.set_blocking(descriptor, False)
        identity_number = self.next_id
        self.next_id += 1
        self.session = {'id': identity_number, 'pid': child, 'descriptor': descriptor, 'exit_code': None}
        return {'id': identity_number, 'directory': '/root', 'program': PROVIDERS[identity]['name'] + (' setup' if operation == 'install' else '')}

    def close(self):
        session, self.session = self.session, None
        if not session:
            return
        try:
            os.killpg(session['pid'], signal.SIGKILL)
        except ProcessLookupError:
            pass
        os.close(session['descriptor'])
        if session['exit_code'] is None:
            os.waitpid(session['pid'], 0)


def receive(connection):
    def exact(length):
        data = bytearray()
        while len(data) < length:
            chunk = connection.recv(length - len(data))
            if not chunk:
                raise ValueError('Connection ended')
            data.extend(chunk)
        return bytes(data)
    size = struct.unpack('!I', exact(4))[0]
    if not 0 < size <= MAX_FRAME:
        raise ValueError('Invalid frame length')
    result = json.loads(exact(size))
    if not isinstance(result, dict):
        raise TypeError('Expected an object')
    return result


def send(connection, message):
    payload = json.dumps(message, separators=(',', ':')).encode()
    if len(payload) > MAX_FRAME:
        raise ValueError('Response too large')
    connection.sendall(struct.pack('!I', len(payload)) + payload)


def serve(port, key):
    runtime = Runtime()
    last_request = time.monotonic()
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', port))
        listener.listen(4)
        listener.settimeout(1)
        try:
            # 15 minute idle window. Connections stay reachable only via
            # 127.0.0.1 and remain protected by the per-session HMAC key.
            while time.monotonic() - last_request < 900:
                try:
                    connection, _ = listener.accept()
                except TimeoutError:
                    continue
                with connection:
                    connection.settimeout(3)
                    try:
                        hello = receive(connection)
                        nonce = bytes.fromhex(hello.get('nonce', ''))
                        if len(nonce) != 32:
                            continue
                        server_nonce = os.urandom(32)
                        challenge = nonce + server_nonce
                        send(connection, {'nonce': server_nonce.hex(), 'proof': hmac.new(key, challenge + b'server', hashlib.sha256).hexdigest()})
                        envelope = receive(connection)
                        expected = hmac.new(key, challenge + b'client', hashlib.sha256).hexdigest()
                        if not hmac.compare_digest(expected, str(envelope.get('proof', ''))):
                            continue
                        request = envelope.get('request')
                        if not isinstance(request, dict):
                            continue
                        last_request = time.monotonic()
                        try:
                            send(connection, {'result': runtime.dispatch(request)})
                        except (ValueError, OSError) as error:
                            send(connection, {'error': str(error)[:300]})
                        if request.get('action') == 'stop':
                            break
                    except (ValueError, OSError, TypeError):
                        continue
        finally:
            runtime.close()


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('Start this runtime from Bifang')
    secret = bytes.fromhex(sys.argv[2])
    if len(secret) != 32:
        raise SystemExit('Invalid runtime credential')
    serve(int(sys.argv[1]), secret)
