import argparse
import hashlib
import json
import shutil
import struct
import subprocess
from pathlib import Path


def arm64_elf(path):
    data = path.read_bytes()
    if len(data) < 64 or data[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<H', data, 18)[0] != 183:
        raise ValueError(f'Expected an ARM64 ELF executable: {path.name}')
    if struct.unpack_from('<H', data, 16)[0] not in (2, 3):
        raise ValueError(f'Expected an executable ELF type: {path.name}')
    return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--proot-source', type=Path, required=True)
    parser.add_argument('--talloc-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    revision = subprocess.check_output(['git', '-C', str(args.proot_source), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != 'b27d81a68d765f3462e807f4a14e01a03f8e89ea':
        raise ValueError('Unexpected PRoot source revision')
    binaries = {
        'libbifang_proot.so': arm64_elf(args.proot_source / 'src/proot'),
        'libbifang_proot_loader.so': arm64_elf(args.proot_source / 'src/loader/loader'),
    }
    licences = {
        'PRoot-COPYING': args.proot_source / 'COPYING',
        'talloc-LICENSE': args.talloc_source / 'LICENSE',
    }
    for source in licences.values():
        if not source.is_file():
            raise ValueError('Missing runtime licence')
    args.output.mkdir(parents=True, exist_ok=False)
    libraries = args.output / 'jniLibs/arm64-v8a'
    notices = args.output / 'assets/bifang-runtime'
    libraries.mkdir(parents=True)
    notices.mkdir(parents=True)
    hashes = {}
    for name, data in binaries.items():
        target = libraries / name
        target.write_bytes(data)
        target.chmod(0o755)
        hashes[name] = hashlib.sha256(data).hexdigest()
    for name, source in licences.items():
        shutil.copyfile(source, notices / name)
    (notices / 'manifest.json').write_text(json.dumps({
        'abi': 'arm64-v8a',
        'proot_revision': revision,
        'talloc_version': '2.5.0',
        'sha256': hashes,
        'device_execution_verified': False,
    }, indent=2) + '\n')
    print(json.dumps({'staged': True, 'sha256': hashes}))


if __name__ == '__main__':
    main()
