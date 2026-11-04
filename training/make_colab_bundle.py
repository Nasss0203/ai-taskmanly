"""Zip what the Colab notebook needs (kế hoạch train Colab, bước 2).

The app code (the planner runs as-is on Colab), the scoring helpers, the
training scripts and the synthetic requests. No .env, no database, no user data.

    python -m training.make_colab_bundle
    # → training/outputs/taskmanly-train.zip, upload it to Google Drive: MyDrive/taskmanly-train/
"""

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "training" / "outputs" / "taskmanly-train.zip"
FILES = [
    "scripts/evaluate_generation.py",
    "training/__init__.py",
    "training/chat_format.py",
    "training/teacher.py",
    "training/requirements-teacher.txt",
    "training/data/requests.jsonl",
]


def bundle(output: Path = OUTPUT) -> list[str]:
    requests = ROOT / "training" / "data" / "requests.jsonl"
    if not requests.exists():
        raise SystemExit("Run `python -m training.prepare_dataset` first.")
    names = sorted(
        str(path.relative_to(ROOT)).replace("\\", "/")
        for path in (ROOT / "app").rglob("*.py")
        if "__pycache__" not in path.parts
    ) + FILES
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            path = ROOT / name
            if path.exists():
                archive.write(path, name)
            elif name == "training/__init__.py":
                archive.writestr(name, "")
    return names


if __name__ == "__main__":
    names = bundle()
    print(f"{OUTPUT} ({len(names)} files, {OUTPUT.stat().st_size // 1024} KB)")
