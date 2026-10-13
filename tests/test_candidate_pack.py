import csv
import io
import json
import unicodedata
from pathlib import Path
import pytest
from evalpilot.engine import parse_dataset

PACK = Path(__file__).resolve().parents[1] / 'datasets/public_candidates_v1'
CASES = [json.loads(x) for x in (PACK/'candidates.jsonl').read_text(encoding='utf-8').splitlines()]
BAD = json.loads((PACK/'input_validation.json').read_text(encoding='utf-8'))

def test_candidate_scope_and_traceable_labels():
    assert len(CASES) == 55
    assert len({r['event_id'] for r in CASES}) == 55
    assert all(r['review_status'] == 'pending' and r['split'] == 'unassigned' for r in CASES)
    for r in CASES:
        text = unicodedata.normalize('NFKC', r['description'])
        for field in ('person', 'company', 'location'):
            for value in r['suggested_'+field]:
                assert value in text, (r['event_id'], field, value)
        assert 'predicted_person' not in r

@pytest.mark.parametrize('case', BAD, ids=[x['case_id'] for x in BAD])
def test_input_validation_specs_reject_as_expected(case):
    first = CASES[0]
    row = {'event_id':first['event_id'], 'description':first['description']}
    for field in ('person','company','location'):
        row['predicted_'+field] = '[]'
        row['reference_'+field] = json.dumps(first['suggested_'+field], ensure_ascii=False)
    row.update(case.get('overrides', {}))
    if case['kind'] == 'schema':
        del row[case['remove_column']]
    if case['kind'] == 'generated_record':
        row['description'] = case['description_character'] * case['description_repeat']
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(row))
    writer.writeheader()
    writer.writerow(row)
    with pytest.raises(ValueError, match=case['expected'].split('：')[1]):
        parse_dataset(buffer.getvalue().encode('utf-8'), 'validation.csv', 'test')
