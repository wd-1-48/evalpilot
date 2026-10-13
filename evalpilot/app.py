from .engine import event_metrics
from concurrent.futures import ThreadPoolExecutor, as_completed
from .evaluation import evaluate_field
import hashlib
import json
import os
import sqlite3
import threading
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .engine import parse_dataset, FIELDS, GRAPH, metrics, strict_counts, POLICIES, LEGACY_SCHEMA
from .diagnostics import entity_analysis, diagnostic_summary, TAGS, PRIMARY_TAGS
from .entity_judge import diagnose
from .diagnostics import validate_diagnoses
from .entity_judge import Diagnosis
from .llm import semantic_judge, pending
from .demo import demo_csv

ROOT=Path(__file__).resolve().parent.parent
for line in (ROOT/'.env').read_text(encoding='utf-8-sig').splitlines() if (ROOT/'.env').exists() else []:
 if '=' in line and not line.strip().startswith('#'):
  k,v=line.split('=',1);os.environ.setdefault(k.strip(),v.strip().strip('"').strip("'"))
DATA=Path(os.getenv('EVALPILOT_DATA',str(ROOT/'data')));DATA.mkdir(exist_ok=True,parents=True)
DB=DATA/'evalpilot.sqlite'; LOCK=threading.Lock()
def conn():
 c=sqlite3.connect(DB,timeout=30);c.row_factory=sqlite3.Row;return c
def dump(x): return json.dumps(x,ensure_ascii=False)
with conn() as c:
 c.executescript('''
 PRAGMA journal_mode=WAL;
 CREATE TABLE IF NOT EXISTS datasets(id TEXT PRIMARY KEY,name TEXT,version TEXT,events TEXT,summary TEXT,cohort TEXT,created REAL);
 CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,dataset_id TEXT,status TEXT,allow_llm INTEGER,created REAL,elapsed REAL DEFAULT 0,error TEXT);
 CREATE TABLE IF NOT EXISTS results(run_id TEXT,event_id TEXT,field TEXT,payload TEXT,PRIMARY KEY(run_id,event_id,field));
 CREATE TABLE IF NOT EXISTS reviews(id INTEGER PRIMARY KEY,run_id TEXT,event_id TEXT,field TEXT,before_json TEXT,after_json TEXT,note TEXT,reviewer TEXT,created REAL);
 ''')
 # An interrupted process can resume from the last committed field.
 c.execute("UPDATE runs SET status='interrupted' WHERE status IN ('running','queued')")
app=FastAPI(title='EvalPilot',version='0.1.0')
app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')

@app.middleware('http')
async def local_only(request,call_next):
 origin=request.headers.get('origin')
 if origin and origin not in ('http://127.0.0.1:8765','http://localhost:8765'):
  return Response('Origin rejected',status_code=403)
 if request.headers.get('host','').split(':')[0] not in ('127.0.0.1','localhost','testserver'):
  return Response('Host rejected',status_code=403)
 length=request.headers.get('content-length')
 if length and int(length)>11*1024*1024: return Response('Upload too large',status_code=413)
 return await call_next(request)

@app.get('/')
def index(): return FileResponse(ROOT/'static/index.html')
@app.get('/api/status')
def status(): return {'llm_configured':bool(os.getenv('LLM_API_KEY') and os.getenv('LLM_MODEL')),'policy_version':'2.0','retrieval':'字符二元组余弦检索（词法基线）'}
@app.get('/api/policies')
def policies(): return POLICIES

def save_dataset(content,name,version):
 try: events,summary=parse_dataset(content,name,version)
 except Exception as e: raise HTTPException(422,str(e))
 did=uuid.uuid4().hex
 # Cohort excludes predictions/version, but includes descriptions and reference validity.
 cohort=hashlib.sha256(dump(sorted([{'id':e['event_id'],'descriptions':sorted(e['description_variants']),'reference':e['reference'],'unknown':e['unknown']} for e in events],key=lambda e:e['id'])).encode()).hexdigest()
 with conn() as c:
  c.execute('INSERT INTO datasets VALUES(?,?,?,?,?,?,?)',(did,Path(name).name,version,dump(events),dump(summary),cohort,time.time()))
 return {'id':did,'summary':summary}

@app.post('/api/datasets')
async def upload(file:UploadFile=File(...),version:str=Form(...)):
 if not version.strip() or len(version)>80: raise HTTPException(422,'模型版本需要 1～80 字符')
 content=await file.read(10*1024*1024+1)
 return save_dataset(content,file.filename or '',version.strip())
@app.post('/api/demo/{version}')
def demo(version:Literal['demo-v1','demo-v2']): return save_dataset(demo_csv(version),version+'.csv',version)
@app.get('/api/template')
def template(): return Response(demo_csv(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="evalpilot-demo.csv"'})
@app.get('/api/datasets')
def datasets():
 with conn() as c: rows=c.execute('SELECT id,name,version,summary,created FROM datasets ORDER BY created DESC').fetchall()
 return [dict(r)|{'summary':annotate_import(json.loads(r['summary']))} for r in rows]

def annotate_import(summary):
 summary['outdated_import']=bool(summary.get('legacy') and summary.get('import_schema')!=LEGACY_SCHEMA)
 if summary['outdated_import']:
  summary['warning']='旧导入口径已过期：曾将空白矫正误作未知。请重新导入原表创建新任务；此处仅保留历史记录。'
 return summary

def require_current_import(c,dataset_id):
 row=c.execute('SELECT summary FROM datasets WHERE id=?',(dataset_id,)).fetchone()
 if not row: raise HTTPException(404,'数据集不存在')
 if annotate_import(json.loads(row['summary']))['outdated_import']:
  raise HTTPException(409,'原表导入口径已更新，请重新上传原表；旧结果保留但不能继续使用旧口径评测。')

class StartRun(BaseModel):
 dataset_id:str
 allow_llm:bool=False
def run_worker(rid):
 with LOCK:
  with conn() as c:
   run=c.execute('SELECT * FROM runs WHERE id=?',(rid,)).fetchone()
   dataset=c.execute('SELECT * FROM datasets WHERE id=?',(run['dataset_id'],)).fetchone()
   done={(r['event_id'],r['field']) for r in c.execute('SELECT event_id,field FROM results WHERE run_id=?',(rid,))}
   c.execute("UPDATE runs SET status='running',error=NULL WHERE id=?",(rid,))
  started=time.monotonic()
  try:
   work=[(e,f) for e in json.loads(dataset['events']) for f in FIELDS if (e['event_id'],f) not in done]
   with ThreadPoolExecutor(max_workers=3) as pool:
    futures=[pool.submit(evaluate_field,e,f,bool(run['allow_llm'])) for e,f in work]
    for future in as_completed(futures):
     payload=future.result()
     with conn() as c: c.execute('INSERT OR IGNORE INTO results VALUES(?,?,?,?)',(rid,payload['event_id'],payload['field'],dump(payload)))
   with conn() as c: c.execute("UPDATE runs SET status='completed',elapsed=elapsed+? WHERE id=?",(time.monotonic()-started,rid))
  except Exception as exc:
   with conn() as c: c.execute("UPDATE runs SET status='failed',error=?,elapsed=elapsed+? WHERE id=?",(type(exc).__name__,time.monotonic()-started,rid))

@app.post('/api/runs')
def start(body:StartRun,background:BackgroundTasks):
 with conn() as c:
  require_current_import(c,body.dataset_id)
  rid=uuid.uuid4().hex
  c.execute('INSERT INTO runs(id,dataset_id,status,allow_llm,created) VALUES(?,?,?,?,?)',(rid,body.dataset_id,'queued',body.allow_llm,time.time()))
 background.add_task(run_worker,rid)
 return {'id':rid}
@app.post('/api/runs/{rid}/resume')
def resume(rid:str,background:BackgroundTasks):
 with conn() as c:
  r=c.execute('SELECT status,dataset_id FROM runs WHERE id=?',(rid,)).fetchone()
  if not r: raise HTTPException(404,'任务不存在')
  require_current_import(c,r['dataset_id'])
  if r['status'] not in ('failed','interrupted'): raise HTTPException(409,'只有中断或失败任务可以恢复')
  c.execute("UPDATE runs SET status='queued' WHERE id=?",(rid,))
 background.add_task(run_worker,rid);return {'id':rid}
@app.get('/api/runs')
def runs():
 with conn() as c: return [dict(r) for r in c.execute('SELECT runs.*,datasets.version,datasets.name FROM runs JOIN datasets ON datasets.id=runs.dataset_id ORDER BY runs.created DESC')]
def get_run(rid):
 with conn() as c:
  run=c.execute('SELECT runs.*,datasets.version,datasets.cohort,datasets.summary FROM runs JOIN datasets ON datasets.id=runs.dataset_id WHERE runs.id=?',(rid,)).fetchone()
  if not run: raise HTTPException(404,'任务不存在')
  results=[json.loads(r['payload']) for r in c.execute('SELECT payload FROM results WHERE run_id=? ORDER BY event_id,field',(rid,))]
 return dict(run),results
@app.get('/api/runs/{rid}')
def detail(rid:str):
 run,rows=get_run(rid);run['summary']=annotate_import(json.loads(run['summary']))
 tokens=Counter()
 for r in rows:
  usage=r['original_result'].get('usage',{})
  tokens.update({k:v for k,v in usage.items() if k in ('prompt_tokens','completion_tokens','total_tokens') and isinstance(v,(int,float))})
 latency=sorted(r['latency_ms'] for r in rows)
 return {'run':run,'results':rows,'metrics':metrics(rows),'event_metrics':event_metrics(rows,run['summary']['events']),'operations':{'processed':len(rows),'expected':run['summary']['events']*3,
  'pending':sum(x['result']['requires_human_review'] for x in rows),'rule_resolved':sum(x['original_result']['evaluation_method']=='rule' for x in rows),
  'llm_calls':sum(x['original_result'].get('attempts',0) for x in rows),'tokens':dict(tokens),
  'entity_diagnosis_calls':sum(x.get('entity_analysis',{}).get('diagnosis_attempts',0) for x in rows),
  'entity_diagnosis_pending':sum(x.get('entity_analysis',{}).get('semantic_status')=='pending' for x in rows),
  'p95_ms':latency[min(len(latency)-1,int(len(latency)*.95))] if latency else 0}}

class Review(BaseModel):
 match_level:Literal['exact','partial','mismatch']
 error_type:Literal['none','missing','extra','mixed','alias','location_granularity','ambiguous','wrong_entity','ocr','boundary_error','name_incomplete','branch_missing','type_error','character_error','unsupported_entity']
 note:str=Field(min_length=2,max_length=1200)
 reviewer:str=Field(min_length=1,max_length=80)
@app.post('/api/runs/{rid}/reviews/{eid}/{field}')
def review(rid:str,eid:str,field:str,body:Review):
 if body.match_level!='exact' and body.error_type=='none':
  raise HTTPException(422,'部分一致或完全不一致必须选择具体差异标签，不能选择 none')
 if not body.note.strip() or not body.reviewer.strip():
  raise HTTPException(422,'复核人和判断依据不能仅为空白')
 with conn() as c:
  row=c.execute('SELECT payload FROM results WHERE run_id=? AND event_id=? AND field=?',(rid,eid,field)).fetchone()
  if not row: raise HTTPException(404,'评测项不存在')
  p=json.loads(row['payload']);before=p['result']
  after={'match_level':body.match_level,'error_type':body.error_type,'reason':body.note,'confidence':1,'requires_human_review':body.error_type=='ambiguous','evaluation_method':'human','applied_rule_ids':before['applied_rule_ids']}
  p['result']=after
  c.execute('INSERT INTO reviews(run_id,event_id,field,before_json,after_json,note,reviewer,created) VALUES(?,?,?,?,?,?,?,?)',(rid,eid,field,dump(before),dump(after),body.note,body.reviewer,time.time()))
  c.execute('UPDATE results SET payload=? WHERE run_id=? AND event_id=? AND field=?',(dump(p),rid,eid,field))
 return {'saved':True}
@app.get('/api/runs/{rid}/reviews')
def history(rid:str):
 with conn() as c: return [dict(r) for r in c.execute('SELECT * FROM reviews WHERE run_id=? ORDER BY id DESC',(rid,))]

class HumanDiagnosis(Diagnosis):
 evidence:str=Field(default="",max_length=2000)

class UnifiedReview(BaseModel):
 match_level:Literal['exact','partial','mismatch']|None=None
 items:list[HumanDiagnosis]=Field(max_length=100)
 reviewer:str=Field(min_length=1,max_length=80)
 note:str=Field(min_length=2,max_length=1200)
 confirm:bool=True

@app.post('/api/runs/{rid}/unified-reviews/{eid}/{field}')
def unified_review(rid:str,eid:str,field:str,body:UnifiedReview):
 if not body.reviewer.strip() or len(body.note.strip())<2:
  raise HTTPException(422,'请填写复核人和判断依据')
 event=event_context(rid,eid)
 with conn() as c:
  row=c.execute('SELECT payload FROM results WHERE run_id=? AND event_id=? AND field=?',(rid,eid,field)).fetchone()
  if not row: raise HTTPException(404,'评测项不存在')
  p=json.loads(row['payload']);a=p.get('entity_analysis') or entity_analysis(p['predicted'],p['reference'],p.get('unknown_reference',False))
  items=[x.model_dump() for x in body.items]
  allowed={'missing','extra','boundary_error','type_error','wrong_entity','alias'}
  if any(x['tag'] not in allowed for x in items): raise HTTPException(422,'请选择统一后的主标签')
  if body.confirm:
   if not a['eligible']: raise HTTPException(422,'参考答案或描述待确认，请保留待复核')
   if body.match_level is None: raise HTTPException(422,'请选择字段结论')
   try: validate_diagnoses([dict(x,evidence=x['evidence'] or event['description']) for x in items],a,event['description'])
   except ValueError as exc: raise HTTPException(422,str(exc))
   for item in items:
    if not item['reason'].strip() or any(v in item['reason'] for v in ('请填写','待补充','待确认')): raise HTTPException(422,'请填写具体差异说明，或选择保留待复核')
    pred,ref=item['predicted_entity'],item['reference_entity']
    if (item['tag']=='missing' and (pred or not ref)) or (item['tag']=='extra' and (ref or not pred)):
     raise HTTPException(422,'实体遗漏仅填写参考实体；多识别仅填写预测实体')
    if item['tag'] in {'boundary_error','wrong_entity','alias'} and not (pred and ref):
     raise HTTPException(422,'边界、内容或表达差异需关联预测和参考实体')
   if body.match_level=='exact' and any(x['tag']!='alias' for x in items):
    raise HTTPException(422,'存在错误实体时不能确认符合评测要求')
   if body.match_level!='exact' and not any(x['tag']!='alias' for x in items):
    raise HTTPException(422,'不符合或部分符合需有具体错误实体')
  before={'result':p['result'],'entity_analysis':p.get('entity_analysis')}
  tags=sorted({x['tag'] for x in items})
  p['result']={'match_level':body.match_level,'error_type':tags[0] if len(tags)==1 else 'mixed' if tags else 'none','error_types':tags,'reason':body.note,'confidence':None,'requires_human_review':not body.confirm,'evaluation_method':'human','applied_rule_ids':p['result'].get('applied_rule_ids',[])}
  a=dict(a,diagnostics=[dict(x,evidence_scope='quoted_source' if x['evidence'] else 'human_full_description_review',source='human',status='human_confirmed' if body.confirm else 'pending_semantic') for x in items],semantic_status='human_confirmed' if body.confirm else 'pending',diagnosis_note=body.note)
  p['entity_analysis']=a
  after={'result':p['result'],'entity_analysis':a}
  c.execute('INSERT INTO reviews(run_id,event_id,field,before_json,after_json,note,reviewer,created) VALUES(?,?,?,?,?,?,?,?)',(rid,eid,field,dump(before),dump(after),'[统一复核] '+body.note,body.reviewer,time.time()))
  c.execute('UPDATE results SET payload=? WHERE run_id=? AND event_id=? AND field=?',(dump(p),rid,eid,field))
 return {'saved':True}

class EntityReview(BaseModel):
 items:list[Diagnosis]=Field(max_length=100)
 reviewer:str=Field(min_length=1,max_length=80)
 note:str=Field(min_length=2,max_length=1200)
 confirm:bool=True

@app.post('/api/runs/{rid}/entity-reviews/{eid}/{field}')
def entity_review(rid:str,eid:str,field:str,body:EntityReview):
 if not body.reviewer.strip() or not body.note.strip(): raise HTTPException(422,'请填写复核人和依据')
 event=event_context(rid,eid)
 with conn() as c:
  row=c.execute('SELECT payload FROM results WHERE run_id=? AND event_id=? AND field=?',(rid,eid,field)).fetchone()
  if not row: raise HTTPException(404,'评测项不存在')
  payload=json.loads(row['payload']);analysis=payload.get('entity_analysis')
  if not analysis or not analysis['eligible']: raise HTTPException(422,'参考或描述待确认，不能确认诊断')
  items=[x.model_dump() for x in body.items]
  if body.confirm:
   try: validate_diagnoses(items,analysis,event['description'])
   except ValueError as exc: raise HTTPException(422,str(exc))
  before=dump(analysis)
  analysis['diagnostics']=[dict(x,source='human',status='human_confirmed' if body.confirm else 'pending_semantic') for x in items]
  analysis['semantic_status']='human_confirmed' if body.confirm else 'pending'
  analysis['diagnosis_note']=body.note
  c.execute('INSERT INTO reviews(run_id,event_id,field,before_json,after_json,note,reviewer,created) VALUES(?,?,?,?,?,?,?,?)',
            (rid,eid,field,before,dump(analysis),'[实体诊断] '+body.note,body.reviewer,time.time()))
  c.execute('UPDATE results SET payload=? WHERE run_id=? AND event_id=? AND field=?',(dump(payload),rid,eid,field))
 return {'saved':True}

@app.get('/api/runs/{rid}/events/{eid}')
def event_context(rid:str,eid:str):
 run,_=get_run(rid)
 with conn() as c: dataset=c.execute('SELECT events FROM datasets WHERE id=?',(run['dataset_id'],)).fetchone()
 for e in json.loads(dataset['events']):
  if e['event_id']==eid: return e
 raise HTTPException(404,'事件不存在')
@app.get('/api/compare')
def compare(a:str,b:str):
 ra,aa=get_run(a);rb,bb=get_run(b)
 if any(annotate_import(json.loads(r['summary']))['outdated_import'] for r in (ra,rb)):
  raise HTTPException(409,'旧导入口径已过期，请重新导入原表后比较')
 if ra['status']!='completed' or rb['status']!='completed': raise HTTPException(409,'请等待两个任务均完成')
 if ra['cohort']!=rb['cohort']: raise HTTPException(422,'事件、描述或标准答案不同，不能直接比较')
 ma,mb=metrics(aa),metrics(bb)
 old={(x['event_id'],x['field']):x for x in aa};changes=[];rank={'mismatch':0,'partial':1,'exact':2}
 for x in bb:
  prev=old[(x['event_id'],x['field'])]
  if prev['result']['requires_human_review'] or x['result']['requires_human_review']: continue
  before,after=prev['result']['match_level'],x['result']['match_level']
  if before!=after: changes.append({'event_id':x['event_id'],'field':x['field'],'before':before,'after':after,'direction':'improved' if rank[after]>rank[before] else 'regressed'})
 return {'a':ra['version'],'b':rb['version'],'metrics_a':ma,'metrics_b':mb,'changes':changes,'paired_confirmed':sum(not old[(x['event_id'],x['field'])]['result']['requires_human_review'] and not x['result']['requires_human_review'] for x in bb)}
@app.get('/api/runs/{rid}/report')
def report(rid:str):
 from .reporting import render_report
 return Response(render_report(detail(rid)),media_type='text/markdown; charset=utf-8',headers={'Content-Disposition':'attachment; filename="evalpilot-report.md"'})
