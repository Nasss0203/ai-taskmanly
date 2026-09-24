import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
)


class QwenProvider:
    def __init__(
        self,
        model_name: str = "Qwen/Qwen3-1.7B",
    ):
        self.model_name = model_name

        print("[AI] Initializing QwenProvider...", flush=True)

        print("[AI] Loading tokenizer...", flush=True)

        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_name,
            local_files_only=True,
        )

        print("[AI] Tokenizer loaded.", flush=True)

        print("[AI] Loading model into GPU...", flush=True)

        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_name,
            torch_dtype="auto",
            device_map="auto",
            local_files_only=True,
        )

        print(
            f"[AI] Model loaded on: {self.model.device}",
            flush=True,
        )

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_new_tokens: int = 300,
    ) -> str:
        messages = [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ]

        text = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )

        inputs = self.tokenizer(
            text,
            return_tensors="pt",
        ).to(self.model.device)

        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
            )

        generated_tokens = outputs[0][
            inputs.input_ids.shape[1]:
        ]

        response = self.tokenizer.decode(
            generated_tokens,
            skip_special_tokens=True,
        )

        return response.strip()
