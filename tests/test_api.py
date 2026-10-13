import importlib
import pytest
from fastapi.testclient import TestClient

def test_entity_review_preserves_counts_and_audits(app):
 import csv,io
 from evalpilot.engine import REQUIRED
 module,c=app
 s=io.StringIO();w=csv.DictWriter(s,fieldnames=REQUIRED);w.writeheader()
 row={k:'[]' for k in REQUIRED};row.update(event_id='ONE',description='林澈出席。',predicted_person='["沈甲"]',reference_person='["林澈"]')
 w.writerow(row)
 did=module.save_dataset(s.getvalue().encode(),'test.csv','test')['id']
 rid=c.post('/api/runs',json={'dataset_id':did,'allow_llm':False}).json()['id']
 before=next(x for x in c.get('/api/runs/'+rid).json()['results'] if x['field']=='person')
 items=[{'tag':'wrong_entity','predicted_entity':'沈甲','reference_entity':'林澈','evidence':'林澈','reason':'预测姓名不在原文'}]
 response=c.post(f'/api/runs/{rid}/entity-reviews/ONE/person',json={'items':items,'reviewer':'tester','note':'逐字核对'})
 assert response.status_code==200
 after=next(x for x in c.get('/api/runs/'+rid).json()['results'] if x['field']=='person')
 assert before['counts']==after['counts']
 assert after['entity_analysis']['semantic_status']=='human_confirmed'
 assert after['result']['requires_human_review']
 assert len(c.get(f'/api/runs/{rid}/reviews').json())==1
 items[0]['evidence']='不存在'
 assert c.post(f'/api/runs/{rid}/entity-reviews/ONE/person',json={'items':items,'reviewer':'tester','note':'错误引用'}).status_code==422

@pytest.fixture
def app(tmp_path,monkeypatch):
 monkeypatch.setenv('EVALPILOT_DATA',str(tmp_path))
 import evalpilot.app as module
 importlib.reload(module)
 return module,TestClient(module.app)

def create(client,version='demo-v1'):
 d=client.post('/api/demo/'+version).json()
 response=client.post('/api/runs',json={'dataset_id':d['id']})
 assert response.status_code==200
 return response.json()['id']

def test_demo_review_compare_report(app):
 module,c=app;a=create(c);b=create(c,'demo-v2')
 d=c.get('/api/runs/'+a).json()
 assert d['operations']['processed']==600 and d['operations']['pending']==80
 assert d['operations']['llm_calls']==0
 x=next(x for x in d['results'] if x['result']['requires_human_review'])
 payload={'match_level':'partial','error_type':'alias','reviewer':'tester','note':'依据测试描述确认'}
 r=c.post(f"/api/runs/{a}/reviews/{x['event_id']}/{x['field']}",json=payload)
 assert r.status_code==200
 assert len(c.get(f'/api/runs/{a}/reviews').json())==1
 after=c.get('/api/runs/'+a).json();assert after['operations']['pending']==79
 xx=next(z for z in after['results'] if z['event_id']==x['event_id'] and z['field']==x['field'])
 assert xx['original_result']['requires_human_review'] and xx['result']['evaluation_method']=='human'
 comparison=c.get('/api/compare',params={'a':a,'b':b})
 assert comparison.status_code==200 and len(comparison.json()['changes'])==20
 report=c.get(f'/api/runs/{a}/report')
 assert report.status_code==200
 assert '严格实体数量' in report.text and '实体差异明细' in report.text
 for row in d['results']:
  analysis=row['entity_analysis']
  assert len(analysis['matched'])==row['counts']['tp']
  assert len(analysis['missing'])==row['counts']['fn']
  assert len(analysis['extra'])==row['counts']['fp']

def test_resume_is_idempotent(app):
 module,c=app;a=create(c)
 with module.conn() as db:
  db.execute("DELETE FROM results WHERE run_id=? AND event_id='SYN-0199'",(a,))
  db.execute("UPDATE runs SET status='interrupted' WHERE id=?",(a,))
 assert c.post(f'/api/runs/{a}/resume').status_code==200
 assert c.get('/api/runs/'+a).json()['operations']['processed']==600
 assert c.post(f'/api/runs/{a}/resume').status_code==409

def test_reject_mismatched_cohorts_and_cross_origin(app):
 module,c=app;a=create(c);b=create(c)
 with module.conn() as db: db.execute("UPDATE datasets SET cohort='changed' WHERE id=(SELECT dataset_id FROM runs WHERE id=?)",(b,))
 assert c.get('/api/compare',params={'a':a,'b':b}).status_code==422
 assert c.post('/api/demo/demo-v1',headers={'origin':'https://evil.example'}).status_code==403

def test_nested_provider_usage_metadata(app):
 import json
 module,c=app;a=create(c)
 with module.conn() as db:
  row=db.execute('SELECT * FROM results WHERE run_id=? LIMIT 1',(a,)).fetchone()
  p=json.loads(row['payload'])
  p['original_result']['usage']={'prompt_tokens':10,'completion_tokens':5,'completion_tokens_details':{'reasoning_tokens':3}}
  db.execute('UPDATE results SET payload=? WHERE run_id=? AND event_id=? AND field=?',(json.dumps(p),a,row['event_id'],row['field']))
 assert c.get('/api/runs/'+a).json()['operations']['tokens']=={'prompt_tokens':10,'completion_tokens':5}

def test_outdated_legacy_import_is_readable_but_cannot_run(app):
 import json
 module,c=app
 did=c.post('/api/demo/demo-v1').json()['id']
 with module.conn() as db:
  db.execute('UPDATE datasets SET summary=? WHERE id=?',(json.dumps({'legacy':True,'events':200}),did))
 dataset=next(x for x in c.get('/api/datasets').json() if x['id']==did)
 assert dataset['summary']['outdated_import']
 assert c.post('/api/runs',json={'dataset_id':did}).status_code==409

def test_unified_review_atomic_and_strict_counts(app):
 import csv,io
 from evalpilot.engine import REQUIRED
 module,c=app
 s=io.StringIO();w=csv.DictWriter(s,fieldnames=REQUIRED);w.writeheader()
 row={k:'[]' for k in REQUIRED};row.update(event_id='ONE',description='林澈出席。',predicted_person='["沈甲"]',reference_person='["林澈"]');w.writerow(row)
 did=module.save_dataset(s.getvalue().encode(),'test.csv','test')['id']
 rid=c.post('/api/runs',json={'dataset_id':did}).json()['id']
 def result(): return next(x for x in c.get('/api/runs/'+rid).json()['results'] if x['field']=='person')
 before=result()
 body={'items':[{'tag':'wrong_entity','predicted_entity':'沈甲','reference_entity':'林澈','evidence':'不存在','reason':'姓名错误'}],'match_level':'mismatch','reviewer':'tester','note':'核对原文'}
 url=f'/api/runs/{rid}/unified-reviews/ONE/person'
 assert c.post(url,json=body).status_code==422
 assert result()==before
 assert c.get(f'/api/runs/{rid}/reviews').json()==[]
 body['items'][0]['evidence']='林澈'
 assert c.post(url,json=body).status_code==200
 after=result()
 assert after['counts']==before['counts'] and after['original_result']==before['original_result']
 assert not after['result']['requires_human_review']
 assert after['entity_analysis']['semantic_status']=='human_confirmed'
 assert len(c.get(f'/api/runs/{rid}/reviews').json())==1
 body['match_level']='exact'
 assert c.post(url,json=body).status_code==422
 body['confirm']=False;body['match_level']=None
 assert c.post(url,json=body).status_code==200
 assert result()['result']['requires_human_review']
 assert result()['entity_analysis']['semantic_status']=='pending'


def test_human_review_without_quote_uses_full_source_scope(app):
 module,c=app;rid=create(c)
 data=c.get('/api/runs/'+rid).json()
 assert data['event_metrics']['eligible']==200
 x=next(r for r in data['results'] if r['entity_analysis']['missing'] and not r['entity_analysis']['extra'])
 items=[dict(tag='missing',reference_entity=v,predicted_entity=None,evidence='',reason='人工核对原文确认遗漏') for v in x['entity_analysis']['missing']]
 response=c.post(f"/api/runs/{rid}/unified-reviews/{x['event_id']}/{x['field']}",json=dict(items=items,match_level='partial' if x['counts']['tp'] else 'mismatch',reviewer='tester',note='核对整段原文'))
 assert response.status_code==200,response.text
 after=c.get('/api/runs/'+rid).json()
 updated=next(r for r in after['results'] if r['event_id']==x['event_id'] and r['field']==x['field'])
 assert updated['entity_analysis']['diagnostics'][0]['evidence_scope']=='human_full_description_review'
 assert after['event_metrics']==data['event_metrics']
 assert '事件级严格指标' in c.get(f'/api/runs/{rid}/report').text
