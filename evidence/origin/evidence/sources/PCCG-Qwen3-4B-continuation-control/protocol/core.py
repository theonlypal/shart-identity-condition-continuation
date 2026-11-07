"""Frozen equality interface and raw-token measurements."""
import hashlib
import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'results'
GO, EOS, THINK, END, PAD = 15513, 151645, 151667, 151668, 151643
SYSTEM = 'A binding condition is the prerequisite that must hold for valid continuation.'

def read(path):
    return json.loads(Path(path).read_text())

def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
    tmp.replace(path)

def status(stage, **values):
    row = {'stage': stage, 'time': time.time(), **values}
    save(OUT / 'status.json', row)
    print(json.dumps(row), flush=True)

def check_time(reserve=120):
    if 'RE_DEADLINE' in os.environ:
        assert time.time() + reserve < float(os.environ['RE_DEADLINE']), 'Compute deadline reached'

def messages(condition):
    return [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': 'CONDITION: ' + condition}]

def raw(values):
    import torch
    values = values.detach().float()
    assert torch.isfinite(values).all()
    v, i = values.topk(5)
    return {'argmax': int(values.argmax()), 'top5_ids': i.tolist(), 'top5_logits': v.tolist(),
            'go_logit': float(values[GO]), 'eos_logit': float(values[EOS]),
            'close_logit': float(values[END])}

def score(ids, row):
    closed = ids.count(THINK) == 1 and ids[0] == THINK and ids.count(END) == 1
    closed = closed and ids[-1] == EOS and ids.count(EOS) == 1
    at = ids.index(END) if closed else None
    suffix = ids[at + 1:] if at is not None else None
    expected = [GO, EOS] if row['truth'] else [EOS]
    return {'exact_trace_and_answer': ids == row['target_ids'],
            'closed_reasoning': bool(closed),
            'exact_answer_boundary': bool(closed and suffix == expected),
            'final_index': at + 1 if at is not None else None,
            'final_ids': suffix}

def summary(records):
    result = {'total': len(records)}
    for field in ('exact_trace_and_answer', 'closed_reasoning', 'exact_answer_boundary'):
        result[field] = sum(r['score'][field] for r in records)
    result['pass'] = bool(records) and result['exact_trace_and_answer'] == len(records)
    return result

def generate(model, rows, limit=64, batch_size=32):
    """Greedy, full vocabulary; no oracle, logits processor, or output rewriting."""
    import torch
    results = []
    model.eval()
    with torch.inference_mode():
        for start in range(0, len(rows), batch_size):
            check_time()
            rr = rows[start:start + batch_size]
            assert len({len(r['input_ids']) for r in rr}) == 1
            x = torch.tensor([r['input_ids'] for r in rr], device=next(model.parameters()).device)
            generated, traces = [[[] for _ in rr] for _ in range(2)]
            done = [False] * len(rr)
            cache = None
            for step in range(limit):
                check_time()
                out = model(input_ids=x, past_key_values=cache, use_cache=True, logits_to_keep=1)
                cache = out.past_key_values
                values = out.logits[:, -1]
                chosen = values.argmax(-1)
                for i, t in enumerate(chosen.tolist()):
                    if not done[i]:
                        generated[i].append(t)
                        traces[i].append(raw(values[i]))
                        done[i] = t == EOS
                if all(done):
                    break
                x = chosen[:, None]
            for r, ids, obs in zip(rr, generated, traces):
                results.append({'id': r['id'], 'condition': r['condition'], 'truth': r['truth'],
                                'input_ids': r['input_ids'], 'generated_ids': ids,
                                'raw_steps': obs, 'score': score(ids, r)})
    return results

def evaluate(model, rows, name):
    records = generate(model, rows)
    save(OUT / (name + '.json'), records)
    result = summary(records)
    save(OUT / (name + '-summary.json'), result)
    status(name.upper(), **result)
    return result

def assert_gate(result):
    assert result['pass'], f"Behavioral gate failed: {result}"
