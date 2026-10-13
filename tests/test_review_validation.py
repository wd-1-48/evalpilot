import pytest
from fastapi import HTTPException


def test_invalid_review_rejected_before_database(monkeypatch, tmp_path):
    monkeypatch.setenv('EVALPILOT_DATA', str(tmp_path))
    import evalpilot.app as module
    for level in ('partial', 'mismatch'):
        body = module.Review(match_level=level, error_type='none', note='测试备注', reviewer='tester')
        with pytest.raises(HTTPException) as exc:
            module.review('not-existing', 'event', 'person', body)
        assert exc.value.status_code == 422
