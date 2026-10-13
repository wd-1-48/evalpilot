from evalpilot.diagnostics import entity_analysis, diagnostic_summary


def test_counts_are_traceable_and_not_forced_pairs():
    a = entity_analysis(['林澈', '沈甲'], ['林澈', '顾棠'])
    assert a['matched'] == ['林澈']
    assert a['missing'] == ['顾棠'] and a['extra'] == ['沈甲']
    assert not a['candidate_links']
    assert all(d['status'] == 'pending_semantic' for d in a['diagnostics'])


def test_substring_is_only_candidate_and_ambiguity_preserved():
    a = entity_analysis(['白岑市'], ['白岑市青芦区', '白岑市松风路'])
    assert len(a['candidate_links']) == 2
    assert all(x['status'] == 'pending_semantic' for x in a['candidate_links'])
    assert not any(d['status'] == 'rule_confirmed' for d in a['diagnostics'])


def test_unknown_and_empty_not_fabricated_errors():
    assert entity_analysis([], [])['status'] == 'exact'
    assert entity_analysis(['甲'], [], True)['diagnostics'] == []


def test_summary_deduplicates_events_and_separates_pending():
    rows = [{'field': 'person', 'event_id': '1', 'entity_analysis': entity_analysis([], ['甲', '乙'])}]
    rows.append({'field': 'person', 'event_id': '2', 'entity_analysis': entity_analysis(['丙'], ['丁'])})
    result = diagnostic_summary(rows)
    assert result['confirmed_event_counts'] == [{'field': 'person', 'tag': 'missing', 'events': 1}]
    assert result['pending_fields'] == {'person': 1}
