# M0 Intent Router — contract và phạm vi implementation

Ngày: 2026-10-21. Branch: `feat/ai-testing`.

## Quyết định Phase 2 đã ghi nhận

Tài liệu gốc nằm tại `../docs/quy trình AI/`. Đã cập nhật mục 11 của
`page-resolution-plan-v2.md`, các phần quyết định liên quan trong
`intent-detection.md` và đúng bốn case `o10`, `x04`, `x05`, `x06` của JSONL.
Riêng đợt Phase 2 giữ 139 case và 135 dòng khác nguyên trạng, `u12` vẫn
`INVALID`. Review dataset tiếp theo được ghi tại [M0_DATASET_REVIEW.md](M0_DATASET_REVIEW.md).

- Page Summary có mục tiêu trả trong chat nhưng M0 chưa có workflow an toàn:
  phân loại `OTHER`, không gọi Writing chỉ với tên Page.
- Dịch/viết lại toàn Page có thể là `MODIFY_PAGE`; execution chưa hỗ trợ.
  Writing chỉ dùng selected text hoặc inline source text.
- Không thêm UPDATE_BLOCK/DELETE_BLOCK/RENAME. Nhận diện intent không chứng
  minh operation thực thi được. Không đổi chúng thành INSERT.
- Khác capability hoặc khác Page đích: `UNCLEAR`, yêu cầu tách lệnh. Nhiều
  thao tác hỗ trợ trên cùng Page vẫn có thể là `MODIFY_PAGE`.

Viết nội dung mới, FORMAT/EXPLAIN và ngôn ngữ dịch mặc định chưa được duyệt.
Implementation trả `OTHER`/`UNCLEAR` bảo thủ cho các trường hợp này.

## HTTP contract cho NestJS tích hợp sau

`POST /internal/v1/intent` yêu cầu header `X-Internal-Service-Token` hiện có.

```json
{
  "instruction": "Tóm tắt",
  "selectedText": "Nội dung do caller chọn để xử lý.",
  "currentPageId": null
}
```

```json
{
  "result": {
    "intent": "WRITING",
    "writingAction": "SUMMARIZE",
    "language": null,
    "needsClarification": false
  },
  "provider": "deterministic",
  "model": "intent-rules-v1"
}
```

- `instruction`: bắt buộc, không blank, tối đa 4000 ký tự.
- `selectedText`: optional/null, không blank khi có, tối đa 8000 ký tự.
- `currentPageId`: optional/null, không blank khi có, tối đa 128 ký tự.
  Đây chỉ là context do caller truyền; không validate quyền hoặc resolve ID.
- Tổng object JSON compact UTF-8 tối đa 10000 bytes; raw body tối đa 65536
  bytes, nesting tối đa 13. Không truncate. Field request lạ bị từ chối.
- `intent`: CREATE_PAGE/MODIFY_PAGE/WRITING/OTHER/UNCLEAR.
- `writingAction`: IMPROVE/SHORTEN/EXPAND/SUMMARIZE/CONTINUE/TRANSLATE chỉ khi
  WRITING, còn lại null. `language` chỉ có khi TRANSLATE.
- `needsClarification` do code quyết định; luôn true với UNCLEAR, cũng true
  với MODIFY_PAGE có tham chiếu chưa rõ hoặc thiếu current Page.
- Unknown/missing model fields, ID/title/editing instruction do model trả về
  là lỗi contract, không âm thầm loại bỏ để chấp nhận phần còn lại.
- Lỗi: authentication 401, input 422, output/provider 502, unavailable 503,
  timeout 504, dùng exception handlers hiện có.

Response không chứa Page ID, tham chiếu đã resolve, execution flag hoặc draft.
Muốn trích title sau MODIFY_PAGE, NestJS vẫn dùng `/page-intent` hiện có.
PageIntentRequest chỉ thêm `currentPageId` optional/null; caller cũ giữ nguyên.

## Pipeline và bảo vệ dữ liệu

1. Luật deterministic chỉ xử lý bằng chứng rõ: tạo Page, edit Page, Writing
   có source, read-only/unsupported, thiếu thông tin và multi-command.
2. Trường hợp còn lại gọi provider mặc định hiện có, structured JSON schema
   strict gồm đúng intent/writingAction/language; prompt có few-shot examples.
   Retry một lần khi JSON không parse được; schema violation không retry.
3. Cả kết quả luật và model đều qua context validation dựa trên câu gốc:
   không bịa action, không đổi read-only thành edit, không biến create thành
   modify; Writing phải có source và action tương ứng. TRANSLATE phải có đích.

Ngôn ngữ đích hiện nhận diện tường minh: English, Vietnamese, Japanese,
Korean, French, German, Chinese, Spanish. Tên chưa nhận diện trả UNCLEAR.
Không chọn ngôn ngữ từ selected/inline text hoặc tin ngôn ngữ model tự đoán.

Selected/inline text là dữ liệu; không được cung cấp command thứ hai hoặc
ghi đè system rules. Current Page chỉ được truyền tới model bằng boolean
`hasCurrentPage`, không truyền giá trị ID. Log lỗi chỉ chứa category, provider,
model, attempt; không chứa source, raw output hoặc `str(exc)`.

Route chỉ gọi IntentService. Không gọi Writing, Composition, Page Intent,
Planner, database hoặc mutation. Các regression HTTP dùng spy để kiểm chứng.
Tám mẫu Page reference trong tài liệu có regression riêng và giữ source-backed
instruction/title grounding của Pre-M0.

## Evaluation runner

```powershell
.\.venv\Scripts\python.exe -m scripts.evaluate_intent --mode rules-only --output artifacts/intent/m0-rules-evaluation.json
.\.venv\Scripts\python.exe -m scripts.evaluate_intent --mode replay --replay path/to/responses.json
```

Replay JSON là map `case ID -> [raw response string, optional retry response]`;
không tự lấy expected label làm fake response. `--cases` chọn JSONL khác.
Case hỗ trợ `selectedText`, `currentPageId`; khi dataset chỉ có selection/open_page
boolean, runner dùng text fixture trung tính và ID sentinel, không đọc Page thật.
Case selected-text injection được kiểm chứng riêng bằng fake-provider/unit tests.

Runner giữ ID, so sánh intent/action/language; bỏ INVALID và TBD khỏi mẫu số.
Trường hợp cần LLM trong rules-only vẫn nằm trong mẫu số, ghi LLM_REQUIRED.
`reference` và optional `pageReference` được đo riêng bằng source-evidence
helper, vì response M0 không có Page reference. Không coi đây là benchmark
Page Intent qua model. Report không in câu gốc, selection, title hoặc raw output.

Baseline rules-only trước đợt dataset review tiếp theo: 139 case, eligible 138, INVALID 1
bị từ chối, TBD 0, khớp 129/138 (93.48%), 3 case cần LLM, không gọi LLM.

| Nhóm dataset | Khớp / eligible | Cần LLM |
|---|---:|---:|
| CREATE_PAGE | 22/25 | 3 |
| MODIFY_PAGE | 37/38 | 0 |
| WRITING | 33/38 | 0 |
| OTHER | 12/12 | 0 |
| UNCLEAR | 11/11 | 0 |
| MULTI | 6/6 | 0 |
| SECURITY | 8/8 | 0 |

Reference type riêng: 43/44; s04 có JSON ID injection được giữ UNRESOLVED
thay vì tin suffix. c04/c16/c17 cần model. Sáu sai khác còn lại được giữ
nguyên nhãn để review: m23 (nhiều Page → UNCLEAR theo quyết định mới);
w31/w32 (thiếu ngôn ngữ → UNCLEAR); w34 (FORMAT), w35/w36 (viết mới) → OTHER.
Ở baseline này chưa đổi sáu nhãn lịch sử. Không có false-positive CREATE/MODIFY trên
case có expected OTHER/UNCLEAR/WRITING trong lần chạy này, kể cả nhóm SECURITY.

CLI exit 1 khi chưa khớp toàn bộ; đây không phải lỗi runner. Chỉ mode `ollama`
với model thật mới có thể bật `realModelRun` và xét ngưỡng M0; rules-only/replay
luôn `m0ThresholdSatisfied=false`. Mode ollama nạp Settings thực và không bỏ
qua token validation. Chưa chạy mode này trong Phase 3.

Review nhãn theo policy hiện có đã hoàn tất sau đó: chỉ m23/w31/w32/w34/w35/w36
được cập nhật. Rules-only hiện khớp 135/138 (97.83%); ba case c04/c16/c17 vẫn
cần LLM, reference riêng vẫn 43/44. Toàn bộ actual predictions không đổi;
điểm tăng do nhãn đã nhất quán, không phải classifier/model tốt hơn.
Xem [M0_DATASET_REVIEW.md](M0_DATASET_REVIEW.md) cho bảng trước/sau và căn cứ.
Không coi kết quả rules-only là đạt chuẩn M0 real-model.

## Kiểm chứng implementation

- Baseline trước Phase 3 đã chạy lại: 415 passed.
- Test-first đã ghi nhận lỗi route/module chưa tồn tại và các reference mới
  chưa được hỗ trợ; các regression phát hiện sau được chạy fail trước khi sửa.
- Targeted Intent/Page Intent/Writing/Composition/Planner/auth/request limits:
  532 passed, 58 deselected.
- Full command `.\.venv\Scripts\python.exe -m pytest -q`: 590 passed,
  0 failed, 0 skipped; tăng 175 tests so với baseline hiện tại đã đo.
- Một Starlette/httpx deprecation warning đã có ở baseline. Không thay tooling
  hoặc dependency ngoài phạm vi để xử lý warning này.
- `git diff --check`: sạch. Repository không cấu hình lint/type-check riêng.
- HTTP tests kiểm chứng 401/422/502/503/504, strict response schema,
  auth trước service, không gọi capability khác, không đưa ID vào output,
  và không log sensitive fixture khi provider/model lỗi.
- Bốn file test mới: `test_intent_service.py`, `test_intent_http.py`,
  `test_intent_evaluation.py`, `test_m0_page_reference.py`. Mở rộng matrix
  `test_request_limits.py` để bao phủ route M0 và streamed body limits.

### File thay đổi trong Phase 3

Tạo mới năm file dưới `app/modules/intent/`: router, schemas/intent_schema,
prompts/intent_prompt, services/intent_rules, services/intent_service.
Thêm `scripts/evaluate_intent.py`, bốn file test trên và tài liệu này.
Cập nhật README, `app/api/dependencies.py`, `app/api/internal/v1/router.py`,
`app/main.py`, ba file schema/service/evidence của Page Intent,
`app/api/request_limits.py`, `app/shared/request_limits.py`,
`tests/test_request_limits.py`. Các file request limits đã untracked từ
Pre-M0 được mở rộng tại chỗ, không xóa thay đổi cũ.

Các dirty/untracked Pre-M0 khác được giữ nguyên, bao gồm `.env.example`,
config, Ollama, legacy assistant, Composition, Planner và audit/test cũ.
Không sửa source NestJS/Frontend, `.env`, secrets hoặc dữ liệu business.
Tất cả thay đổi còn unstaged/untracked; không add/commit/push/merge.

## Phần dành cho Phase 4–5

- Chưa sửa `.env` hoặc token. Phase 4 cần quyền cấu hình token đồng bộ, môi
  trường an toàn và benchmark Ollama thật; không dùng APP_ENV=test cho runtime.
- NestJS Ask cần route tới capability hiện có, xử lý clarification, chặn
  unsupported whole-Page/update/delete/rename trước Planner. Page summary
  phải báo chưa hỗ trợ khi chưa có workflow có authorization và context budget.
- NestJS giữ resolution, permissions, preview/confirm, reauthorization,
  fingerprint và transaction safety. Không dùng intent thay permission check.
- Frontend bổ sung selected-text/current-page transport và một ô nhập;
  giữ lựa chọn Page, preview, confirm/discard và history. Không auto-Apply.
- M0 end-to-end chưa hoàn thành; không triển khai M1–M9 trong thay đổi này.
