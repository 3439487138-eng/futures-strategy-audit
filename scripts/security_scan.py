from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".py", ".toml", ".yml", ".yaml", ".md", ".json", ".txt", ".csv", ".example"}
SECRET_ASSIGNMENT = re.compile(r"(?i)(token|api[_-]?key|secret|password)\s*[:=]\s*['\"][^'\"]{12,}['\"]")
WINDOWS_ABSOLUTE = re.compile(r"(?i)[a-z]:\\(?:users|大学文件)\\")


def main() -> None:
    failures: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in {".git", ".venv", "data"} for part in path.parts):
            continue
        if path.suffix == ".ipynb":
            failures.append(f"Notebook must not be published: {path.relative_to(ROOT)}")
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name != ".env.example":
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if SECRET_ASSIGNMENT.search(text):
            failures.append(f"Possible hard-coded credential: {path.relative_to(ROOT)}")
        if WINDOWS_ABSOLUTE.search(text):
            failures.append(f"Local absolute path: {path.relative_to(ROOT)}")
    try:
        tracked = subprocess.check_output(
            ["git", "ls-files"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).splitlines()
    except subprocess.CalledProcessError:
        tracked = []
    forbidden = [item for item in tracked if item.startswith("data/raw/") or item.startswith("data/processed/") or item.endswith(".ipynb")]
    if forbidden:
        failures.append(f"Forbidden tracked inputs: {forbidden}")
    if failures:
        raise SystemExit("\n".join(failures))
    print("Security scan passed: no notebooks, raw data, credential literals, or local paths detected")


if __name__ == "__main__":
    main()
