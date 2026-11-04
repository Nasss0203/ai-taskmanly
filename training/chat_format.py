"""Training text in the exact form Ollama feeds qwen3 (kế hoạch train Colab, T3).

The app calls ``/api/chat`` with one system and one user message and
``think: false``. Ollama's qwen3 template then renders the prompt below
(decoded from the ``context`` tokens of qwen3:1.7b on 2026-11-01): the system
text after a blank line, " /no_think" after the user text, and an empty think
block before the answer. The student must learn on that same string.
"""

from typing import Any

END = "<|im_end|>"


def render_prompt(system: str, user: str) -> str:
    return (
        f"<|im_start|>system\n\n{system}{END}\n"
        f"<|im_start|>user\n{user} /no_think{END}\n"
        "<|im_start|>assistant\n<think>\n\n</think>\n\n"
    )


def render_example(chat: dict[str, Any]) -> dict[str, str]:
    """Prompt and completion of one recorded call; loss goes on the completion only."""
    messages = {message["role"]: message["content"] for message in chat["messages"]}
    return {
        "prompt": render_prompt(messages["system"], messages["user"]),
        # Ollama stops at <|im_end|> (a stop word of the model).
        "completion": messages["assistant"] + END,
    }
