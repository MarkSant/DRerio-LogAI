import re
from collections import defaultdict
from pathlib import Path


def analyze_mypy_report():
    report_path = Path("src_mypy_errors_3.txt")
    if not report_path.exists():
        print("Report file not found.")
        return

    errors_by_file = defaultdict(int)
    pattern = re.compile(r"^(.+?):\d+: error: (.+)$")

    with open(report_path, encoding="utf-8") as f:
        for line in f:
            match = pattern.match(line.strip())
            if match:
                file_path, message = match.groups()
                file_path = file_path.replace("\\", "/")
                errors_by_file[file_path] += 1

    print("\nTop Problematic Files:")
    print("-" * 40)
    for filepath, count in sorted(errors_by_file.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"{filepath} ({count})")


if __name__ == "__main__":
    analyze_mypy_report()
