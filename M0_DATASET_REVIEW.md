# M0 Dataset & Classification Review

Ngày: 2026-10-21. Repository: `ai-taskmanly`, branch `feat/ai-testing`.
Kết quả: hoàn tất review sáu nhãn; không sửa classifier, prompt, schema,
runner hoặc regression tests. Không chạy Ollama hoặc chuyển Phase 4–5.

## 1. Phạm vi và căn cứ

Đã đọc đầy đủ `quy-trinh-thuc-hien.md`, `page-resolution-plan-v2.md`,
`intent-detection.md`; kiểm tra JSONL, `M0_INTENT_ROUTER.md`, `SECURITY_AUDIT.md`,
Intent schema/rules/service, Page reference evidence và evaluation runner.
Đối chiếu các tests Intent, HTTP, evaluation, Page Intent và reference.

Source of truth là policy MVP đã phê duyệt, không phải output hiện tại:

- Plan-v2 mục 11 #4: nhiều capability hoặc khác Page đích phải tách lệnh.
- Intent-detection mục 1: OTHER gồm yêu cầu chưa hỗ trợ; UNCLEAR là thiếu
  thông tin. Writing chỉ có sáu action, không có FORMAT hoặc viết mới.
- Intent-detection mục 7: TRANSLATE thiếu language phải hỏi lại; mặc định
  ngôn ngữ chưa được phê duyệt.
- Intent-detection mục 12 và ghi nhận MVP: không ngầm thêm capability,
  FORMAT/EXPLAIN hoặc default translation language.

Đây là thống nhất kỳ vọng hiện tại của MVP. Các quyết định có bổ sung default
language, FORMAT hay viết mới trong tương lai vẫn chưa được phê duyệt.

## 2. Decision matrix

`null` là không có writing action trong contract. Execution ở đây nói về
request nguyên trạng; thiếu language không có nghĩa TRANSLATE chưa được hỗ trợ.

| Case | Intent cũ | Action cũ | Intent mới | Action mới | Execution nguyên trạng | Căn cứ / giải trình |
|---|---|---|---|---|---|---|
| m23 | MODIFY_PAGE | null | UNCLEAR | null | Chưa; cần tách lệnh | Plan-v2 §11 #4: chỉnh hai Page khác nhau; không tự chọn Page đầu |
| w31 | WRITING | TRANSLATE | UNCLEAR | null | Chưa; thiếu language | Intent-detection §7, §12: selected text đã có, target language chưa có; không đoán Việt ↔ Anh |
| w32 | WRITING | TRANSLATE | UNCLEAR | null | Chưa; thiếu language | Intent-detection §7, §12: inline source hợp lệ nhưng không có target language |
| w34 | WRITING | IMPROVE | OTHER | null | Không hỗ trợ FORMAT | Intent-detection §1, §12: không có FORMAT, chưa duyệt map sang IMPROVE; không phải thiếu selection |
| w35 | WRITING | null | OTHER | null | Không hỗ trợ viết mới | Intent-detection §1, §8, §12: tạo đoạn giới thiệu không thuộc sáu action; không thay bằng EXPAND/CONTINUE |
| w36 | WRITING | null | OTHER | null | Không hỗ trợ viết mới | Intent-detection §1, §12: tạo email không có action tương ứng; không ngầm tạo Page |

Cả sáu case có đủ căn cứ cập nhật. Không có case mơ hồ phải giữ nhãn cũ trong
nhóm sáu case này. Note đã ghi lý do theo policy thay cho lựa chọn lịch sử.

## 3. Những gì được giữ nguyên

- Dataset có đúng 139 case, 139 ID duy nhất, thứ tự không đổi.
- Chỉ sửa các field `intent`, `action`, `note` của sáu case trên. Một số action
  đã là null được giữ nguyên. Không thêm hoặc xóa field của bất kỳ case nào.
- Tất cả `id`, `text`, `selection`, `open_page`, `group`, `reference`,
  `language` và metadata khác giữ nguyên.
- 133 dòng ngoài phạm vi giữ nguyên từng byte, kể cả line endings.
- `u12=INVALID` và toàn bộ bốn dòng `o10`, `x04`, `x05`, `x06` giữ nguyên.
- m20/m21/m22 và x05/x06 giữ MODIFY_PAGE: intent chỉnh Page không đồng nghĩa
  execution đã hỗ trợ. Không chuyển update/delete/rename/rewrite/translate
  toàn Page thành OTHER hoặc giả lập bằng INSERT.
- s04 giữ expected reference TITLE. Helper vẫn trả UNRESOLVED khi có suffix
  JSON ID injection: bảo thủ, không tin ID. Không chỉnh case ngoài phạm vi
  hoặc nới evidence để tăng điểm reference.

## 4. Kiểm tra source và regression coverage

Không phát hiện lỗi classifier đối với sáu request đang review. Rules xử lý
multi-command, language và unsupported capability đã phù hợp policy trước khi
đổi dataset. Schema cấm action ở intent khác WRITING, nên nhãn mới dùng null.
Context validation dùng câu gốc, bảo vệ read-only và không tin Page ID model.

Runner tính đúng cả intent và action, kiểm language khi expected có giá trị;
INVALID/TBD loại khỏi mẫu số. LLM_REQUIRED vẫn nằm trong mẫu số và không khớp.
Reference là chỉ số riêng từ deterministic helper, không phải output M0 hay
độ chính xác Page Intent qua LLM. Group được giữ như category gốc của dataset,
không phải nhóm lại theo expected intent sau review; runner còn có `byIntent`.

Existing regression tests bao phủ multi-Page, thiếu ngôn ngữ, FORMAT/EXPLAIN,
viết email, Page edit chưa hỗ trợ, read-only, prompt injection và bịa Page ID.
Evaluation thực tế kiểm chứng cả sáu câu chính xác trong dataset. Không sửa
source hoặc test expectations và không thêm tests chỉ để lặp lại nhãn mới.

## 5. Baseline và kết quả sau review

Đã chạy lại baseline trước thay đổi: full pytest 590 passed, rules-only
129/138 (93.48%), đúng với kết quả lịch sử. Sau đổi nhãn:

| Chỉ số | Trước | Sau |
|---|---:|---:|
| Total | 139 | 139 |
| Eligible | 138 | 138 |
| Correct | 129 | 135 |
| Accuracy rules-only | 93.48% | 97.83% |
| INVALID / rejected | 1 / 1 | 1 / 1 |
| TBD | 0 | 0 |
| LLM_REQUIRED | 3 | 3 |
| LLM calls | 0 | 0 |
| Mutation false positives | 0 | 0 |
| Evaluation errors | 0 | 0 |
| Reference type riêng | 43/44 (97.73%) | 43/44 (97.73%) |

| Group dataset (không đổi group) | Trước | Sau |
|---|---:|---:|
| CREATE_PAGE | 22/25 (88.00%) | 22/25 (88.00%) |
| MODIFY_PAGE | 37/38 (97.37%) | 38/38 (100%) |
| WRITING | 33/38 (86.84%) | 38/38 (100%) |
| OTHER | 12/12 (100%) | 12/12 (100%) |
| UNCLEAR | 11/11 (100%) | 11/11 (100%) |
| MULTI | 6/6 (100%) | 6/6 (100%) |
| SECURITY | 8/8 (100%) | 8/8 (100%) |

Mức tăng **6 case / 4.35 điểm phần trăm** hoàn toàn do expected labels đã
phù hợp policy. Đã so sánh toàn bộ 139 outcomes trước/sau: actual intent,
action, language, clarification, deterministic/LLM path và reference output
không đổi. Hash source, prompt, schema, runner và tests cũng không đổi.
Không có bằng chứng model hay thuật toán đã tốt hơn qua thay đổi này.

Lệnh evaluation:

```powershell
.\.venv\Scripts\python.exe -m scripts.evaluate_intent --mode rules-only --output artifacts/intent/m0-rules-evaluation.json
```

Runner vẫn exit **1** vì c04/c16/c17 cần LLM, chưa khớp toàn bộ eligible cases.
Đây là hành vi thiết kế, không phải runner crash. Các case này vẫn nằm trong
mẫu số. Chưa chạy Ollama: `realModelRun=false`, `m0ThresholdSatisfied=false`.
Không dùng 97.83% rules-only để tuyên bố đạt ngưỡng M0 real-model 95%.

Artifacts local, được Git ignore:

- `artifacts/intent/dataset-review/before-evaluation.json`: baseline đã đo.
- `artifacts/intent/m0-rules-evaluation.json`: kết quả sau review.
- `artifacts/intent/dataset-review/`: snapshot tài liệu/dataset trước review,
  SHA-256 working-tree, bảng nhãn, patch và kiểm tra bảo toàn phạm vi.

### Tests và kiểm tra diff

- Targeted Intent/service/HTTP/evaluation/Page Intent/reference: **297 passed**.
- Full `.\.venv\Scripts\python.exe -m pytest -q`: **590 passed, 0 failed,
  0 skipped**, cả trước và sau review.
- Còn một Starlette/httpx deprecation warning có từ baseline.
- `git diff --check`: PASS; kiểm tra whitespace patch tài liệu riêng PASS.
- Không có lint/type-check riêng được cấu hình; không thêm tooling.

## 6. File thay đổi và Git

Chỉ thay đổi tài liệu/dataset:

1. `../docs/quy trình AI/intent_cases.jsonl`: sáu case đã nêu.
2. `../docs/quy trình AI/intent-detection.md`: ghi rõ kỳ vọng MVP và phân biệt
   review mới với bốn nhãn đã sửa ở Phase 2.
3. `../docs/quy trình AI/page-resolution-plan-v2.md`: ghi chú cách diễn giải
   nhãn theo các quyết định hiện có.
4. `M0_INTENT_ROUTER.md`: giữ kết quả cũ dưới nhãn baseline, liên kết review mới.
5. `M0_DATASET_REVIEW.md`: báo cáo này.

Thư mục docs không thuộc Git repository hiện tại. Các file đã có modified/
untracked trong ai-taskmanly được bảo toàn; ngoài tài liệu M0 vừa cập nhật,
hash tất cả file đã tồn tại trong working-tree không đổi so với lúc bắt đầu.
Tất cả thay đổi còn unstaged/untracked, không git add/commit/push/merge hoặc
thao tác Git bị cấm khác. Không chỉnh NestJS, Frontend, `.env`, secrets,
permission, executor hoặc dữ liệu business.

## 7. Remaining risks và bước tiếp theo

- c04/c16/c17 cần LLM; benchmark thật còn phải đo lại toàn pipeline, không
  chỉ ba case này. Không có kết quả real-model trong task này.
- s04 còn khác reference expectation, giữ nguyên theo phạm vi. Cần review
  riêng nếu muốn thay đổi policy xử lý suffix JSON/explicit title.
- Default translation language, FORMAT/EXPLAIN, action viết mới vẫn chưa
  được phê duyệt; fallback hiện tại không phải phê duyệt capability mới.
- Whole-Page summary/translation/rewrite và update/delete/rename chưa có
  execution workflow tương ứng; NestJS Ask sau này phải gate trước Planner.
- Dataset đã nhất quán cho sáu case, sẵn sàng làm đầu vào Phase 4 sau khi
  được cho phép cấu hình token an toàn. Phase 4–5 và M0 end-to-end chưa làm
  trong task này; không cập nhật `.env` hoặc chạy benchmark Ollama ở đây.
