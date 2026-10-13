"""Verify the generated CSV with the real parser, workflow and localhost API."""
import json
import sys
import time
from pathlib import Path
from collections import Counter
import httpx
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from evalpilot.engine import parse_dataset, GRAPH, FIELDS
from evalpilot.llm import pending

root=Path(__file__).resolve().parents[1]
path=root/'datasets/public_simulation_v1/evalpilot-simulated-v1.csv'
events,summary=parse_dataset(path.read_bytes(),path.name,'simulated-v1')
assert len(events)==55 and not any(e['unknown'] for e in events)
counts=Counter()
for event in events:
    for field in FIELDS:
        result=GRAPH.invoke({'event':event,'field':field,'judge':lambda *a:pending('Simulated offline run')})['result']
        counts['pending' if result['requires_human_review'] else result['match_level']]+=1
assert counts=={'exact':140,'partial':10,'mismatch':10,'pending':5},counts
print(json.dumps({'parser':'passed','events':55,'fields':165,'results':dict(counts)}),flush=True)
with httpx.Client(base_url='http://127.0.0.1:8765',timeout=30) as client:
    response=client.post('/api/datasets',data={'version':'simulated-v1'},files={'file':(path.name,path.read_bytes(),'text/csv')})
    response.raise_for_status();dataset_id=response.json()['id']
    response=client.post('/api/runs',json={'dataset_id':dataset_id,'allow_llm':False})
    response.raise_for_status();run_id=response.json()['id']
    deadline=time.monotonic()+60
    while time.monotonic()<deadline:
        response=client.get('/api/runs/'+run_id);response.raise_for_status();detail=response.json()
        if detail['run']['status']=='completed':break
        if detail['run']['status']=='failed':raise RuntimeError(detail['run']['error'])
        time.sleep(.5)
    else:raise TimeoutError('Run did not finish')
    assert detail['operations']['processed']==165 and detail['operations']['pending']==5
    response=client.get('/api/runs/'+run_id+'/report');response.raise_for_status()
    report='# 数据来源声明\n\n以下评测采用全新虚构事件、模拟机器预测和未经人工独立审核的 AI 建议参考，仅用于功能演示。\n\n'+response.text
    (path.parent/'simulation-report.md').write_text(report,encoding='utf-8')
    print(json.dumps({'api':'passed','run_id':run_id,'llm_calls':detail['operations']['llm_calls'],'operations':detail['operations']}))
