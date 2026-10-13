from evalpilot.evaluation import evaluate_field

def event():
 return {'event_id':'test','description':'林澈与顾棠在青页展馆见面。','unknown':[],
         'predicted':{'person':['林澈'],'company':['青页展馆'],'location':[]},
         'reference':{'person':['林澈','顾棠'],'company':[],'location':['青页展馆']}}

def test_simple_and_cross_field_errors_do_not_call_llm(monkeypatch):
 monkeypatch.setattr('evalpilot.entity_judge.httpx.Client',lambda **kwargs: (_ for _ in ()).throw(AssertionError('Unexpected model call')))
 for field in ['person','company','location']:
  result=evaluate_field(event(),field,True)
  assert result['result']['attempts']==0
  assert result['entity_analysis']['semantic_status']=='rule_resolved'
  if field!='person': assert result['entity_analysis']['diagnostics'][0]['tag']=='type_error'

def test_combined_judgment_keeps_strict_counts(monkeypatch):
 e=event();e['predicted']['person']=['林澈和']
 def fake(e,f,a,enabled):
  a.update(semantic_status='validated',field_match_level='partial',diagnosis_attempts=1,
           diagnostics=[{'tag':'boundary_error','reason':'字符边界错误'}])
  return a
 monkeypatch.setattr('evalpilot.evaluation.diagnose',fake)
 result=evaluate_field(e,'person',True)
 assert result['counts']=={'tp':0,'fp':1,'fn':2}
 assert result['result']['match_level']=='partial'
 assert result['result']['attempts']==1

def test_unknown_reference_never_auto_confirms():
 e=event();e['unknown']=['person']
 result=evaluate_field(e,'person',True)
 assert result['unknown_reference'] and result['result']['requires_human_review']
