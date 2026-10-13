"""Evidence-based reports; aggregation never asks an LLM to count."""
from collections import Counter
from .diagnostics import PRIMARY_TAGS

FIELDS={'person':'姓名','company':'公司','location':'地点'}
SOURCES={'rule_confirmed':'规则判断','llm_validated':'LLM 自动通过校验','human_confirmed':'人工确认'}
ADVICE={
 '实体遗漏':('参考实体未出现在预测集合中。','核对参考答案是否符合标注范围；请模型负责人检查输入是否完整、输出是否被过滤。','若确认是过滤导致，再调整过滤逻辑；若集中于特定实体结构，再补充相应测试样本。'),
 '多识别':('预测包含参考集合以外的实体。','先检查参考答案是否漏标、实体范围是否一致，再核对预测实体在原文中的依据。','若参考漏标则修订参考；若确为无依据输出，再针对该模式排查抽取或后处理。'),
 '边界／完整性错误':('关联实体存在范围或完整性差异；具体表现需结合代表案例。','检查标注边界约定，并请模型负责人检查分词、输入及后处理截断等可能环节。','仅在验证具体环节后调整；对地址层级、连接词或分支机构限定分别建立回归样本。'),
 '类型错误':('实体在预测与参考中被分配到不同类别。','核对姓名、公司、地点的类别定义，尤其检查场所名与组织名的界限。','若类别约定不一致先统一约定，再验证剩余错分。'),
 '内容错误':('预测与参考的实体内容存在差异。','核对原文、参考答案及输入预处理，区分字符差异与不同实体；不能据此直接认定 OCR 原因。','根据核实后的问题环节安排修正，并保留相似名称对照样本。')}

def pct(v): return '不适用' if v is None else f'{v:.2%}'
def clean(v): return str(v or '').replace('|','／').replace('\n',' ')
def explanation(v):
 return '未提供具体说明，仅保留该条判断；不作为原因证据' if not v or '请填写' in v or '待补充' in v else clean(v)

def aggregate(rows):
 groups={};denom={f:set() for f in FIELDS};pending=set();unavailable=set()
 for r in rows:
  key=(r['event_id'],r['field']);a=r.get('entity_analysis')
  if not a or not a.get('eligible'): unavailable.add(key);continue
  if a.get('semantic_status')=='pending' or any(i.get('status')=='pending_semantic' for i in a.get('diagnostics',[])):
   pending.add(key);continue
  accepted=[i for i in a.get('diagnostics',[]) if i.get('status') in SOURCES]
  for i in accepted:
   label=PRIMARY_TAGS.get(i['tag'])
   if not label: continue
   g=groups.setdefault((r['field'],label),{'events':set(),'sources':{},'examples':[]})
   g['events'].add(r['event_id']);g['sources'].setdefault(SOURCES[i['status']],set()).add(r['event_id'])
   g['examples'].append((r['event_id'],i))
   if label!='允许的表达差异': denom[r['field']].add(r['event_id'])
 return groups,denom,pending,unavailable

def render_report(d):
 rows=d['results'];em=d['event_metrics'];o=d['operations'];groups,denom,pending,unavailable=aggregate(rows)
 field_pending={(r['event_id'],r['field']) for r in rows if r['result']['requires_human_review']}
 methods=Counter(r['result']['evaluation_method'] for r in rows)
 initial=sum(r.get('original_result',r['result'])['requires_human_review'] for r in rows)
 lines=['# EvalPilot 质量报告','',f"模型版本：{clean(d['run']['version'])}",f"任务 ID：{d['run']['id']}；外部 LLM：{'启用' if d['run']['allow_llm'] else '关闭'}；请求尝试：{o['llm_calls']} 次。",f"已处理 {o['processed']}/{o['expected']} 字段；当前待复核（字段结论或诊断去重）：{len(field_pending|pending)} 个字段。",f"初始字段结论待复核：{initial}；当前字段结论待复核：{len(field_pending)}；实体诊断待确认：{len(pending)}。",f"字段结论来源：规则 {methods['rule']}；LLM 自动通过校验 {methods['llm_combined']+methods['rag_llm']}；人工确认 {methods['human']}。",'自动通过校验不等于人工验证正确；本报告分析已导入的预测，不训练或重新调用原抽取模型。','', '## 严格实体数量与指标','严格指标只依据固定规范化后的预测和参考计算，不随语义或人工改判改变。未知参考排除。各字段为实体 Micro 指标。','| 字段 | 有效字段数 | TP 正确 | FN 遗漏 | FP 多出 | Precision | Recall | F1 |','|---|---:|---:|---:|---:|---:|---:|---:|']
 for f,m in d['metrics'].items(): lines.append(f"| {FIELDS[f]} | {m['strict_eligible']} | {m['tp']} | {m['fn']} | {m['fp']} | {pct(m['strict_precision'])} | {pct(m['strict_recall'])} | {pct(m['strict_f1'])} |")
 lines+=['','## 事件级严格指标',f"事件全部正确率：{pct(em['exact_rate'])}（{em['exact']}/{em['eligible']} 个有效事件）。",f"参考待确认 {em['unknown_reference']}；处理未齐 {em['incomplete']}；双方全空 {em['all_empty']}（计入全部正确）。",f"事件级平均 F1：{pct(em['mean_f1'])}（{em['mean_f1_events']} 个非空有效事件，全空事件排除）。",'姓名、公司、地点均精确匹配才算事件全部正确。事件指标每事件等权，与按实体计数的 Micro-F1 互补。','', '## 语义评审结果','语义符合率分母为非待复核字段，包括规则、LLM 自动判断和人工确认，不是经人工验证的准确率。','| 字段 | 非待复核 | 待复核 | 符合评测要求比例 |','|---|---:|---:|---:|']
 for f,m in d['metrics'].items(): lines.append(f"| {FIELDS[f]} | {m['confirmed']} | {m['pending']} | {pct(m['exact_rate'])} |")
 lines+=['','## 批量错误分析','统计单位是“事件×字段”；同一主类型在同一字段事件内只计一次。不同类型可重叠，占比不能相加。',f'诊断待确认 {len(pending)} 个字段，以及缺少有效实体分析的 {len(unavailable)} 个字段，不计入下方诊断统计。','| 字段 | 主类型 | 涉及事件数 | 该字段已诊断错误事件数 | 占比 | 来源（事件数，可重叠） |','|---|---|---:|---:|---:|---|']
 for (f,label),g in sorted(groups.items(),key=lambda kv:(kv[0][0],-len(kv[1]['events']),kv[0][1])):
  if label=='允许的表达差异':continue
  n=len(g['events']);base=len(denom[f]);src='；'.join(f'{k} {len(v)}' for k,v in g['sources'].items())
  lines.append(f'| {FIELDS[f]} | {label} | {n} | {base} | {pct(n/base if base else None)} | {src} |')
 for f in FIELDS:
  candidates=[(label,g) for (field,label),g in groups.items() if field==f and label!='允许的表达差异']
  if not candidates:continue
  top=max(len(g['events']) for _,g in candidates);names='、'.join(label for label,g in candidates if len(g['events'])==top)
  lines.append(f"- {FIELDS[f]}：当前已诊断错误事件 {len(denom[f])} 个；最多的类型为 {names}，各涉及 {top} 个事件。仅描述本样本，不据此断言模型整体能力。")
 for (f,label),g in groups.items():
  if label=='允许的表达差异':lines.append(f'- 允许的表达差异：{FIELDS[f]} {len(g["events"])} 个事件，单列且不计入错误分母。')
 lines+=['','## 代表案例与排查建议','以下为基于错误模式的排查清单，不是已经证实的原因；不假定原模型采用何种训练或抽取技术。按涉及字段事件数排列。']
 for (f,label),g in sorted(groups.items(),key=lambda kv:-len(kv[1]['events'])):
  if label not in ADVICE:continue
  fact,check,action=ADVICE[label]
  lines += ['',f'### {FIELDS[f]} / {label}（{len(g["events"])} 个事件）',f'观察事实：{fact}',f'建议验证：{check}',f'条件性建议：{action}']
  seen=set()
  for eid,i in g['examples']:
   if eid in seen:continue
   seen.add(eid)
   evidence=clean(i.get('evidence')) or ('人工核对整段原文，未提供逐字引用' if i['status']=='human_confirmed' else '集合差异或跨字段比较，无语义引文')
   lines.append(f"- {eid}【{SOURCES[i['status']]}】：预测「{clean(i.get('predicted_entity')) or '无'}」；参考「{clean(i.get('reference_entity')) or '无'}」。依据：{evidence}。说明：{explanation(i.get('reason'))}。")
   if len(seen)>=3:break
 lines+=['','## 实体差异明细（最多 30 个字段）']
 for r in [r for r in rows if r['counts']['fp'] or r['counts']['fn']][:30]:
  a=r.get('entity_analysis',{});lines.append(f"- {r['event_id']} / {FIELDS[r['field']]}：正确 {clean('、'.join(a.get('matched',[]))) or '无'}；遗漏 {clean('、'.join(a.get('missing',[]))) or '无'}；多出 {clean('、'.join(a.get('extra',[]))) or '无'}。")
 blocked=Counter(code for r in rows for code in r.get('entity_analysis',{}).get('gate_errors',[]))
 if blocked:
  lines+=['','## 自动放行拦截记录','以下是程序拦截原因，不代表已经人工确认模型判断错误。']
  lines += [f'- {code}：{count} 个字段' for code,count in sorted(blocked.items())]
 lines+=['','## 运行记录',f"累计任务耗时 {d['run'].get('elapsed',0):.2f} 秒；字段 P95 {o['p95_ms']} 毫秒；请求尝试 {o['llm_calls']} 次。",'报告统计和排版由代码完成，诊断来源逐项注明。字段延迟与并发任务总耗时不是同一指标；费用未核对账单，不据 Token 推称实际费用。']
 return '\n'.join(lines)
