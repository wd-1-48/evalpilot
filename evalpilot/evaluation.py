"""One combined semantic call per unresolved field; strict results immutable."""
import time
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from .engine import strict_counts, rule_compare
from .diagnostics import entity_analysis
from .entity_judge import diagnose
from .llm import pending

class EvaluationState(TypedDict, total=False):
    event: dict
    field: str
    enabled: bool
    analysis: dict
    result: dict

def prepare(state):
    e,f=state['event'],state['field']
    unknown=f in e['unknown'] or e.get('description_conflict',False)
    return {'analysis':entity_analysis(e['predicted'][f],e['reference'][f],unknown),
            'result':rule_compare(e['predicted'][f],e['reference'][f],unknown)}

def diagnostic_node(state):
    return {'analysis':diagnose(state['event'],state['field'],state['analysis'],state['enabled'])}

graph=StateGraph(EvaluationState)
graph.add_node('strict_compare',prepare)
graph.add_node('diagnose_difference',diagnostic_node)
graph.add_edge(START,'strict_compare')
graph.add_conditional_edges('strict_compare',lambda s:'diagnose' if s['analysis']['eligible'] and (s['analysis']['missing'] or s['analysis']['extra']) else 'done',{'diagnose':'diagnose_difference','done':END})
graph.add_edge('diagnose_difference',END)
COMBINED_GRAPH=graph.compile()

def evaluate_field(event, field, allow_llm=False):
    started=time.monotonic()
    unknown=field in event['unknown'] or event.get('description_conflict',False)
    p,r=event['predicted'][field],event['reference'][field]
    state=COMBINED_GRAPH.invoke({'event':event,'field':field,'enabled':allow_llm})
    analysis,result=state['analysis'],state['result']
    if result is None:
        level=analysis.get('field_match_level')
        if analysis.get('semantic_status')=='validated' and level:
            tags={d['tag'] for d in analysis['diagnostics']}
            result=dict(match_level=level,error_type=next(iter(tags)) if len(tags)==1 else 'mixed',
                        reason='；'.join(d['reason'] for d in analysis['diagnostics']),
                        confidence=None,requires_human_review=False,evaluation_method='llm_combined',applied_rule_ids=[])
        else:
            result=pending(analysis.get('diagnosis_note','参考答案或描述待确认'))
    result.update(attempts=analysis.get('diagnosis_attempts',0),usage=analysis.get('diagnosis_usage',{}))
    return dict(event_id=event['event_id'],field=field,predicted=p,reference=r,
                unknown_reference=unknown,result=result,original_result=dict(result),counts=strict_counts(p,r),
                entity_analysis=analysis,trace=['normalize_entities','compare_entity_sets','combined_diagnosis' if analysis.get('diagnosis_attempts') else 'rule_diagnosis'],
                policies=[],policy_version='2.0',latency_ms=round((time.monotonic()-started)*1000,2))
