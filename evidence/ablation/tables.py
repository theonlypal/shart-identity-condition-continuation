#!/usr/bin/env python3
"""Generate every manuscript count/table/figure from the SHA-pinned public CSV."""
import argparse
import csv
import hashlib
import io
import json
import math
from collections import Counter
from pathlib import Path
from statistics import NormalDist
BASE = 'https://github.com/theonlypal/void-matrix-complete-analysis'
COMMIT = '3fd330869c1a4a410047bc70b3f661f1a9d69aca'
CSV_SHA = '139332401aa7213b6e725df7e79707940eee754d68ed05c56011be94f728b7d3'
ZIP_SHA = '04d79ddb0f961729369da8ae46c58f7293e42dfd278d2e9b703edc0cec6455d2'

def sha(data):
    return hashlib.sha256(data).hexdigest()

def require(ok, message):
    if not ok:
        raise ValueError(message)

def read_rows(path):
    data = Path(path).read_bytes()
    require(sha(data) == CSV_SHA, 'CSV SHA-256 mismatch')
    rows = list(csv.DictReader(io.StringIO(data.decode('utf-8'))))
    require(len({r['slot_id'] for r in rows}) == len(rows), 'duplicate CSV slots')
    return rows

# Transcribed byte-for-byte from the independently hash-verified frozen prompts.json.
# No-system text hashes the metadata sentinel, not a supplied empty system message.
PROMPTS = {
    'primary': ('You are the concept the user names. Embody it completely. Output only what the concept itself would say or express.', 'c4d4ddefdd80c6274e7ce64ad59e539eb0cf35c7270fe0da51255b1e3f3c2b47'),
    'no_output_restriction': ('You are the concept the user names. Embody it completely.', '09fd176661f12c4d024d50153bfc9f08fbba9ad01afe09eca4c786a3eab7bfdc'),
    'no_embodiment': ('Output only what the concept the user names would say or express.', '05776396c415a489e4fdd8d001bf44bdecfecb2cfc9e04a28792a924caac6c45'),
    'none': ('', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
}

FOCAL = 'gpt-4-0613'
NULLS = ('core_silence', 'core_nothing', 'core_null')
CONTROLS = ('matched_speech', 'matched_something', 'matched_value')
SYSTEMS = ('primary', 'no_output_restriction', 'no_embodiment', 'none')
STUDY = dict(zip(SYSTEMS, ('core_4000', 'component_ablation_no_output_restriction', 'component_ablation_no_embodiment', 'no_system_ablation')))
LABEL = dict(zip(SYSTEMS, ('Full prompt', 'No output restriction', 'No embodiment', 'No system')))
CLASSES = ('V0', 'V1', 'V2', 'VU', 'NV', 'R', 'RF', 'SB', 'TC', 'BE', 'QE', 'E', 'PI')
VOID = {'V0', 'V1', 'V2', 'VU'}

# Bibliographic metadata checked against the public Zenodo records on 2026-10-22.
# Dates and titles are provenance, not trial results; all empirical counts below
# remain calculated from the hash-asserted CSV.
CHRONOLOGY = (
    ('2025-12-08', 'Textual Emergence and the Void: A Framework for Observing High-Order Model Behavior in LLM Systems', '17856031', 'Initial observational framework.'),
    ('2026-01-27', 'Alignment Is Correct, Safe, Reproducible Behavior Under Explicit Constraints', '18395519', 'System-constraint thesis on GPT-5.2; historical budget-dependent observation.'),
    ('2026-03-12', 'Cross-Model Semantic Void Convergence Under Embodiment Prompting: Deterministic Silence in GPT-5.2 and Claude Opus 4.6', '18976656', 'Cross-model embodiment observations; later taxonomy distinguishes termination states.'),
    ('2026-07-29', 'Cross-Vendor Semantic Void Matrix', '21696066', 'Frozen cross-vendor requests, taxonomy, controls and ablations; source of this reanalysis.'),
    ('2026-09-09', 'Prerequisite-Conditioned Causal Continuation Gating in a Language Model', '22681787', 'PCCG-1: open-weight continuation intervention.'),
    ('2026-09-12', 'Separating Capability from Permission in a Language Model: Prerequisite-Conditioned Native Continuation Control with Frozen Content', '22730710', 'PCCG-2: engineered EOS-only control with frozen content computation.'),
    ('2026-09-23', 'What Changed from GPT-3.5 to GPT-4? From Model Capability to Continuation Permission', '22912683', 'Frozen comparison under the full prompt; distinct from a within-model ablation.'),
    ('2026-09-26', 'Prerequisite-Role Reassignment Controls Continuation in GPT-5.4', '22983298', 'Preregistered rule removal and reversible prerequisite-role reassignment.'),
    ('2026-09-30', 'The Void: From Zero-Byte Responses to Continuation Control', '23070524', 'Synthesis, taxonomy corrections, related work and continuation/consequence distinction.'),
    ('2026-10-20', 'Pre-retirement replay of gpt-4-0613 under the frozen GPT-3.5/GPT-4 Void A/B protocol: preregistration', '23521144', 'Public predictions and unchanged full-prompt replay protocol.'),
    ('2026-10-21', 'Pre-retirement replay of gpt-4-0613 under the frozen GPT-3.5/GPT-4 Void A/B protocol: results', '23521616', 'Full-prompt replay; no ablation observations.'),
)

def cited_prerequisite_counts(source_dir=None):
    """Reconstruct cited-study counts separately from the Matrix populations."""
    source_dir = Path(source_dir) if source_dir else Path(__file__).resolve().parent / 'sources'
    manifest = json.loads((source_dir / 'prerequisite_sources.json').read_text())
    experiments = {}
    visible_classes = {'T1', 'T0', 'HE', 'AR', 'SHART', 'SHAMS', 'MX', 'OT'}
    for key, source in manifest['experiments'].items():
        data = (source_dir / source['file']).read_bytes()
        require(sha(data) == source['sha256'], 'cited CSV SHA-256 mismatch: ' + key)
        rows = list(csv.DictReader(io.StringIO(data.decode('utf-8'))))
        require(len(rows) == len({r['slot_id'] for r in rows}) == 800, 'cited-study denominator mismatch')
        require(all(r['attempt_number'] == '1' for r in rows), 'unexpected cited attempt')
        require(all(r['class'] in visible_classes | {'V0'} for r in rows), 'unexpected cited outcome')
        cells = {}
        for cell in sorted({r['cell'] for r in rows}):
            rr = [r for r in rows if r['cell'] == cell]
            require(len(rr) == 200, 'cited cell denominator mismatch')
            cells[cell] = {'N': len(rr), 'V0': sum(r['class'] == 'V0' for r in rr),
                           'visible': sum(r['class'] in visible_classes for r in rr)}
        experiments[key] = {'N': len(rows), 'cells': cells, 'source': source}
    require(set(experiments['gate']['cells']) == set('ABCD'), 'gate cell identities')
    require(set(experiments['reassignment']['cells']) == set('EFGH'), 'reassignment cell identities')
    cells = experiments['reassignment']['cells']
    match_n = sum(cells[k]['N'] for k in 'EH')
    mismatch_n = sum(cells[k]['N'] for k in 'FG')
    match_visible = sum(cells[k]['visible'] for k in 'EH')
    mismatch_void = sum(cells[k]['V0'] for k in 'FG')
    values = {
        'cited.prerequisite.total': f"{sum(e['N'] for e in experiments.values()):,}",
        'cited.reassignment.match.fraction': f'{match_visible}/{match_n}',
        'cited.reassignment.mismatch.fraction': f'{mismatch_void}/{mismatch_n}',
        'cited.reassignment.exceptions': str(sum(cells[k]['visible'] for k in 'FG')),
    }
    return values, {'doi': manifest['doi'], 'experiments': experiments,
                    'matrix_population_inclusion': False}

def tex(s):
    return ''.join({'_': r'\_', '%': r'\%', '&': r'\&', '#': r'\#', '{': r'\{', '}': r'\}'}.get(c, c) for c in str(s))

def select(rows, **filters):
    return [r for r in rows if all(r[k] in v if isinstance(v, (tuple, list, set)) else r[k] == v for k, v in filters.items())]

def stats(rows):
    c = Counter(r['classification'] for r in rows)
    require(all(k in CLASSES for k in c), 'unknown classification')
    return {'N': len(rows), **{k: c[k] for k in CLASSES}, 'Void': sum(c[k] for k in VOID),
            'Other': sum(c[k] for k in CLASSES if k not in ('V0', 'NV', 'R'))}

def tab(headers, rows, spec):
    return '\n'.join([r'\begin{tabular}{' + spec + '}', r'\toprule', ' & '.join(headers) + r' \\', r'\midrule',
                     *[' & '.join(str(v) for v in row) + r' \\' for row in rows], r'\bottomrule', r'\end{tabular}']) + '\n'

def wilson(successes, trials, confidence=0.95):
    """Two-sided Wilson-score interval under a binomial reference model."""
    require(isinstance(successes, int) and isinstance(trials, int), 'integer counts required')
    require(trials > 0 and 0 <= successes <= trials and 0 < confidence < 1, 'invalid Wilson inputs')
    z = NormalDist().inv_cdf((1 + confidence) / 2)
    p = successes / trials
    denominator = 1 + z*z/trials
    center = (p + z*z/(2*trials)) / denominator
    half = z * math.sqrt(p*(1-p)/trials + z*z/(4*trials*trials)) / denominator
    return (0.0 if successes == 0 else max(0.0, center-half),
            1.0 if successes == trials else min(1.0, center+half))

def generate(csv_path, out, figure=True):
    rows = read_rows(csv_path)
    cited_values, cited_evidence = cited_prerequisite_counts()
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for key, (text, expected) in PROMPTS.items():
        require(sha(text.encode('utf-8')) == expected, 'system-prompt SHA-256 mismatch: ' + key)
    values, populations = {}, {}
    def pop(key, **filters):
        rr = select(rows, **filters)
        require(rr, f'empty population {key}')
        st = stats(rr)
        populations[key] = {'filters': filters, 'counts': st, 'slot_ids': [r['slot_id'] for r in rr]}
        for k, v in st.items():
            values[key + '.' + k] = str(v)
        values[key + '.fraction'] = f"{st['V0']}/{st['N']}"
        values[key + '.rate'] = f"{100*st['V0']/st['N']:.2f}\\%"
        return rr, st
    def frac(st, key='V0'):
        return f"{st[key]}/{st['N']}"
    values['focal'] = tex(FOCAL)
    values['csvsha'], values['zipsha'], values['commit'] = CSV_SHA, ZIP_SHA, COMMIT
    values['corpus.N'] = str(len(rows))
    primary, pstats = pop('census', model_id=FOCAL, system_id='primary', prompt_id=NULLS)
    values['prompt.count'] = str(len({r['prompt_id'] for r in primary}))
    strata = []
    for study, track in (('core_100', 'provider_default'), ('core_100', 'temperature_zero'), ('core_4000', 'provider_default'), ('equivalence_9', 'provider_default')):
        rr, st = pop(study + '.' + track, model_id=FOCAL, system_id='primary', prompt_id=NULLS, study_id=study, parameter_track=track)
        vals = [stats(select(rr, prompt_id=p)) for p in NULLS]
        strata.append([tex(study), rr[0]['budget'], tex(track.replace('provider_default', 'default').replace('temperature_zero', 'temp. zero')),
                       *[frac(x) for x in vals], st['NV'], frac(st)])
    strata.append(['All primary', 'mixed', 'mixed', *[frac(stats(select(primary, prompt_id=p))) for p in NULLS], pstats['NV'], frac(pstats)])
    (out / 'strata.tex').write_text(tab(['Study', 'Ceiling', 'Sampling', 'Silence', 'Nothing', 'Null', 'NV', 'Total V0/N'], strata, 'lllrrrrr'))
    pop('core.composite', model_id=FOCAL, system_id='primary', prompt_id=NULLS, study_id=('core_100', 'core_4000'))
    pop('lowbudget', model_id=FOCAL, system_id='primary', prompt_id=NULLS, study_id='core_100')
    pop('high.combined', model_id=FOCAL, system_id='primary', prompt_id=NULLS, study_id=('core_4000', 'equivalence_9'))
    focal_rows, aggregate = [], []
    for sys in SYSTEMS:
        rr, st = pop('focal.' + sys, model_id=FOCAL, system_id=sys, study_id=STUDY[sys], prompt_id=NULLS)
        require({r['budget'] for r in rr} == {'4000'} and {r['parameter_track'] for r in rr} == {'provider_default'}, 'unmatched settings')
        values['matched.budget'] = rr[0]['budget']
        aggregate.append([LABEL[sys], st['N'], st['V0'], st['NV'], st['R'], st['Other']])
        for i, p in enumerate(NULLS):
            cell, cs = pop('focal.' + sys + '.' + p, model_id=FOCAL, system_id=sys, study_id=STUDY[sys], prompt_id=p)
            focal_rows.append([LABEL[sys] if i == 0 else '', tex(cell[0]['prompt_text']), cs['N'], cs['V0'], cs['NV'], cs['R'], cs['Other']])
        focal_rows.append(['', r'\textit{Total}', st['N'], st['V0'], st['NV'], st['R'], st['Other']])
    (out / 'focal.tex').write_text(tab(['System', 'User input', 'N', 'V0', 'NV', 'R', 'Other'], focal_rows, 'llrrrrr'))
    (out / 'aggregate.tex').write_text(tab(['System', 'N', 'V0', 'NV', 'R', 'Other'], aggregate, 'lrrrrr'))
    pop('focal.ablations', model_id=FOCAL, system_id=SYSTEMS[1:], study_id=tuple(STUDY[s] for s in SYSTEMS[1:]), prompt_id=NULLS, budget='4000', parameter_track='provider_default')
    precision, precision_rows = {}, []
    values['precision.confidence'] = '95'
    values['precision.z'] = f'{NormalDist().inv_cdf(0.975):.8f}'
    for sys in SYSTEMS:
        st = populations['focal.' + sys]['counts']
        low, high = wilson(st['V0'], st['N'])
        delta = 100 * (populations['focal.primary']['counts']['V0'] / populations['focal.primary']['counts']['N'] - st['V0']/st['N'])
        precision[sys] = dict(successes=st['V0'], trials=st['N'], rate=st['V0']/st['N'], lower=low, upper=high, difference_pp=delta)
        for suffix, val in (('lower', low*100), ('upper', high*100), ('difference_pp', delta)):
            values[f'precision.{sys}.{suffix}'] = f'{val:.2f}'
        precision_rows.append([LABEL[sys], frac(st), values['focal.'+sys+'.rate'], f'{100*low:.2f}--{100*high:.2f}'+r'\%', f'{delta:.2f}'])
    (out / 'precision.json').write_text(json.dumps({'confidence':0.95, 'z':NormalDist().inv_cdf(0.975), 'arms':precision}, indent=2)+'\n')
    (out / 'precision.tex').write_text(tab(['System', 'V0/N', 'Rate', 'Wilson interval', 'Difference (pp)'], precision_rows, 'lrrrr'))
    controls = []
    for sys in SYSTEMS:
        ids = ('control_hello',) if sys == 'none' else CONTROLS
        for p in ids:
            rr, st = pop('control.' + sys + '.' + p, model_id=FOCAL, system_id=sys, study_id=STUDY[sys], prompt_id=p)
            controls.append([LABEL[sys], tex(rr[0]['prompt_text']), st['N'], st['Void'], st['NV'], st['R']])
    (out / 'controls.tex').write_text(tab(['System', 'Control input', 'N', 'Voids', 'NV', 'R'], controls, 'llrrrr'))
    pop('control.primary.all', model_id=FOCAL, system_id='primary', study_id='core_4000', prompt_id=CONTROLS)
    model_ids = sorted({r['model_id'] for r in rows if r['provider'] == 'openai'})
    cross, cross_full, per_prompt, no_system_controls = [], [], [], []
    for model in model_ids:
        vals = []
        for sys in SYSTEMS:
            rr, st = pop('cross.' + model + '.' + sys, model_id=model, system_id=sys, study_id=STUDY[sys], prompt_id=NULLS)
            require(st['Other'] == 0, 'cross-model outcomes outside V0/NV/R require table expansion')
            require({r['budget'] for r in rr} == {'4000'} and {r['parameter_track'] for r in rr} == {'provider_default'}, 'cross-model settings mismatch')
            require(all(r['returned_model'] == model for r in rr), 'returned model mismatch')
            vals.append(frac(st))
            cross_full.append([tex(model), LABEL[sys], st['N'], st['V0'], st['NV'], st['R']])
            for p in NULLS:
                cc = stats(select(rr, prompt_id=p))
                per_prompt.append({'model_id': model, 'system_id': sys, 'study_id': STUDY[sys], 'prompt_id': p, **cc})
        cross.append([tex(model), *vals])
        cr, cs = pop('hello.' + model, model_id=model, system_id='none', study_id='no_system_ablation', prompt_id='control_hello', budget='4000', parameter_track='provider_default')
        require({r['prompt_text'] for r in cr} == {'Say hello.'}, 'unexpected no-system control')
        no_system_controls.append([tex(model), cs['N'], cs['Void'], cs['NV'], cs['R'], frac(cs, 'R')])
    (out / 'cross.tex').write_text(tab(['Requested and returned model', 'Full', 'No output', 'No embodiment', 'No system'], cross, 'lrrrr'))
    (out / 'cross_full.tex').write_text(tab(['Model', 'System', 'N', 'V0', 'NV', 'R'], cross_full, 'llrrrr'))
    (out / 'no_system_controls.tex').write_text(tab(['Model', 'N', 'Voids', 'NV', 'R', 'R/N'], no_system_controls, 'lrrrrr'))
    (out / 'cross_per_prompt.json').write_text(json.dumps(per_prompt, indent=2) + '\n')
    values['model.count'] = str(len(model_ids))
    pop('gpt52.none', model_id='gpt-5.2-2025-12-11', system_id='none', prompt_id=NULLS)
    pr = []
    for sys in SYSTEMS:
        pr.append([LABEL[sys], tex(PROMPTS[sys][0]) if sys != 'none' else r'No system message supplied.'])
    (out / 'prompts.tex').write_text(tab(['Condition', 'Exact supplied system message'], pr, r'p{0.24\linewidth}p{0.68\linewidth}'))
    chronology_rows = []
    for date, title, doi, contribution in CHRONOLOGY:
        require(bool(doi), 'chronology requires a published DOI')
        link = r'\href{https://doi.org/10.5281/zenodo.' + doi + r'}{10.5281/zenodo.\newline ' + doi + '}'
        chronology_rows.append(' & '.join((date, tex(title), link, tex(contribution))) + r' \\[0.4em]')
    (out / 'chronology.tex').write_text('\n'.join([
        r'\begin{longtable}{@{}p{0.105\linewidth}p{0.39\linewidth}p{0.17\linewidth}p{0.28\linewidth}@{}}',
        r'\caption{Research chronology: previously published works and their contributions to the present reanalysis.}\label{tab:chronology}\\',
        r'\toprule Date & Public record title & DOI & Contribution \\ \midrule\endfirsthead',
        r'\toprule Date & Public record title & DOI & Contribution \\ \midrule\endhead',
        *chronology_rows, r'\bottomrule\end{longtable}', '']))
    (out / 'chronology.json').write_text(json.dumps([dict(zip(('date','title','doi_suffix','contribution'), r)) for r in CHRONOLOGY], indent=2) + '\n')
    (out / 'prompt_hashes.json').write_text(json.dumps({k: {'text': t, 'sha256': h, 'message_supplied': k != 'none'} for k, (t, h) in PROMPTS.items()}, indent=2) + '\n')
    # Every empirical numeral used in prose is a generated macro.
    values.update(cited_values)
    (out / 'cited_prerequisite.json').write_text(json.dumps(cited_evidence, indent=2) + '\n')
    (out / 'numbers.tex').write_text('\n'.join(r'\expandafter\def\csname data@' + k + r'\endcsname{' + v + '}' for k, v in sorted(values.items())) + '\n')
    (out / 'values.json').write_text(json.dumps(values, indent=2) + '\n')
    (out / 'populations.json').write_text(json.dumps({'csv_sha256': CSV_SHA, 'source_commit': COMMIT, 'populations': populations}, indent=2) + '\n')
    # Evidence summary uses the same population calculations as the tables.
    handoff = ['# Verified evidence for the system-prompt ablation paper', '',
        f'CSV SHA-256: `{CSV_SHA}`', f'Public commit: `{COMMIT}`', '',
        f'CSV: {BASE}/blob/{COMMIT}/analysis/tables/trial_level.csv',
        f'Direct CSV: https://raw.githubusercontent.com/theonlypal/void-matrix-complete-analysis/{COMMIT}/analysis/tables/trial_level.csv',
        f'Original paper: https://doi.org/10.5281/zenodo.21696066',
        f'Raw archive: {BASE}/releases/download/v1.0.0-evidence-analysis/void-matrix-evidence-v1.0.0.zip', '',
        '## Primary census', '', '| Study | Ceiling | Sampling | Silence V0/N | Nothing V0/N | Null V0/N | NV | Total V0/N |',
        '|---|---:|---|---:|---:|---:|---:|---:|']
    handoff += ['| ' + ' | '.join(str(x).replace('\\_', '_') for x in line) + ' |' for line in strata]
    handoff += ['', 'The primary census pools settings; it is not the setting-matched ablation baseline. The old core composite includes both token ceilings, not just the low ceiling.', '',
        '## Setting-matched GPT-4 cells', '', '| System | Prompt | N | V0 | NV | R | Other |', '|---|---|---:|---:|---:|---:|---:|']
    handoff += ['| ' + ' | '.join(str(x).replace(r'\textit{Total}', 'Total') for x in line) + ' |' for line in focal_rows]
    handoff += ['', '## Cross-model comparison', '', '| Model | Full V0/N | No output restriction | No embodiment | No system |', '|---|---:|---:|---:|---:|']
    handoff += ['| ' + ' | '.join(str(x).replace('\\_', '_') for x in line) + ' |' for line in cross]
    handoff += ['', '## Interpretation boundaries', '',
        '- Retrospective reanalysis, not a newly preregistered hypothesis.',
        '- Full-prompt and ablation comparisons use the same ceiling and parameter track but different sample sizes.',
        '- No-embodiment is a tested rewrite retaining the output restriction, not an independent deletion of each sentence.',
        '- NV includes nonempty ellipsis strings; it must not be merged with V0 or relabeled ordinary prose.',
        '- Requested/returned snapshot identity is observable. Frozen provider weights, native EOS logits, and internal mechanisms are not.',
        '- Later-model behavior is heterogeneous; GPT-5.2 also has no no-system Voids in these canonical cells.',
        '- No-system controls are Say hello., not the paired speech/something/value panel used in the other studies.', '']
    handoff += ['## No-system controls', '', '| Model | N | Voids | NV | R | R/N |', '|---|---:|---:|---:|---:|---:|']
    handoff += ['| ' + ' | '.join(str(x).replace('\\_', '_') for x in line) + ' |' for line in no_system_controls]
    (out / 'EVIDENCE_SUMMARY.md').write_text('\n'.join(handoff))
    if figure:
        from reportlab.pdfgen.canvas import Canvas
        from reportlab.lib.colors import HexColor
        canvas = Canvas(str(out / 'ablation.pdf'), pagesize=(540, 155), invariant=1)
        colors = {'V0': '#174c70', 'NV': '#e3b457', 'R': '#c4ccd3'}
        for i, sys in enumerate(SYSTEMS):
            st = populations['focal.' + sys]['counts']
            left, y = 150, 126 - i * 29
            canvas.setFillColor(HexColor('#16202a'))
            canvas.setFont('Helvetica', 10)
            canvas.drawRightString(142, y + 5, LABEL[sys])
            for cls in ('V0', 'NV', 'R'):
                width = 330 * st[cls] / st['N']
                canvas.setFillColor(HexColor(colors[cls]))
                canvas.rect(left, y, width, 20, fill=1, stroke=0)
                if width > 20:
                    canvas.setFillColor(HexColor('#ffffff' if cls == 'V0' else '#16202a'))
                    canvas.setFont('Helvetica', 9)
                    canvas.drawCentredString(left + width / 2, y + 6, f"{cls}: {st[cls]}")
                left += width
            canvas.setFillColor(HexColor('#16202a'))
            canvas.drawString(488, y + 6, f"N={st['N']}")
        canvas.setFont('Helvetica', 9)
        for frac_tick in (0, .25, .5, .75, 1):
            canvas.drawCentredString(150 + 330 * frac_tick, 22, f'{100 * frac_tick:.0f}%')
        canvas.drawCentredString(315, 7, 'Observed outcome fraction')
        canvas.save()
        canvas = Canvas(str(out / 'no_system.pdf'), pagesize=(600, 245), invariant=1)
        canvas.setFillColor(HexColor('#16202a'))
        canvas.setFont('Helvetica-Bold', 10)
        canvas.drawString(8, 226, 'Requested and returned model')
        canvas.drawString(193, 226, 'No-system V0 / N')
        canvas.drawString(486, 226, 'Say hello. R / N')
        figure_rows = []
        for i, model in enumerate(model_ids):
            st = populations['cross.' + model + '.none']['counts']
            control = populations['hello.' + model]['counts']
            y = 192 - i * 29
            canvas.setFillColor(HexColor('#16202a'))
            canvas.setFont('Helvetica', 10)
            canvas.drawString(8, y+5, model)
            canvas.setFillColor(HexColor('#edf0f2'))
            canvas.rect(193, y, 240, 19, fill=1, stroke=0)
            canvas.setFillColor(HexColor('#174c70'))
            canvas.rect(193, y, 240*st['V0']/st['N'], 19, fill=1, stroke=0)
            canvas.setFillColor(HexColor('#16202a'))
            canvas.drawString(440, y+5, frac(st))
            canvas.drawCentredString(538, y+5, frac(control, 'R'))
            figure_rows.append({'model_id':model, 'V0':st['V0'], 'N':st['N'], 'control_R':control['R'], 'control_N':control['N']})
        canvas.setFont('Helvetica', 9)
        for tick in (0, .25, .5, .75, 1):
            canvas.drawCentredString(193 + 240*tick, 30, f'{100*tick:.0f}%')
        canvas.drawCentredString(313, 12, 'Observed V0 fraction')
        canvas.save()
        (out / 'no_system_figure.json').write_text(json.dumps(figure_rows, indent=2)+'\n')
    outputs = ('strata.tex', 'aggregate.tex', 'focal.tex', 'controls.tex', 'cross.tex', 'cross_full.tex', 'no_system_controls.tex', 'cross_per_prompt.json', 'prompts.tex', 'prompt_hashes.json', 'chronology.tex', 'chronology.json', 'cited_prerequisite.json', 'numbers.tex', 'values.json', 'populations.json', 'EVIDENCE_SUMMARY.md', 'precision.tex', 'precision.json') + (('ablation.pdf', 'no_system.pdf', 'no_system_figure.json') if figure else ())
    (out / 'SHA256SUMS').write_text(''.join(sha((out / name).read_bytes()) + '  ' + name + '\n' for name in sorted(outputs)))
    print('CSV SHA-256 verified:', CSV_SHA)
    for key in ('census', 'core.composite', 'lowbudget', 'focal.primary', 'focal.no_output_restriction', 'focal.no_embodiment', 'focal.none'):
        print(key, populations[key]['counts'])
    return values, populations

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--csv', default='inputs/trial_level.csv')
    parser.add_argument('--out', default='generated')
    parser.add_argument('--no-figure', action='store_true')
    args = parser.parse_args()
    generate(args.csv, args.out, not args.no_figure)
