import json
from unittest.mock import MagicMock
import pytest
from evalpilot.diagnostics import entity_analysis, validate_diagnoses
from evalpilot.entity_judge import diagnose

def sample():
    return {'description':'前往白岑市青芦区松风路16号。','predicted':{'location':['白岑市']},'reference':{'location':['白岑市青芦区松风路16号']}}

def item():
    return {'tag':'location_granularity','predicted_entity':'白岑市','reference_entity':'白岑市青芦区松风路16号','evidence':'白岑市青芦区松风路16号','reason':'遗漏区和门牌'}

@pytest.mark.parametrize('mutation',['evidence','entity','duplicate','missing','tag'])
def test_reject_untraceable_diagnosis(mutation):
    e=sample();a=entity_analysis(e['predicted']['location'],e['reference']['location']);i=item();items=[i]
    if mutation=='evidence': i['evidence']='原文不存在'
    if mutation=='entity': i['predicted_entity']='错误城市'
    if mutation=='duplicate': items.append(dict(i))
    if mutation=='missing': items=[]
    if mutation=='tag': i['tag']='training_data_insufficient'
    with pytest.raises(ValueError): validate_diagnoses(items,a,e['description'])

def test_model_diagnosis_does_not_change_strict_sets(monkeypatch):
    monkeypatch.setenv('LLM_API_KEY','test');monkeypatch.setenv('LLM_MODEL','test')
    response=MagicMock();response.json.return_value={'choices':[{'message':{'content':json.dumps({'requires_review':False,'items':[item()]})}}]}
    client=MagicMock();client.__enter__.return_value.post.return_value=response
    monkeypatch.setattr('evalpilot.entity_judge.httpx.Client',lambda **kwargs:client)
    e=sample();a=entity_analysis(e['predicted']['location'],e['reference']['location'])
    out=diagnose(e,'location',a,True)
    assert out['semantic_status']=='validated'
    assert out['missing']==e['reference']['location'] and out['extra']==e['predicted']['location']

def test_disabled_does_not_call_model(monkeypatch):
    monkeypatch.setattr('evalpilot.entity_judge.httpx.Client',lambda **kwargs:pytest.fail('unexpected call'))
    e=sample();a=entity_analysis(e['predicted']['location'],e['reference']['location'])
    assert diagnose(e,'location',a,False)['diagnosis_attempts']==0
