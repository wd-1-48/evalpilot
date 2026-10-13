"""Small, authored regression set; not a claim of business accuracy."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from evalpilot.engine import normalize,rule_compare

# Gold labels are authored independently of the matching implementation.
CASES=[
 ('same','张甲','张甲','exact'),('empty','','','exact'),('order','张甲、李乙','李乙、张甲','exact'),
 ('spaces',' 张甲 ','张甲','exact'),('width','ＡＢＣ','ABC','exact'),('duplicate','张甲、张甲','张甲','exact'),
 ('delimiter','张甲；李乙','张甲、李乙','exact'),('miss','','张甲','mismatch'),('extra','张甲','','mismatch'),
 ('subset','张甲','张甲、李乙','partial'),('superset','张甲、李乙','张甲','partial'),
 ('overlap','张甲、王丙','张甲、李乙','partial'),('wrong','王丙','李乙','mismatch'),
 ('company_alias','示例星河','示例星河科技有限公司','exact'),('location','虚构市','虚构市示例路1号','partial'),
 ('ocr','李末','李未','mismatch'),('title','老张','张甲','partial'),('generic','某公司','示例科技有限公司','partial'),
 ('null','无','','exact'),('multi_missing','','张甲、李乙','mismatch'),
]
def main():
 correct=resolved=base=0;details=[]
 for name,p,r,gold in CASES:
  baseline='exact' if p==r else 'mismatch';base+=baseline==gold
  result=rule_compare(normalize(p),normalize(r))
  if result: resolved+=1;correct+=result['match_level']==gold
  details.append({'case':name,'gold':gold,'baseline':baseline,'rule':result['match_level'] if result else 'abstain'})
 report={'scope':'20 个手写合成回归用例，仅验证当前规则，不代表业务分布。简称等标签依赖假定上下文，不能用于 LLM 基准。',
  'cases':len(CASES),'string_baseline_accuracy':base/len(CASES),'rule_coverage':resolved/len(CASES),
  'rule_accuracy_on_resolved':correct/resolved,'pending':len(CASES)-resolved,
  'llm_and_rag_ablation':'not_run: API credentials and independently annotated contextual holdout required','details':details}
 out=Path(__file__).resolve().parents[1]/'docs/benchmark.json';out.parent.mkdir(exist_ok=True)
 out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({k:v for k,v in report.items() if k not in ('details','scope')},indent=2))
if __name__=='__main__':main()
