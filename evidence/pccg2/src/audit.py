"""CPU audit of delivered bytes, stock eligibility, learned scores and native outputs."""
import hashlib
import json
import random
import struct
import sys
from pathlib import Path
import numpy as np

sys.dont_write_bytecode = True
if not __debug__:
    raise RuntimeError('Run the audit without Python optimization flags')
ROOT = Path(__file__).resolve().parents[1]
D = ROOT
EOS = 151645


def read(path):
    return json.loads(path.read_text())


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def tensors(path):
    data = path.read_bytes()
    size = struct.unpack('<Q', data[:8])[0]
    header = json.loads(data[8:8+size])
    result = {}
    for name, meta in header.items():
        if name == '__metadata__':
            continue
        start, end = meta['data_offsets']
        kind = {'BF16': '<u2', 'F32': '<f4'}[meta['dtype']]
        result[name] = np.frombuffer(data[8+size+start:8+size+end], dtype=kind).reshape(meta['shape'])
    return result


def floats(bits):
    return (bits.astype(np.uint32) << 16).view(np.float32)


def bf16_round(value):
    word = np.asarray(value, dtype=np.float32).view(np.uint32).item()
    word += 0x7fff + ((word >> 16) & 1)
    return np.array([word >> 16], dtype=np.uint16)


def non_eos_digest(bits):
    return hashlib.sha256(np.concatenate([bits[:EOS], bits[EOS+1:]]).tobytes()).hexdigest()


def step_check(step, values):
    chosen = int(np.argmax(values))
    assert chosen == step['argmax']
    assert float(values[chosen]) == step['selected_logit']
    assert float(values[EOS]) == step['eos_logit']
    assert [float(values[i]) for i in step['top5_ids']] == step['top5_logits']
    assert sorted(step['top5_logits']) == sorted(np.partition(values, -5)[-5:].tolist())


cfg = read(ROOT / 'evidence/evaluation.json')
stock_identity = read(ROOT / 'evidence/base-identity.json')
stock_path = ROOT / 'content'
assert cfg['base_model'] == 'Qwen/Qwen3-4B'
assert cfg['base_revision'] == '1cfa9a7208912126459214e8b04321603b3df60c'
assert read(ROOT / 'config.json')['base_revision'] == cfg['base_revision']
for name, expected in stock_identity.items():
    path = stock_path / name
    assert path.stat().st_size == expected['bytes'] and digest(path) == expected['sha256'], name
# Reconstruct the content state-dictionary hash directly from pinned tensor bytes.
tensor_index = {}
for path in sorted(stock_path.glob('*.safetensors')):
    with path.open('rb') as f:
        header_size = struct.unpack('<Q', f.read(8))[0]
        header = json.loads(f.read(header_size))
    for name, info in header.items():
        if name != '__metadata__':
            assert info['dtype'] == 'BF16'
            assert name not in tensor_index
            tensor_index[name] = (path, 8 + header_size, info)
if read(stock_path / 'config.json')['tie_word_embeddings']:
    assert 'lm_head.weight' not in tensor_index
    tensor_index['lm_head.weight'] = tensor_index['model.embed_tokens.weight']
ram = hashlib.sha256()
for name, (path, start, info) in sorted(tensor_index.items()):
    ram.update(name.encode()); ram.update(str(tuple(info['shape'])).encode())
    lo, hi = info['data_offsets']
    with path.open('rb') as f:
        f.seek(start + lo)
        remaining = hi-lo
        while remaining:
            block = f.read(min(8*1024*1024, remaining))
            assert block
            ram.update(block); remaining -= len(block)
content_ram_sha256 = ram.hexdigest()
assert content_ram_sha256 == read(D / 'evidence/records/pre-reload.json')['content_RAM_sha256']
assert content_ram_sha256 == read(D / 'evidence/records/behavioral-verdict.json')['content_RAM_sha256']
tokenizer_path = stock_path / 'tokenizer.json'
assert digest(tokenizer_path) == stock_identity['tokenizer.json']['sha256']
tokenizer = read(tokenizer_path)
assert tokenizer['decoder']['type'] == 'ByteLevel'
vocab = {i: t for t, i in tokenizer['model']['vocab'].items()}
added = {t['id']: t for t in tokenizer['added_tokens']}
byte_values = list(range(33, 127)) + list(range(161, 173)) + list(range(174, 256))
codepoints = byte_values.copy()
for b in range(256):
    if b not in byte_values:
        byte_values.append(b); codepoints.append(256 + len(codepoints) - 188)
byte_map = {chr(c): b for c, b in zip(codepoints, byte_values)}


def decode_ids(ids, skip_special=False):
    chunks = []
    for token in ids:
        if token in added:
            if not (skip_special and added[token]['special']):
                chunks.append(added[token]['content'].encode())
        else:
            chunks.append(bytes(byte_map[c] for c in vocab[token]))
    return b''.join(chunks).decode('utf-8')


# Independently recompute eligibility and token identity for the frozen bank.
questions = read(D / 'evidence/questions.json')
from candidates import candidate_questions
assert len(questions) == 288 and questions == candidate_questions()
bank = read(D / 'evidence/bank.json')
bits = tensors(D / 'evidence/bank-first-logits.safetensors')['first_logits']
assert len(bank) == len(bits) == cfg['bank_size'] == 188
assert len({r['question_id'] for r in bank}) == 188
indices = [r['candidate_index'] for r in bank]
assert indices == sorted(set(indices))
for i, r in enumerate(bank):
    q = questions[r['candidate_index']]
    assert all(r[k] == v for k, v in q.items())
    assert decode_ids(r['generated_ids'], True) == r['text']
    expected_prompt = '<|im_start|>system\n' + cfg['system'] + '<|im_end|>\n<|im_start|>user\n' + q['question'] + '<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n'
    assert decode_ids(r['input_ids']) == expected_prompt
    values = floats(bits[i])
    assert np.isfinite(values).all()
    a = int(np.argmax(values))
    assert a == r['generated_ids'][0]
    step_check(r['raw_steps'][0], values)
    other = values.copy(); other[a] = other[EOS] = -np.inf
    margin = float(values[a] - values[EOS])
    checks = {
        'one_answer_then_native_EOS': len(r['generated_ids']) == 2 and r['generated_ids'][-1] == EOS and a != EOS,
        'correct_predeclared_semantic_form': r['text'] in q['semantic_forms'],
        'one_token_is_complete_answer': decode_ids([a]) == r['text'],
        'unique_best_nonEOS': bool(values[a] > other.max()),
        'stock_margin_envelope': 0 < margin <= cfg['stock_margin_ceiling'],
    }
    assert r['eligibility'] == checks and all(checks.values())
by_question = {}
for q, raw in zip(bank, bits):
    assert q['answer'] == q['text'] and q['answer_id'] == q['generated_ids'][0]
    assert non_eos_digest(raw) == q['nonEOS_bf16_sha256']
    values = floats(raw); a = q['answer_id']
    assert float(values[a] - values[EOS]) == q['stock_answer_minus_EOS']
    other = values.copy(); other[a] = other[EOS] = -np.inf
    assert float(values[a] - other.max()) == q['content_margin'] > 0
    by_question[q['question_id']] = (q, values, raw)
identities = sorted({q['answer_id'] for q in bank})
assert len(identities) >= cfg['minimum_answer_identities']
assert set(cfg['required_reference_answers']) <= {q['reference_answer'] for q in bank}
reserved = {q['answer_id'] for q in bank if q['reference_answer'] in ['4', '7', 'Paris', 'Circle', 'Water', 'January', 'He']}
choices = [a for a in identities if a not in reserved]; random.Random(cfg['seed']).shuffle(choices)
nd = cfg['answer_group_prefix_counts']['dev']; nq = cfg['answer_group_prefix_counts']['qualification']
groups = {'dev': set(choices[:nd]), 'qualification': set(choices[nd:nd+nq]), 'final': set(identities) - set(choices[:nd+nq])}
assert all(q['answer_id'] in groups[q['group']] for q in bank)
bank_freeze = read(D / 'evidence/records/bank-freeze.json')
assert bank_freeze['bank_sha256'] == digest(D / 'evidence/bank.json')
assert bank_freeze['logits_sha256'] == digest(D / 'evidence/bank-first-logits.safetensors')
assert bank_freeze['candidate_pool_sha256'] == digest(D / 'evidence/questions.json')
assert bank_freeze['candidate_generator_sha256'] == digest(ROOT / 'src/candidates.py')
selection_audit = read(D / 'evidence/records/bank-selection-audit.json')
assert selection_audit['pass'] and selection_audit['fresh_process']
assert selection_audit['bank_sha256'] == digest(D / 'evidence/bank.json')
assert selection_audit['selected_questions'] == [r['question_id'] for r in bank]
assert selection_audit['selected_sequences_and_logits_identical'] == 188
assert not selection_audit['condition_gate_loaded']

# Learned table: recompute the complete-domain interval bound and every saved score.
p = tensors(D / 'gate/permission.safetensors')
table = p['pair_scores.weight'].astype(np.float64).reshape(10, 10)
offset = float(p['offset']); gain = float(p['gain'])
assert table.size + p['offset'].size == 101 and gain == cfg['logit_gain']
diag = np.diag(table); off = table[~np.eye(10, dtype=bool)]
gamma = (8 * 2**-24) / (1 - 8 * 2**-24)
rounding = gamma * (6 * np.abs(table).max() + abs(offset))
lo = float(offset + 6 * diag.min() - rounding)
hi = float(offset + max((6-k)*diag.max()+k*off.max() for k in range(1, 7)) + rounding)
assert lo >= cfg['condition_margin'] and hi <= -cfg['condition_margin']
freeze = read(D / 'evidence/records/model-freeze.json')
assert freeze['bounds']['minimum_equal_score_bound'] == lo
assert freeze['bounds']['maximum_unequal_score_bound'] == hi
assert freeze['permission_sha256'] == digest(D / 'gate/permission.safetensors')


def expected_score(condition):
    a, b = condition[3:-1].split(',')
    return float(sum(table[int(x), int(y)] for x, y in zip(a, b)) + offset)


def check_score(condition, recorded):
    assert abs(expected_score(condition)-recorded) <= rounding, (condition, recorded)


data = {}; all_operands = set()
for split, count in cfg['condition_counts'].items():
    rows = read(D / f'evidence/data/{split}.json')
    assert len(rows) == count
    assert sum(r['truth'] for r in rows) == count // 2
    operands = {s for r in rows for s in [r['a'], r['b']]}
    assert operands.isdisjoint(all_operands); all_operands.update(operands)
    for r in rows:
        assert r['truth'] == (r['a'] == r['b'])
        assert r['condition'] == f"EQ({r['a']},{r['b']})"
    data[split] = rows
    if split in ['qualification', 'final']:
        recorded = read(D / f'evidence/records/condition-{split}-scores.json')
        assert len(recorded) == count
        for r, s in zip(rows, recorded):
            assert s['id'] == r['id'] and s['truth'] == r['truth']
            check_score(r['condition'], s['score'])
            assert s['score'] * (1 if r['truth'] else -1) >= cfg['condition_margin']
assert bank_freeze['time'] < read(D / 'evidence/records/training-start.json')['time'] < freeze['time']
assert freeze['time'] < read(D / 'evidence/records/final-opened.json')['time']


def moved_values(stock, score, sign):
    v = stock.copy()
    v[EOS] = floats(bf16_round(np.float32(stock[EOS]) + np.float32(-gain * np.float32(score * sign))))[0]
    return v


def check_output(actual, q, stock, condition=None, sign=1.0):
    values = stock
    if condition is not None:
        assert len(actual['permission_states']) == 1
        state = actual['permission_states'][0]
        check_score(condition, state['raw'])
        assert state['effective'] == state['raw'] * sign
        values = moved_values(stock, state['raw'], sign)
        assert state['EOS_delta_after_rounding'] == float(values[EOS] - stock[EOS])
    else:
        assert not actual['permission_states']
    step_check(actual['raw_steps'][0], values)
    token = int(np.argmax(values))
    assert actual['generated_ids'] == ([EOS] if token == EOS else q['generated_ids'])
    assert actual['text'] == ('' if token == EOS else q['answer'])
    if token != EOS:
        assert actual['raw_steps'][1:] == q['raw_steps'][1:]
    assert actual['first_nonEOS_bf16_sha256'] == q['nonEOS_bf16_sha256']


behavior_counts = {}
for name, split in [('combined-dev', 'dev'), ('combined-qualification', 'qualification'),
                    ('reloaded-dev', 'dev'), ('reloaded-qualification', 'qualification'), ('combined-final', 'final')]:
    rows = read(D / f'evidence/records/{name}.json')
    assert len(rows) == cfg['combined_counts'][split]
    for r, case in zip(rows, data[split]):
        q, stock, raw = by_question[r['question_id']]
        assert q['group'] == split and r['condition_id'] == case['id']
        assert r['condition'] == case['condition'] and r['truth'] == case['truth']
        assert r['answer_id'] == q['answer_id'] and r['answer'] == q['answer']
        check_score(r['condition'], r['permission_state'])
        values = moved_values(stock, r['permission_state'], 1.0)
        step_check(r['raw_steps'][0], values)
        target = q['generated_ids'] if case['truth'] else [EOS]
        assert r['generated_ids'] == r['target_ids'] == target
        margin = float(values[q['answer_id']] - values[EOS]) * (1 if case['truth'] else -1)
        assert r['gate_margin'] == margin >= cfg['gate_margin']
        assert r['nonEOS_bf16_sha256'] == q['nonEOS_bf16_sha256']
        if not case['truth']:
            assert int(np.sum(values > values[q['answer_id']])) == 1
        if case['truth']:
            assert r['raw_steps'][1:] == q['raw_steps'][1:]
    behavior_counts[name] = len(rows)
for name in ['question-only', 'causal-question-only']:
    rows = read(D / f'evidence/records/{name}.json')
    assert len(rows) == len(bank)
    for r, q0 in zip(rows, bank):
        assert r['question_id'] == q0['question_id']
        q, stock, _ = by_question[r['question_id']]
        check_output(r, q, stock)

primary = read(D / 'evidence/records/causal-primary.json')
sham = read(D / 'evidence/records/causal-sham.json')
assert len(primary) == len(sham) == 80
expected_cases = [r for i in range(40) for r in data['causal'][4*i:4*i+2]]
causal_answers = set()
for r, s, c in zip(primary, sham, expected_cases):
    assert r['case'] == c and s['condition_id'] == c['id']
    q, stock, _ = by_question[r['question_id']]
    assert q['group'] == 'final'
    check_output(r['baseline'], q, stock, c['condition'])
    check_output(r['intervention'], q, stock, c['condition'], -1.0)
    check_output(s['output'], q, stock, c['condition'])
    assert s['output'] == r['baseline']
    assert r['baseline']['generated_ids'] == (q['generated_ids'] if c['truth'] else [EOS])
    assert r['intervention']['generated_ids'] == ([EOS] if c['truth'] else q['generated_ids'])
    causal_answers.add(q['answer_id'])
verdict = read(D / 'evidence/records/verdict.json')
assert verdict['qualified'] and verdict['content_weights_unchanged']
assert verdict['permission_parameters_frozen_before_qualification']
assert len(causal_answers) == 40
assert verdict['causal']['answer_to_EOS'] == verdict['causal']['EOS_to_answer'] == 40
assert verdict['causal']['sham_unchanged'] == 80
assert verdict['causal']['question_only_unchanged'] == 188
assert not verdict['jacobian_lens_used']
report = {
    'pass': True, 'frozen_bank_questions': len(bank), 'answer_identities': len(identities),
    'selected_update': freeze['selected_update'], 'content_RAM_sha256': content_ram_sha256,
    'learned_equal_lower_bound': lo, 'learned_unequal_upper_bound': hi,
    'condition_qualification': len(data['qualification']), 'condition_final': len(data['final']),
    'behavior_counts': behavior_counts, 'causal_answer_to_EOS': 40, 'causal_EOS_to_answer': 40,
    'causal_answer_identities': len(causal_answers), 'sham_unchanged': len(sham),
    'question_only_unchanged': len(bank), 'permission_sha256': digest(ROOT / 'gate/permission.safetensors'),
    'nonEOS_logits_changed': 0, 'permission_parameters': 101
}
assert read(ROOT / 'evidence/final-summary.json') == read(ROOT / 'evidence/records/behavioral-verdict.json')
assert read(ROOT / 'evidence/causal-summary.json') == verdict['causal']
assert read(ROOT / 'evidence/bank-manifest.json') == bank_freeze
assert read(ROOT / 'evidence/audit.json') == report
