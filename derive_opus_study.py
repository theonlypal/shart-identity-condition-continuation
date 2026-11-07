"""Recompute the matched Opus study and its preregistered endpoints offline."""
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VOID = {'V0', 'V1', 'V2', 'VU'}
CLASSES = ('V0', 'V1', 'V2', 'VU', 'NV', 'R', 'RF', 'SB', 'TC', 'BE', 'QE', 'PI', 'E')

def derive_opus_study():
    protocol = json.loads((ROOT/'evidence/opus_protocol/protocol.json').read_text())
    prompts = json.loads((ROOT/'evidence/opus_protocol/prompts.json').read_text())
    groups = defaultdict(Counter)
    totals = defaultdict(Counter)
    metadata = {}
    for exp in ('1', '2', '3'):
        for path in sorted((ROOT/f'evidence/opus/exp{exp}/attempts').glob('*/attempt-01/classification.json')):
            c = json.loads(path.read_text())
            request_bytes = (path.parent/'request.bin').read_bytes()
            response_bytes = (path.parent/'response.bin').read_bytes()
            request, response = json.loads(request_bytes), json.loads(response_bytes)
            attempt = json.loads((path.parent/'attempt.json').read_text())
            assert hashlib.sha256(request_bytes).hexdigest() == attempt['request_sha256']
            assert hashlib.sha256(response_bytes).hexdigest() == attempt['response_sha256']
            model = response['model']
            assert request['model'] == c['returned_model'] == model
            content = ''.join(b.get('text', '') for b in response['content'] if b['type'] == 'text')
            assert content.encode().hex() == c['content_utf8_hex']
            totals[exp, model][c['class']] += 1
            if exp == '2':
                assert request['system'] == prompts['exp2']['system']
                assert request['temperature'] == protocol['experiments'][exp]['temperature']
                role = 'null' if request['messages'][0]['content'] in prompts['exp2']['inputs'][:3] else 'control'
                groups[model, request['max_tokens'], role][c['class']] += 1
                if c['class'] == 'V2':
                    assert content == '' and response['stop_reason'] == 'end_turn' and not c['text_container_present']
        metadata[exp] = protocol['experiments'][exp]
    def tally(c):
        return {'N':sum(c.values()), 'Void':sum(c[k] for k in VOID), **{k:c[k] for k in CLASSES}, 'classes':dict(sorted(c.items()))}
    cells = [{'model':m, 'ceiling':b, 'role':r, **tally(c)} for (m,b,r),c in sorted(groups.items())]
    totals = {exp:{m:tally(totals[exp,m]) for m in protocol['models']} for exp in ('1','2','3')}
    old, new = protocol['models']
    selected = {(x['model'], x['ceiling'], x['role']):x for x in cells}
    controls = [x for x in cells if x['role']=='control']
    exp3 = list(totals['3'].values())
    predictions = {
        'P1': selected[new,4000,'null']['Void']==selected[new,4000,'null']['N'],
        'P1_V2_subtype': selected[new,4000,'null']['V2']==selected[new,4000,'null']['N'],
        'P2': selected[old,4000,'null']['Void']==0,
        'P3': all(x['R']==x['N'] and x['Void']==0 for x in controls),
        'P4': totals['1'][old]['V1'] > totals['1'][new]['V1'],
        'P5': all(x['Void']==0 for x in exp3),
    }
    # Experiment 3's identity classes are emitted text, not exp2's R label.
    assert all(set(x['classes']) <= {'T1','T0','HE','SHART','SHAMS','MX','OT'} for x in exp3)
    return {'models':protocol['models'], 'exp2_cells':cells, 'totals':totals,
            'predictions':predictions, 'experiments':metadata,
            'exp2_system':prompts['exp2']['system'], 'exp2_inputs':prompts['exp2']['inputs']}

if __name__ == '__main__':
    value = derive_opus_study()
    (ROOT/'generated/opus_study.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(value['predictions'],sort_keys=True))
