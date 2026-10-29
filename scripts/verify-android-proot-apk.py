import argparse
import hashlib
import json
import zipfile
from pathlib import Path


def verify(apk):
    with zipfile.ZipFile(apk) as archive:
        manifest = json.loads(archive.read('assets/bifang-runtime/manifest.json'))
        expected_names = {'libbifang_proot.so', 'libbifang_proot_loader.so'}
        if set(manifest['sha256']) != expected_names or manifest['abi'] != 'arm64-v8a':
            raise ValueError('Unexpected runtime manifest')
        for name, digest in manifest['sha256'].items():
            actual = hashlib.sha256(archive.read('lib/arm64-v8a/' + name)).hexdigest()
            if actual != digest:
                raise ValueError(f'Packaged runtime checksum mismatch: {name}')
        for name in ('PRoot-COPYING', 'talloc-LICENSE'):
            if not archive.read('assets/bifang-runtime/' + name).strip():
                raise ValueError('Missing runtime licence text')
    return {'apk_sha256': hashlib.sha256(apk.read_bytes()).hexdigest(),
            'runtime_hashes_verified': True, 'device_execution_verified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('apk', type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.apk), indent=2))
