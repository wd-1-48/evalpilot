import json,time,os,sys,hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from evalpilot.entity_judge import diagnose,build_prompt
from evalpilot.diagnostics import entity_analysis,PRIMARY_TAGS,GATE_VERSION

def main():
 for line in Path('.env').read_text(encoding='utf-8-sig').splitlines():
  if '=' in line and not line.strip().startswith('#'):
   k,v=line.split('=',1);os.environ.setdefault(k.strip(),v.strip().strip('"').strip("'"))
 raw=Path('benchmarks/expanded_candidates_30.json').read_bytes();data=json.loads(raw)
 out=Path('benchmarks/ab_runs')/('expanded-'+time.strftime('%Y%m%d-%H%M%S'));out.mkdir(parents=True)
 (out/'dataset.json').write_bytes(raw)
 manifest=dict(dataset_sha256=hashlib.sha256(raw).hexdigest(),model=os.getenv('LLM_MODEL'),temperature=0,max_tokens=4096,gate=GATE_VERSION,concurrency=3,repetitions=1,status='candidate_not_human_approved')
 for v in ('P0','P1'):
  text=build_prompt(v);(out/f'prompt_{v}.txt').write_text(text,encoding='utf-8');manifest[v+'_sha256']=hashlib.sha256(text.encode()).hexdigest()
 (out/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
 def work(c,v):
  e=c['event'];f=c['field'];start=time.monotonic();a=diagnose(e,f,entity_analysis(e['predicted'][f],e['reference'][f]),True,v)
  tags_ok=links_ok=None
  try:
   items=json.loads(a['raw_response'])['items']
   tags_ok=sorted({PRIMARY_TAGS[x['tag']] for x in items})==c['expected']['primary_tags']
   links=sorted((PRIMARY_TAGS[x['tag']],x.get('predicted_entity') or '',x.get('reference_entity') or '') for x in items)
   gold=sorted((x['label'],x['predicted_entity'] or '',x['reference_entity'] or '') for x in c['expected']['links'])
   links_ok=links==gold
  except (KeyError,ValueError,TypeError):pass
  return dict(id=e['event_id'],field=f,variant=v,seconds=time.monotonic()-start,accepted=a.get('semantic_status')=='validated' and bool(a.get('field_match_level')),tags_ok=tags_ok,links_ok=links_ok,analysis=a)
 results=[]
 with ThreadPoolExecutor(max_workers=3) as pool:
  futures=[pool.submit(work,c,v) for i,c in enumerate(data['cases']) for v in (('P0','P1') if i%2==0 else ('P1','P0'))]
  for future in as_completed(futures):
   results.append(future.result());(out/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
   print('completed',len(results),'/60',flush=True)
 lines=['# 扩展30案例 P0/P1 对照试跑','', '公开合成开发候选集，非人工金标准；单轮，无生产效果或因果结论。字段语义等级不评分。两组共用输入、模型、参数、JSON及门禁，仅P1追加分类定义。','', '| 版本 | 原始主标签符合 | 原始实体关联符合 | 自动接受 | 接受但关联不符候选 | 平均请求耗时秒 | Token |','|---|---:|---:|---:|---:|---:|---:|']
 for v in ('P0','P1'):
  rs=[r for r in results if r['variant']==v]
  lines.append(f"| {v} | {sum(r['tags_ok'] is True for r in rs)}/30 | {sum(r['links_ok'] is True for r in rs)}/30 | {sum(r['accepted'] for r in rs)}/30 | {sum(r['accepted'] and r['links_ok'] is False for r in rs)} | {sum(r['seconds'] for r in rs)/30:.2f} | {sum(r['analysis'].get('diagnosis_usage',{}).get('total_tokens',0) for r in rs)} |")
 lines+=['','## 待核查案例','自动判定与候选标签不同，不直接等于模型错误；应由人工核对候选标准及输出。']
 for r in sorted(results,key=lambda x:(x['id'],x['variant'])):
  if r['links_ok'] is not True or not r['accepted']:lines.append(f"- {r['id']} {r['variant']}：标签符合={r['tags_ok']}，关联符合={r['links_ok']}，自动接受={r['accepted']}；门禁={r['analysis'].get('gate_errors',[])}")
 lines+=['','耗时为并发环境下单请求端到端时间，受服务端负载和缓存影响；Token不等于实际账单。新样本由开发方编制，仍需独立确认。类型错误等未充分覆盖，不代表所有场景。重复运行与正式留出实验尚未完成。']
 (out/'report.md').write_text('\n'.join(lines),encoding='utf-8');print('OUTPUT',out,flush=True)
if __name__=='__main__':main()
