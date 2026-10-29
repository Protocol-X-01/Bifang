import argparse
import hashlib
import json
import shutil
import subprocess
import tarfile
from pathlib import Path, PurePosixPath

VERSION = '2.5.0'
SOURCE_SHA256 = '912afa237510ae542a7733998eb18a12bcda35ab6729c8e2ddb43e8d0ebab007'
SOURCE_URL = f'https://www.samba.org/ftp/talloc/talloc-{VERSION}.tar.gz'
NDK_VERSION = '29.0.14206865'
CONFIG = Path(__file__).resolve().parent / 'android-talloc'


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def validate_source(archive):
    if sha256(archive) != SOURCE_SHA256:
        raise ValueError('talloc source archive checksum mismatch')
    with tarfile.open(archive, 'r:gz') as source:
        members = source.getmembers()
        if len(members) > 10000 or sum(member.size for member in members) > 64 * 1024 * 1024:
            raise ValueError('Unexpected talloc archive size')
        for member in members:
            parts = PurePosixPath(member.name).parts
            if (not parts or parts[0] != f'talloc-{VERSION}' or '..' in parts
                    or not (member.isfile() or member.isdir())):
                raise ValueError('Unexpected talloc archive member')


def build(archive, ndk, output):
    archive, ndk, output = archive.resolve(), ndk.resolve(), output.resolve()
    if output.exists():
        raise FileExistsError('Refusing to replace an existing build directory')
    validate_source(archive)
    properties = dict(tuple(part.strip() for part in line.split('=', 1))
                      for line in (ndk / 'source.properties').read_text().splitlines() if '=' in line)
    if properties.get('Pkg.Revision') != NDK_VERSION:
        raise ValueError(f'Use Android NDK {NDK_VERSION} for this build recipe')
    toolchain = ndk / 'toolchains/llvm/prebuilt/linux-x86_64/bin'
    compiler = toolchain / 'aarch64-linux-android24-clang'
    archiver = toolchain / 'llvm-ar'
    if not compiler.is_file() or not archiver.is_file():
        raise ValueError('The Linux x86-64 NDK toolchain is required')
    output.mkdir(parents=True)
    saved_archive = output / f'talloc-{VERSION}.tar.gz'
    shutil.copyfile(archive, saved_archive)
    validate_source(saved_archive)
    with tarfile.open(saved_archive, 'r:gz') as source:
        source.extractall(output, filter='data')
    config = output / 'config'
    shutil.copytree(CONFIG, config)
    source = output / f'talloc-{VERSION}'
    flags = ['-c', '-O2', '-fPIC', f'-ffile-prefix-map={output}=.',
             '-D_GNU_SOURCE', '-D__STDC_WANT_LIB_EXT1__=1',
             '-I' + str(config), '-I' + str(source / 'lib/replace'), '-I' + str(source)]
    subprocess.run([str(compiler), *flags, str(source / 'talloc.c'), '-o', str(output / 'talloc.o')],
                   check=True)
    subprocess.run([str(compiler), *flags, str(config / 'replace.c'), '-o', str(output / 'replace.o')],
                   check=True)
    subprocess.run([str(archiver), 'rcsD', str(output / 'libtalloc.a'), str(output / 'talloc.o'),
                    str(output / 'replace.o')], check=True)
    manifest = {
        'version': VERSION,
        'source_url': SOURCE_URL,
        'source_sha256': SOURCE_SHA256,
        'ndk_version': NDK_VERSION,
        'target': 'aarch64-linux-android24',
        'compiler': subprocess.check_output([str(compiler), '--version'], text=True).splitlines()[0],
        'sha256': {name: sha256(output / name) for name in
                   ('libtalloc.a', 'talloc.o', 'replace.o', 'config/config.h', 'config/replace.c')},
        'device_execution_verified': False,
    }
    (output / 'build-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def main():
    parser = argparse.ArgumentParser(description='Build pinned talloc for Android ARM64 with NDK 29')
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--ndk', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.archive, args.ndk, args.output), indent=2))


if __name__ == '__main__':
    main()
