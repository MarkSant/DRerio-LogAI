"""Parse coverage.xml and print per-package summary sorted by coverage."""

import xml.etree.ElementTree as ET

tree = ET.parse("coverage.xml")
root = tree.getroot()
rate = float(root.attrib.get("line-rate", "0")) * 100
print(f"Overall line coverage: {rate:.1f}%")
print()

packages = root.findall(".//package")
for p in sorted(packages, key=lambda x: float(x.attrib.get("line-rate", "0"))):
    r = float(p.attrib.get("line-rate", "0")) * 100
    name = p.attrib.get("name", "?")
    # Count lines
    classes = p.findall(".//class")
    total_lines = sum(
        int(c.attrib.get("line-count", "0")) if "line-count" in c.attrib else 0 for c in classes
    )
    print(f"  {r:5.1f}%  {name}")

print()
print("--- Lowest coverage files (< 30%) ---")
for cls in sorted(
    root.findall(".//class"),
    key=lambda x: float(x.attrib.get("line-rate", "0")),
):
    r = float(cls.attrib.get("line-rate", "0")) * 100
    if r >= 30:
        continue
    name = cls.attrib.get("filename", cls.attrib.get("name", "?"))
    print(f"  {r:5.1f}%  {name}")
