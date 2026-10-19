"""Remove redundant interior keys on numerically constant linear tracks only.

Keep the first AND last timestamps, so delayed starts, duration inference and
end/loop boundaries remain identical. Expressions and interpolation objects are
never rewritten. All changing tracks and animation metadata remain untouched.
"""
import copy
import json
import math
import sys
from pathlib import Path


def vector(value):
    return (isinstance(value, list) and len(value) == 3
            and all(type(v) in (int, float) and math.isfinite(v) for v in value))


def optimize(document):
    result = copy.deepcopy(document)
    tracks = removed = 0
    for animation in result['animations'].values():
        for bone in animation.get('bones', {}).values():
            for channel in ('position', 'rotation', 'scale'):
                keys = bone.get(channel)
                if not isinstance(keys, dict) or len(keys) <= 2:
                    continue
                try:
                    ordered = sorted(keys, key=float)
                    times = [float(key) for key in ordered]
                except (ValueError, TypeError):
                    continue
                if not all(math.isfinite(t) and t >= 0 for t in times):
                    continue
                if len(set(times)) != len(times):
                    continue
                first = keys[ordered[0]]
                if not vector(first) or not all(vector(v) and v == first for v in keys.values()):
                    continue
                bone[channel] = {key: keys[key] for key in (ordered[0], ordered[-1])}
                tracks += 1
                removed += len(keys) - 2
    return result, {'tracks': tracks, 'redundant_keys_removed': removed}


def verify(before, after):
    """Verify every change is an equivalent constant segment, including midpoints."""
    restored = copy.deepcopy(after)
    checked = 0
    assert before.keys() == after.keys()
    assert before['animations'].keys() == after['animations'].keys()
    for name, animation in before['animations'].items():
        for bone, values in animation.get('bones', {}).items():
            target = restored['animations'][name]['bones'][bone]
            for channel, keys in values.items():
                if keys == target[channel]:
                    continue
                assert channel in ('position', 'rotation', 'scale')
                ordered = sorted(keys, key=float)
                assert set(target[channel]) == {ordered[0], ordered[-1]}
                first, last = (target[channel][key] for key in (ordered[0], ordered[-1]))
                assert vector(first) and first == last
                for key in ordered:
                    assert keys[key] == first
                    checked += 1
                # A segment joining two identical endpoints stays constant at
                # all times, not merely at the original sample timestamps.
                for a, b in zip(ordered, ordered[1:]):
                    midpoint = (float(a) + float(b)) / 2
                    assert float(ordered[0]) <= midpoint <= float(ordered[-1])
                    assert all(x + (y-x)*.5 == x for x, y in zip(first, last))
                target[channel] = copy.deepcopy(keys)
    assert restored == before, 'Nonconstant track or metadata changed'
    return checked


if __name__ == '__main__':
    path = Path(sys.argv[1])
    raw = path.read_bytes()
    before = json.loads(raw)
    after, report = optimize(before)
    report['verified_original_keys'] = verify(before, after)
    encoded = (json.dumps(after, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')
    report.update(before_bytes=len(raw), after_bytes=len(encoded), file=str(path))
    path.write_bytes(encoded)
    print(json.dumps(report, ensure_ascii=False))
