from app.modules.page_composition.prompts.page_composition_prompt import SYSTEM_PROMPT


def test_tasks_and_checklists_are_todo_blocks() -> None:
    # A weekly meeting draft once listed its tasks as numbered TOGGLE blocks.
    assert "mỗi mục là MỘT block TODO" in SYSTEM_PROMPT
    assert "Không dùng TOGGLE cho nhiệm vụ hoặc checklist." in SYSTEM_PROMPT
    assert 'Không đánh số "1.", "2." trong content.text của TODO' in SYSTEM_PROMPT


def test_named_page_keeps_the_users_title() -> None:
    # "Tạo trang họp tuần" once became "Hội họp tuần".
    assert "page.title phải giữ đúng các từ đó" in SYSTEM_PROMPT
    assert "Không thêm, bớt hoặc đổi từ." in SYSTEM_PROMPT
