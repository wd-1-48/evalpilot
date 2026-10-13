import pytest
from evalpilot.diagnostics import semantic_gate

def item(tag='missing',p=None,r='林舟',e='林舟到场。'):
 return dict(tag=tag,predicted_entity=p,reference_entity=r,evidence=e,reason='核对实体')

def test_contradiction_and_pair_constraints():
 assert 'exact_conflicts_with_error_diagnosis' in semantic_gate([item()],{},'林舟到场。','exact')
 assert 'paired_tag_requires_two_entities' in semantic_gate([item('wrong_entity')],{},'林舟到场。','mismatch')
 assert 'extra_requires_prediction_only' in semantic_gate([item('extra','夏宁')],{},'林舟到场。','mismatch')

def test_alias_needs_explicit_evidence():
 good=item('alias','星禾','星禾公司','星禾公司（简称星禾）')
 assert semantic_gate([good],{},good['evidence'],'exact')==[]
 good['evidence']='星禾公司与星禾合作'
 assert 'alias_requires_explicit_relation_evidence' in semantic_gate([good],{},good['evidence'],'exact')

def test_unsupported_entity_cannot_appear_in_source():
 assert 'unsupported_entity_appears_in_source' in semantic_gate([item('unsupported_entity','林舟',None)],{},'林舟到场。','mismatch')

def test_judge_gate_routes_to_pending(monkeypatch):
 from evalpilot.entity_judge import diagnose
 from evalpilot.diagnostics import entity_analysis
 import json
 monkeypatch.setenv('LLM_API_KEY','test');monkeypatch.setenv('LLM_MODEL','mock')
 class Response:
  status_code=200
  def raise_for_status(self):pass
  def json(self):return {'choices':[{'message':{'content':json.dumps(dict(requires_review=False,match_level='exact',items=[item(),item('extra','夏宁',None)]))}}]}
 class Client:
  def __init__(self,**kwargs):pass
  def __enter__(self):return self
  def __exit__(self,*args):pass
  def post(self,*args,**kwargs):return Response()
 monkeypatch.setattr('evalpilot.entity_judge.httpx.Client',Client)
 a=entity_analysis(['夏宁'],['林舟'])
 e=dict(description='林舟到场。',predicted={'person':['夏宁']},reference={'person':['林舟']})
 result=diagnose(e,'person',a,True)
 assert result['semantic_status']=='pending'
 assert result['gate_errors']==['exact_conflicts_with_error_diagnosis']
 assert result['suggested_diagnostics']

def test_prompt_b_only_adds_steps_to_a():
 from evalpilot.entity_judge import build_prompt
 a,b=build_prompt('A'),build_prompt('B')
 assert b.startswith(a) and len(b)>len(a)
 assert build_prompt()==a
 with pytest.raises(ValueError):build_prompt('invalid')

def test_definitions_design_is_additive_and_production_unchanged():
 from evalpilot.entity_judge import build_prompt
 assert build_prompt('P1').startswith(build_prompt('P0'))
 assert build_prompt()==build_prompt('A')
 assert '分类标准' not in build_prompt('P0')
 assert '分类标准' in build_prompt('P1')
