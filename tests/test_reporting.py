from evalpilot.reporting import aggregate,explanation

def test_primary_counts_deduplicate_and_exclude_pending():
 def row(e,tags,status='validated'):
  return dict(event_id=e,field='person',entity_analysis=dict(eligible=True,semantic_status=status,diagnostics=[dict(tag=t,status='llm_validated') for t in tags]))
 g,d,p,u=aggregate([row('a',['extra','unsupported_entity','missing']),row('b',['missing'],'pending'),row('c',['alias'])])
 assert len(g[('person','多识别')]['events'])==1
 assert len(d['person'])==1
 assert ('b','person') in p
 assert len(g[('person','允许的表达差异')]['events'])==1
 assert '请填写' not in explanation('请填写关联依据')
