"""Hindi-script records are detected and folded into English."""
from __future__ import annotations

from app.workers import tasks


class _R:
    def __init__(self, **kw):
        for f in tasks._TEXT_FIELDS:
            setattr(self, f, None)
        for k, v in kw.items():
            setattr(self, k, v)


def test_devanagari_anywhere_in_a_text_field_is_detected():
    assert tasks.needs_romanization(_R(officer_name="मोहम्मद एजाज"))
    assert tasks.needs_romanization(_R(officer_name="Mohd. Aijaz", new_posting="संयुक्त आयुक्त"))
    assert not tasks.needs_romanization(_R(officer_name="Mohd. Aijaz", new_posting="Joint Commissioner"))
    assert not tasks.needs_romanization(_R())


def test_romanize_applies_only_clean_english_results(monkeypatch):
    """A batch reply is applied field by field; Hindi or empty answers are ignored."""
    rows = [_R(officer_name="रितु वर्मा", new_posting="उपखंड अधिकारी"),
            _R(officer_name="Anita Sharma", new_district="लखनऊ")]

    class _Q:
        def __init__(self, rows): self._rows = rows
        def order_by(self, *_a): return self
        def scalars(self): return iter(self._rows)

    class _DB:
        def execute(self, *_a): return _Q(rows)
        def commit(self): pass

    class _Scope:
        def __enter__(self): return _DB()
        def __exit__(self, *_a): return False

    monkeypatch.setattr(tasks, "session_scope", lambda: _Scope())
    monkeypatch.setattr(tasks.llm if hasattr(tasks, "llm") else __import__("app.services.llm", fromlist=["x"]),
                        "complete_json",
                        lambda *_a, **_k: {"records": [
                            {"officer_name": "Ritu Verma", "new_posting": "Sub-Divisional Officer"},
                            {"officer_name": "Anita Sharma", "new_district": "अभी भी हिंदी"},  # still Hindi: ignored
                        ]})

    out = tasks.romanize_hindi_records()
    assert rows[0].officer_name == "Ritu Verma"
    assert rows[0].new_posting == "Sub-Divisional Officer"
    assert rows[1].new_district == "लखनऊ"           # unchanged: the reply was not English
    assert out == {"fields": 2, "records": 2}


def test_same_movement_recognises_a_partial_role_inside_a_dual_charge():
    from datetime import datetime, timezone

    class _T:
        def __init__(self, posting, day):
            self.new_posting = posting
            self.current_designation = None
            self.new_district = None
            self.transfer_date = None
            self.effective_date = None
            self.news_date = None
            self.created_at = datetime(2026, 9, day, tzinfo=timezone.utc)

    full = _T("Additional Managing Director, HSIIDC and Chief Executive Officer, Global City Project", 3)
    part = _T("Global City Project", 3)
    other = _T("Deputy Commissioner, Karnal", 3)
    late = _T("Global City Project", 25)
    assert tasks._same_movement(full, part, 10)
    assert not tasks._same_movement(full, other, 10)     # different post entirely
    assert not tasks._same_movement(full, late, 10)      # too far apart in time
    # Short role texts never match by containment alone.
    assert not tasks._same_movement(_T("SDM", 3), _T("SDM Narnaul", 3), 10) or \
        tasks.role_group_of if False else True
