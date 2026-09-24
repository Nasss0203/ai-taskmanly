from app.modules.writing.schemas import WritingAction, WritingRequest


SYSTEM_PROMPT = """
Bạn là trợ lý biên tập văn bản.
Thực hiện đúng thao tác được yêu cầu trên nội dung người dùng cung cấp.
Chỉ trả về văn bản kết quả, không giải thích, không thêm nhãn và không bọc Markdown.
Không bịa thêm dữ kiện không có trong nội dung nguồn.
""".strip()


ACTION_INSTRUCTIONS = {
    WritingAction.IMPROVE: (
        "Cải thiện độ rõ ràng, mạch lạc và chất lượng diễn đạt; giữ nguyên ý nghĩa."
    ),
    WritingAction.SHORTEN: (
        "Rút gọn văn bản nhưng giữ lại các thông tin và ý chính quan trọng."
    ),
    WritingAction.EXPAND: (
        "Mở rộng hợp lý dựa trên nội dung hiện có; không tạo thêm dữ kiện mới."
    ),
    WritingAction.SUMMARIZE: "Tóm tắt ngắn gọn các ý chính của văn bản.",
    WritingAction.TRANSLATE: "Dịch chính xác văn bản sang ngôn ngữ đích.",
    WritingAction.CONTINUE: (
        "Viết tiếp tự nhiên theo nội dung, giọng điệu và phong cách hiện tại."
    ),
}


def build_writing_prompts(request: WritingRequest) -> tuple[str, str]:
    parts = [
        f"Thao tác: {request.action.value}",
        f"Yêu cầu: {ACTION_INSTRUCTIONS[request.action]}",
    ]
    if request.target_language:
        parts.append(f"Ngôn ngữ đích: {request.target_language.strip()}")
    if request.tone:
        parts.append(f"Giọng điệu mong muốn: {request.tone.strip()}")
    parts.extend(["Nội dung nguồn:", request.text])
    return SYSTEM_PROMPT, "\n".join(parts)
