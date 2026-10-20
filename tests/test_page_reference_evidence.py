import pytest

from app.modules.page_intent.services.page_reference_evidence import (
    detect_page_reference,
    is_standalone_writing_request,
)


@pytest.mark.parametrize(
    "source,reference_type,title,instruction",
    [
        (
            "Thêm heading vào page Release 2.0",
            "TITLE", "Release 2.0", "Thêm heading",
        ),
        (
            'Thêm checklist vào trang "Kế hoạch phát hành"',
            "TITLE", "Kế hoạch phát hành", "Thêm checklist",
        ),
        (
            "Chỉnh heading trong trang Sprint Planning 2026",
            "TITLE", "Sprint Planning 2026", "Chỉnh heading",
        ),
        (
            "Thêm checklist vào trang hiện tại",
            "CURRENT_PAGE", None, "Thêm checklist",
        ),
        (
            "Thêm checklist vào page tôi sửa hôm qua",
            "UNRESOLVED", None, "Thêm checklist",
        ),
        (
            "Thêm checklist vào trang nói về OAuth",
            "UNRESOLVED", None, "Thêm checklist",
        ),
        (
            "Thêm checklist vào trang Alpha hoặc trang Beta",
            "UNRESOLVED", None, "Thêm checklist",
        ),
        (
            "Thêm checklist vào page",
            "UNRESOLVED", None, "Thêm checklist",
        ),
        (
            "Thêm checklist QA",
            "UNRESOLVED", None, None,
        ),
        (
            "Thêm checklist vào page named Release 2.0",
            "TITLE", "Release 2.0", "Thêm checklist",
        ),
        (
            'Thêm checklist vào page `Release 2.0`',
            "TITLE", "Release 2.0", "Thêm checklist",
        ),
        (
            "Thêm checklist vào page Release 2.0 và page Release 3.0",
            "UNRESOLVED", None, "Thêm checklist",
        ),
        (
            "Thêm checklist vào page của tôi",
            "UNRESOLVED", None, "Thêm checklist",
        ),
        (
            "Thêm checklist vào trang mà tôi sửa hôm qua",
            "UNRESOLVED", None, "Thêm checklist",
        ),
        (
            'Thêm checklist vào trang "nói về OAuth"',
            "TITLE", "nói về OAuth", "Thêm checklist",
        ),
        (
            "Thêm checklist vào trang có tên nói về OAuth",
            "TITLE", "nói về OAuth", "Thêm checklist",
        ),
        (
            "Add checklist to this page",
            "CURRENT_PAGE", None, None,
        ),
        (
            "Add checklist to current page",
            "CURRENT_PAGE", None, None,
        ),
        (
            'Add one TEXT block to page "Phase556 Fake Missing Page ZZZ96931".',
            "TITLE", "Phase556 Fake Missing Page ZZZ96931", "Add one TEXT block",
        ),
        (
            'Add one TEXT block to page "Page A" and page Beta',
            "UNRESOLVED", None, "Add one TEXT block",
        ),
        (
            "Trong page Release 2.0, thêm checklist QA",
            "TITLE", "Release 2.0", "thêm checklist QA",
        ),
        (
            "Thêm heading trong page Release 2.0, rồi thêm checklist QA",
            "TITLE", "Release 2.0", "Thêm heading rồi thêm checklist QA",
        ),
        (
            "Thêm checklist trong page Release 2.0, phần QA",
            "UNRESOLVED", None, "Thêm checklist",
        ),
    ],
)
def test_reference_evidence(source, reference_type, title, instruction):
    assert detect_page_reference(source) == (
        detect_page_reference(source).__class__(
            reference_type, title, instruction
        )
    )


@pytest.mark.parametrize(
    "source,expected",
    [
        ("Viết lại câu này cho ngắn gọn", True),
        ("Tóm tắt đoạn văn này", True),
        ("Rewrite this sentence", True),
        ("Viết lại nội dung page Release 2.0", False),
        ("Thêm checklist QA", False),
    ],
)
def test_standalone_writing_guard(source, expected):
    assert is_standalone_writing_request(source) is expected


@pytest.mark.parametrize("source,title,edit", [
    ('Trong page tên "Release 2.0", hãy thêm checklist QA', 'Release 2.0', 'hãy thêm checklist QA'),
    ('Modify the existing page named Release 2.0. Add one TEXT block.', 'Release 2.0', 'Add one TEXT block.'),
    ('Trong page Release 2.0, thêm checklist QA', 'Release 2.0', 'thêm checklist QA'),
    ('Trong page tên "Release 2.0", hãy thêm checklist QA vào cuối trang.', 'Release 2.0', 'hãy thêm checklist QA vào cuối trang.'),
    ('Trong page tên "Phase5 E2E disposable 1792399482659", hãy thêm một đoạn text vào cuối trang.', 'Phase5 E2E disposable 1792399482659', 'hãy thêm một đoạn text vào cuối trang.'),
    ('Add one TEXT block to page "Phase556 Fake Missing Page ZZZ96931".', 'Phase556 Fake Missing Page ZZZ96931', 'Add one TEXT block'),
])
def test_explicit_trailing_edit(source, title, edit):
    from app.modules.page_intent.services.page_reference_evidence import explicit_trailing_page_edit
    result = explicit_trailing_page_edit(source)
    assert result is not None
    assert (result.title, result.instruction) == (title, edit)


@pytest.mark.parametrize("source", [
    'Thêm checklist vào page Release 2.0',
    'Thêm checklist vào trang nói về OAuth',
    'Trong page Alpha hoặc page Beta, thêm checklist',
    'Viết lại văn bản này',
])
def test_ambiguous_or_plain_reference_does_not_skip_model(source):
    from app.modules.page_intent.services.page_reference_evidence import explicit_trailing_page_edit
    assert explicit_trailing_page_edit(source) is None
