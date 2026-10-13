from evalpilot.engine import event_metrics

def test_event_metrics_weighting_and_exclusions():
 rows=[]
 def add(e,tp,fp,fn,unknown=False):
  for f in ('person','company','location'):
   rows.append({'event_id':e,'field':f,'counts':dict(tp=tp if f=='person' else 0,fp=fp if f=='person' else 0,fn=fn if f=='person' else 0),'unknown_reference':unknown})
 add('many',20,0,0);add('few',0,0,2);add('empty',0,0,0);add('unknown',1,0,0,True)
 m=event_metrics(rows,5)
 assert m['eligible']==3 and m['exact']==2 and m['exact_rate']==2/3
 assert m['mean_f1']==0.5 and m['mean_f1_events']==2
 assert m['all_empty']==1 and m['unknown_reference']==1 and m['incomplete']==1
 assert event_metrics([])['exact_rate'] is None
