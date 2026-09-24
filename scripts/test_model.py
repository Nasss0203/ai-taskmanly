import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_NAME = "Qwen/Qwen3-1.7B"

print("CUDA:", torch.cuda.is_available())

if torch.cuda.is_available():
    print("GPU:", torch.cuda.get_device_name(0))

print("Loading tokenizer...")

tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

print("Loading model...")

model = AutoModelForCausalLM.from_pretrained(
    MODEL_NAME,
    torch_dtype="auto",
    device_map="auto",
)

messages = [
    {
        "role": "system",
        "content": (
            "Bạn là AI Assistant của Taskmanly, "
            "một hệ thống quản lý công việc."
        ),
    },
    {
        "role": "user",
        "content": "Tạo một task cho chức năng đăng nhập bằng Google.",
    },
]

text = tokenizer.apply_chat_template(
    messages,
    tokenize=False,
    add_generation_prompt=True,
    enable_thinking=False,
)

inputs = tokenizer(
    text,
    return_tensors="pt",
).to(model.device)

with torch.no_grad():
    outputs = model.generate(
        **inputs,
        max_new_tokens=250,
        temperature=0.7,
        top_p=0.8,
        do_sample=True,
    )

generated_tokens = outputs[0][inputs.input_ids.shape[1]:]

response = tokenizer.decode(
    generated_tokens,
    skip_special_tokens=True,
)

print("\n==========================")
print("TASKMANLY AI RESPONSE")
print("==========================")
print(response)