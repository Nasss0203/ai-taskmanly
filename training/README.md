# Fine-tune planner (kế hoạch train Colab)

Kế hoạch và tiêu chí chấp nhận: `docs/quy trình AI/ke-hoach-train-colab.md`.

| Bước | Lệnh (từ thư mục `ai-taskmanly`) | Chạy ở |
|---|---|---|
| 0. Đo trước | `python -m scripts.evaluate_generation --capability planner --repeat 3 --output training/baseline/planner-4b.json` và `be-task-management/scripts/check-based-on-drafts.ts` | máy |
| 1. Sinh câu hỏi giả | `python -m training.prepare_dataset --count 700 --seed 7` → `training/data/requests.jsonl` | máy |
| 1b. Đóng gói | `python -m training.make_colab_bundle` → tải `training/outputs/taskmanly-train.zip` lên `MyDrive/taskmanly-train/` | máy |
| 2–4. Model thầy, train, GGUF | mở `training/colab_train.ipynb` trên Colab (runtime T4), chạy từ trên xuống | Colab |
| 5. Nạp vào Ollama | tải GGUF về `training/outputs/`, `python -m training.make_modelfile training/outputs/taskmanly-planner-1.7b-q4_k_m.gguf`, `ollama create taskmanly-planner-1.7b -f training/outputs/Modelfile` | máy |
| 6. Đo sau | `python -m scripts.evaluate_generation --capability planner --repeat 3 --planner-model taskmanly-planner-1.7b` + `check-based-on-drafts.ts` | máy |

Sửa notebook: sửa `training/build_notebook.py` rồi `python -m training.build_notebook` (không sửa tay file `.ipynb`).
Định dạng văn bản train (`chat_format.py`) khớp từng ký tự chuỗi Ollama dựng cho qwen3 khi `think: false`;
notebook kiểm tra lại điều này trước khi train.

- Dữ liệu chỉ là dữ liệu sinh giả (`prepare_dataset.py`), không lấy từ database.
- Tên trang, câu lệnh và chủ đề của bộ đo (gp/gc, I8, `intent_cases.jsonl`) bị loại khỏi dữ liệu train.
- `teacher.py` chạy đúng `ModificationPlannerService` của app; chỉ giữ ví dụ mà bản nháp qua
  `check_plan` (và mọi to-do lấy từ nguồn, nếu có nguồn).
- `data/`, `baseline/`, `outputs/`, `*.gguf` không commit.

## Lọc nhãn thô (2026-11-04)

Teacher kiểm tra nhãn generation trước khi service sửa vị trí, chuyển loại block
hoặc lọc grounding: schema, semantic, `check_plan` và `extra_failures` đều phải đạt.
Plan cuối vẫn được kiểm tra. Mẫu bị loại không ghi cả hai chat route/generation;
mẫu được giữ lưu nguyên câu trả lời assistant, không đổi thành plan wrapper.

Log mới có `filter_version=raw-labels-v1`. Không tiếp tục output/log đã tạo bằng bộ
lọc cũ; lệnh từ chối trước khi ghi để giữ nguyên SFT lịch sử. Khi được phép chạy
teacher vòng mới, dùng output riêng, ví dụ `--output training/outputs/v2/sft.jsonl`.
Nếu chạy Colab, phải cập nhật bundle và đường dẫn SFT/output của phiên mới trước;
không chỉ chạy tiếp notebook cũ trên file Drive hiện có. Chưa chạy teacher/train lại.

Kiểm thử ngoại tuyến: `python -m pytest tests/test_training_dataset.py tests/test_training_raw_labels.py -q`.
Fixtures là các yêu cầu sinh giả và nhãn lỗi đã kiểm toán, không phải dữ liệu Page thật.
