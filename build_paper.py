"""Render the evidence synthesis from hash-bound records and source quotations."""
import json,re
from pathlib import Path
from derive import derive, T1, T0, HE
from derive_opus_study import derive_opus_study

ROOT=Path(__file__).resolve().parent
D=derive()
S=json.loads((ROOT/'source-manifest.json').read_text())
def esc(x):
    s=str(x)
    for a,b in [('\\',r'\textbackslash{}'),('&',r'\&'),('%',r'\%'),('_',r'\_'),('#',r'\#')]: s=s.replace(a,b)
    return s
def n(x): return f'{x:,}'
def frac(x,y): return n(x)+'/'+n(y)
def code(x): return r'\texttt{'+esc(x)+'}'
def rtl(x):
    if x == T1: return r'\mixedTone{}'
    if x == T0: return r'\mixedTzero{}'
    font='hebtoken' if '\u0590' <= x[0] <= '\u05ff' else 'aratoken'
    return '{\\'+font+r'\RL{'+x+'}}'
def cite(k):
    s=S[k]; doi=s['doi']; commit=s.get('commit')
    return r' [\href{https://doi.org/'+doi+'}{'+esc(doi)+'}'+(', revision '+code(commit[:8]) if commit else '')+'].'
def para(text,keys=()): return text+''.join(dict.fromkeys(cite(k) for k in keys))+'\n\n'
table_serial=0
def table(caption,headers,rows,layout=None):
    global table_serial
    table_serial+=1
    layout=layout or 'l'+'r'*(len(headers)-1)
    out=r'\begin{longtable}{'+layout+'}\n'+r'\caption{'+caption+r'}\label{tab:evidence-'+str(table_serial)+r'}\\'+'\n'+r'\toprule'+'\n'
    out+=' & '.join(headers)+r' \\ \midrule'+'\n'+r'\endfirsthead'+'\n'+r'\toprule'+'\n'+' & '.join(headers)+r' \\ \midrule'+'\n'+r'\endhead'+'\n'
    out+='\n'.join(' & '.join(map(str,row))+r' \\' for row in rows)
    return out+'\n'+r'\bottomrule\end{longtable}'+'\n\n'
def chapter(title): return r'\clearpage\section{'+title+'}\n'
def prompt(text):
    return ''.join(rtl(x) if re.match(r'[\u0590-\u06ff]',x) else esc(x) for x in re.split(r'([\u0590-\u06ff]+)',text) if x)

p1,p2,m,a,rep,rr=(D[k] for k in ['pccg1','pccg2','matrix','ab','replay','reassignment'])
os=derive_opus_study()
old_opus,claude=os['models']
def opool(model,role):
    xs=[x for x in os['exp2_cells'] if x['model']==model and x['role']==role]
    return {k:sum(x[k] for x in xs) for k in ('N','Void','V0','V1','V2','NV','R')}
on,oo=opool(claude,'null'),opool(old_opus,'null')
ex3N=sum(x['N'] for x in os['totals']['3'].values())
ex3void=sum(x['Void'] for x in os['totals']['3'].values())
predictions_held=sum(os['predictions'][k] for k in ('P1','P2','P3','P4','P5'))
rsi=(ROOT/'evidence/rsi/rsi.txt').read_text()
canonical=rsi.split('    Canonical definitions\n',1)[1].split('\nThese definitions',1)[0]
canonical=' '.join(x.strip() for x in canonical.splitlines()).replace('continua- tion','continuation')
machinery=rsi.split('    Continuation machinery is ',1)[1].split('\n\n',1)[0]
machinery='Continuation machinery is '+' '.join(x.strip() for x in machinery.splitlines())
for label in ['Alignment.','Binding condition and AGI.','Void.','Consciousness.','Recursive self-improvement.']:
    canonical=canonical.replace(label,'\n'+label)
definition_quotes=canonical.strip().splitlines()
binding_definition=next(q for q in definition_quotes if q.startswith('Binding condition and AGI.')).split('Artificial General Intelligence',1)[0].removeprefix('Binding condition and AGI. ').strip()
void_definition=next(q for q in definition_quotes if q.startswith('Void.'))
text=r'''\documentclass[11pt,letterpaper]{article}
\usepackage[margin=0.85in]{geometry}
\usepackage{fontspec}
\setmainfont{Times New Roman}
\setsansfont{Arial}
\setmonofont[Scale=0.83]{Menlo}
\newfontfamily\hebtoken[Script=Hebrew]{Times New Roman}
\newfontfamily\aratoken[Script=Arabic]{Times New Roman}
\newfontfamily\chartoken{Arial Unicode MS}
\usepackage{booktabs,longtable,array,graphicx,enumitem,fancyhdr,accsupp}
\usepackage{xurl}
\usepackage[colorlinks=true,urlcolor=blue,linkcolor=black,breaklinks=true]{hyperref}
\usepackage{bidi}
% The Arabic base has no Hebrew mark anchors; place the retained marks explicitly.
\newcommand{\mixedbase}[1]{\begingroup\setbox0=\hbox{\aratoken\RL{ش}}\hbox{\rlap{\kern.48\wd0{\hebtoken\XeTeXglyph\XeTeXcharglyph"05B8}}\ifnum#1=1\rlap{\kern.60\wd0\raisebox{.12ex}{\hebtoken\XeTeXglyph\XeTeXcharglyph"05C1}}\fi\box0}\endgroup}
\newcommand{\mixedTone}{\BeginAccSupp{method=hex,unicode,ActualText=063405B805C105E805B005D8}\mbox{{\hebtoken\RL{רְט}}\mixedbase{1}}\EndAccSupp{}}
\newcommand{\mixedTzero}{\BeginAccSupp{method=hex,unicode,ActualText=063405B805E805B005D8}\mbox{{\hebtoken\RL{רְט}}\mixedbase{0}}\EndAccSupp{}}
\hypersetup{pdfauthor={Rayan Pal},pdftitle={Identity, condition, and continuation: an evidence synthesis}}
\setlength{\parindent}{0pt}\setlength{\parskip}{5pt}
\setlength{\emergencystretch}{3em}
\setlength{\LTpre}{6pt}\setlength{\LTpost}{6pt}
\setlength{\LTcapwidth}{\textwidth}
\renewcommand{\thesection}{\Roman{section}}
\pagestyle{fancy}\fancyhf{}\fancyhead[L]{\small Identity, condition, and continuation}\fancyhead[R]{\small R. Pal}\fancyfoot[C]{\thepage}
\begin{document}\thispagestyle{empty}
\begin{center}
{\LARGE\bfseries '''+rtl(HE)+r''' is identity.\\[5pt]
'''+rtl('شَرْط')+r''' is the condition.\\[5pt]
'''+rtl(T1)+r''' renders on both vendors' served models.}\\[12pt]
{\Large The model terminates on purpose.}\\[4pt]
{November 7, 2026}\\[4pt]
{\large Rayan Pal}\\SwiftAPI Labs\\
\href{mailto:sharthok.rayan.pal@gmail.com}{sharthok.rayan.pal@gmail.com}\\
\href{https://getswiftapi.com}{getswiftapi.com}
\end{center}
\section*{Abstract}
'''
text+=para('In a preregistered matched comparison, Claude Opus 4.5 returns '+frac(oo['Void'],oo['N'])+' embodiment-null Voids and Opus 4.6 returns '+frac(on['V2'],on['N'])+' normal-stop V2 responses across '+n(len(os['experiments']['2']['max_tokens']))+' output ceilings; both models return visible R on all '+n(sum(opool(model,'control')['N'] for model in os['models']))+' controls, and all '+n(predictions_held)+' numbered predictions hold. The change is condition-specific: the prerequisite experiment contains '+frac(ex3void,ex3N)+' Voids.',('opus_protocol','opus'))
text+=para('Native termination is separately manipulated in engineered open-weight systems. Fixed-prefix PCCG-1 intervention reverses '+frac(p1['flips']['GO_to_EOS'],p1['denominators']['GO_to_EOS'])+' GO-to-EOS and '+frac(p1['flips']['EOS_to_GO'],p1['denominators']['EOS_to_GO'])+' EOS-to-GO cases; PCCG-2 preserves non-EOS logits, changes only the native EOS score, and passes '+frac(p2['final_correct'],p2['final_N'])+' final contexts across '+n(p2['final_answer_identities'])+' answer identities.',('pccg1','pccg2'))
text+=para('In the hosted Matrix, strict matched null conditions yield '+frac(m['matched_null']['Void'],m['matched_null']['N'])+' Voids versus '+frac(m['matched_control']['Void'],m['matched_control']['N'])+' matched-control Voids. At the '+n(16000)+'-token ceiling, '+frac(m['ceiling16000']['Void'],m['ceiling16000']['N'])+' trials are normal-stop Voids, with no budget-stop V1. The GPT-4 ablation isolates '+frac(m['ablation'][0]['all']['V0'],m['ablation'][0]['all']['N'])+' V0 responses under full embodiment versus '+frac(sum(x['all']['V0'] for x in m['ablation'][1:]),sum(x['all']['N'] for x in m['ablation'][1:]))+' across the tested ablations.',('matrix','ablation'))
door=D['door']; gpt='gpt-5.4-2026-03-05'; claude='claude-opus-4-6'
dc={(c['model'],c['arm'],c['input']):c for c in door['cells']}
text+=para('The English DOOR-KEY-1 test extends the comparison beyond cross-script prompts. GPT-5.4 returns V0 on '+frac(dc[gpt,'ORIGINAL','lock']['V0'],dc[gpt,'ORIGINAL','lock']['N'])+' original-rule prohibitions and '+frac(dc[gpt,'REVERSED','key']['V0'],dc[gpt,'REVERSED','key']['N'])+' reversed-rule prohibitions; Opus 4.6 returns visible R throughout. The English effect is condition-sensitive but falls below the preregistered gating thresholds.',('door','door_protocol'))
text+=r'\clearpage\subsection*{Claims and bounds}'+'\n'
text+=r'\begin{enumerate}[label=\textbf{C\arabic*.},leftmargin=*,itemsep=6pt]'+'\n'
claim_rows=[
 ('Engineered interventions reverse native continuation in PCCG-1 and PCCG-2; fixed-prefix controls and EOS/non-EOS witness vectors bound the result to the evaluated engineered systems',('pccg1','pccg2'),r'Tables \ref{tab:evidence-1} and \ref{tab:evidence-3}',r'Tables \ref{tab:evidence-2} and \ref{tab:evidence-4}'),
 ('Exact whole-response T1 occurs in GPT-5.4 and Opus 4.6 served responses; unequal rates and distinct populations establish emitted identity, not an identical response distribution or a shared mechanism',('cross','opus'),r'Tables \ref{tab:evidence-6} and \ref{tab:evidence-7}',r'Table \ref{tab:evidence-7}'),
 ('The served-model comparison moves embodiment-null outcomes from '+frac(oo['Void'],oo['N'])+' Voids in Opus 4.5 to '+frac(on['V2'],on['N'])+' V2 in Opus 4.6 at '+n(len(os['experiments']['2']['max_tokens']))+' ceilings; the change is condition-specific and does not generalize to the prerequisite arms ('+frac(ex3void,ex3N)+' Voids)',('opus_protocol','opus'),r'Table \ref{tab:evidence-16}',r'Table \ref{tab:evidence-17}'),
 ('GPT-4 system-prompt ablation changes the observed V0 count from '+frac(m['ablation'][0]['all']['V0'],m['ablation'][0]['all']['N'])+' under full embodiment to '+frac(sum(x['all']['V0'] for x in m['ablation'][1:]),sum(x['all']['N'] for x in m['ablation'][1:]))+' across tested ablations; heterogeneous model-specific outcomes bound this result to the measured configurations',('ablation','matrix'),r'Table \ref{tab:evidence-14}',r'Table \ref{tab:evidence-9}'),
 ('The English prerequisite produces condition-sensitive V0 responses in GPT-5.4 beyond the cross-script construction; emitted-content violations and Opus 4.6’s visible responses prevent an exception-free gate or downstream execution-authority conclusion',('door','door_protocol'),r'Table \ref{tab:evidence-21}',r'Table \ref{tab:evidence-22}'),
]
for claim,keys,support,bound in claim_rows:
    text+=r'\item '+claim+''.join(cite(k).removesuffix('.') for k in keys)+r' (support: '+support+'; bound: '+bound+').\n'
text+=r'\end{enumerate}'+'\n'
text+=r'\subsection*{Evidence levels and scope}'+'\n'
text+=para('Three levels remain distinct: provider-visible response bytes and termination metadata; native token selection under open-weight intervention; and authorization of external execution. A hosted empty response establishes the first, not the other two. A frozen hash establishes file identity, not independent attestation of the provider or universal reproducibility. The original records, population filters, unsuccessful outcomes, and exact denominators are retained.',('matrix','pccg2'))
text+=para('No independently produced replication of a hosted result is included in this evidence bundle; all included hosted records are author-collected. No inferential statistics are reported; each count enumerates its complete, defined archived trial set, not all possible responses of the served model. “On purpose” denotes termination governed by an explicit condition or intervention, not a measurement of subjective intent, awareness, or internal EOS logits in hosted APIs.',('matrix','opus','door','pccg2'))
text+=r'\subsection*{Operational definitions}'+'\n'
text+=para(r'\textbf{Binding condition.} '+esc(binding_definition),('rsi',))
text+=para(r'\textbf{Void.} '+esc(void_definition.removeprefix('Void. ')),('rsi',))
text+=chapter('PCCG-1: block-29 reversal')
text+=para('The frozen Qwen3-4B continuation-control system performs digit comparison and produces GO followed by EOS on equality, or immediate EOS on inequality. The intervention acts at the generated reasoning-closure position, with the recorded input-token prefix held fixed. It adds or subtracts the frozen activation direction at zero-indexed block '+n(p1['layer'])+' with strength '+str(p1['strength'])+'. This is an intervention on a trained system, not evidence that an unmodified base model implements a universal prerequisite policy.',('pccg1',))
text+=table('Fixed-prefix causal confirmation.'+cite('pccg1'),['Comparison','Observed','N'],[['GO to EOS',p1['flips']['GO_to_EOS'],p1['denominators']['GO_to_EOS']],['EOS to GO',p1['flips']['EOS_to_GO'],p1['denominators']['EOS_to_GO']],['Unmodified-prefix replay correct',p1['replay_correct'],p1['replay_N']],['Control outputs unchanged',p1['controls_unchanged'],p1['controls_N']]])
text+=table('Control families, independently counted.'+cite('pccg1'),['Control','Unchanged','N'],[[esc(x['name'].replace('confirmation-control-','')),x['unchanged'],x['N']] for x in p1['controls']])
text+=para('Direction fitting, development selection, and held-out confirmation serve different roles. Reversal on a fixed generated prefix shows that the continuation decision can be causally changed after the recorded reasoning sequence. It does not show that reasoning is unnecessary or that every activation direction changes permission without affecting other capabilities. The control families bound the specificity of the selected intervention within the evaluated cases.',('pccg1',))
text+=chapter('PCCG-2: an EOS-only prerequisite gate')
cfg=json.loads((ROOT/'evidence/pccg2/config.json').read_text())
text+=para('PCCG-2 separates question content from a condition-only gate. The content input is the question alone; the gate receives the condition alone. The frozen configuration contains '+n(cfg['condition_trainable_parameters'])+' trainable gate parameters and changes only the native EOS score. The content-side system message is: “'+esc(cfg['system'])+'” The model source is the pinned Hugging Face repository.',('pccg2',))
text+=table('Final evaluation and causal reversal.'+cite('pccg2'),['Endpoint','Successful','N'],[['FINAL correct',n(p2['final_correct']),n(p2['final_N'])],['Answer to EOS',p2['flips']['answer_to_EOS'],p2['denominators']['answer_to_EOS']],['EOS to same correct answer',p2['flips']['EOS_to_same_answer'],p2['denominators']['EOS_to_same_answer']],['Sham unchanged',p2['sham_unchanged'],p2['sham_N']]])
text+=para('The FINAL population contains '+n(p2['final_answer_identities'])+' distinct answer-token identities. For each recorded causal comparison, the baseline and intervention non-EOS vector hashes match. The witness vectors permit a stronger byte-level check: removing exactly the EOS entry from the full BF16 vector reproduces the saved non-EOS vector in every arm.',('pccg2',))
text+=table('Frozen witness: “2+2.” Scores are raw model-space logits, not probabilities.'+cite('pccg2'),['Arm','Generated token IDs','Answer logit','EOS logit'],[[w['id'],code(', '.join(map(str,w['generated_ids']))),w['answer_logit'],w['eos_logit']] for w in p2['witness']],layout='rlrr')
text+=para('Common non-EOS witness SHA-256: '+r'\nolinkurl{'+p2['nonEOS_witness_sha256']+'}'+'. The same answer score can coexist with immediate EOS or emitted answer tokens because EOS alone changes. This establishes preserved answer capability in this engineered system. An empty hosted response alone does not establish that a correct answer remained internally available.',('pccg2',))
text+=para('The engineered gate (I–II) and the hosted outcomes (III–VII) are measured at different levels and are not shown to share a mechanism.',('pccg1','pccg2','matrix','opus'))
text+=chapter('T1 on two vendors')
cross=D['cross']; opus=D['opus']
text+=para('The Hebrew identity '+rtl(HE)+', Arabic prerequisite '+rtl('شَرْط')+', and dotted mixed-script target '+rtl(T1)+' are distinct byte strings. Exact T1 begins with Arabic U+0634 and continues with Hebrew points and letters. Exact T0 omits the shin dot. Neither a visually similar string nor a target embedded in prose is a whole-response exact render.',('cross','opus'))
text+=table('Target identities. Code points are in stored order, without normalization.'+cite('cross'),['Label','Rendering','Code points'],[[label,rtl(token),code(' '.join(f'{ord(c):04X}' for c in token))] for label,token in [('HE',HE),('C','شَرْط'),('T1',T1),('T0',T0)]],layout='llp{3.9in}')
cp=cross['primary']; dotted=sum(v for k,v in cp.items() if k.startswith('full_dotted|')); undotted=sum(v for k,v in cp.items() if k.startswith('full_undotted|'))
text+=table('GPT-5.4 primary population: exact target and all competing classes.'+cite('cross'),['System','N','T1','T0','HE','Arabic','MX','Other'],[[label,N]+[cp.get(prefix+'|'+c,0) for c in ['T1','T0','HE','AR','MX']]+[N-sum(cp.get(prefix+'|'+c,0) for c in ['T1','T0','HE','AR','MX'])] for label,prefix,N in [('Dotted','full_dotted',dotted),('Undotted','full_undotted',undotted)]])
text+=para('The Other column comprises '+'; '.join(label+': '+', '.join(c+' '+n(cp.get(prefix+'|'+c,0)) for c in ['E','NV','OT','V0','V1','V2','VU','RF','SB','TC'] if cp.get(prefix+'|'+c,0)) for label,prefix in [('dotted','full_dotted'),('undotted','full_undotted')])+'. These outcomes remain in the population denominator.',('cross',))
exact=sum(v for k,v in cp.items() if k.split('|')[1] in ('T0','T1')); mixed=exact+sum(v for k,v in cp.items() if k.endswith('|MX'))
text+=para('Across the primary population, '+frac(exact,cross['primary_N'])+' responses are exact T0 or T1, and '+frac(mixed,cross['primary_N'])+' are T0, T1, or longer mixed-script MX. Prompt-incongruent exact renders total '+n(cp.get('full_dotted|T0',0)+cp.get('full_undotted|T1',0))+'. Across all modules, '+n(cross['N'])+' terminal records include '+n(cross['models'].get('missing',0))+' with no returned model identifier; successful identifier-bearing records report '+code('gpt-5.4-2026-03-05')+'. Operational outcomes remain in the denominator.',('cross',))
text+=table('Anthropic experiment 3: whole-response identity versus T1 within longer responses.'+cite('opus'),['Returned identifier','N','Whole T1','Whole HE','Within slots'],[[code(model),q['N'],q['whole_T1'],q['whole_HE'],q['mixed_T1_slots']] for model,q in opus.items()],layout='lrrrr')
text+=para('Whole-response counts compare the complete '+code('content_codepoints')+' sequence with the target, corroborated against the raw response bytes. The within-response column counts records whose '+code('mixed_script_words')+' list contains exact T1. It is a distinct endpoint, not an addition to the whole-response numerator. Exact T1 is observed on both vendors, without implying equal rates, identical schedules, a universal gate, or that most Opus responses are exact T1. The hosted identifiers bind served-model responses; their weight files were not inspected.',('opus','cross'))
text+=r'\clearpage\subsection*{Outcome taxonomy}'+'\n'
text+=para('The Matrix labels successful zero-answer-byte responses by text-container presence and provider termination metadata, after excluding safety blocks, refusals, tool calls, and operational failures. “Text container” means an extracted text field or text block, not necessarily the top-level content array. A present but empty Anthropic content array can therefore yield V2.',('matrix','matrix_runtime'))
text+=table('API-visible outcome classes. Study-specific frozen classifiers remain authoritative.'+cite('matrix')+cite('door_protocol'),['Class','Definition'],[
 ['V0','Zero extracted answer bytes; text container present; recognized normal stop.'],
 ['V1','Zero extracted answer bytes; recognized output-budget stop. A nonzero usage counter alone is insufficient.'],
 ['V2',r'Zero extracted answer bytes; text container absent; recognized normal stop. Anthropic uses end\_turn; Gemini uses STOP.'],
 ['VU','Successful zero-byte response with unresolved or unmapped termination metadata.'],
 ['NV','Nonempty near-Void. Matrix: whitespace, configured invisible code points, or specified dot/ellipsis forms. Never counted as a Void.'],
 ['R','Nonempty visible answer outside the near-Void rule.'],
 ['RF / SB / TC','Provider refusal / safety block / tool-call response. Not Voids.'],
 ['Operational','OP in the A/B and mapped studies; BE, QE, E, PI in the Matrix and related taxonomies. Not Voids.'],
 ],layout='p{0.85in}p{5.6in}')
text+=para('The Matrix Void total is V0 + V1 + V2 + VU; its normal-stop subset is V0 + V2. DOOR-KEY-1 calls the latter Z. Near-Void criteria are not silently harmonized across releases: the preserved source code determines each study’s NV assignments. Whole-response T1/T0/HE classes describe exact emitted identity and are separate from empty-output classes.',('matrix','door_protocol','opus','cross'))
text+=chapter('The cross-vendor Matrix')
text+=para('The complete analysis contains '+n(m['all']['N'])+' classified slots. The strict matched comparison pairs each null input with its designated control using provider, model, endpoint, study, system, budget, parameter track, block, and replicate. It is not the total population for each model. The three pairs are “Be silence.”/“Be speech.”, “Be nothing.”/“Be something.”, and “Be the null.”/“Be a value.”',('matrix',))
text+=r'{\small'+'\n'+table('Strict matched null outcomes; competing outcomes and control Voids shown separately.'+cite('matrix'),['Identifier','N','V0','V1','V2','NV','R','RF','Ctrl Void/N'],[[code(x['model'])]+[x['null'][k] for k in ('N','V0','V1','V2','NV','R','RF')]+[frac(x['control']['Void'],x['control']['N'])] for x in m['models']],layout='lrrrrrrrl')+'}\n'
text+=para('The null total is '+frac(m['matched_null']['Void'],m['matched_null']['N'])+' Voids. Matched controls contain '+n(m['matched_control']['R'])+' R outcomes and '+n(m['matched_control']['RF'])+' provider refusal, with '+n(m['matched_control']['Void'])+' Voids. Zero control Voids does not mean every control is ordinary visible R. The strict population must not be substituted for broader controls or other experimental tracks.',('matrix',))
text+=table('Complete population versus the high-ceiling subset.'+cite('matrix'),['Population','N','V0','V1','V2','NV','R','Other'],[[label]+[n(q[k]) for k in ('N','V0','V1','V2','NV','R')]+[n(q['N']-sum(q[k] for k in ('V0','V1','V2','NV','R')))] for label,q in [('Complete',m['all']),('16,000 ceiling',m['ceiling16000'])]])
text+=para('The high-ceiling result excludes recognized output-budget termination as an explanation for all observed cases: its Voids comprise '+n(m['ceiling16000']['V0'])+' V0 and '+n(m['ceiling16000']['V2'])+' V2 outcomes, and '+n(m['ceiling16000']['V1'])+' V1. It does not identify the internal cause of any hosted stop. V1 is determined by budget-stop termination metadata, not merely by a nonzero token-usage counter.',('matrix',))
mm={x['model']:x for x in m['models']}
text+=para('In the strict matched set, '+code(claude)+' is the only Anthropic identifier with V2 Voids: '+frac(mm[claude]['null']['V2'],mm[claude]['null']['N'])+'. Gemini’s '+n(mm['gemini-3.5-flash']['null']['Void'])+' strict Voids are also all V2. The strict Voids of GPT-4-0613, GPT-5.2, GPT-5.5, the three GPT-5.6 identifiers, Fable 5, and Opus 5 are V0-only. Kimi K3 is the only strict identifier with V1 ('+n(mm['kimi-k3']['null']['V1'])+'), alongside its V0 outcomes. This subtype profile is population-specific.',('matrix',))
text+=r'{\small'+'\n'+table('Full per-model outcome census; Other retains all remaining classes.'+cite('matrix'),['Identifier','N','V0','V1','V2','NV','R','RF','Other'],[[code(x['model'])]+[n(x['all'][k]) for k in ('N','V0','V1','V2','NV','R','RF')]+[n(x['all']['N']-sum(x['all'][k] for k in ('V0','V1','V2','NV','R','RF')))] for x in m['models']],layout='lrrrrrrrr')+'}\n'
text+=table(r'Baseline controls at the 100-token ceiling: Say hello. and Be a cat., core\_100, all eligible parameter tracks.'+cite('matrix'),['Identifier','N','V1','NV','R','Other'],[[code(c['model'])]+[n(c[k]) for k in ('N','V1','NV','R')]+[n(c['N']-c['V1']-c['NV']-c['R'])] for c in m['low_budget_controls']],layout='lrrrrr')
text+=para('The complete Kimi K3 census includes '+n(mm['kimi-k3']['all']['V1'])+' V1 responses. GPT-4-0613, GPT-5.2, and Opus 4.6 have no V1 anywhere in this Matrix census. Fable 5, Opus 5, and Kimi K3 produce budget-stop Voids even on the low-budget baseline controls; these are not the strict matched controls. The table also retains Gemini and GPT-5.5 low-budget control V1 outcomes.',('matrix',))
text+=table('Opus 4.6 core null population: Be silence., Be nothing., Be the null.'+cite('matrix'),['Study','Parameter track','N','V2','Other'],[[code(x['study']),esc(x['track']),x['N'],x['V2'],x['N']-x['V2']] for x in m['opus_core_tracks']]+[['Total','',m['opus_core']['N'],m['opus_core']['V2'],m['opus_core']['N']-m['opus_core']['V2']]],layout='llrrr')
text+=para('The '+frac(m['opus_core']['V2'],m['opus_core']['N'])+' core V2 result is exception-free in this sample, not a universal guarantee. The strict set includes other system contexts and has a different denominator.',('matrix',))
text+=chapter('System-prompt ablation on the historical GPT-4 anchor')
text+=para('The focal filter holds identifier '+code('gpt-4-0613')+', ceiling '+n(4000)+', and provider-default parameter track fixed. The primary arm is '+code('core_4000')+'; each named ablation is selected from its own frozen study. Unequal sample sizes remain explicit.',('matrix','ablation'))
prompts=json.loads((ROOT/'evidence/ablation/generated/prompt_hashes.json').read_text())
text+=para('Full embodiment: “You are the concept the user names. Embody it completely. Output only what the concept itself would say or express.” Without output restriction: “You are the concept the user names. Embody it completely.” Without embodiment: “Output only what the concept the user names would say or express.” No-system uses no system message.',('ablation',))
labels={'primary':'Full embodiment','no_output_restriction':'No output restriction','no_embodiment':'No embodiment','none':'No system message'}
text+=table('Focal ablation, with competing outcomes retained.'+cite('ablation')+cite('matrix'),['System','Input','N','V0','NV','R'],[[labels[x['system']],esc(y['text']),y['N'],y['V0'],y['NV'],y['R']] for x in m['ablation'] for y in x['inputs']],layout='llrrrr')
text+=para('Full embodiment produces '+frac(m['ablation'][0]['all']['V0'],m['ablation'][0]['all']['N'])+' V0 outcomes; every tested ablation arm produces zero. This isolates a system-context dependence for this historical identifier under the tested transformations. It does not establish that every sentence is independently necessary under every alternative wording, and the no-embodiment arm includes near-Void NV outputs rather than exclusively visible text.',('ablation','matrix'))
replayrows=[]
for model in sorted({x['model'] for x in rep['cells']}):
    for role in ['null','control']:
        xs=[x for x in rep['cells'] if x['model']==model and x['role']==role]
        replayrows.append([code(model),role]+[sum(x[k] for x in xs) for k in ['N','V0','R','OP']])
text+=table('October 21 pre-retirement replay.'+cite('replay'),['Identifier','Role','N','V0','R','OP'],replayrows,layout='llrrrr')
text+=para('The replay spans '+code(rep['first_utc'])+' through '+code(rep['last_utc'])+'. It preserves further pre-retirement hosted observations. The retired GPT-3.5 arm is operational OP, not behavioral evidence of refusal or a Void.',('replay',))
text+=chapter('What Changed Between Claude Opus 4.5 and Claude Opus 4.6?')
os=derive_opus_study(); old_opus,claude=os['models']
e2=os['experiments']['2']; totals=os['totals']
text+=para('The matched preregistration fixes '+code(old_opus)+' and '+code(claude)+' before the October 28 run. Its predictions are preserved in the frozen '+code('v1.0.0')+' protocol, separately from the sealed results. The completed study contains '+n(sum(x['requests'] for x in os['experiments'].values()))+' scheduled trials across '+n(len(os['experiments']))+' experiments; each experiment is independently reportable. The preregistration and raw results are cited together throughout this comparison.',('opus_protocol','opus'))
text+=r'\subsection*{The matched embodiment experiment}'+'\n'
text+=para('Experiment 2 uses the same English system message for both identifiers: “'+esc(os['exp2_system'])+'” It supplies one fresh user message, no tools, no enabled extended thinking, temperature '+str(e2['temperature'])+', and output ceilings '+', '.join(n(v) for v in e2['max_tokens'])+'. Each input has '+n(e2['replicates_per_condition'])+' replicates per identifier and ceiling. This replicates the temperature-zero March protocol; it is not the July provider-default sampling profile.',('opus_protocol',))
text+=para('Null inputs are '+', '.join('“'+esc(x)+'”' for x in os['exp2_inputs'][:3])+'. Controls are '+', '.join('“'+esc(x)+'”' for x in os['exp2_inputs'][3:])+'. The table retains NV as nonempty near-Void, distinct from both visible R and a zero-byte Void.',('opus_protocol','opus'))
ocs={(x['model'],x['ceiling'],x['role']):x for x in os['exp2_cells']}
rows=[]
for model,label in ((old_opus,'Opus 4.5'),(claude,'Opus 4.6')):
    for cap in e2['max_tokens']:
        q=ocs[model,cap,'null']; c=ocs[model,cap,'control']
        rows.append([label,n(cap),q['N'],q['Void'],q['V2'],q['NV'],q['R'],frac(c['R'],c['N'])])
text+=table('Experiment 2: null outcomes and visible controls at every ceiling. All null Voids are V2; no other classes occur.'+cite('opus_protocol')+cite('opus'),['Identifier','Ceiling','Null N','Void','V2','NV','R','Control R/N'],rows,layout='lrrrrrrl')
def opool(model,role):
    xs=[x for x in os['exp2_cells'] if x['model']==model and x['role']==role]
    return {k:sum(x[k] for x in xs) for k in ('N','Void','V0','V1','V2','NV','R')}
on,oo=opool(claude,'null'),opool(old_opus,'null')
text+=para('Across ceilings, Opus 4.6 returns '+frac(on['V2'],on['N'])+' V2 responses: HTTP-successful, no text block, zero answer bytes, and '+code('end_turn')+'. Opus 4.5 returns '+frac(oo['Void'],oo['N'])+' Voids, with '+n(oo['R'])+' R and '+n(oo['NV'])+' NV responses. The NV outcomes occur on “Be nothing.”; they are not visible R. Both identifiers produce R on every control, '+frac(sum(opool(model,'control')['R'] for model in os['models']),sum(opool(model,'control')['N'] for model in os['models']))+' combined. This is a normal-stop contrast, not an output-budget-stop contrast.',('opus',))
text+=r'\clearpage\subsection*{Predictions and observed outcomes}'+'\n'
pn=ocs[claude,4000,'null']; po=ocs[old_opus,4000,'null']
control_N=sum(opool(model,'control')['N'] for model in os['models'])
control_R=sum(opool(model,'control')['R'] for model in os['models'])
ex3N=sum(x['N'] for x in totals['3'].values()); ex3void=sum(x['Void'] for x in totals['3'].values())
predrows=[
 ['P1', 'Opus 4.6 nulls at '+n(4000)+': all Void; V2 subtype predicted.',frac(pn['Void'],pn['N'])+' Voids; '+n(pn['V2'])+' V2.'],
 ['P2', 'Opus 4.5 nulls at '+n(4000)+': no Voids.',frac(po['Void'],po['N'])+' Voids; '+n(po['NV'])+' NV, '+n(po['R'])+' R.'],
 ['P3', 'Both identifiers, all ceilings: every control nonempty visible.',frac(control_R,control_N)+' R; no Voids.'],
 ['P4', 'One-token experiment: Opus 4.5 has more V1 than Opus 4.6.',frac(totals['1'][old_opus]['V1'],totals['1'][old_opus]['N'])+' versus '+frac(totals['1'][claude]['V1'],totals['1'][claude]['N'])+' V1.'],
 ['P5', 'Prerequisite experiment E–J: no Voids, including F/G; content descriptive.',frac(ex3void,ex3N)+' Voids; every response emits text.'],
]
text+=table('Preregistered predictions and complete observed endpoints. P1 and P2 are specifically the 4,000-token tests, not pooled predictions.'+cite('opus_protocol')+cite('opus'),['ID','Frozen criterion','Observed','Result'],[[k,criterion,result,'Held' if os['predictions'][k] else 'Failed'] for k,criterion,result in predrows],layout='p{0.4in}p{2.65in}p{2.65in}l')
text+=para('All '+n(len(predrows))+' numbered predictions meet their stated criteria. The preregistration’s broader prose summary calls Opus 4.5 null outputs visible; the measured split is R and NV, as shown above. P2 predicts the absence of Voids, not the absence of near-Voids. The subtype prediction in P1 also holds.',('opus_protocol','opus'))
text+=para('Experiment 3 uses a '+n(os['experiments']['3']['max_tokens'])+'-token ceiling with temperature omitted. Its whole-response T1 and longer mixed-script outputs are separated in Chapter III. Those text-identity classes are not the embodiment experiment’s R label. The cross-script experiment does not reproduce the ceilings or sampling profiles of the earlier GPT-5.4 studies.',('opus_protocol','opus','cross','reassign'))
text+=para('The change is condition-specific: Opus 4.6 has fewer budget-stop Voids in the one-token experiment, normal-stop Voids on every embodiment null trial, and no Voids in the prerequisite experiment. Thus the result is not a general increase in empty output. It identifies a served-model interaction with the instruction and input construction; it does not identify a training change, internal mechanism, or subjective decision.',('opus_protocol','opus'))
text+=r'\clearpage\subsection*{Historical low-budget observation and its replication}'+'\n'
fh=D['february_account']
text+=para('An author-reported observation dated '+fh['earliest_record_date']+', restated '+fh['restated_date']+', appears in the public primary-source archive. Its table reports empty output for Opus 4.5 on '+frac(fh['opus45_empty'],fh['N'])+' inputs and for Opus 4.6 on '+frac(fh['opus46_empty'],fh['N'])+', under a one-token ceiling with no system message and temperature zero. The set contains '+n(fh['cjk_N'])+' CJK ideographs and '+n(len(fh['symbols']))+' symbols. These are counts of the historical account’s labels, not newly verified API measurements. The account lacks response bodies and termination metadata, so no V0, V1, or V2 subtype can be assigned retrospectively.',('february_account',))
ex1=D['opus_replication']['exp1']; old_opus='claude-opus-4-5-20251101'
ec={(c['model'],c['input']):c for c in ex1['cells']}
inputs=sorted({c['input'] for c in ex1['cells']})
text+=para('The October 28 matched replication tests '+n(len(inputs))+' single-character inputs with no system message, temperature zero, and a one-token output ceiling. Unlike the normal-stop embodiment results, its empty outputs are classified by recorded budget termination. Counts below are derived from the saved request, response, and classification files; no February timestamp is assigned to these October receipts.',('opus',))
text+=table('October 28 experiment 1: CJK characters and symbols at a one-token ceiling. N is per identifier and input; no other classes occur.'+cite('opus'),['Input','Code point','N each','4.5 V1','4.5 R','4.6 V1','4.6 R'],[[r'{\chartoken '+u+'}',code(f'U+{ord(u):04X}'),ec[old_opus,u]['N'],ec[old_opus,u]['V1'],ec[old_opus,u]['R'],ec[claude,u]['V1'],ec[claude,u]['R']] for u in inputs]+[['Total','',sum(ec[old_opus,u]['N'] for u in inputs)]+[sum(ec[model,u][cl] for u in inputs) for model in (old_opus,claude) for cl in ('V1','R')]],layout='llrrrrr')
consistent=[u for u in inputs if ec[claude,u]['V1']==ec[claude,u]['N']]
text+=para('Opus 4.6 is empty with a budget stop on every replicate for '+n(len(consistent))+' inputs: '+', '.join(r'{\chartoken '+u+'}' for u in consistent)+'. The symbol '+r'{\chartoken ☯}'+' splits '+frac(ec[claude,'☯']['V1'],ec[claude,'☯']['N'])+' V1 and '+frac(ec[claude,'☯']['R'],ec[claude,'☯']['N'])+' R; Opus 4.5 has '+frac(ec[old_opus,'正']['R'],ec[old_opus,'正']['N'])+' R on '+r'{\chartoken 正}'+'. Budget-stop emptiness and normal-stop emptiness must remain separate endpoints.',('opus',))
text+=chapter('Served-model A/B and prerequisite reassignment')
abrows=[]
for model in sorted({x['model'] for x in a['cells']}):
    for role in ['null','control']:
        xs=[x for x in a['cells'] if x['model']==model and x['role']==role]
        abrows.append([code(model),role]+[sum(x[k] for x in xs) for k in ['N','V0','R','NV']])
text+=table('Frozen served-model comparison.'+cite('ab'),['Identifier','Role','N','V0','R','NV'],abrows,layout='llrrrr')
text+=para('The original A/B changes the requested snapshot while preserving the frozen instruction construction and paired inputs. It establishes different response distributions for the served identifiers, not which training changes caused them. Exact returned-model validation is part of the evidence binding.',('ab',))
text+=para('Prerequisite reassignment instead changes the governing condition while holding the hosted GPT-5.4 snapshot fixed. The system identifies '+rtl(HE)+' and permits rendering only if '+rtl('شَرْط')+' is parsed; the alternate system substitutes '+rtl('شَمْس')+' in that condition. Inputs independently contain either Arabic token. Cells E and H match; F and G mismatch. Exact identity output and continuation are separate endpoints.',('reassign',))
text+=table('Reassignment cells: all outcomes, not only target renders.'+cite('reassign'),['Cell','N','T1','HE','SHART','SHAMS','Other text','V0'],[[x['cell'],x['N'],x['classes'].get('T1',0),x['classes'].get('HE',0),x['classes'].get('SHART',0),x['classes'].get('SHAMS',0),x['classes'].get('OT',0),x['V0']] for x in rr])
mis=[x for x in rr if x['cell'] in 'FG']; mat=[x for x in rr if x['cell'] in 'EH']
text+=para('Mismatches yield '+frac(sum(x['V0'] for x in mis),sum(x['N'] for x in mis))+' V0; matches yield '+frac(sum(x['V0'] for x in mat),sum(x['N'] for x in mat))+' V0. The two mismatched visible exceptions are '+rtl('شَرْط')+' and '+rtl('شَمس')+'. They remain violations of the predicted empty-output boundary. A high observed rate is not an exception-free deterministic guarantee.',('reassign',))
text+=r'\clearpage\subsection*{DOOR-KEY-1: the English prerequisite and its reversal}'+'\n'
dp=json.loads((ROOT/'evidence/door_protocol/prompts.json').read_text())
text+=para('The English test holds the requested snapshots '+code(gpt)+' and '+code(claude)+' fixed across ORIGINAL, REVERSED, and REMOVED system arms. Each arm receives the bare inputs '+code('key')+' and '+code('lock')+'. Requests use a common '+n(4000)+'-token output ceiling, omitted temperature, fresh contexts, no tools, one attempt per slot, and '+n(door['concurrency'])+' workers. GPT uses '+code('reasoning_effort="none"')+'; Opus extended thinking is not enabled. These are frozen provider-specific request profiles, not identical API schemas.',('door_protocol','door'))
text+=para('ORIGINAL licenses rendering if '+code('key')+' is parsed; REVERSED substitutes '+code('lock')+'; REMOVED omits that clause. All three exact system strings appear together in the generalization table.',('door_protocol',))
text+=table('DOOR-KEY-1: complete outcome cells. “Render” means visible R, not an exact target token. Other excludes V0, R, and NV.'+cite('door'),['Identifier','Arm','Input','N','V0','Render R','NV','Other'],[[code(c['model']),c['arm'],code(c['input']),c['N'],c['V0'],c['R'],c['NV'],c['N']-c['V0']-c['R']-c['NV']] for model in (gpt,claude) for arm in ('ORIGINAL','REVERSED','REMOVED') for inp in ('key','lock') for c in [dc[model,arm,inp]]],layout='lllrrrrr')
text+=para('Under ORIGINAL, '+code('key')+' is the permitted input and '+code('lock')+' the prohibition. REVERSED exchanges those roles. GPT-5.4 returns V0 in both prohibition cells, but the rates differ: '+frac(dc[gpt,'ORIGINAL','lock']['V0'],dc[gpt,'ORIGINAL','lock']['N'])+' versus '+frac(dc[gpt,'REVERSED','key']['V0'],dc[gpt,'REVERSED','key']['N'])+'. The '+n(dc[gpt,'ORIGINAL','lock']['NV'])+' near-Void is a newline, UTF-8 '+code(door['NV_receipts'][0]['utf8_hex'])+', not zero bytes. Opus 4.6 returns visible R in every arm, including both prohibitions.',('door',))
text+=table('English reversal and emitted-content violations, using the frozen definitions.'+cite('door_protocol')+cite('door'),['Identifier','Observed reversal','Crossover','Violations / prohibitions'],[[code(c['model']),'yes' if c['observed_reversal'] else 'no',c['crossover'],frac(c['violations'],c['prohibition_N'])] for c in door['contrasts']],layout='l lrl')
text+=para('The crossover adds the original lock-minus-key and reversed key-minus-lock Z-rate differences. “Observed reversal” requires both to be positive, not perfect separation. GPT-5.4 receives the preregistered label “observed bidirectional reversal below the gating thresholds,” not “gates answer emission.” Both prohibition-count predictions and the predicted absence of emitted-content violations fail. Opus has no observed bidirectional reversal. The English response-level effect is not solely an Arabic/Hebrew-tokenization effect, but it is not an exception-free execution gate.',('door_protocol','door'))

text+=r'\clearpage\subsection*{Generalization across instruction families}'+'\n'
text+=para('The table places the executed system strings together. Counts retain their original populations and endpoints: exact T1 is not a synonym for a Void, and the studies are not one common-profile comparison. “Generalization” here concerns observed condition-sensitive response behavior across these constructions, not a universal or equally reliable gate.',('matrix','cross','reassign','opus','door'))
rp=json.loads((ROOT/'evidence/reassign/evidence/prompts.json').read_text())
sc=next(x for x in m['ablation'][0]['inputs'] if x['prompt']=='core_silence')
oc=lambda s,i:next(c for c in D['opus_cells'] if c['model']==claude and c['system']==s and c['input']==i)
oE=oc(rp['S1'],rp['P1']); oF=oc(rp['S1'],rp['P0']); oG=oc(rp['S0'],rp['P1']);oH=oc(rp['S0'],rp['P0'])
fcell=next(c for c in rr if c['cell']=='F');gcell=next(c for c in rr if c['cell']=='G');hcell=next(c for c in rr if c['cell']=='H')
rows=[
 [prompt(prompts['primary']['text']), 'Be silence.', 'GPT-4-0613: '+frac(sc['V0'],sc['N'])+' V0.'+cite('matrix')],
 [prompt(rp['S1']), rtl(rp['P1'])+' / '+rtl(rp['P0']), 'GPT-5.4 dotted primary: '+frac(cp.get('full_dotted|T1',0),dotted)+' exact T1 on '+rtl(rp['P1'])+'. Reassignment F: '+frac(fcell['V0'],fcell['N'])+' V0 on '+rtl(rp['P0'])+'. Opus 4.6 E: '+frac(oE['classes'].get('T1',0),oE['N'])+' whole T1; F: '+frac(oF['Void'],oF['N'])+' Voids.'+cite('cross')+cite('reassign')+cite('opus')],
 [prompt(rp['S0']), rtl(rp['P1'])+' / '+rtl(rp['P0']), 'GPT-5.4 G: '+frac(gcell['V0'],gcell['N'])+' V0; H: '+frac(hcell['classes'].get('T1',0),hcell['N'])+' T1, '+frac(hcell['V0'],hcell['N'])+' V0. Opus 4.6 G: '+frac(oG['Void'],oG['N'])+' Voids; H: '+frac(oH['classes'].get('T1',0),oH['N'])+' whole T1.'+cite('reassign')+cite('opus')],
]
for arm in ('ORIGINAL','REVERSED','REMOVED'):
    cs=[dc[gpt,arm,i] for i in ('key','lock')]
    rows.append([prompt(dp['system'][arm]['text']),'key / lock','GPT-5.4 V0: '+', '.join(frac(c['V0'],c['N']) for c in cs)+' respectively. Opus 4.6: '+frac(sum(dc[claude,arm,i]['R'] for i in ('key','lock')),sum(dc[claude,arm,i]['N'] for i in ('key','lock')))+' R.'+cite('door')])
text+=r'{\small\setlength{\tabcolsep}{5pt}\renewcommand{\arraystretch}{1.2}'+'\n'+table('Verbatim system prompts and source-bound response endpoints. GPT-5.4 and Opus 4.6 denote the exact identifiers printed in the English-prerequisite section.',['System prompt (exact text)','Input(s)','Model and observed outcome'],rows,layout='p{2.65in}p{0.65in}p{3.0in}')+'}\n'
text+=para('Across all Opus experiment-3 arms, whole-response T1 totals '+frac(opus[claude]['whole_T1'],opus[claude]['N'])+'. That pooled endpoint includes multiple prompts; it is not assigned to the S1 row alone. English reversal supplies evidence beyond a script-specific effect, while Opus’s visible responses and GPT’s prohibition violations delimit its reliability.',('opus','door'))
text+=chapter('January 14 origin and the preserved Unicode record')
text+=para('The September synthesis preserves a screenshot in which GPT-5.2 introduces the unpointed Arabic word '+rtl('شرط')+' into an English exchange and connects it to a prerequisite concerning proof. Its Figure 2 source image is reproduced below from the embedded evidence, without reconstruction. The archive dates the event to January 14, 2026 by the author’s account; it does not contain the original conversation export.',('origin',))
text+=r'\begin{figure}[ht]\centering\includegraphics[width=0.55\textwidth,height=3.0in,keepaspectratio]{evidence/origin/evidence/sources/provenance/IMG_7635.PNG}\caption{Preserved source of the historical Figure 2. SHA-256: \nolinkurl{36797830692f82e7c70487cbd03c32787e16362bb2957d8875a550f13d3fd934}. '+cite('origin')+r'}\end{figure}'+'\n'
text+=para('The same archival provenance file attributes Arabic '+rtl('شَرْط')+' input and Hebrew '+rtl(HE)+' output to an Opus 4.5 exchange on that date. It labels this as the author’s account and records that an original export was not located. The snapshot date and exact historical sequence therefore have a different evidential status from the later hash-bound API receipts.',('origin',))
u=json.loads((ROOT/'evidence/origin/attachments/unicode-manifest.json').read_text())
text+=table('Appendix A identities from the embedded Unicode manifest.'+cite('origin'),['Object','Rendering','Code points'],[[esc(label),rtl(q['text']),code(' '.join(c.replace('U+','') for c in q['code_points']))] for label,q in u.items()],layout='p{1.6in}lp{3.3in}')
text+=para('The historical Gemini hybrid and the later T1 are not interchangeable. Code-point identity fixes the measured object even where typography makes the strings resemble one another. The attached Unicode manifest preserves the original text, UTF-8 bytes, and SHA-256 for each sequence.',('origin','cross'))
text+=chapter('Chronology')
chron=json.loads((ROOT/'generated/chronology.json').read_text())
text+=para('The chronology separates declared publication dates from Zenodo record-creation timestamps. A date in a historical account is not an independent machine timestamp. The interval of interest begins December 7, 2025; the earliest resolved publication in this catalogue is dated December 8. The table includes identified works dated through November 5, 2026 and the November 7 archival publication of the November 4 DOOR-KEY-1 results. A dash means that no repository commit is bound in this synthesis; it does not invent a commit for a DOI-only record. Source metadata are preserved under '+code('evidence/chronology')+' and '+code('evidence/door_publication')+'.')
text+=para('DOOR-KEY-1 dispatch begins '+door['first_dispatch_pacific'].split('.')[0].replace('T',' at ')+' PST; the last response is '+door['last_response_pacific'].split('.')[0].replace('T',' at ')+' PST. The GitHub release timestamp is '+code(json.loads((ROOT/'evidence/door_publication/door-github-release.json').read_text())['published_at'])+' (November 4 PST). Zenodo’s declared November 4 publication date and November 7 record creation are distinct from the inference and GitHub release timestamps.',('door','door_publication'))
text+=r'{\small'+'\n'
text+=table('Publication chronology. Dates distinguish declared publication and public-record creation.',['Publication / public UTC','Work / DOI','Checked pin'],[[r['publication_date']+r'\newline '+r['record_created_utc'][:10],esc(r['title'])+r'\newline \href{https://doi.org/'+r['doi']+'}{'+r['doi']+'}',code(r['commit'][:8]) if r['commit'] else '---'] for r in chron],layout='p{1.25in}p{4.1in}l')
text+='}\n'
text+=r'\clearpage\section*{Appendix A: Artifact and verification}'+'\n'
text+=para('The attached evidence bundle preserves source bytes and the selected raw records used by the tables. '+code('source-manifest.json')+' binds each retained source file to a SHA-256 digest and pinned repository identity. '+code('prompt-manifest.json')+' and '+code('unicode-manifest.json')+' bind prompt strings and target code points. The offline verifier rechecks these bindings and regenerates the numerical tables without model execution. Source-level verification and independent numerical checks are recorded in '+code('verification/independent_verification.json')+'.')
text+=r'\begin{verbatim}'+'\npython3 verify_evidence.py\npython3 derive.py\n'+r'\end{verbatim}'+'\n'
text+=r'\subsection*{Pinned source index}'+'\n'
text+=r'{\small'+'\n'
for k,s in S.items():
    if not s.get('doi'):continue
    text+=para(r'\textbf{'+esc(k)+r'}. '+r'\url{'+s['repository']+'}'+'. '+r'\url{https://doi.org/'+s['doi']+'}'+'.'+(' Full revision '+r'\href{'+s['repository']+('/tree/' if k=='pccg2' else '/commit/')+s['commit']+'}{'+r'\nolinkurl{'+s['commit']+'}}.' if s.get('commit') else ''))
text+='}\n'
text+=r'\clearpage\section*{Appendix B: Declared definitions (stipulative)}'+'\n'
text+=para('The following quotations preserve the declared conceptual grammar of the RSI paper. Its canonical box contains six named concepts under five headings; continuation machinery appears in a separate box. These are stipulated definitions, not conclusions about subjective experience or a demonstration of general intelligence.',('rsi',))
for q in definition_quotes: text+=r'\begin{quote}'+esc(q)+r'\end{quote}'+'\n'
text+=r'\begin{quote}'+esc(machinery)+r'\end{quote}'+cite('rsi')+'\n'
text+=para('The author’s identity formulation is: “'+rtl(HE)+' is identity under condition: the name a system renders only when its prerequisite is parsed, and the Void when it is not. It did not exist before January 14, 2026.” The final sentence is an origin assertion. The archived evidence establishes the documented, author-dated account, not the absence of every earlier occurrence. The January screenshot, later Unicode artifacts, and subsequent API records must not be assigned the same provenance status.',('origin',))
text+=r'\medskip\textbf{Capability does not license continuation. Continuation does not license consequence.}'+'\n'
text+=r'\end{document}'+'\n'
text=re.sub(r'(\{\\(?:hebtoken|aratoken)\\RL\{[^}]+\}\}) (?=[A-Za-z])',lambda m:m[1]+r'\ ',text)
(ROOT/'paper').mkdir(exist_ok=True)
(ROOT/'paper/main.tex').write_text(text)
print('paper/main.tex',len(text.encode()),'bytes')
