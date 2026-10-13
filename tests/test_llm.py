import json
from unittest.mock import MagicMock
import pytest
from evalpilot.llm import semantic_judge

@pytest.mark.parametrize('confidence,rule,pending',[(.95,'BASE_01',False),(.5,'BASE_01',True),(.99,'INVENTED',True)])
def test_llm_validation(monkeypatch,confidence,rule,pending):
 monkeypatch.setenv('LLM_API_KEY','test-key');monkeypatch.setenv('LLM_MODEL','test-model')
 body={'match_level':'exact','error_type':'alias','confidence':confidence,'reason':'测试理由','applied_rule_ids':[rule],'requires_human_review':False}
 response=MagicMock();response.status_code=200;response.json.return_value={'choices':[{'message':{'content':json.dumps(body)}}],'usage':{'prompt_tokens':20,'completion_tokens':10}}
 client=MagicMock();client.__enter__.return_value.post.return_value=response
 monkeypatch.setattr('evalpilot.llm.httpx.Client',lambda **kw:client)
 e={'description':'合成案例','predicted':{'company':['A']},'reference':{'company':['AB']}}
 result=semantic_judge(e,'company',[{'id':'BASE_01','text':'规则'}])
 assert result['requires_human_review']==pending
