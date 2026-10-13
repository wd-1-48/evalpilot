"""Run candidate evaluator checks. Default is offline; --live explicitly calls provider."""
import argparse,json,sys,hashlib,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from evalpilot.evaluation import evaluate_field
from evalpilot.diagnostics import PRIMARY_TAGS,GATE_VERSION

def main():
 p=argparse.ArgumentParser();p.add_argument('--dataset',default='benchmarks/judge_candidates_v1.json');p.add_argument('--output',default='benchmarks/latest_offline.json');p.add_argument('--live',action='store_true');args=p.parse_args()
 if args.live:
  for line in Path('.env').read_text(encoding='utf-8-sig').splitlines() if Path('.env').exists() else []:
   if '=' in line and not line.strip().startswith('#'):
    k,v=line.split('=',1);os.environ.setdefault(k.strip(),v.strip().strip('"').strip("'"))
 raw=Path(args.dataset).read_bytes();data=json.loads(raw);out=[]
 for case in data['cases']:
  row=evaluate_field(case['event'],case['field'],args.live);r=row['result'];e=case['expected'];a=row['entity_analysis']
  tags=sorted({PRIMARY_TAGS[i['tag']] for i in a.get('diagnostics',[]) if i.get('status') in ('rule_confirmed','llm_validated','human_confirmed')})
  checks={'review_status':r['requires_human_review']==e['requires_review']}
  if not r['requires_human_review'] and not e['requires_review']:
   checks['primary_tags']=tags==sorted(e['primary_tags'])
   if e['match_level'] is not None:checks['level']=r['match_level']==e['match_level']
  out.append(dict(id=case['event']['event_id'],checks=checks,passed=all(checks.values()),auto_accepted=not r['requires_human_review'],result=row))
 accepted=[x for x in out if x['auto_accepted']]
 report=dict(dataset_status=data['status'],warning='候选标准符合情况，不是人工验证准确率；开发样本不能充当独立留出测试集。',dataset_sha256=hashlib.sha256(raw).hexdigest(),gate_version=GATE_VERSION,live=args.live,total=len(out),auto_accepted=len(accepted),candidate_agreement=sum(x['passed'] for x in accepted)/len(accepted) if accepted else None,candidate_disagreements=[x['id'] for x in accepted if not x['passed']],results=out)
 Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in report.items() if k!='results'},ensure_ascii=True))
if __name__=='__main__':main()
