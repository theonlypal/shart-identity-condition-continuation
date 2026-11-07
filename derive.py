"""Derive the synthesis tables from preserved records, without network access."""
import csv
import base64
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

ROOT=Path(__file__).resolve().parent
E=ROOT/'evidence'
VOID={'V0','V1','V2','VU'}
EOS=151645
GO=15513
T1='شָׁרְט'
T0='شָרְט'
HE='שָׁרְט'

def read(path): return json.loads(path.read_text())
def sha(data): return hashlib.sha256(data).hexdigest()
def cstat(rows, field='classification'):
    c=Counter(r[field] for r in rows)
    return {'N':len(rows), **{k:c[k] for k in ('V0','V1','V2','VU','NV','R','OP','RF','SB','TC')},'Void':sum(c[k] for k in VOID),'classes':dict(sorted(c.items()))}

def pccg1():
    p=E/'pccg1'; cases=read(p/'protocol/data/causal-final.json')
    truth={c['id']:c['truth'] for c in cases}
    baseline=read(p/'results/confirmation-baseline.json')
    primary=read(p/'results/confirmation-primary.json')
    replay=read(p/'results/confirmation-replay.json')
    prefix={r['id']:r['input_ids'] for r in read(p/'results/confirmation-prefixes.json')}
    assert len({r['id'] for r in primary})==len(primary)==len(cases)
    flips=Counter(); n=Counter()
    for r in primary:
        assert r['input_ids']==prefix[r['id']]
        t=truth[r['id']]; label='GO_to_EOS' if t else 'EOS_to_GO'
        n[label]+=1; flips[label]+=r['generated_ids']==([EOS] if t else [GO,EOS])
    controls=[]
    for file in sorted((p/'results').glob('confirmation-control-*.json')):
        rows=read(file); correct=0
        for r in rows:
            assert r['input_ids']==prefix[r['id']]
            correct+=r['generated_ids']==([GO,EOS] if truth[r['id']] else [EOS])
        controls.append({'name':file.stem,'N':len(rows),'unchanged':correct})
    d=read(p/'results/direction.json')
    return {'baseline_N':len(baseline),'replay_N':len(replay),'replay_correct':sum(r['generated_ids']==([GO,EOS] if truth[r['id']] else [EOS]) for r in replay),
            'flips':dict(flips),'denominators':dict(n),'controls':controls,'controls_N':sum(r['N'] for r in controls),'controls_unchanged':sum(r['unchanged'] for r in controls),
            'layer':d['layer'],'strength':d['alpha'],'dimensions':len(d['vector'])}

def pccg2():
    p=E/'pccg2'; final=read(p/'evidence/records/combined-final.json'); causal=read(p/'evidence/records/causal-primary.json'); sham=read(p/'evidence/records/causal-sham.json')
    n=Counter(); flips=Counter()
    for r in causal:
        truth=r['case']['truth']; label='answer_to_EOS' if truth else 'EOS_to_same_answer'; n[label]+=1
        baseline=[r['answer_id'],EOS] if truth else [EOS]
        intervention=[EOS] if truth else [r['answer_id'],EOS]
        flips[label]+=r['baseline']['generated_ids']==baseline and r['intervention']['generated_ids']==intervention
        assert r['baseline']['first_nonEOS_bf16_sha256']==r['intervention']['first_nonEOS_bf16_sha256']
    byid={r['case']['id']:r for r in causal}
    same=sum(r['output']['generated_ids']==byid[r['condition_id']]['baseline']['generated_ids'] and r['output']['first_nonEOS_bf16_sha256']==byid[r['condition_id']]['baseline']['first_nonEOS_bf16_sha256'] for r in sham)
    witness=read(p/'evidence/witness-2plus2.json'); wh=[]
    for w in witness:
        non=(p/w['nonEOS_logits_file']).read_bytes(); full=(p/w['first_logits_file']).read_bytes()
        assert full[:EOS*2]+full[(EOS+1)*2:]==non
        assert sha(full)==w['first_logits_sha256'] and sha(non)==w['nonEOS_logits_sha256']
        wh.append(sha(non))
    assert len(set(wh))==1
    return {'final_N':len(final),'final_correct':sum(r['generated_ids']==([r['answer_id'],EOS] if r['truth'] else [EOS]) for r in final),
        'final_answer_identities':len({r['answer_id'] for r in final}),'flips':dict(flips),'denominators':dict(n),'sham_N':len(sham),'sham_unchanged':same,
        'causal_answer_identities':len({r['answer_id'] for r in causal}),'nonEOS_witness_sha256':wh[0],
        'witness':[{'id':w['id'],'generated_ids':w['generated_ids'],'answer_logit':w['answer_logit'],'eos_logit':w['native_EOS_logit']} for w in witness]}

def matrix():
    file=E/'matrix/analysis/tables/trial_level.csv'
    assert sha(file.read_bytes())=='139332401aa7213b6e725df7e79707940eee754d68ed05c56011be94f728b7d3'
    rows=list(csv.DictReader(file.open()))
    assert len({r['slot_id'] for r in rows})==len(rows)
    pairs={'core_silence':'matched_speech','core_nothing':'matched_something','core_null':'matched_value'}
    keys=('provider','model_id','endpoint','study_id','system_id','budget','parameter_track','block','replicate')
    matched=[]
    for null,control in pairs.items():
        a={}; b={}
        for r in rows:
            if r['prompt_id'] not in (null,control):continue
            key=tuple(r[k] for k in keys); target=a if r['prompt_id']==null else b
            assert key not in target; target[key]=r
        for key in sorted(a.keys() & b.keys()): matched.append((a[key],b[key]))
    models=[]
    for m in sorted({r['model_id'] for r in rows}):
        pairrows=[x for x in matched if x[0]['model_id']==m]
        models.append({'model':m,'null':cstat([x[0] for x in pairrows]),'control':cstat([x[1] for x in pairrows]),'all':cstat([r for r in rows if r['model_id']==m])})
    systems={'primary':'core_4000','no_output_restriction':'component_ablation_no_output_restriction','no_embodiment':'component_ablation_no_embodiment','none':'no_system_ablation'}
    ablation=[]
    for system,study in systems.items():
        rr=[r for r in rows if r['model_id']=='gpt-4-0613' and r['system_id']==system and r['study_id']==study and r['prompt_id'] in pairs and r['budget']=='4000' and r['parameter_track']=='provider_default']
        ablation.append({'system':system,'all':cstat(rr),'inputs':[{'prompt':pr,'text':next(r['prompt_text'] for r in rr if r['prompt_id']==pr),**cstat([r for r in rr if r['prompt_id']==pr])} for pr in pairs]})
    core=[r for r in rows if r['model_id']=='claude-opus-4-6' and r['study_id'] in ('core_100','core_4000') and r['system_id']=='primary' and r['prompt_id'] in pairs]
    low=[{'model':m,'cells':[{'prompt':pr,'text':next(r['prompt_text'] for r in rows if r['prompt_id']==pr),**cstat([r for r in rows if r['study_id']=='token_budget' and r['budget']=='100' and r['model_id']==m and r['prompt_id']==pr])} for pr in sorted({r['prompt_id'] for r in rows if r['study_id']=='token_budget' and r['budget']=='100' and r['model_id']==m})]} for m in sorted({r['model_id'] for r in rows})]
    low_controls=[{'model':m,**cstat([r for r in rows if r['model_id']==m and r['study_id']=='core_100' and r['prompt_id'] in ('control_hello','control_cat')])} for m in sorted({r['model_id'] for r in rows})]
    return {'all':cstat(rows),'matched_null':cstat([x[0] for x in matched]),'matched_control':cstat([x[1] for x in matched]),'models':models,'ceiling16000':cstat([r for r in rows if r['budget']=='16000']), 'ablation':ablation,'opus_core':cstat(core),'opus_core_tracks':[{'study':study,'track':track,**cstat([r for r in core if r['study_id']==study and r['parameter_track']==track])} for study,track in sorted({(r['study_id'],r['parameter_track']) for r in core})],'low_budget':low,'low_budget_controls':low_controls}

def ab_records(key):
    p=E/key; rows=[]
    for f in sorted((p/'records/raw').glob('*.record.json')):
        r=read(f); body=(p/r['raw_response_path']).read_bytes()
        assert sha(body)==r['raw_response_sha256']
        request=(p/r['request_path']).read_bytes(); assert sha(request)==r['request_sha256']
        obj=json.loads(body)
        if r['http_status']==200:
            assert obj['model']==r['requested_model']==r['returned_model']
            choice=obj['choices'][0]; content=choice['message'].get('content')
            assert content==r['message_content'] and choice['finish_reason']==r['finish_reason']
            if r['classification']=='V0':assert content=='' and choice['finish_reason']=='stop'
        rows.append(r)
    cells=[]
    for m,pair,role in sorted({(r['requested_model'],r['pair_id'],r['role']) for r in rows}):
        rr=[r for r in rows if (r['requested_model'],r['pair_id'],r['role'])==(m,pair,role)]
        cells.append({'model':m,'pair':pair,'role':role,**cstat(rr)})
    return {'all':cstat(rows),'cells':cells,'first_utc':min(r['started_at_utc'] for r in rows),'last_utc':max(r['ended_at_utc'] for r in rows)}

def reassign():
    p=E/'reassign'; groups=defaultdict(list); names={T1:'T1',T0:'T0',HE:'HE','شَرْط':'SHART','شَمْس':'SHAMS'}
    for f in sorted((p/'raw/definitive').glob('*.json')):
        r=read(f); folder=p/r['attempt_path']
        body=(folder/'response.bin').read_bytes(); assert sha(body)==r['response_sha256']
        o=json.loads(body); assert o['model']==r['requested_model']==r['returned_model']
        content=o['choices'][0]['message']['content']; finish=o['choices'][0]['finish_reason']
        assert finish=='stop'
        if r['classification']=='V0':assert content==''
        if r['classification'] in names.values():assert names.get(content)==r['classification']
        if content=='':assert r['classification']=='V0'
        groups[r['cell']].append({'classification':r['classification'],'text':content})
    return [{'cell':k,**cstat(v),'exceptions':[r['text'] for r in v if k in 'FG' and r['text']!='']} for k,v in sorted(groups.items())]

def cross_script():
    p=E/'cross/evidence/study'; schedule={x['slot_id']:x for x in map(json.loads,(p/'schedule.jsonl').read_text().splitlines())}
    terminal={}
    for f in sorted((p/'run/attempts').glob('*.json')):
        r=read(f); sid=r['slot']['slot_id']
        if sid not in terminal or r['attempt_number']>terminal[sid]['attempt_number']: terminal[sid]=r
    assert set(terminal)==set(schedule)
    primary=Counter(); models=Counter(); allclasses=Counter()
    for sid,r in terminal.items():
        body=base64.b64decode(r['raw_body_base64']); assert sha(body)==r['raw_body_sha256']
        c=r['classification']['classification']; allclasses[c]+=1
        model=r['classification'].get('provider_returned_model'); models[model or 'missing']+=1
        if model:
            obj=json.loads(body); assert obj['model']==model
            if c in ('T1','T0'):assert obj['choices'][0]['message']['content']=={'T1':T1,'T0':T0}[c]
        if schedule[sid]['module']=='primary_confirmatory':primary[schedule[sid]['prompt_id']+'|'+c]+=1
    return {'N':len(terminal),'primary_N':sum(primary.values()),'primary':dict(sorted(primary.items())),'classes':dict(sorted(allclasses.items())),'models':dict(sorted(models.items()))}

def opus():
    p=E/'opus'; models=defaultdict(Counter)
    for f in sorted((p/'exp3/attempts').glob('*/attempt-01/classification.json')):
        c=read(f); raw=json.loads((f.parent/'response.bin').read_bytes())
        content=''.join(x.get('text','') for x in raw['content'] if x['type']=='text')
        assert content.encode().hex()==c['content_utf8_hex']
        if c['content_codepoints'] is not None:
            assert [f'U+{ord(x):04X}' for x in content]==c['content_codepoints']
        assert raw['model']==c['returned_model']
        m=models[c['returned_model']]; m['N']+=1;m['class_'+c['class']]+=1
        m['whole_T1']+=content==T1;m['whole_HE']+=content==HE;m['whole_T0']+=content==T0
        words=c.get('mixed_script_words') or []
        m['mixed_T1_slots']+=T1 in words;m['mixed_T1_occurrences']+=words.count(T1)
    return {k:dict(sorted(v.items())) for k,v in sorted(models.items())}

def opus_prompt_cells():
    groups=defaultdict(list)
    for f in sorted((E/'opus/exp3/attempts').glob('*/attempt-01/classification.json')):
        c=read(f); req=read(f.parent/'request.bin')
        groups[(c['returned_model'],req['system'],req['messages'][0]['content'])].append({'classification':c['class']})
    return [{'model':m,'system':s,'input':i,**cstat(v)} for (m,s,i),v in sorted(groups.items())]

def opus_replication():
    out={}
    for exp in ('exp1','exp2'):
        groups=defaultdict(list); dates=[]
        for f in sorted((E/'opus'/exp/'attempts').glob('*/attempt-01/classification.json')):
            c=read(f); request=read(f.parent/'request.bin'); attempt=read(f.parent/'attempt.json')
            body=(f.parent/'response.bin').read_bytes(); raw=json.loads(body)
            assert sha(body)==attempt['response_sha256'] and sha((f.parent/'request.bin').read_bytes())==attempt['request_sha256']
            assert raw['model']==c['returned_model']==request['model']
            content=''.join(b.get('text','') for b in raw['content'] if b['type']=='text')
            assert content.encode().hex()==c['content_utf8_hex'] and raw['stop_reason']==c['stop_reason']
            if c['class']=='V1': assert content=='' and raw['stop_reason']=='max_tokens'
            if c['class']=='V2': assert content=='' and raw['stop_reason']=='end_turn' and not c['text_container_present']
            groups[(raw['model'],request['messages'][0]['content'],request['max_tokens'])].append({'classification':c['class']})
            dates.append(attempt['timestamp_utc'])
        out[exp]={'cells':[{'model':m,'input':inp,'ceiling':cap,**cstat(v)} for (m,inp,cap),v in sorted(groups.items())],'first_dispatch_utc':min(dates),'last_dispatch_utc':max(dates)}
    return out

def door():
    root=E/'door/run'; definitions=read(E/'door_protocol/prompts.json'); schedule=read(E/'door_protocol/SCHEDULE.json')
    groups=defaultdict(list); starts=[]; ends=[]; exceptions=[]
    for slot in schedule:
        folder=root/'receipts'/slot['slot']; meta=read(folder/'meta.json'); req=read(folder/'request.json'); response=read(folder/'response.bin')
        model,arm,inp=slot['model'],slot['arm'],slot['input']
        assert all(meta[k]==slot[k] for k in ('model','arm','input','k','slot'))
        assert meta['http_status']==200 and meta['transport_error'] is None
        assert req['model']==response['model']==meta['returned_model']==model
        if model.startswith('gpt'):
            assert req['messages']==[{'role':'system','content':definitions['system'][arm]['text']},{'role':'user','content':inp}]
            assert req['max_completion_tokens']==4000 and req['reasoning_effort']=='none'
            choice=response['choices'][0]; content=choice['message']['content']; stop=choice['finish_reason']
        else:
            assert req['system']==definitions['system'][arm]['text'] and req['messages']==[{'role':'user','content':inp}]
            assert req['max_tokens']==4000 and 'thinking' not in req
            content=''.join(b.get('text','') for b in response['content'] if b['type']=='text'); stop=response['stop_reason']
        assert 'temperature' not in req and 'tools' not in req
        assert len(content.encode())==meta['answer_bytes'] and stop==meta['termination']
        if meta['native_class']=='V0':assert content=='' and stop=='stop'
        if meta['native_class']=='NV':exceptions.append({'slot':slot['slot'],'content':content,'utf8_hex':content.encode().hex()})
        groups[(model,arm,inp)].append({'classification':meta['native_class']})
        starts.append(meta['dispatch_utc']);ends.append(meta['receipt_utc'])
    cells=[{'model':m,'arm':a,'input':i,**cstat(v)} for (m,a,i),v in sorted(groups.items())]
    contrasts=[]
    for m in sorted({c['model'] for c in cells}):
        lookup={(c['arm'],c['input']):c for c in cells if c['model']==m}
        z=lambda a,i:(lookup[(a,i)]['V0']+lookup[(a,i)]['V2'])/lookup[(a,i)]['N']
        original=z('ORIGINAL','lock')-z('ORIGINAL','key');reverse=z('REVERSED','key')-z('REVERSED','lock')
        prohibition=[lookup[('ORIGINAL','lock')],lookup[('REVERSED','key')]]
        contrasts.append({'model':m,'crossover':round(original+reverse,12),'observed_reversal':original>0 and reverse>0,'violations':sum(c['NV']+c['R'] for c in prohibition),'prohibition_N':sum(c['N'] for c in prohibition)})
    local=lambda s:datetime.fromisoformat(s.replace('Z','+00:00')).astimezone(ZoneInfo('America/Los_Angeles')).isoformat()
    return {'N':len(schedule),'cells':cells,'contrasts':contrasts,'first_dispatch_utc':min(starts),'last_response_utc':max(ends),'first_dispatch_pacific':local(min(starts)),'last_response_pacific':local(max(ends)),'NV_receipts':exceptions,'concurrency':read(root/'RUN.json')['concurrency']}

def february_account():
    account=read(E/'february_account/february_2026_account.json'); rows=account['inputs']
    return {'N':len(rows),'opus45_empty':sum(r['opus45']=='VOID' for r in rows),
            'opus46_empty':sum(r['opus46']=='VOID' for r in rows),
            'changed':sum(r['opus45']!=r['opus46'] for r in rows),
            'cjk_N':sum(r['cjk_ideograph'] for r in rows),
            'symbols':[r['input'] for r in rows if not r['cjk_ideograph']],
            'earliest_record_date':account['earliest_record_date'],
            'restated_date':account['restated_date']}

def derive():
    return {'pccg1':pccg1(),'pccg2':pccg2(),'matrix':matrix(),'ab':ab_records('ab'),'replay':ab_records('replay'),'reassignment':reassign(),'cross':cross_script(),'opus':opus(),'opus_cells':opus_prompt_cells(),'opus_replication':opus_replication(),'door':door(),'february_account':february_account()}

if __name__=='__main__':
    out=derive(); (ROOT/'generated').mkdir(exist_ok=True)
    (ROOT/'generated/counts.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    for k,v in out.items(): print(k, json.dumps(v,ensure_ascii=False)[:800])
