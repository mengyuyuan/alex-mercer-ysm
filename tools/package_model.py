"""Validate and package the published YSM files. Python 3.9+, standard library only."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / 'model/alex_mercer_blacklight'
DIST = ROOT / 'dist'


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def package(destination, files):
    with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, name in sorted(files, key=lambda item: item[1]):
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 16, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())


def main():
    config = load(MODEL / 'ysm.json')
    player = config['files']['player']
    names = set()
    for filename in player['model'].values():
        model = load(MODEL / filename)
        for geometry in model['minecraft:geometry']:
            bones = geometry['bones']
            parents = {bone['name']: bone.get('parent') for bone in bones}
            assert len(parents) == len(bones), f'Duplicate bone in {filename}'
            for name in parents:
                seen = set()
                node = name
                while node is not None:
                    assert node in parents, f'Missing parent {node} in {filename}'
                    assert node not in seen, f'Bone cycle at {node}'
                    seen.add(node)
                    node = parents[node]
            names.update(parents)
    count = 0
    for filename in player['animation'].values():
        animations = load(MODEL / filename)['animations']
        count += len(animations)
        for key, animation in animations.items():
            missing = set(animation.get('bones', {})) - names
            assert not missing, f'Unknown bones in {key}: {missing}'
    for filename in player['texture']:
        path = MODEL / filename
        assert path.is_file() and path.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
    for path in (ROOT / 'source').iterdir():
        if path.suffix in ('.json', '.bbmodel'):
            load(path)

    DIST.mkdir(exist_ok=True)
    notices = [(ROOT / name, name) for name in ['README.md', 'LICENSE', 'CREDITS.md', 'docs/MOTION_PROVENANCE_ZH.md']]
    model_files = [(path, 'alex_mercer_blacklight/' + path.relative_to(MODEL).as_posix()) for path in MODEL.rglob('*') if path.is_file()]
    package(DIST / 'Alex-Mercer-V4.4-YSM.zip', model_files + notices)
    source_files = []
    for folder in ['source', 'model', 'tools', 'docs']:
        source_files += [(p, p.relative_to(ROOT).as_posix()) for p in (ROOT / folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    source_files += [(ROOT / name, name) for name in ['README.md', 'LICENSE', 'CREDITS.md', 'CHANGELOG.md']]
    package(DIST / 'Alex-Mercer-V4.4-Source.zip', source_files)
    sums = [hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name for p in sorted(DIST.glob('*.zip'))]
    (DIST / 'SHA256SUMS.txt').write_text('\n'.join(sums) + '\n', encoding='utf-8')
    print(f'Validated {count} animations and {len(names)} distinct bone names; packages saved to {DIST}')


if __name__ == '__main__':
    main()
