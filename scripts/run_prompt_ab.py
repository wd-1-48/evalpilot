"""Paired pilot: production A vs additive B, public candidate data only."""
import sys,json,time,hashlib,os,argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from evalpilot.entity_judge import diagnose,build_prompt
from evalpilot.diagnostics import entity_analysis,PRIMARY_TAGS,GATE_VERSION

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--live',action='store_true');parser.add_argument('--design',choices=['steps','definitions'],default='steps');args=parser.parse_args();variants=('P0','P1') if args.design=='definitions' else ('A','B')
 for line in Path('.env').read_text(encoding='utf-8-sig').splitlines() if Path('.env').exists() else []:
  if '=' in line and not line.strip().startswith('#'):
   k,v=line.split('=',1);os.environ.setdefault(k.strip(),v.strip().strip('"').strip("'"))
 if args.live and not os.getenv('LLM_API_KEY'):raise SystemExit('Missing local API configuration')
 raw=Path('benchmarks/judge_candidates_v2.json' if args.design=='definitions' else 'benchmarks/judge_candidates_v1.json').read_bytes();data=json.loads(raw)
 out=Path('benchmarks/ab_runs')/time.strftime('%Y%m%d-%H%M%S');out.mkdir(parents=True)
 cases=[c for c in data['cases'] if not c['event']['unknown'] and set(c['event']['predicted'][c['field']])-set(c['event']['reference'][c['field']]) and set(c['event']['reference'][c['field']])-set(c['event']['predicted'][c['field']])]
 manifest=dict(design=args.design,baseline_reconstructed=args.design=='definitions',status='candidate_pilot_not_human_validated',dataset_sha256=hashlib.sha256(raw).hexdigest(),gate=GATE_VERSION,model=os.getenv('LLM_MODEL'),temperature=0,max_tokens=4096,live=args.live,cases=len(cases),notes='Single run, alternating AB/BA; no accuracy claim; tag and level scores exclude entity alignment correctness.')
 results=[]
 for v in variants:(out/f'prompt_{v}.txt').write_text(build_prompt(v),encoding='utf-8')
 manifest['prompt_hashes']={v:hashlib.sha256(build_prompt(v).encode()).hexdigest() for v in variants}
 (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
 for index,c in enumerate(cases):
  for variant in (variants if index%2==0 else variants[::-1]):
   e=c['event'];f=c['field'];start=time.monotonic()
   a=diagnose(e,f,entity_analysis(e['predicted'][f],e['reference'][f]),args.live,variant)
   accepted=a.get('semantic_status')=='validated' and bool(a.get('field_match_level'))
   tags=sorted({PRIMARY_TAGS[i['tag']] for i in a.get('diagnostics',[]) if i.get('status')=='llm_validated'})
   expected=c['expected'];checks={}
   if accepted:
    checks['tags']=tags==sorted(expected['primary_tags'])
    if args.design!='definitions' and expected['match_level'] is not None:checks['level']=a['field_match_level']==expected['match_level']
   raw_tags_match=None
   try:
    parsed=json.loads(a.get('raw_response',''));raw_tags_match=sorted({PRIMARY_TAGS[i['tag']] for i in parsed['items']})==sorted(expected['primary_tags'])
   except (ValueError,KeyError,TypeError):pass
   r=dict(raw_tags_match=raw_tags_match,id=e['event_id'],variant=variant,elapsed_seconds=round(time.monotonic()-start,3),accepted=accepted,candidate_checks=checks,analysis=a)
   results.append(r)
   (out/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
   print(e['event_id'],variant,'accepted',accepted,flush=True)
 description='P0 为重建的简化基线；P1 仅追加标签与判定标准。两组共用标签名称、JSON、安全约束、模型参数和门禁。主要评分为差异主标签，字段结论只记录不评分，避免未冻结的业务口径影响主指标。' if args.design=='definitions' else 'A 为当前生产 Prompt；B 仅附加实体关联顺序和结论自检。JSON、模型、参数、门禁与输入相同。'
 lines=['# Prompt A/B 候选样本试跑','', '不是人工金标准实验，也不是独立留出集；单次小样本不支持生产准确率或优劣结论。',description,'只比较实际需要 LLM 的双侧差异，规则案例不混入 Prompt 效果。','', '| 版本 | 样本 | 自动接受 | 接受项标签及可评分结论符合候选标准 | 总耗时秒 | Token（返回 usage） |','|---|---:|---:|---:|---:|---:|']
 for v in variants:
  rows=[r for r in results if r['variant']==v];accepted=[r for r in rows if r['accepted']]
  good=sum(all(r['candidate_checks'].values()) for r in accepted)
  tokens=sum(r['analysis'].get('diagnosis_usage',{}).get('total_tokens',0) for r in rows)
  lines.append(f'| {v} | {len(rows)} | {len(accepted)} | {good}/{len(accepted)} | {sum(r["elapsed_seconds"] for r in rows):.2f} | {tokens} |')
 lines += ['', '| 版本 | 原始输出主标签符合候选标准／全部案例 | 无法评分的原始输出 |', '|---|---:|---:|']
 for v in variants:
  rs=[r for r in results if r['variant']==v]
  lines.append(f"| {v} | {sum(r['raw_tags_match'] is True for r in rs)}/{len(rs)} | {sum(r['raw_tags_match'] is None for r in rs)} |")
 failures=sum('raw_response' not in r['analysis'] for r in results)
 lines += ['',f'未取得模型原始响应：{failures}/{len(results)} 次；存在此类失败时不能把覆盖率下降归因为 Prompt。']
 lines+=['','实体关联正确性仍需独立人工核对；null 预期结论不评分。缓存命中、网络和服务端波动影响耗时。未调用的离线结果不用于判断 Prompt 效果。','后续：先独立确认人工标准并冻结，再使用留出样本和重复运行验证，不自动切换生产 Prompt。']
 (out/'report.md').write_text('\n'.join(lines),encoding='utf-8');print('OUTPUT',out,flush=True)
if __name__=='__main__':main()
