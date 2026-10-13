"""Deterministic differences; candidate links are not semantic conclusions."""
from collections import Counter

NORMALIZATION_VERSION = 'nfkc-trim-markers-v1'
TAGS = {'missing':'实体遗漏','extra':'多识别','unsupported_entity':'无原文依据实体',
        'alias':'显式简称等价','boundary_error':'实体边界错误','name_incomplete':'名称不完整',
        'branch_missing':'分支机构信息缺失','location_granularity':'地点粒度不足',
        'type_error':'实体类型错误','character_error':'字符差异','wrong_entity':'错误实体'}
PRIMARY_TAGS={'missing':'实体遗漏','extra':'多识别','unsupported_entity':'多识别',
 'boundary_error':'边界／完整性错误','name_incomplete':'边界／完整性错误',
 'branch_missing':'边界／完整性错误','location_granularity':'边界／完整性错误',
 'type_error':'类型错误','character_error':'内容错误','wrong_entity':'内容错误','alias':'允许的表达差异'}


def validate_diagnoses(items, analysis, description):
    """Every difference must be explained once; evidence must be verbatim."""
    seen_p, seen_r = set(), set()
    for item in items:
        p, r = item.get('predicted_entity'), item.get('reference_entity')
        if item.get('tag') not in TAGS or not (p or r):
            raise ValueError('Unknown tag or empty link')
        if p is not None:
            if p not in analysis['extra'] or p in seen_p: raise ValueError('Invalid prediction link')
            seen_p.add(p)
        if r is not None:
            if r not in analysis['missing'] or r in seen_r: raise ValueError('Invalid reference link')
            seen_r.add(r)
        if not item.get('evidence') or item['evidence'] not in description:
            raise ValueError('Evidence must be a source substring')
    if seen_p != set(analysis['extra']) or seen_r != set(analysis['missing']):
        raise ValueError('Incomplete difference coverage')
    return items


def entity_analysis(predicted, reference, unknown=False):
    p, r = set(predicted), set(reference)
    matched, missing, extra = sorted(p & r), sorted(r - p), sorted(p - r)
    result = {
        'normalization_version': NORMALIZATION_VERSION,
        'eligible': not unknown,
        'matched': matched, 'missing': missing, 'extra': extra,
        'status': 'unknown_reference' if unknown else (
            'exact' if p == r else 'partial_entities' if matched else 'no_exact_match'),
        'diagnostics': [], 'candidate_links': [],
    }
    if unknown:
        return result
    # Both-sided differences may be aliases/boundary errors. Never assert a
    # semantic omission or an invented entity solely from lexical non-match.
    unresolved = bool(missing and extra)
    for kind, entities in [('missing', missing), ('extra', extra)]:
        for entity in entities:
            result['diagnostics'].append({
                'tag': kind, 'reference_entity': entity if kind == 'missing' else None,
                'predicted_entity': entity if kind == 'extra' else None,
                'source': 'strict_set_difference',
                'status': 'pending_semantic' if unresolved else 'rule_confirmed',
                'reason': '规范化后的参考集合与预测集合差异；不推断模型内部原因',
            })
    for gold in missing:
        for pred in extra:
            if gold in pred or pred in gold:
                result['candidate_links'].append({
                    'reference_entity': gold, 'predicted_entity': pred,
                    'basis': 'substring_overlap', 'status': 'pending_semantic',
                })
    return result


def diagnostic_summary(rows):
    """Count event IDs per field/tag, not FP+FN as independent diagnoses."""
    events = {}
    pending = Counter()
    for row in rows:
        analysis = row.get('entity_analysis')
        if not analysis or not analysis['eligible']:
            continue
        if analysis.get('semantic_status')=='pending' or any(d['status'] == 'pending_semantic' for d in analysis['diagnostics']):
            pending[row['field']] += 1
        for d in analysis['diagnostics']:
            if d['status'] not in ('rule_confirmed','llm_validated','human_confirmed'):
                continue
            events.setdefault((row['field'], d['tag']), set()).add(row['event_id'])
    return {'confirmed_event_counts': [
        {'field': field, 'tag': tag, 'events': len(ids)}
        for (field, tag), ids in sorted(events.items())
    ], 'pending_fields': dict(pending)}

GATE_VERSION = 'semantic-gate-v1'

def semantic_gate(items, analysis, description, level):
    """Conservative, deterministic vetoes; passing is not proof of semantic truth."""
    errors=[]
    for item in items:
        tag=item['tag'];p=item.get('predicted_entity');r=item.get('reference_entity');quote=item.get('evidence','')
        if tag=='missing' and (p or not r): errors.append('missing_requires_reference_only')
        if tag in ('extra','unsupported_entity') and (r or not p): errors.append('extra_requires_prediction_only')
        if tag in ('alias','boundary_error','name_incomplete','branch_missing','location_granularity','character_error','wrong_entity') and not (p and r): errors.append('paired_tag_requires_two_entities')
        if tag=='unsupported_entity' and p and p in description: errors.append('unsupported_entity_appears_in_source')
        if tag=='alias' and p and r:
            # Explicit relation must be present in the same quoted passage.
            if p not in quote or r not in quote or not any(marker in quote for marker in ('简称','又称','也称','全称')):
                errors.append('alias_requires_explicit_relation_evidence')
        if not item.get('reason','').strip(): errors.append('empty_reason')
    if level=='exact' and any(i['tag']!='alias' for i in items): errors.append('exact_conflicts_with_error_diagnosis')
    if level in ('partial','mismatch') and items and all(i['tag']=='alias' for i in items): errors.append('error_level_with_only_allowed_aliases')
    return sorted(set(errors))
