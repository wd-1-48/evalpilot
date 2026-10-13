import csv
import io
import pytest
from evalpilot.engine import normalize,rule_compare,parse_dataset,metrics,GRAPH,REQUIRED
from evalpilot.llm import pending

def test_normalization():
 assert normalize(' 张三；李四、张三\n无 ') == ['张三','李四']
 assert normalize('["ACME, Inc.","A"]') == ['A','ACME, Inc.']
 assert normalize('ＡＢＣ')==['ABC']

@pytest.mark.parametrize('p,r,level',[([],[],'exact'),([],['a'],'mismatch'),(['a'],[],'mismatch'),(['a'],['a','b'],'partial'),(['a','b'],['a'],'partial')])
def test_deterministic_rules(p,r,level): assert rule_compare(p,r)['match_level']==level

def test_ambiguous_routes_to_review():
 e={'predicted':{'company':['星河']},'reference':{'company':['星河科技有限公司']},'unknown':[]}
 state=GRAPH.invoke({'event':e,'field':'company','judge':lambda *args:pending('not configured')})
 assert state['result']['requires_human_review']
 assert 'retrieve_evaluation_policy' in state['trace']
 assert rule_compare([],[],True) is None

def make_csv(rows,headers=REQUIRED):
 s=io.StringIO();w=csv.DictWriter(s,fieldnames=headers);w.writeheader();w.writerows(rows);return s.getvalue().encode()

def row(**kw): return dict.fromkeys(REQUIRED,'')|{'event_id':'1','description':'合成描述'}|kw

def test_aggregation_deduplication_and_conflict():
 a=row(predicted_person='张三',reference_person='张三');b=row(predicted_person='李四',reference_person='李四')
 events,summary=parse_dataset(make_csv([a,a,b]),'t.csv','v1')
 assert summary['duplicate_rows']==1 and len(events)==1
 assert events[0]['reference']['person']==['张三','李四']
 with pytest.raises(ValueError,match='冲突'):parse_dataset(make_csv([a,row(description='其他')]),'t.csv','v1')

def test_bad_files():
 with pytest.raises(ValueError,match='仅支持'):parse_dataset(b'', 't.xlsm','v')
 with pytest.raises(ValueError,match='缺少'):parse_dataset(b'a,b\n1,2','t.csv','v')
 with pytest.raises(ValueError,match='事件 ID'):parse_dataset(make_csv([row(event_id='')]),'t.csv','v')

def test_pending_and_unknown_denominators():
 rows=[{'field':'person','counts':{'tp':1,'fp':0,'fn':1},'result':rule_compare(['a'],['a','b'])},
       {'field':'person','counts':{'tp':0,'fp':1,'fn':0},'unknown_reference':True,'result':pending('unknown')}]
 m=metrics(rows)['person']
 assert m['confirmed']==1 and m['pending']==1 and m['strict_eligible']==1
 assert m['strict_f1']==pytest.approx(2/3) and m['exact_rate']==0

def test_whitespace_variants_preserved():
 events,summary=parse_dataset(make_csv([row(),row(description='合成 描述')]),'t.csv','v')
 assert len(events[0]['description_variants'])==2
 assert not events[0]['description_conflict']

def test_legacy_conflict_forces_review():
 from evalpilot.engine import ALIASES
 headers=list(ALIASES)
 a=dict.fromkeys(headers,'');a.update({'事件id':'1','描述':'甲','姓名':'张甲','人员矫正':'张甲'})
 events,summary=parse_dataset(make_csv([a,a|{'描述':'乙'}],headers),'t.csv','v')
 e=events[0]
 def forbidden(*args): raise AssertionError('Conflicting descriptions must not reach LLM')
 state=GRAPH.invoke({'event':e,'field':'person','judge':forbidden})
 assert state['result']['requires_human_review']
 assert summary['description_conflicts']==1 and len(e['raw_rows'])==2

def legacy_rows(rows):
 from evalpilot.engine import ALIASES
 headers=list(ALIASES)
 values=[dict.fromkeys(headers,'')|{'事件id':'1','描述':'合成描述'}|r for r in rows]
 return parse_dataset(make_csv(values,headers),'corrections.csv','v1')

def test_legacy_blank_keeps_prediction_before_aggregation():
 events,summary=legacy_rows([{'姓名':'张甲','公司名称':'甲公司'}, {'姓名':'李错','人员矫正':'李乙'}, {'姓名':'王丙','人员矫正':'未体现'}])
 e=events[0]
 assert e['reference']['person']==['张甲','李乙']
 assert e['predicted']['person']==['张甲','李错','王丙']
 assert e['reference']['company']==['甲公司']
 assert not e['unknown']
 assert summary['import_schema']=='correction-overlay-v2'
 assert e['raw_rows'][0]['reference_person']==''

@pytest.mark.parametrize('marker',['未体现','未提及','无法体现'])
def test_absence_marker_is_not_entity(marker):
 events,_=legacy_rows([{'发生地点':'无依据地点','地区矫正':marker}])
 e=events[0]
 result=GRAPH.invoke({'event':e,'field':'location','judge':lambda *args:pending('unused')})['result']
 assert e['reference']['location']==[] and e['unknown']==[]
 assert result['match_level']=='mismatch' and result['error_type']=='extra'

def test_canonical_blank_does_not_inherit_prediction():
 events,_=parse_dataset(make_csv([row(predicted_person='张甲')]),'canonical.csv','v1')
 assert events[0]['reference']['person']==[]

def test_unconfirmed_marker_remains_unknown():
 events,_=legacy_rows([{'公司名称':'甲公司','公司矫正':'未识别'}])
 assert events[0]['unknown']==['company']
