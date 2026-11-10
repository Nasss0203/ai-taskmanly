import pytest

from app.modules.intent.schemas.intent_schema import IntentRequest
from app.modules.intent.services.intent_rules import deterministic_result
from app.modules.page_intent.services.page_reference_evidence import detect_page_reference


@pytest.mark.parametrize(("instruction", "title", "edit"), [  # D-40
    ("ở trang Ôn thi cuối kỳ tích việc Ôn chương 3 nha", "Ôn thi cuối kỳ", "tích việc Ôn chương 3 nha"),
    ("ở trang Ôn thi cuối kỳ đánh dấu Làm đề năm 2023 là đã xong", "Ôn thi cuối kỳ",
     "đánh dấu Làm đề năm 2023 là đã xong"),
    ("trong trang sub man hoàn thành Kiểm tra hệ thống", "sub man", "hoàn thành Kiểm tra hệ thống"),
    ("ở trang sub man bỏ tích việc Gửi email", "sub man", "bỏ tích việc Gửi email"),
    ("ở trang sub man, tích việc Kiểm tra hệ thống", "sub man", "tích việc Kiểm tra hệ thống"),
    ("giúp mình ở trang sub man bỏ việc in tài liệu đi nhé", "sub man", "bỏ việc in tài liệu đi nhé"),
])
def test_a_tick_or_untick_after_a_leading_page_is_split_off(instruction, title, edit) -> None:
    evidence = detect_page_reference(instruction)
    assert (evidence.reference_type, evidence.title, evidence.instruction) == ("TITLE", title, edit)
    intent = deterministic_result(IntentRequest(instruction=instruction))
    assert intent is not None and intent.intent == "MODIFY_PAGE" and not intent.needsClarification


@pytest.mark.parametrize(("instruction", "title", "edit"), [  # D-40
    ("ở trang Kế hoạch bỏ thuốc lá thêm việc chạy bộ", "Kế hoạch bỏ thuốc lá", "thêm việc chạy bộ"),
    ("ở trang sub man xoá việc in tài liệu", "sub man", "xoá việc in tài liệu"),
    ("ở trang Ôn thi cuối kỳ thêm việc gọi khách", "Ôn thi cuối kỳ", "thêm việc gọi khách"),
    ("tích việc Ôn chương 3 ở trang Ôn thi cuối kỳ", "Ôn thi cuối kỳ", "tích việc Ôn chương 3"),
])
def test_other_page_names_stay_as_before(instruction, title, edit) -> None:
    evidence = detect_page_reference(instruction)
    assert (evidence.reference_type, evidence.title, evidence.instruction) == ("TITLE", title, edit)
