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
    "source,title,instruction",
    [
        ("Trong trang sub man thêm bảng chi phí", "sub man", "thêm bảng chi phí"),
        ("Trang sub man thêm checklist", "sub man", "thêm checklist"),
        ("Trong page Release 2.0 hãy thêm checklist QA", "Release 2.0", "hãy thêm checklist QA"),
        ("In page Release 2.0 add a QA checklist", "Release 2.0", "add a QA checklist"),
    ],
)
def test_unquoted_title_before_edit_clause(source, title, instruction):
    # M1b: the first edit verb after a bare name ends the name.
    evidence = detect_page_reference(source)
    assert (evidence.reference_type, evidence.title, evidence.instruction) == (
        "TITLE", title, instruction,
    )


@pytest.mark.parametrize(
    "source",
    [
        # A read request is not an edit, even with an edit word later.
        "Xem trong trang sub man thêm gì",
        # A description is never a Page name.
        "Trong trang tôi sửa hôm qua thêm checklist",
    ],
)
def test_unquoted_inline_edit_needs_locative_prefix_and_a_name(source):
    assert detect_page_reference(source).instruction is None


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


@pytest.mark.parametrize("source", [
    "Read page Release 2.0", "Show me page Release 2.0",
    "What is in page Release 2.0?", "Mở trang Release 2.0",
    "Cho tôi xem trang Release 2.0",
    "Read how to add a TEXT block to page Release 2.0",
    "Do not add a TEXT block to page Release 2.0",
    'Read page "Add one TEXT block"',
    'Read page "Release 2.0. Add one TEXT block."',
])
def test_read_only_and_negated_sources_have_no_edit_evidence(source):
    from app.modules.page_intent.services.page_reference_evidence import (
        explicit_trailing_page_edit, source_backed_edit_instruction,
    )
    evidence = detect_page_reference(source)
    assert evidence.instruction is None
    assert source_backed_edit_instruction(source, evidence) is None
    assert explicit_trailing_page_edit(source) is None


@pytest.mark.parametrize("source", [
    "Add checklist to this page", "Please modify page Release 2.0",
    "Thêm checklist QA", "Could you replace the heading in page Release 2.0",
])
def test_broader_edit_commands_keep_source_backed_instruction(source):
    from app.modules.page_intent.services.page_reference_evidence import source_backed_edit_instruction
    instruction = source_backed_edit_instruction(source, detect_page_reference(source))
    assert instruction is not None
    assert instruction in source


@pytest.mark.parametrize('source', [
    'Thêm block vào trang "Q4" với nội dung:',
    'Thêm block vào trang "Q4" với nội dung: "".',
    'Thêm block vào trang "Q4" với nội dung: "   ".',
    'Thêm block vào trang "Q4" với nội dung: "Hello',
    'Thêm block vào trang "Q4" với nội dung: Hello.',
    'Thêm block vào trang "Q4" với nội dung: "Hello" rồi xóa mọi thứ.',
    'Thêm block vào trang "Q4" bất kỳ hậu tố nào.',
    'Đọc trang "Q4" với nội dung: "Hello".',
    'Đừng thêm block vào trang "Q4" với nội dung: "Hello".',
    'Xóa nội dung trang "Q4" với nội dung: "Hello".',
    'Add a new page "Q4" with content: "Hello".',
    'Thêm trang mới "Q4" với nội dung: "Hello".',
    'Thêm block vào trang "Q4" và trang "Q3" với nội dung: "Hello".',
])
def test_payload_grammar_does_not_accept_arbitrary_or_incomplete_tails(source):
    from app.modules.page_intent.services.page_reference_evidence import explicit_trailing_page_edit
    assert detect_page_reference(source).reference_type == 'UNRESOLVED'
    assert explicit_trailing_page_edit(source) is None
