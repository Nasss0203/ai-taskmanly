"""Writes training/colab_train.ipynb (kế hoạch train Colab, bước 2–4).

Kept as code so the notebook stays reviewable in diffs and always valid JSON.

    python -m training.build_notebook
"""

import json
from pathlib import Path

OUTPUT = Path(__file__).resolve().parent / "colab_train.ipynb"


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip("\n").splitlines(keepends=True)}


def code(text: str) -> dict:
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
            "source": text.strip("\n").splitlines(keepends=True)}


CELLS = [
    md("""
# Taskmanly — fine-tune planner `qwen3:1.7b` (kế hoạch train Colab)

Kế hoạch: `docs/quy trình AI/ke-hoach-train-colab.md`. Chạy **từ trên xuống**, runtime **GPU T4**
(Runtime → Change runtime type → T4 GPU).

Trước khi chạy, trên máy: `python -m training.prepare_dataset` rồi `python -m training.make_colab_bundle`,
tải `training/outputs/taskmanly-train.zip` lên Google Drive vào thư mục **`MyDrive/taskmanly-train/`**.

Kết quả (đáp án model thầy, checkpoint, file GGUF) lưu trên Drive, nên phiên Colab bị ngắt thì chạy lại
từ đầu: các bước đã xong sẽ được bỏ qua hoặc làm tiếp.

Dữ liệu chỉ là dữ liệu sinh giả, không có dữ liệu người dùng.
"""),
    md("## 1. Chuẩn bị"),
    code("""
!nvidia-smi --query-gpu=name,memory.total --format=csv
from google.colab import drive
drive.mount('/content/drive')

import os, pathlib, zipfile
DRIVE = pathlib.Path('/content/drive/MyDrive/taskmanly-train')
WORK = pathlib.Path('/content/taskmanly')
BUNDLE = DRIVE / 'taskmanly-train.zip'
assert BUNDLE.exists(), f'Tải taskmanly-train.zip lên {DRIVE} trước'
WORK.mkdir(exist_ok=True)
zipfile.ZipFile(BUNDLE).extractall(WORK)
os.chdir(WORK)
SFT = DRIVE / 'sft.jsonl'          # đáp án model thầy (chạy tiếp được)
CHECKPOINTS = DRIVE / 'checkpoints'
print(sum(1 for _ in open(WORK / 'training/data/requests.jsonl')), 'câu hỏi giả')
"""),
    md("""
## 2. Đáp án của model thầy (`qwen3:14b` qua Ollama)

`teacher.py` chạy đúng `ModificationPlannerService` của app với model thầy và chỉ giữ ví dụ đúng.
Mỗi câu khoảng 30–60 giây trên T4: 700 câu có thể mất vài giờ — chạy lại ô cuối của phần này sẽ làm tiếp
(dựa vào `sft.log.jsonl` trên Drive). **Bỏ qua cả phần 2** nếu `sft.jsonl` đã đủ.
"""),
    code("""
# Môi trường riêng cho app (không đụng thư viện của Unsloth ở phần 3).
# Python của Colab không có ensurepip nên `python -m venv` không tạo được pip: dùng virtualenv.
!pip install -q virtualenv
!python -m virtualenv -q /content/teacher-env
!/content/teacher-env/bin/pip install -q -r training/requirements-teacher.txt
"""),
    code("""
import subprocess, time, urllib.request
# The Ollama installer needs zstd to unpack, which Colab does not ship.
!apt-get install -y -qq zstd > /dev/null
!curl -fsSL https://ollama.com/install.sh | sh
env = {**os.environ, 'OLLAMA_FLASH_ATTENTION': '1', 'OLLAMA_KV_CACHE_TYPE': 'q8_0'}
ollama = subprocess.Popen(['ollama', 'serve'], env=env, stdout=open('/content/ollama.log', 'w'), stderr=subprocess.STDOUT)
for _ in range(60):
    try:
        urllib.request.urlopen('http://localhost:11434/api/version'); break
    except Exception:
        time.sleep(1)
!ollama pull qwen3:14b
!ollama pull qwen3:1.7b
# The installer warns it cannot detect a GPU (no lspci on Colab); check Ollama really uses CUDA,
# otherwise qwen3:14b runs on CPU and the teacher step will not finish.
!grep -iE "inference compute|library=cuda|no compatible GPUs" /content/ollama.log | head -5
assert 'library=cuda' in open('/content/ollama.log').read().lower(), 'Ollama không thấy GPU: xem /content/ollama.log'
"""),
    md("""
### Kiểm tra định dạng prompt

Văn bản train (`training/chat_format.py`) phải **giống từng ký tự** chuỗi Ollama dựng cho `qwen3:1.7b`
khi app gọi với `think: false`. Ô này giải mã token Ollama thật sự dựng và so sánh.
"""),
    code("""
import json, sys
sys.path.insert(0, str(WORK))
!pip install -q transformers
from transformers import AutoTokenizer
from training.chat_format import render_prompt

tokenizer_check = AutoTokenizer.from_pretrained('Qwen/Qwen3-1.7B')
answer = json.loads(urllib.request.urlopen(urllib.request.Request(
    'http://localhost:11434/api/generate',
    data=json.dumps({'model': 'qwen3:1.7b', 'system': 'SYS LINE', 'prompt': 'USER LINE', 'think': False,
                     'stream': False, 'options': {'num_predict': 1, 'temperature': 0}}).encode(),
    headers={'Content-Type': 'application/json'})).read())
assert 'context' in answer, 'Ollama này không trả context: so định dạng bằng tay với training/chat_format.py'
rendered = tokenizer_check.decode(answer['context'])
expected = render_prompt('SYS LINE', 'USER LINE')
print(repr(rendered))
assert rendered.startswith(expected), 'Định dạng khác: KHÔNG train, báo lại chuỗi in ở trên'
print('Định dạng khớp')
"""),
    code("""
import json  # also here: the format check above may be skipped on a later session
# Chạy (hoặc chạy tiếp) model thầy. Có thể thêm --limit 100 để chạy từng đợt.
!cd {WORK} && /content/teacher-env/bin/python -m training.teacher --model qwen3:14b --requests training/data/requests.jsonl --output {SFT} --num-ctx 16384 --timeout 600
log = [json.loads(line) for line in open(SFT.with_suffix('.log.jsonl'))]
kept = sum(entry['kept'] for entry in log)
print(f'{len(log)} câu đã chạy, giữ {kept}, bỏ {len(log) - kept}')
from collections import Counter
print(Counter(entry['reason'] for entry in log if not entry['kept']).most_common(10))
"""),
    code("""
# Giải phóng GPU cho phần train.
ollama.terminate()
!pkill -f "ollama" || true
"""),
    md("""
## 3. Train QLoRA (Unsloth)

**Runtime → Restart session** trước khi chạy phần này (Unsloth cần phiên bản thư viện riêng), rồi chạy
tiếp từ ô dưới — không cần chạy lại phần 1–2.

Loss chỉ tính trên phần trả lời (JSON). Mỗi câu hỏi có 2 ví dụ (route + sinh thao tác); chia train/dev
**theo câu hỏi** để hai ví dụ của cùng một câu không nằm ở hai bên.
"""),
    code("""
from google.colab import drive
drive.mount('/content/drive')
import os, sys, pathlib
DRIVE = pathlib.Path('/content/drive/MyDrive/taskmanly-train')
WORK = pathlib.Path('/content/taskmanly')
SFT = DRIVE / 'sft.jsonl'
CHECKPOINTS = DRIVE / 'checkpoints'
os.chdir(WORK)
sys.path.insert(0, str(WORK))
assert SFT.exists(), 'Chưa có sft.jsonl: chạy phần 2 trước'
"""),
    code("""
!pip install -q unsloth
import unsloth, trl, transformers
print('unsloth', unsloth.__version__, '| trl', trl.__version__, '| transformers', transformers.__version__)
"""),
    code("""
import hashlib, json
from datasets import Dataset
from unsloth import FastLanguageModel
from training.chat_format import END, render_example

MAX_SEQ = 6144
model, tokenizer = FastLanguageModel.from_pretrained('unsloth/Qwen3-1.7B', max_seq_length=MAX_SEQ, load_in_4bit=True)

chats = [json.loads(line) for line in open(SFT)]
rows = {'train': [], 'dev': []}
too_long = 0
for chat in chats:
    example = render_example(chat)
    if tokenizer.eos_token == END:      # TRL thêm eos ở cuối: không thêm hai lần
        example['completion'] = example['completion'][:-len(END)]
    if len(tokenizer(example['prompt'] + example['completion']).input_ids) > MAX_SEQ - 8:
        too_long += 1
        continue
    request_id = chat['id'].rsplit('-', 1)[0]
    split = 'dev' if int(hashlib.sha1(request_id.encode()).hexdigest(), 16) % 10 == 0 else 'train'
    rows[split].append(example)
train_set, dev_set = Dataset.from_list(rows['train']), Dataset.from_list(rows['dev'])
print(f'train {len(train_set)} | dev {len(dev_set)} | bỏ vì quá dài {too_long} | eos {tokenizer.eos_token!r}')
"""),
    code("""
from trl import SFTConfig, SFTTrainer

model = FastLanguageModel.get_peft_model(
    model, r=16, lora_alpha=32, lora_dropout=0, bias='none',
    target_modules=['q_proj', 'k_proj', 'v_proj', 'o_proj', 'gate_proj', 'up_proj', 'down_proj'],
    use_gradient_checkpointing='unsloth', random_state=7,
)
trainer = SFTTrainer(
    model=model, processing_class=tokenizer, train_dataset=train_set, eval_dataset=dev_set,
    args=SFTConfig(
        output_dir=str(CHECKPOINTS), max_length=MAX_SEQ, completion_only_loss=True,
        per_device_train_batch_size=1, gradient_accumulation_steps=8,
        num_train_epochs=2, learning_rate=2e-4, lr_scheduler_type='cosine', warmup_ratio=0.05,
        fp16=not transformers.utils.is_torch_bf16_gpu_available(),
        bf16=transformers.utils.is_torch_bf16_gpu_available(),
        logging_steps=10, eval_strategy='epoch', save_strategy='epoch', save_total_limit=2,
        report_to='none', seed=7,
    ),
)
resume = CHECKPOINTS.exists() and any(CHECKPOINTS.glob('checkpoint-*'))
trainer.train(resume_from_checkpoint=resume or None)
print(trainer.evaluate())
"""),
    md("""
## 4. Kiểm tra nhanh trên dev rồi xuất GGUF

Đây chỉ là kiểm tra sơ bộ (JSON hợp lệ, giống đáp án model thầy). Đo thật (gp01–gp08, I8, thời gian)
làm trên máy theo T6 của kế hoạch.
"""),
    code("""
FastLanguageModel.for_inference(model)
sample = rows['dev'][:20]
valid = same = 0
for example in sample:
    inputs = tokenizer(example['prompt'], return_tensors='pt').to('cuda')
    output = model.generate(**inputs, max_new_tokens=1500, do_sample=False)
    text = tokenizer.decode(output[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
    expected = example['completion'].removesuffix(END)
    try:
        valid += 1 if json.loads(text) is not None else 0
        same += json.loads(text) == json.loads(expected)
    except json.JSONDecodeError:
        pass
print(f'JSON hợp lệ {valid}/{len(sample)} | giống đáp án model thầy {same}/{len(sample)}')
"""),
    code("""
GGUF_DIR = pathlib.Path('/content/gguf')
model.save_pretrained(str(DRIVE / 'lora-adapter'))
tokenizer.save_pretrained(str(DRIVE / 'lora-adapter'))
model.save_pretrained_gguf(str(GGUF_DIR), tokenizer, quantization_method='q4_k_m')
import shutil
gguf = max(GGUF_DIR.rglob('*.gguf'), key=lambda path: path.stat().st_mtime)
target = DRIVE / 'taskmanly-planner-1.7b-q4_k_m.gguf'
shutil.copy(gguf, target)
print(target, round(target.stat().st_size / 2**30, 2), 'GB')
"""),
    md("""
## 5. Trên máy (không chạy ở đây)

1. Tải `taskmanly-planner-1.7b-q4_k_m.gguf` từ Drive về `ai-taskmanly/training/outputs/`.
2. `python -m training.make_modelfile training/outputs/taskmanly-planner-1.7b-q4_k_m.gguf`
3. `ollama create taskmanly-planner-1.7b -f training/outputs/Modelfile`
4. Đo theo T6: `python -m scripts.evaluate_generation --capability planner --repeat 3 --planner-model taskmanly-planner-1.7b`
   và `check-based-on-drafts.ts` với model mới; chỉ đổi `.env` khi đạt.
"""),
]


def build() -> dict:
    return {
        "cells": CELLS,
        "metadata": {
            "accelerator": "GPU",
            "colab": {"gpuType": "T4", "provenance": []},
            "kernelspec": {"display_name": "Python 3", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 0,
    }


if __name__ == "__main__":
    OUTPUT.write_text(json.dumps(build(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(OUTPUT)
