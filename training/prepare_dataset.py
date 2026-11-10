"""Synthetic planner requests for fine-tuning (kế hoạch train Colab, T2).

Every request is made up here: page contexts and instructions come from the
word lists below, never from the database. Each request carries the
expectations ``scripts.evaluate_generation.check_plan`` understands, so the
teacher's answers are kept only when they are right, not just valid.

Requests the rules answer without a model (tick, edit text, delete, checklist
from a named source Page) are skipped: there is nothing to learn there. Page
titles, instructions and topics of the evaluation sets are kept out (T2).

    python -m training.prepare_dataset --count 700 --seed 7
"""

import argparse
import json
import random
import re
import unicodedata
import uuid
from pathlib import Path
from typing import Any

from app.modules.modification_planner.schemas.modification_planner_schema import ModificationPlannerRequest
from app.modules.modification_planner.services.database_rows import plan_database_rows, plan_rows_and_blocks
from app.modules.modification_planner.services.block_delete import plan_block_delete
from app.modules.modification_planner.services.missing_target import plan_missing_target
from app.modules.modification_planner.services.explicit_plan import plan_explicit_content
from app.modules.modification_planner.services.block_text import plan_block_text
from app.modules.modification_planner.services.reference_checklist import plan_reference_checklist
from app.modules.modification_planner.services.todo_status import plan_todo_status
from scripts.evaluate_generation import _block, _context, _property, _todo

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "training" / "data" / "requests.jsonl"
GENERATION_CASES = ROOT / "evaluation" / "generation_cases.jsonl"
INTENT_CASES = ROOT.parent / "docs" / "quy trình AI" / "intent_cases.jsonl"

# Pages and sentences of the evaluation sets (gp/gc, I8 in check-based-on-drafts.ts).
RESERVED_TITLES = {"hội họp tuần", "sub man", "release 2.0", "bug tracker", "ghi chú qa",
                   "công thức nấu ăn", "du lịch đà lạt", "ôn thi cuối kỳ", "trip to hanoi", "đọc sách 2026"}
# Topics of those sets: no training sentence or page may be about them.
RESERVED_WORDS = re.compile(r"\b(?:release|bug|qa|hop|phat hanh|changelog|regression|hoi quy)\b")
I8_SENTENCES = (
    "thêm checklist các bug blocker", "thêm checklist các lỗi cần sửa", "thêm mục rủi ro",
    "thêm checklist kiểm thử", "thêm checklist các việc qa còn thiếu", "thêm mục lỗi thanh toán",
    "thêm checklist kiểm tra hiệu năng", "thêm checklist các lỗi nhỏ",
)

# One page theme per entry. `items` are new checklist items (never already on
# the page), `todos` / `headers` / `texts` fill the page, `source` is another
# Page whose passages can be references.
DOMAINS: list[dict[str, Any]] = [
    {"lang": "vi", "titles": ["Tuyển dụng quý 1", "Kế hoạch tuyển dụng"],
     "headers": ["Vị trí cần tuyển", "Lịch phỏng vấn", "Ngân sách", "Ghi chú"],
     "todos": ["Đăng tin tuyển dụng", "Lọc hồ sơ ứng viên", "Gửi bài test", "Hẹn lịch phỏng vấn"],
     "texts": ["Ưu tiên ứng viên có kinh nghiệm hai năm.", "Ngân sách tuyển dụng đã được duyệt."],
     "items": ["Chuẩn bị câu hỏi phỏng vấn", "Liên hệ người tham chiếu", "Soạn thư mời nhận việc",
               "Cập nhật mô tả công việc", "Đặt lịch với trưởng nhóm", "Gửi email cảm ơn ứng viên"],
     "topics": ["phỏng vấn", "đón nhân viên mới", "tuyển dụng"],
     "db": {"name": "Ứng viên", "options": ["Mới", "Đang phỏng vấn", "Đã nhận"],
            "rows": ["Nguyễn Văn An", "Trần Thị Bình", "Lê Hoàng Cường", "Phạm Minh Đức"],
            "new_rows": ["Võ Thị Hạnh", "Đặng Quốc Huy", "Bùi Thanh Mai", "Hồ Gia Bảo"]},
     "source": {"title": "Quy trình tuyển dụng",
                "passages": ["Xác nhận nhu cầu với trưởng bộ phận", "Đăng tin trên hai kênh tuyển dụng",
                             "Phỏng vấn vòng chuyên môn trong một tuần", "Gửi phản hồi cho mọi ứng viên"]}},
    {"lang": "vi", "titles": ["Chiến dịch mùa hè", "Marketing tháng 6"],
     "headers": ["Mục tiêu", "Kênh quảng cáo", "Nội dung", "Đo lường"],
     "todos": ["Viết bài blog", "Thiết kế banner", "Lên lịch đăng bài", "Chạy quảng cáo Facebook"],
     "texts": ["Mục tiêu là tăng 20% lượt truy cập.", "Ngân sách quảng cáo tối đa 10 triệu đồng."],
     "items": ["Quay video giới thiệu", "Gửi bản tin email", "Liên hệ người có ảnh hưởng",
               "Tối ưu trang đích", "Làm khảo sát khách hàng", "Tổng hợp số liệu tuần"],
     "topics": ["quảng cáo", "nội dung mạng xã hội", "đo lường hiệu quả"],
     "db": {"name": "Nội dung", "options": ["Ý tưởng", "Đang viết", "Đã đăng"],
            "rows": ["Bài giới thiệu sản phẩm", "Video hướng dẫn", "Ảnh khuyến mãi"],
            "new_rows": ["Bài mẹo sử dụng", "Video đập hộp", "Infographic giá", "Bài phỏng vấn khách"]},
     "source": {"title": "Ý tưởng nội dung",
                "passages": ["Chuỗi bài mẹo dùng sản phẩm", "Video phỏng vấn khách hàng thân thiết",
                             "Minigame tặng quà cuối tuần", "Bài so sánh trước và sau"]}},
    {"lang": "vi", "titles": ["Học tiếng Anh", "Lộ trình IELTS"],
     "headers": ["Từ vựng", "Ngữ pháp", "Luyện nghe", "Tài liệu"],
     "todos": ["Học 20 từ mới", "Làm đề nghe số 3", "Viết một đoạn văn", "Ôn thì hiện tại hoàn thành"],
     "texts": ["Mỗi ngày dành ít nhất 45 phút.", "Thi thử vào cuối tháng."],
     "items": ["Xem một tập phim không phụ đề", "Luyện phát âm 15 phút", "Đọc một bài báo tiếng Anh",
               "Ghi âm phần nói", "Làm bài đọc hiểu", "Ôn lại từ vựng tuần trước"],
     "topics": ["luyện nói", "ôn thi", "kỹ năng đọc"],
     "db": None,
     "source": {"title": "Mẹo học ngoại ngữ",
                "passages": ["Học từ vựng theo chủ đề", "Nghe podcast khi đi đường",
                             "Tìm bạn luyện nói hằng tuần", "Viết nhật ký bằng tiếng Anh"]}},
    {"lang": "vi", "titles": ["Chuyển văn phòng", "Dọn sang văn phòng mới"],
     "headers": ["Thời gian", "Đồ đạc", "Nhà cung cấp", "Việc còn lại"],
     "todos": ["Đóng thùng tài liệu", "Thuê xe tải", "Báo địa chỉ mới cho khách", "Kiểm tra mạng internet"],
     "texts": ["Ngày chuyển dự kiến là thứ Bảy.", "Mỗi phòng ban tự đóng gói đồ của mình."],
     "items": ["Dán nhãn từng thùng", "Đặt lại chỗ ngồi", "Cập nhật địa chỉ trên website",
               "Lắp máy in", "Chụp ảnh văn phòng cũ", "Trả chìa khoá cho chủ nhà"],
     "topics": ["ngày chuyển", "sắp xếp chỗ ngồi", "thiết bị"],
     "db": {"name": "Thiết bị", "options": ["Chưa chuyển", "Đang chuyển", "Đã lắp"],
            "rows": ["Máy chiếu", "Tủ hồ sơ", "Bàn làm việc lớn"],
            "new_rows": ["Máy pha cà phê", "Bộ phát wifi", "Ghế công thái học", "Bảng trắng"]},
     "source": {"title": "Danh sách nhà cung cấp",
                "passages": ["Công ty vận chuyển Hoà Bình", "Dịch vụ lắp đặt mạng FPT",
                             "Đơn vị vệ sinh công nghiệp", "Cửa hàng nội thất văn phòng"]}},
    {"lang": "vi", "titles": ["Tập luyện sức khoẻ", "Kế hoạch giảm cân"],
     "headers": ["Lịch tập", "Dinh dưỡng", "Theo dõi", "Mục tiêu"],
     "todos": ["Chạy bộ 3 km", "Tập plank 2 phút", "Uống đủ 2 lít nước", "Ngủ trước 11 giờ"],
     "texts": ["Tập ít nhất bốn buổi mỗi tuần.", "Ghi cân nặng vào sáng Chủ nhật."],
     "items": ["Đi bộ sau bữa tối", "Chuẩn bị bữa trưa mang đi", "Giãn cơ 10 phút",
               "Đăng ký lớp yoga", "Mua giày chạy mới", "Đo vòng eo"],
     "topics": ["tập buổi sáng", "ăn uống lành mạnh", "theo dõi tiến độ"],
     "db": {"name": "Buổi tập", "options": ["Kế hoạch", "Đã tập", "Bỏ lỡ"],
            "rows": ["Chạy bộ công viên", "Bơi 30 phút", "Tập tạ chân"],
            "new_rows": ["Đạp xe 10 km", "Yoga buổi tối", "Tập bụng 15 phút", "Leo cầu thang"]},
     "source": {"title": "Thực đơn tuần",
                "passages": ["Bữa sáng yến mạch và chuối", "Bữa trưa cơm gạo lứt với cá",
                             "Bữa tối salad gà", "Ăn nhẹ bằng sữa chua"]}},
    {"lang": "vi", "titles": ["Đón nhân viên mới", "Onboarding tháng 7"],
     "headers": ["Ngày đầu tiên", "Tuần đầu", "Tài khoản", "Người hướng dẫn"],
     "todos": ["Cấp laptop", "Tạo email công ty", "Giới thiệu với nhóm", "Đọc sổ tay nhân viên"],
     "texts": ["Người hướng dẫn gặp nhân viên mới mỗi sáng.", "Hoàn thành đào tạo bắt buộc trong hai tuần."],
     "items": ["Cấp quyền phần mềm kế toán", "Đặt bữa trưa chào mừng", "Ký hợp đồng lao động",
               "Chụp ảnh thẻ nhân viên", "Hướng dẫn quy trình nghỉ phép", "Hẹn buổi gặp sau 30 ngày"],
     "topics": ["ngày đầu tiên", "tài khoản và quyền", "đào tạo"],
     "db": None,
     "source": {"title": "Sổ tay nhân viên",
                "passages": ["Giờ làm việc từ 8 giờ đến 17 giờ", "Nghỉ phép cần báo trước ba ngày",
                             "Trang phục lịch sự vào thứ Hai", "Mọi chi phí phải có hoá đơn"]}},
    {"lang": "vi", "titles": ["Tài chính gia đình", "Chi tiêu tháng 8"],
     "headers": ["Thu nhập", "Chi cố định", "Tiết kiệm", "Khoản phát sinh"],
     "todos": ["Trả tiền điện", "Đóng học phí", "Chuyển tiền tiết kiệm", "Gia hạn bảo hiểm xe"],
     "texts": ["Tiết kiệm ít nhất 15% thu nhập.", "Hạn chế ăn ngoài cuối tuần."],
     "items": ["So sánh gói cước internet", "Lập quỹ khẩn cấp", "Kiểm tra sao kê thẻ",
               "Huỷ dịch vụ không dùng", "Mua sắm theo danh sách", "Ghi lại chi tiêu hằng ngày"],
     "topics": ["tiết kiệm", "hoá đơn hằng tháng", "mua sắm"],
     "db": {"name": "Khoản chi", "options": ["Chưa trả", "Đã trả"],
            "rows": ["Tiền nhà", "Tiền nước", "Tiền internet"],
            "new_rows": ["Tiền gas", "Phí gửi xe", "Học phí tiếng Anh", "Tiền điện thoại"]},
     "source": {"title": "Mục tiêu tài chính",
                "passages": ["Mua xe máy mới trước Tết", "Đủ quỹ khẩn cấp sáu tháng",
                             "Trả hết nợ thẻ tín dụng", "Mở sổ tiết kiệm cho con"]}},
    {"lang": "vi", "titles": ["Bán hàng online", "Shop đồ handmade"],
     "headers": ["Sản phẩm", "Đơn hàng", "Vận chuyển", "Chăm sóc khách"],
     "todos": ["Chụp ảnh sản phẩm", "Cập nhật giá", "Đóng gói đơn hàng", "Trả lời tin nhắn khách"],
     "texts": ["Miễn phí giao hàng cho đơn từ 300 nghìn.", "Đơn đặt trước 15 giờ được gửi trong ngày."],
     "items": ["Viết mô tả sản phẩm mới", "Kiểm kê hàng tồn", "Tạo mã giảm giá",
               "Liên hệ đơn vị vận chuyển", "Xin đánh giá từ khách cũ", "Thiết kế thiệp cảm ơn"],
     "topics": ["đóng gói", "khuyến mãi", "chăm sóc khách hàng"],
     "db": {"name": "Đơn hàng", "options": ["Chờ xử lý", "Đang giao", "Hoàn tất"],
            "rows": ["Đơn của chị Lan", "Đơn của anh Tuấn", "Đơn sỉ quán cà phê"],
            "new_rows": ["Đơn của chị Hoa", "Đơn quà tặng công ty", "Đơn của anh Phúc", "Đơn đổi hàng"]},
     "source": {"title": "Phản hồi khách hàng",
                "passages": ["Hộp quà bị móp khi giao", "Muốn thêm màu xanh pastel",
                             "Giao hàng chậm hai ngày", "Thích thiệp viết tay"]}},
    {"lang": "en", "titles": ["Hiring pipeline", "Engineering hiring"],
     "headers": ["Open roles", "Interview loop", "Offers", "Notes"],
     "todos": ["Post the job ad", "Screen resumes", "Send take-home task", "Book onsite interviews"],
     "texts": ["Prefer candidates who can start in March.", "Every loop has one culture interview."],
     "items": ["Prepare interview questions", "Call references", "Draft the offer letter",
               "Update the job description", "Share feedback with the panel", "Send rejection emails"],
     "topics": ["interviews", "onboarding", "offers"],
     "db": {"name": "Candidates", "options": ["New", "Interviewing", "Hired"],
            "rows": ["Alex Morgan", "Priya Shah", "Diego Ruiz"],
            "new_rows": ["Mei Tanaka", "Omar Haddad", "Lena Fischer", "Sam Carter"]},
     "source": {"title": "Hiring playbook",
                "passages": ["Confirm headcount with finance", "Post on two job boards",
                             "Finish technical interviews within a week", "Reply to every candidate"]}},
    {"lang": "en", "titles": ["Fitness plan", "Marathon training"],
     "headers": ["Schedule", "Nutrition", "Progress", "Goals"],
     "todos": ["Run 5 km", "Stretch for 10 minutes", "Drink 2 liters of water", "Sleep by 11 pm"],
     "texts": ["Train at least four days a week.", "Log weight every Sunday morning."],
     "items": ["Book a physio session", "Buy new running shoes", "Plan a long run route",
               "Track heart rate zones", "Prepare post-run snacks", "Join the Saturday group run"],
     "topics": ["recovery", "long runs", "nutrition"],
     "db": {"name": "Workouts", "options": ["Planned", "Done", "Skipped"],
            "rows": ["Tempo run", "Hill repeats", "Easy recovery jog"],
            "new_rows": ["Track intervals", "Long Sunday run", "Core workout", "Bike cross-training"]},
     "source": {"title": "Coach notes",
                "passages": ["Keep easy runs truly easy", "Add strides after two runs a week",
                             "Taper for ten days before race day", "Practice race-day breakfast"]}},
]

PLACEMENTS_VI = {"end": "ở cuối trang", "after_header": "sau mục {header}", "under_header": "dưới heading {header}"}
PLACEMENTS_EN = {"end": "at the end of the page", "after_header": "after the {header} section",
                 "under_header": "under the {header} heading"}


def fold(text: str) -> str:
    text = unicodedata.normalize("NFD", text).casefold().replace("đ", "d")
    return "".join(char for char in text if unicodedata.category(char) != "Mn")


class Builder:
    def __init__(self, seed: int) -> None:
        self.random = random.Random(seed)

    def id(self) -> str:
        return str(uuid.UUID(int=self.random.getrandbits(128), version=4))

    def join(self, items: list[str], lang: str) -> str:
        last = " và " if lang == "vi" else " and "
        return items[0] if len(items) == 1 else ", ".join(items[:-1]) + last + items[-1]

    def page(self, domain: dict[str, Any], with_db: bool) -> dict[str, Any]:
        """A page of 4–10 blocks: headers, each followed by to-dos or text."""
        blocks: list[dict[str, Any]] = []
        headers = self.random.sample(domain["headers"], self.random.randint(1, 3))
        for header in headers:
            blocks.append(_block(self.id(), "HEADER", header, len(blocks)))
            if self.random.random() < 0.6:
                for todo in self.random.sample(domain["todos"], self.random.randint(1, 3)):
                    blocks.append(_todo(self.id(), todo, self.random.random() < 0.3, len(blocks)))
            else:
                blocks.append(_block(self.id(), "TEXT", self.random.choice(domain["texts"]), len(blocks)))
        databases, references = [], []
        if with_db and domain["db"]:
            db = domain["db"]
            db_id, title_id, status_id, view_id = self.id(), self.id(), self.id(), self.id()
            options = [{"id": self.id(), "name": name, "color": None, "position": str(i)}
                       for i, name in enumerate(db["options"])]
            view_block = {**_block(self.id(), "DATABASE_VIEW", "", len(blocks)), "content": None}
            blocks.append(view_block)
            title_name = "Tên" if domain["lang"] == "vi" else "Name"
            status_name = "Trạng thái" if domain["lang"] == "vi" else "Status"
            rows = [{"id": self.id(), "databaseId": db_id,
                     "values": {title_id: row, status_id: self.random.choice(options)["id"]}}
                    for row in self.random.sample(db["rows"], self.random.randint(1, len(db["rows"])))]
            databases.append({
                "id": db_id, "pageId": "page", "name": db["name"],
                "properties": [_property(title_id, title_name, "TITLE", "0"),
                               _property(status_id, status_name, "SELECT", "1", options)],
                "views": [{"id": view_id, "databaseId": db_id, "name": "Table", "type": "TABLE", "position": "0",
                           "properties": [{"propertyId": title_id, "position": "0", "visible": True, "width": None},
                                          {"propertyId": status_id, "position": "1", "visible": True, "width": None}]}],
                "rows": rows,
            })
            references.append({"blockId": view_block["id"], "databaseId": db_id, "viewId": view_id})
        context = _context(self.random.choice(domain["titles"]), blocks, databases, references)
        context["page"]["id"] = self.id()
        context["page"]["workspaceId"] = self.id()
        for database in context["databases"]:
            database["pageId"] = context["page"]["id"]
        return context

    def placement(self, context: dict[str, Any], lang: str) -> tuple[str, list[str | None] | None]:
        """Words for where to insert, and the afterBlockId values that honour them."""
        top = [b for b in context["blocks"] if b["parentBlockId"] is None]
        headers = [b for b in top if b["type"] == "HEADER"]
        kind = self.random.choice(["none", "none", "end", "after_header"])
        words = PLACEMENTS_VI if lang == "vi" else PLACEMENTS_EN
        if kind == "end":
            return " " + words["end"], [top[-1]["id"], None]
        if kind == "after_header" and headers:
            header = self.random.choice(headers)
            # "after the X section": after the last block of that section.
            section = top[top.index(header):]
            following = next((i for i, b in enumerate(section[1:], 1) if b["type"] == "HEADER"), len(section))
            last = section[following - 1]
            return " " + words["after_header"].format(header=header["content"]["text"]), [last["id"], header["id"]]
        return "", None

    def request(self, domain: dict[str, Any]) -> dict[str, Any]:
        lang = domain["lang"]
        vi = lang == "vi"
        # M8 sources are where the 4B model invents items: weighted up (kế hoạch, §1).
        kinds = ["checklist", "checklist", "checklist", "heading", "paragraph", "quote",
                 "heading_checklist", "topic_checklist", "references", "references", "references",
                 "missing_section"]
        if domain["db"]:
            kinds += ["rows", "row_status", "mixed"]
        kind = self.random.choice(kinds)
        context = self.page(domain, with_db=kind in {"rows", "row_status", "mixed"})
        existing = {fold(b["content"]["text"]) for b in context["blocks"] if isinstance(b.get("content"), dict)}
        items = [item for item in domain["items"] if fold(item) not in existing]
        chosen = self.random.sample(items, self.random.randint(2, min(4, len(items))))
        new_header = self.random.choice(
            ["Kết quả", "Việc tuần sau", "Rủi ro cần theo dõi", "Tổng kết", "Câu hỏi mở"] if vi
            else ["Summary", "Next steps", "Open questions", "Risks to watch", "Wrap-up"])
        expect: dict[str, Any] = {"status": ["PLAN_READY"], "max_operations": 1}
        references: list[dict[str, Any]] = []
        where, after = self.placement(context, lang)

        if kind == "checklist":
            topic = self.random.choice(domain["topics"] + [""])
            if vi:
                lead = self.random.choice(["thêm checklist{topic} gồm", "thêm danh sách việc{topic}:",
                                           "thêm các việc cần làm{topic}:"])
            else:
                lead = self.random.choice(["add a checklist{topic}:", "add a to-do list{topic}:",
                                           "add these tasks{topic}:"])
            topic_words = (f" {topic}" if vi else f" for {topic}") if topic else ""
            instruction = f"{lead.format(topic=topic_words)} {self.join(chosen, lang)}{where}"
            expect.update(todo_texts=chosen)
        elif kind == "heading":
            instruction = (f"thêm heading {new_header}" if vi else f"add a heading {new_header}") + where
            expect.update(block_types=["HEADER"], texts_contain=[new_header])
        elif kind in {"paragraph", "quote"}:
            text = self.random.choice([
                "Cuộc gọi tổng kết diễn ra vào chiều thứ Sáu.", "Mọi thay đổi cần báo trước một ngày.",
                "Hạn chót là ngày 15 hằng tháng.", "Người phụ trách chính là chị Thảo.",
                "Kết quả sẽ được gửi qua email cho cả nhóm.", "Ngân sách còn lại khoảng 30%.",
                "Ưu tiên những việc ảnh hưởng tới khách hàng."] if vi else [
                "The review call is on Friday afternoon.", "Report changes one day in advance.",
                "The deadline is the 15th of every month.", "Thao is the main owner.",
                "Results will be emailed to the whole team.", "About 30% of the budget is left.",
                "Customer-facing work comes first."])
            noun = ("đoạn văn" if kind == "paragraph" else "trích dẫn") if vi else ("paragraph" if kind == "paragraph" else "quote")
            instruction = (f'thêm {noun} "{text}"' if vi else f'add a {noun} "{text}"') + where
            expect.update(block_types=["TEXT" if kind == "paragraph" else "QUOTE"], texts_contain=[text])
        elif kind == "heading_checklist":
            instruction = (f"thêm heading {new_header} và checklist gồm {self.join(chosen, lang)}" if vi
                           else f"add a heading {new_header} and a checklist: {self.join(chosen, lang)}")
            expect.update(block_types=["HEADER"] + ["TODO"] * len(chosen), todo_texts=chosen)
        elif kind == "topic_checklist":
            # gp02's rule: a topic alone is one to-do, never invented items.
            topic = self.random.choice(domain["topics"])
            instruction = f"thêm checklist {topic}" if vi else f"add a checklist for {topic}"
            expect.update(max_new_blocks=1)
        elif kind == "references":
            source = domain["source"]
            passages = self.random.sample(source["passages"], self.random.randint(2, len(source["passages"])))
            # No section / heading: the rule only takes named-Page sources with headings.
            references = [{"label": f"S{i + 1}", "pageTitle": source["title"], "text": text}
                          for i, text in enumerate(passages)]
            instruction = self.random.choice(
                ["thêm checklist", "thêm danh sách việc cần làm", "thêm checklist các việc chính"] if vi
                else ["add a checklist", "add a to-do list", "add a checklist of the main points"])
            expect.update(todos_from=passages, min_todos=1)
        elif kind == "missing_section":
            # The section named is not on the page: ask instead of guessing a place.
            missing = "Phụ lục" if vi else "Appendix"
            instruction = (f"thêm checklist gồm {self.join(chosen, lang)} sau mục {missing}" if vi
                           else f"add a checklist after the {missing} section: {self.join(chosen, lang)}")
            expect = {"status": ["NEED_MORE_CONTEXT"]}
            where, after = "", None
        else:
            db = context["databases"][0]
            pool = list(domain["db"]["new_rows"])
            name = db["name"]
            if kind == "rows":
                titles = self.random.sample(pool, min(len(pool), self.random.randint(1, 3)))
                instruction = (f"thêm {len(titles)} dòng vào bảng {name}: {self.join(titles, lang)}" if vi
                               else f"add {len(titles)} row{'s' if len(titles) > 1 else ''} to the {name} table: {self.join(titles, lang)}")
                expect.update(operation_types=["CREATE_DATABASE_ROWS"], row_titles=titles)
            elif kind == "row_status":
                title = self.random.choice(pool)
                option = self.random.choice(db["properties"][1]["options"])
                instruction = (f"thêm {title} với trạng thái {option['name']} vào bảng {name}" if vi
                               else f"add {title} with status {option['name']} to the {name} table")
                expect.update(operation_types=["CREATE_DATABASE_ROWS"], row_titles=[title], row_option=option["id"])
            else:
                title = self.random.choice(pool)
                instruction = (f"thêm dòng {title} vào bảng {name} và heading {new_header}" if vi
                               else f"add a row {title} to the {name} table and a heading {new_header}")
                expect = {"status": ["PLAN_READY"], "row_titles": [title], "texts_contain": [new_header]}
            where, after = "", None

        if after is not None and kind not in {"rows", "row_status", "mixed", "missing_section"}:
            expect["after_block"] = after
        # Users often type without accents; only where no exact words must be copied.
        if kind in {"references", "topic_checklist", "missing_section"} and self.random.random() < 0.3:
            instruction = fold(instruction)
        return {
            "kind": kind, "lang": lang,
            "request": {"instruction": instruction, "context": context,
                        **({"references": references} if references else {})},
            "expect": expect,
        }


def reserved_sentences() -> set[str]:
    sentences = {fold(s) for s in I8_SENTENCES}
    for path in (GENERATION_CASES, INTENT_CASES):
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if line.strip():
                case = json.loads(line)
                sentences.add(fold(case.get("instruction") or case.get("text") or ""))
    sentences.discard("")
    return sentences


def answered_by_rules(request: ModificationPlannerRequest) -> bool:
    return any(plan(request.instruction, request.context) is not None
               for plan in (plan_todo_status, plan_block_text, plan_block_delete, plan_missing_target,
                                 plan_database_rows, plan_rows_and_blocks)) or (
        plan_reference_checklist(request.instruction, request.context.page.id, request.references) is not None) or (
        plan_explicit_content(request.instruction, request.context, request.references) is not None)


def keep(example: dict[str, Any], reserved: set[str]) -> bool:
    request = example["request"]
    instruction = fold(request["instruction"])
    title = request["context"]["page"]["title"].casefold()
    if title in RESERVED_TITLES or RESERVED_WORDS.search(instruction) or RESERVED_WORDS.search(fold(title)):
        return False
    if any(sentence in instruction or instruction in sentence for sentence in reserved if len(sentence) > 12):
        return False
    return not answered_by_rules(ModificationPlannerRequest.model_validate(request))


def generate(count: int, seed: int) -> list[dict[str, Any]]:
    builder, reserved = Builder(seed), reserved_sentences()
    examples, seen, attempts = [], set(), 0
    while len(examples) < count and attempts < count * 20:
        attempts += 1
        example = builder.request(builder.random.choice(DOMAINS))
        request = example["request"]
        # The same sentence on a different page or source is a different example.
        key = json.dumps([request["instruction"], request["context"]["page"]["title"],
                          [b["content"] for b in request["context"]["blocks"]],
                          [r["text"] for r in request.get("references", [])]], ensure_ascii=False)
        if key in seen or not keep(example, reserved):
            continue
        seen.add(key)
        examples.append({"id": f"t{len(examples) + 1:04d}", **example})
    return examples


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=700)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    examples = generate(args.count, args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in examples), encoding="utf-8")
    kinds: dict[str, int] = {}
    for example in examples:
        kinds[example["kind"]] = kinds.get(example["kind"], 0) + 1
    print(json.dumps({"written": len(examples), "output": str(args.output), "kinds": kinds}, ensure_ascii=False))


if __name__ == "__main__":
    main()
