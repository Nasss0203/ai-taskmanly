"""Ollama Modelfile for the fine-tuned GGUF (kế hoạch train Colab, T5).

Copies the template and stop words of the local ``qwen3:1.7b`` so the new
model gets prompts exactly as the old one did (the text it was trained on,
see chat_format.py), and only points FROM at the downloaded GGUF.

    python -m training.make_modelfile training/outputs/taskmanly-planner-1.7b-q4_k_m.gguf
    ollama create taskmanly-planner-1.7b -f training/outputs/Modelfile
"""

import argparse
import subprocess
from pathlib import Path


def modelfile(base_modelfile: str, gguf: Path) -> str:
    lines = base_modelfile.splitlines()
    # Only the header comments and the one FROM line go: "# Tools" inside the
    # TEMPLATE block is part of the template.
    while lines and (lines[0].startswith("#") or not lines[0].strip()):
        lines.pop(0)
    first_from = next(i for i, line in enumerate(lines) if line.startswith("FROM "))
    kept = lines[:first_from] + lines[first_from + 1:]
    if not any(line.startswith("TEMPLATE") for line in kept):
        raise ValueError("The base Modelfile has no TEMPLATE.")
    # Relative to the Modelfile, which sits next to the GGUF: no spaces in FROM.
    return "\n".join([f"FROM ./{gguf.name}", *kept]) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gguf", type=Path)
    parser.add_argument("--base", default="qwen3:1.7b")
    args = parser.parse_args()
    if not args.gguf.exists():
        raise SystemExit(f"{args.gguf} not found")
    base = subprocess.run(["ollama", "show", args.base, "--modelfile"], check=True, capture_output=True,
                          text=True, encoding="utf-8").stdout
    output = args.gguf.parent / "Modelfile"
    output.write_text(modelfile(base, args.gguf), encoding="utf-8")
    print(f'{output} written; next: ollama create taskmanly-planner-1.7b -f "{output}"')


if __name__ == "__main__":
    main()
