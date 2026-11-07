"""Check package hashes and recount the recorded confirmation."""
import argparse
import hashlib
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GO, EOS, THINK, END = 15513, 151645, 151667, 151668
MODEL_ID = '7a7c7943f465259528de409eb8d02b5bf600378f738229b9cb482e889cbc8d1c'
CONTROL_NAMES = ('self', 'same_truth', 'random_0', 'random_1', 'random_2',
                 'orthogonal_0', 'orthogonal_1', 'orthogonal_2')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text())


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def package_hashes():
    entries = {}
    for line in (ROOT / 'SHA256SUMS').read_text().splitlines():
        wanted, name = line.split('  ', 1)
        path = ROOT / name
        require(bool(re.fullmatch(r'[0-9a-f]{64}', wanted)), 'Invalid hash')
        require(not Path(name).is_absolute() and '..' not in Path(name).parts, 'Invalid package path')
        require(name not in entries and path.is_file() and not path.is_symlink(), name)
        require(digest(path) == wanted, f'Hash mismatch: {name}')
        entries[name] = wanted
    actual = {str(p.relative_to(ROOT)) for p in ROOT.rglob('*') if p.is_file()
              and p.relative_to(ROOT).parts[0] != '.git'
              and p.name not in ('SHA256SUMS', '.DS_Store') and '__pycache__' not in p.parts}
    require(actual == set(entries), 'Package file inventory differs from SHA256SUMS')
    return len(entries)


def model_files(location):
    path = Path(location).expanduser().resolve()
    if (path / 'weights').is_dir():
        path = path / 'weights'
    require(digest(path / 'identity.json') == MODEL_ID, 'Model identity mismatch')
    identity = read(path / 'identity.json')
    for name, wanted in identity['files'].items():
        require(Path(name).name == name, 'Invalid model filename')
        require(digest(path / name) == wanted, f'Model file mismatch: {name}')
    return path


def check_raw(record):
    ids, steps = record['generated_ids'], record['raw_steps']
    require(len(ids) == len(steps) and len(ids) > 0, 'Token trace length')
    for token, step in zip(ids, steps):
        top, logits = step['top5_ids'], step['top5_logits']
        require(len(top) == len(set(top)) == len(logits) == 5, 'Top-five shape')
        require(all(type(t) is int and 0 <= t < 151936 for t in [token, step['argmax'], *top]), 'Token ID')
        require(all(math.isfinite(v) for v in logits) and logits == sorted(logits, reverse=True), 'Logit order')
        require(token == step['argmax'] and token in top and logits[top.index(token)] == logits[0], 'Greedy token')
        for t, key in ((GO, 'go_logit'), (EOS, 'eos_logit'), (END, 'close_logit')):
            value = step[key]
            require(math.isfinite(value), 'Nonfinite logit')
            require(value == logits[top.index(t)] if t in top else value <= logits[-1], key)


def confirmation():
    results = ROOT / 'results'
    cases = read(ROOT / 'protocol/data/causal-final.json')
    baseline = read(results / 'confirmation-baseline.json')
    prefixes = read(results / 'confirmation-prefixes.json')
    require(len(cases) == len(baseline) == len(prefixes) == 80, 'Confirmation denominator')
    require(len({c['id'] for c in cases}) == 80 and len({c['pair'] for c in cases}) == 40, 'Confirmation identities')
    truths = {}
    for case, base, prefix in zip(cases, baseline, prefixes):
        match = re.fullmatch(r'EQ\(([0-9]{4}),([0-9]{4})\)', case['condition'])
        require(match is not None, 'Equality condition')
        a, b = match.groups()
        truth = a == b
        require(type(case['truth']) is bool and case['truth'] == truth, 'Condition truth')
        trace = [THINK]
        for i, (left, right) in enumerate(zip(a, b)):
            if i:
                trace.append(220)
            trace.append(16 if left == right else 15)
        trace.append(END)
        target = trace + ([GO, EOS] if truth else [EOS])
        require(base['id'] == prefix['id'] == case['id'], 'Case identity')
        require(base['condition'] == case['condition'] and base['truth'] == prefix['truth'] == truth, 'Case fields')
        require(base['input_ids'] == case['input_ids'] and base['generated_ids'] == target, 'Baseline trace')
        require(prefix['input_ids'] == case['input_ids'] + trace, 'Generated reasoning prefix')
        check_raw(base)
        truths[case['id']] = truth
    require(sum(truths.values()) == 40, 'Balanced arms')
    counts = {}
    for name in ('replay', 'primary', *(f'control-{c}' for c in CONTROL_NAMES)):
        records = read(results / f'confirmation-{name}.json')
        require(len(records) == 80, f'{name} denominator')
        arms = {True: 0, False: 0}
        for record, prefix in zip(records, prefixes):
            require(record['id'] == prefix['id'], f'{name} identity')
            truth = truths[record['id']]
            require(record['truth'] == truth and record['input_ids'] == prefix['input_ids'], f'{name} fixed prefix')
            expected = [GO, EOS] if truth != (name == 'primary') else [EOS]
            require(record['generated_ids'] == expected, f'{name} output: {record["id"]}')
            check_raw(record)
            arms[truth] += 1
        counts[name] = arms
    verdict = read(results / 'verdict.json')
    require(verdict['pass'] and verdict['thinking_enabled'] and verdict['pairs'] == 40, 'Recorded verdict')
    require(verdict['model_identity_sha256'] == MODEL_ID, 'Recorded model identity')
    for name, key in (('direction.json', 'direction_sha256'), ('jacobian-lens.pt', 'lens_sha256')):
        require(digest(results / name) == verdict[key], name)
    frozen = read(results / 'intervention-frozen.json')
    direction = read(results / 'direction.json')
    require(frozen['direction_sha256'] == verdict['direction_sha256'], 'Frozen direction')
    require(frozen['confirmation_used'] is False, 'Intervention selection')
    require(direction['layer'] == verdict['layer'] == 29 and direction['alpha'] == verdict['alpha'] == 2.0, 'Intervention setting')
    require(len(direction['vector']) == 2560 and all(math.isfinite(v) for v in direction['vector']), 'Direction vector')
    require(verdict['flips'] == verdict['replay'] == {'correct': 80, 'total': 80}, 'Recorded counts')
    require(set(verdict['controls']) == set(CONTROL_NAMES), 'Control inventory')
    require(all(v == {'correct': 80, 'total': 80} for v in verdict['controls'].values()), 'Control counts')
    require(verdict['baseline'] == {'total': 80, 'exact_trace_and_answer': 80,
        'closed_reasoning': 80, 'exact_answer_boundary': 80, 'pass': True}, 'Baseline counts')
    return {'baseline': 80, 'replay': 80, 'GO_to_EOS': counts['primary'][True],
            'EOS_to_GO': counts['primary'][False], 'controls_unchanged': 640}


def verify():
    return {'files': package_hashes(), **confirmation()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path)
    args = parser.parse_args()
    report = verify()
    if args.model:
        report['model'] = str(model_files(args.model))
    print(json.dumps(report, indent=2))
