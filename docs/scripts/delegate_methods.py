#!/usr/bin/env python3
"""Script to help identify methods to delegate in gui.py"""

import re
from pathlib import Path


def analyze_methods(filepath):
    """Analyze methods in gui.py and categorize them."""
    content = Path(filepath).read_text()
    lines = content.split('\n')

    methods = []
    current_method = None
    current_start = None

    for i, line in enumerate(lines, 1):
        # Detect method definition
        if re.match(r'^    def [_a-zA-Z]', line):
            if current_method:
                # Save previous method
                methods.append({
                    'name': current_method,
                    'start': current_start,
                    'end': i - 1,
                    'lines': i - current_start
                })
            # Start new method
            match = re.match(r'^    def ([_a-zA-Z][_a-zA-Z0-9]*)', line)
            if match:
                current_method = match.group(1)
                current_start = i
        # Detect end of class (next class or end of file)
        elif re.match(r'^class ', line) and current_method:
            methods.append({
                'name': current_method,
                'start': current_start,
                'end': i - 1,
                'lines': i - current_start
            })
            current_method = None

    # Handle last method
    if current_method:
        methods.append({
            'name': current_method,
            'start': current_start,
            'end': len(lines),
            'lines': len(lines) - current_start + 1
        })

    return methods

def main():
    methods = analyze_methods('src/zebtrack/ui/gui.py')

    # Filter methods by size (50-100 lines)
    medium_methods = [m for m in methods if 50 <= m['lines'] <= 100]

    # Sort by size
    medium_methods.sort(key=lambda x: x['lines'], reverse=True)

    print(f"Found {len(medium_methods)} methods between 50-100 lines:\n")

    total_lines = 0
    for m in medium_methods[:15]:  # Top 15
        print(f"{m['lines']:3d} lines: {m['name']:50s} (line {m['start']})")
        total_lines += m['lines']

    print(f"\nTotal lines in top 15: {total_lines}")

if __name__ == '__main__':
    main()
