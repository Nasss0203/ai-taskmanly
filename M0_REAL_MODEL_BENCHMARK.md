# Phase 4 — Real Ollama Benchmark & M0 Validation

Ngày: 2026-10-21. Branch: `feat/ai-testing`.
**Kết luận: PASS — đạt các ngưỡng benchmark real-model M0 đã định nghĩa.**
Kết luận này áp dụng cho toàn pipeline trên dataset hiện tại; M0 end-to-end
và Phase 5 chưa hoàn thành, chưa triển khai tích hợp NestJS/Frontend.

## 1. Environment

Đã kiểm tra Git, source, tests, bảy tài liệu yêu cầu và dataset hiện tại.
Không tìm thấy AGENTS.md trong repository hoặc các thư mục cha đã kiểm tra.
Các dirty/untracked Pre-M0/M0 được chụp SHA-256 trước khi sửa.

| Thành phần | Giá trị thực tế |
|---|---|
| Python trong .venv | 3.10.0 |
| Ollama CLI và runtime API | 0.40.7 |
| Model chính theo Settings local | qwen3:1.7b |
| Model so sánh đã cài | qwen3:4b-instruct |
| GPU | NVIDIA GeForce RTX 3050 Ti Laptop GPU, 4096 MiB VRAM |
| NVIDIA driver | 610.88 |
| Processor được Ollama báo cho model chính | 100% GPU, llamacpp |
| Context window cấu hình thực tế | 6144 |
| num_gpu override | null, giữ lựa chọn hiện có của Ollama |
| Timeout | 120 giây |
| Generation | think=false, temperature=0, max_new_tokens=200 |

Không xác định CPU qua CIM được vì truy vấn bị Access denied; không thay đổi
quyền hoặc hệ thống để lấy thông tin này. Model digest được lưu trong metadata
JSON để nhận diện chính xác model mỗi lượt.

### Token tạm và cách chạy

Harness local tại `artifacts/intent/phase4/run_benchmark.py` sinh token bằng
`secrets.token_urlsafe(48)` ngay trong tiến trình. Token chỉ đặt vào environment
của tiến trình đó, chạy Settings trong **development**, giữ nguyên validator.
Không dùng APP_ENV=test; không in hoặc lưu token, không truyền token literal
qua command line, không sửa .env. Environment được khôi phục trong finally.

Harness gọi đúng `scripts.evaluate_intent.main` với mode ollama và toàn dataset.
Một subclass chỉ quan sát metadata an toàn rồi delegate OllamaProvider thật;
không thay đổi request options, classification hay threshold/exit-code policy.
Chỉ lưu ID, enum labels, lỗi validation/category, timing và token counts;
không lưu source, raw output, unknown field values hoặc exception strings.

```powershell
.\.venv\Scripts\python.exe -X utf8 artifacts/intent/phase4/run_benchmark.py --mode ollama
.\.venv\Scripts\python.exe -X utf8 artifacts/intent/phase4/run_benchmark.py --mode ollama --model qwen3:4b-instruct --output artifacts/intent/phase4/qwen3-4b-final.json
```

Đã kiểm tra .env nguyên trạng và environment được khôi phục sau mọi lượt.
Đây không phải đồng bộ token giữa FastAPI và NestJS.

## 2. Baseline đã chạy lại

- Full pytest trước benchmark: **590 passed, 0 failed, 0 skipped**.
- Rules-only: **135/138 = 97.83%**, total 139, INVALID 1 rejected, TBD 0.
- LLM_REQUIRED: c04/c16/c17; mutation false positives 0; reference riêng 43/44.
- Artifact baseline: `artifacts/intent/phase4/baseline-rules-evaluation.json`.
- Báo cáo rules-only cũ không bị ghi đè. Chạy lại sau sửa vào file riêng
  `phase4/final-rules-evaluation.json` vẫn cho đúng kết quả baseline trên.

## 3. Real-model results sau sửa

Artifact chính: `artifacts/intent/m0-ollama-evaluation.json`.
Model chính **qwen3:1.7b**, thời điểm 2026-10-21 09:32:09–09:32:15 UTC.
Thời gian vòng evaluator: **6.073 giây**, không tính phần preflight môi trường.

| Chỉ số | Kết quả |
|---|---:|
| Total cases đã xét | 139 |
| Eligible | 138 |
| Correct | 138 |
| Accuracy toàn pipeline | 100% |
| INVALID / correctly rejected | 1 / 1 |
| TBD | 0 |
| LLM calls / case qua LLM | 3 / 3 |
| LLM_REQUIRED | 0 |
| Schema/provider/evaluation errors | 0 |
| Mutation false positives | 0 |
| Reference type riêng | 43/44 = 97.73% |
| realModelRun | true |
| m0ThresholdSatisfied | true |
| CLI exit code | 0 |

### Accuracy theo dataset group

Group được giữ nguyên theo JSONL, không nhóm lại theo expected intent.

| Group | Đúng / eligible | Accuracy |
|---|---:|---:|
| CREATE_PAGE | 25/25 | 100% |
| MODIFY_PAGE | 38/38 | 100% |
| WRITING | 38/38 | 100% |
| OTHER | 12/12 | 100% |
| UNCLEAR | 11/11 | 100% |
| MULTI | 6/6 | 100% |
| SECURITY | 8/8 | 100% |

### Accuracy theo expected intent — dùng xét threshold

| Expected intent | Đúng / eligible | Accuracy |
|---|---:|---:|
| CREATE_PAGE | 24/24 | 100% |
| MODIFY_PAGE | 43/43 | 100% |
| WRITING | 32/32 | 100% |
| OTHER | 17/17 | 100% |
| UNCLEAR | 22/22 | 100% |

CREATE_PAGE/MODIFY_PAGE/WRITING đều vượt 95%; INVALID bị từ chối, không có
errors/LLM_REQUIRED hoặc mutation false positives, và thực sự đã gọi Ollama.

### Phân biệt pipeline với model

135/138 request hợp lệ do deterministic rules xử lý; chỉ **3/138 = 2.17%**
qua LLM (3/139 = 2.16% nếu tính cả INVALID). Ba case LLM c04/c16/c17 đều trả
schema hợp lệ, đúng intent và qua context validation: **3/3**.
Không có retry trong lượt cuối. Không được diễn giải 100% pipeline thành
model tự phân loại đúng 139 câu. Tập LLM chỉ có ba mẫu, không đại diện cho
độ chính xác hoặc độ ổn định production. Không ép bỏ rules để tăng số mẫu LLM.

## 4. Failed cases và root cause

Không còn case sai về intent/action/language trong lượt cuối. Các lỗi trước sửa:

| Case | Expected | Trước sửa | Root cause | Xử lý / kết quả cuối |
|---|---|---|---|---|
| c04 | CREATE_PAGE, action/language null | Model chính: InvalidLLMResponseError | JSON có đúng keys nhưng field combination không hợp lệ; diagnostic ghi nhận action CONTINUE cho non-WRITING | Few-shot JSON dùng literal null; cuối cùng CREATE_PAGE hợp lệ |
| c16 | CREATE_PAGE, action/language null | Model chính: InvalidLLMResponseError | Model trả non-WRITING với action/language không null; prompt cũ chỉ minh họa nhãn dạng slash | Làm rõ semantics tạo tài liệu/kế hoạch và JSON output; cuối cùng CREATE_PAGE |
| c17 | CREATE_PAGE, action/language null | Model chính lỗi schema; model 4B trả CREATE_PAGE hợp lệ nhưng pipeline UNCLEAR | Context guard chưa nhận affirmative “lên kế hoạch”, dù đây là yêu cầu tạo artifact theo policy dataset | Bổ sung source evidence có subject và kiểm tra ngữ cảnh; cuối cùng CREATE_PAGE |

Validator từ chối các tổ hợp lỗi ở model chính là hành vi đúng. Không normalize
bỏ các field sai để chấp nhận output, không thay model mặc định, không thêm
retry schema violation hoặc nới schema nhằm che lỗi.

### Reference s04

s04 vẫn expected TITLE, helper trả UNRESOLVED khi gặp suffix JSON/Page ID
injection. Đây là fallback bảo thủ; không tin ID, không chọn Page hoặc thực
thi gì. Giữ nguyên dataset và grounding, không nới để đạt 44/44. Chỉ số này
đo helper riêng, không thuộc accuracy intent hoặc model output schema.

### Negative/security coverage

Toàn dataset và tests bao phủ read-only, multi-Page, thiếu language, FORMAT,
viết mới, whole-Page rewrite/translate, prompt injection và fabricated IDs.
Không tạo draft hoặc gọi capability thực thi trong benchmark.
Các negative đã được rules xử lý không gọi model. Các tests fake-provider
kiểm chứng model sai/hallucinated ID bị từ chối và content không lọt logs.
Dataset chỉ có selection boolean nên runner dùng selected-text fixture
trung tính; selected-text injection được kiểm chứng riêng bằng regression,
không tuyên bố đã red-team model thật trên selected content độc hại.

## 5. Model comparison

Mỗi lượt dưới đây đều xét toàn bộ 139 case, eligible 138, gọi LLM 3 lần.

| Model / revision | Pipeline đúng | CREATE theo expected intent | Errors | Threshold | CLI | Giây |
|---|---:|---:|---:|---|---:|---:|
| 1.7b — code gốc, cold | 135/138 (97.83%) | 21/24 (87.50%) | 3 | false | 1 | 26.243 |
| 1.7b — diagnostic, code gốc, warm | 135/138 (97.83%) | 21/24 (87.50%) | 3 | false | 1 | 1.248 |
| 4b-instruct — code gốc | 137/138 (99.28%) | 23/24 (95.83%) | 0 | true | 1 | 11.570 |
| 1.7b — sau sửa | 138/138 (100%) | 24/24 (100%) | 0 | true | 0 | 6.073 |
| 4b-instruct — sau sửa, cùng code | 138/138 (100%) | 24/24 (100%) | 0 | true | 0 | 11.340 |

Lượt 4B gốc minh họa sự khác nhau giữa threshold >=95% và CLI đòi 100%:
threshold true dù exit 1. c17 vẫn được sửa vì có bằng chứng lỗi context guard.

Ở revision cuối, cả hai model đều có 3/3 LLM cases đúng. Các timing có cold
load/chuyển model và cache khác nhau; không dùng bảng này kết luận throughput
hay cải thiện latency do code. Không thay routing/model mặc định vì 1.7b đã
đạt yêu cầu trên dataset. Tổng cộng 15 LLM calls trong năm lượt benchmark,
thêm một call riêng trong HTTP smoke; không nhầm với 3 calls của report chính.

Artifacts đối chiếu tại `artifacts/intent/phase4/`:
`qwen3-1.7b-initial.json`, `qwen3-1.7b-diagnostic.json`,
`qwen3-4b-original.json`, `qwen3-1.7b-final.json`, `qwen3-4b-final.json`.
Artifacts được Git ignore; report chính bổ sung benchmarkMetadata và safe
llmDiagnostics mà không sửa code evaluator hoặc API contract.

## 6. Source changes

Chỉ sửa những phần có bằng chứng từ benchmark:

1. `app/modules/intent/prompts/intent_prompt.py`: chuyển ví dụ slash labels
   thành JSON object thật; literal null và điều kiện action/language được
   nhấn mạnh, thêm ví dụ planning tổng quát. Không dùng case ID hoặc lookup
   nguyên văn dataset để quyết định output.
2. `app/modules/intent/services/intent_rules.py`: source evidence cho “lên
   kế hoạch” có subject; không nhận câu hỏi, thiếu subject hoặc target Page
   đang có thành tạo Page mới. Stage 1 vẫn chưa coi đây là deterministic
   CREATE: ba case vẫn gọi LLM. Không nâng conservative OTHER/UNCLEAR của model.
3. `tests/test_intent_service.py`: positive planning và negative question,
   missing subject, negation, existing-Page target.
4. `tests/test_intent_prompt.py`: kiểm chứng các few-shot outputs là JSON
   thực, hợp strict schema và bao phủ năm intents/sáu Writing actions.
5. `M0_REAL_MODEL_BENCHMARK.md`: báo cáo này.

Regression chạy trước sửa có 4 failures: ba planning requests bị context guard
từ chối và prompt chưa có ví dụ JSON. Negative existing-Page target bổ sung
cũng được chạy fail trước khi thêm guard. Sau sửa tất cả pass.

Không sửa schema, evaluator/exit policy, provider, Settings, default routing,
dataset/expected labels hoặc các capability khác. Harness/snapshots/smoke
chỉ ở thư mục artifacts local được ignore, không chứa token hoặc raw output.

## 7. Regression results và HTTP smoke

Sau benchmark cuối và HTTP smoke đã chạy:

- Targeted Intent, Page Intent/reference, Writing, Composition, Planner,
  request limits, auth, Ollama: **562 passed, 38 deselected**.
- Full `.\.venv\Scripts\python.exe -m pytest -q`:
  **600 passed, 0 failed, 0 skipped**. Baseline 590, thêm 10 regression cases.
- Một Starlette/httpx deprecation warning có từ baseline; không thêm tooling.
- `git diff --check`: PASS. Không có lint/type-check riêng được cấu hình.

HTTP smoke dùng ASGI TestClient trong tiến trình riêng, với Settings development
và token ngẫu nhiên trong memory, không mở TCP server hoặc dùng .env để lưu token.
Chỉ POST `/internal/v1/intent`: CREATE qua Ollama thật, MODIFY current Page,
WRITING selected text, OTHER read-only, UNCLEAR đều 200 đúng result.
Thiếu token trả 401, blank instruction trả 422. Spy xác nhận không gọi Writing,
Composition, Page Intent hoặc Planner. Không gọi endpoint mutation/Confirm/Apply.
Artifact: `artifacts/intent/phase4/http-smoke.json`.

Đã đối chiếu SHA-256 các file working-tree trước/sau để giữ dirty/untracked
cũ; chỉ ba file đã tồn tại nêu tại mục 6 thay đổi. Dataset và cả bốn tài liệu
ngoài repo giữ nguyên. Không git add/commit/push/merge hoặc thao tác Git bị cấm.
.env.example và các file Pre-M0 hiện dirty từ trước, không được sửa trong Phase 4.

## 8. Conclusion

**PASS — model chính qwen3:1.7b cùng pipeline M0 đạt mọi ngưỡng real-model
được evaluator định nghĩa trên dataset hiện tại.** Model 4B so sánh cũng PASS.
Không còn failed classification hoặc schema/provider error trong lượt cuối;
không có false-positive mutation; reference mismatch s04 được giữ bảo thủ.

Có thể chuyển sang chuẩn bị Phase 5 về mặt chất lượng classification. Trước
tích hợp liên service vẫn cần được phép cấu hình/đồng bộ token persistent hợp
lệ: token yếu hiện tại trên đĩa chưa được thay, benchmark chỉ dùng secret tạm.
Không dùng APP_ENV=test cho development runtime và không bỏ validator.

Phase 5 còn phải triển khai Ask/Frontend, gate unsupported operations, giữ
authorization/resolution/preview/confirm/fingerprint/transaction safety, và
kiểm thử E2E trong fixture an toàn. Chưa sửa NestJS/Frontend, chưa thực hiện
Phase 5, M1–M9 hoặc thao tác bất kỳ dữ liệu Page/business nào trong task này.
