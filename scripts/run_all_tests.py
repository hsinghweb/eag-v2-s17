import os
import sys
import subprocess
from pathlib import Path


def iter_test_files(root: Path) -> list[Path]:
    scripts = sorted((root / "scripts").glob("test_*.py"))
    tests = sorted((root / "tests").glob("*.py"))
    return scripts + tests


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    test_files = iter_test_files(repo_root)
    if not test_files:
        print("No test scripts found.")
        return 1

    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")

    overall_rc = 0
    for test_file in test_files:
        rel = test_file.relative_to(repo_root)
        print(f"\n=== Running {rel} ===")
        result = subprocess.run(
            [sys.executable, str(test_file)],
            cwd=str(repo_root),
            env=env,
        )
        if result.returncode != 0:
            overall_rc = result.returncode
            print(f"--- {rel} failed with exit code {result.returncode} ---")

    return overall_rc


if __name__ == "__main__":
    raise SystemExit(main())
