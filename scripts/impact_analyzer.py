#!/usr/bin/env python3
"""
Impact Analyzer for ZebTrack-AI

A tool to analyze the impact of code changes by tracing dependencies,
event subscriptions, and DI injection chains.

Usage:
    python scripts/impact_analyzer.py file <filepath>
    python scripts/impact_analyzer.py class <classname>
    python scripts/impact_analyzer.py function <funcname>
    python scripts/impact_analyzer.py event <eventname>
    python scripts/impact_analyzer.py settings <setting_path>
    python scripts/impact_analyzer.py di
    python scripts/impact_analyzer.py graph [--output <file.dot>]

Examples:
    python scripts/impact_analyzer.py file src/zebtrack/core/project_manager.py
    python scripts/impact_analyzer.py class ProcessingCoordinator
    python scripts/impact_analyzer.py event VIDEO_ANALYZE_SINGLE
    python scripts/impact_analyzer.py settings behavioral_analysis.perspective
"""

import argparse
import ast
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

# Project root detection
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
SRC_DIR = PROJECT_ROOT / "src" / "zebtrack"


@dataclass
class ImpactResult:
    """Result of an impact analysis."""

    target: str
    target_type: str
    direct_dependents: list[str] = field(default_factory=list)
    indirect_dependents: list[str] = field(default_factory=list)
    event_publishers: list[str] = field(default_factory=list)
    event_subscribers: list[str] = field(default_factory=list)
    di_consumers: list[str] = field(default_factory=list)
    serialization_chain: list[str] = field(default_factory=list)
    test_files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_report(self) -> str:
        """Generate a human-readable report."""
        lines = [
            f"\n{'=' * 70}",
            f"IMPACT ANALYSIS: {self.target_type.upper()} '{self.target}'",
            f"{'=' * 70}\n",
        ]

        if self.direct_dependents:
            lines.append("📦 DIRECT DEPENDENTS (files that import/use this):")
            for dep in sorted(set(self.direct_dependents)):
                lines.append(f"   └── {dep}")
            lines.append("")

        if self.indirect_dependents:
            lines.append("🔗 INDIRECT DEPENDENTS (transitive dependencies):")
            for dep in sorted(set(self.indirect_dependents))[:20]:
                lines.append(f"   └── {dep}")
            if len(self.indirect_dependents) > 20:
                lines.append(f"   ... and {len(self.indirect_dependents) - 20} more")
            lines.append("")

        if self.event_publishers:
            lines.append("📤 EVENT PUBLISHERS (files that emit this event):")
            for pub in sorted(set(self.event_publishers)):
                lines.append(f"   └── {pub}")
            lines.append("")

        if self.event_subscribers:
            lines.append("📥 EVENT SUBSCRIBERS (files that handle this event):")
            for sub in sorted(set(self.event_subscribers)):
                lines.append(f"   └── {sub}")
            lines.append("")

        if self.di_consumers:
            lines.append("💉 DI CONSUMERS (services receiving this via constructor):")
            for consumer in sorted(set(self.di_consumers)):
                lines.append(f"   └── {consumer}")
            lines.append("")

        if self.serialization_chain:
            lines.append("🔄 SERIALIZATION CHAIN:")
            for step in self.serialization_chain:
                lines.append(f"   └── {step}")
            lines.append("")

        if self.test_files:
            lines.append("🧪 RELATED TEST FILES:")
            for test in sorted(set(self.test_files)):
                lines.append(f"   └── {test}")
            lines.append("")

        if self.warnings:
            lines.append("⚠️  WARNINGS:")
            for warn in self.warnings:
                lines.append(f"   └── {warn}")
            lines.append("")

        # Summary
        total_affected = len(
            set(
                self.direct_dependents
                + self.event_publishers
                + self.event_subscribers
                + self.di_consumers
            )
        )
        lines.append(f"📊 SUMMARY: {total_affected} files directly affected")
        lines.append("")

        # Recommended tests
        lines.append("🧪 RECOMMENDED TEST COMMANDS:")
        if self.test_files:
            test_paths = " ".join(self.test_files[:5])
            lines.append(f"   pytest {test_paths} -v")

        # Domain detection
        domains = self._detect_domains()
        if "gui" in domains:
            lines.append("   pytest -m gui -n0  # GUI tests (sequential)")
        if "multi_aquarium" in domains:
            lines.append('   pytest -k "multi_aquarium or partitioned"')
        if "processing" in domains:
            lines.append("   pytest tests/test_processing*.py tests/test_recorder.py")
        if "event" in domains:
            lines.append("   pytest tests/test_event*.py tests/coordinators/")

        lines.append("")
        return "\n".join(lines)

    def _detect_domains(self) -> set[str]:
        """Detect which domains are affected."""
        domains = set()
        all_files = (
            self.direct_dependents
            + self.event_publishers
            + self.event_subscribers
            + self.di_consumers
        )
        for f in all_files:
            f_lower = f.lower()
            if "gui" in f_lower or "widget" in f_lower or "dialog" in f_lower:
                domains.add("gui")
            if "multi" in f_lower and "aquarium" in f_lower:
                domains.add("multi_aquarium")
            if "process" in f_lower or "worker" in f_lower or "recorder" in f_lower:
                domains.add("processing")
            if "event" in f_lower or "coordinator" in f_lower:
                domains.add("event")
        return domains


class ImportVisitor(ast.NodeVisitor):
    """AST visitor to extract imports from a Python file."""

    def __init__(self):
        self.imports: list[str] = []
        self.from_imports: dict[str, list[str]] = defaultdict(list)

    def visit_Import(self, node):
        for alias in node.names:
            self.imports.append(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module:
            for alias in node.names:
                self.from_imports[node.module].append(alias.name)
        self.generic_visit(node)


class ClassVisitor(ast.NodeVisitor):
    """AST visitor to extract class definitions and their dependencies."""

    def __init__(self):
        self.classes: dict[str, dict] = {}
        self.current_class = None

    def visit_ClassDef(self, node):
        class_info = {
            "name": node.name,
            "bases": [self._get_name(b) for b in node.bases],
            "methods": [],
            "init_params": [],
            "decorators": [self._get_name(d) for d in node.decorator_list],
        }

        # Find __init__ parameters (DI injection)
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                class_info["methods"].append(item.name)
                if item.name == "__init__":
                    for arg in item.args.args:
                        if arg.arg != "self":
                            class_info["init_params"].append(arg.arg)

        self.classes[node.name] = class_info
        self.generic_visit(node)

    def _get_name(self, node) -> str:
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._get_name(node.value)}.{node.attr}"
        elif isinstance(node, ast.Call):
            return self._get_name(node.func)
        return str(node)


class EventVisitor(ast.NodeVisitor):
    """AST visitor to find event publish/subscribe patterns."""

    def __init__(self):
        self.publishes: list[tuple[str, int]] = []  # (event_name, line)
        self.subscribes: list[tuple[str, int]] = []  # (event_name, line)

    def visit_Call(self, node):
        # Check for publish patterns
        if isinstance(node.func, ast.Attribute):
            method_name = node.func.attr
            if method_name in ("publish", "publish_event", "emit"):
                event_name = self._extract_event_name(node.args)
                if event_name:
                    self.publishes.append((event_name, node.lineno))
            elif method_name in ("subscribe", "on", "add_listener"):
                event_name = self._extract_event_name(node.args)
                if event_name:
                    self.subscribes.append((event_name, node.lineno))
        self.generic_visit(node)

    def _extract_event_name(self, args) -> str | None:
        if not args:
            return None
        arg = args[0]
        if isinstance(arg, ast.Constant):
            return str(arg.value)
        elif isinstance(arg, ast.Attribute):
            return f"{self._get_attr_chain(arg)}"
        elif isinstance(arg, ast.Name):
            return arg.id
        return None

    def _get_attr_chain(self, node) -> str:
        if isinstance(node, ast.Attribute):
            parent = self._get_attr_chain(node.value)
            return f"{parent}.{node.attr}" if parent else node.attr
        elif isinstance(node, ast.Name):
            return node.id
        return ""


class ImpactAnalyzer:
    """Main analyzer class for tracing code impact."""

    def __init__(self, src_dir: Path = SRC_DIR, project_root: Path = PROJECT_ROOT):
        self.src_dir = src_dir
        self.project_root = project_root
        self.file_cache: dict[str, str] = {}
        self.ast_cache: dict[str, ast.AST] = {}
        self.import_graph: dict[str, set[str]] = defaultdict(set)
        self.reverse_import_graph: dict[str, set[str]] = defaultdict(set)
        self._build_import_graph()

    def _get_all_python_files(self) -> list[Path]:
        """Get all Python files in the source directory."""
        files = []
        for root, dirs, filenames in os.walk(self.src_dir):
            # Skip __pycache__ and test directories
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for filename in filenames:
                if filename.endswith(".py"):
                    files.append(Path(root) / filename)
        return files

    def _get_all_test_files(self) -> list[Path]:
        """Get all test files."""
        test_dir = self.project_root / "tests"
        if not test_dir.exists():
            return []
        files = []
        for root, dirs, filenames in os.walk(test_dir):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for filename in filenames:
                if filename.endswith(".py") and filename.startswith("test_"):
                    files.append(Path(root) / filename)
        return files

    def _read_file(self, path: Path) -> str | None:
        """Read and cache file contents."""
        str_path = str(path)
        if str_path not in self.file_cache:
            try:
                with open(path, encoding="utf-8", errors="ignore") as f:
                    self.file_cache[str_path] = f.read()
            except Exception:
                return None
        return self.file_cache.get(str_path)

    def _parse_file(self, path: Path) -> ast.AST | None:
        """Parse and cache AST for a file."""
        str_path = str(path)
        if str_path not in self.ast_cache:
            content = self._read_file(path)
            if content:
                try:
                    self.ast_cache[str_path] = ast.parse(content)
                except SyntaxError:
                    return None
        return self.ast_cache.get(str_path)

    def _build_import_graph(self):
        """Build the import dependency graph."""
        for file_path in self._get_all_python_files():
            tree = self._parse_file(file_path)
            if not tree:
                continue

            visitor = ImportVisitor()
            visitor.visit(tree)

            rel_path = str(file_path.relative_to(self.project_root))

            # Process imports
            for imp in visitor.imports:
                if imp.startswith("zebtrack"):
                    self.import_graph[rel_path].add(imp)
                    self.reverse_import_graph[imp].add(rel_path)

            for module, names in visitor.from_imports.items():
                if module.startswith("zebtrack"):
                    self.import_graph[rel_path].add(module)
                    self.reverse_import_graph[module].add(rel_path)

    def _module_to_path(self, module: str) -> str | None:
        """Convert module name to file path."""
        parts = module.replace("zebtrack.", "").split(".")
        potential_path = self.src_dir / "/".join(parts)

        # Try as file
        if (potential_path.parent / f"{potential_path.name}.py").exists():
            return str(
                (potential_path.parent / f"{potential_path.name}.py").relative_to(self.project_root)
            )

        # Try as package
        if (potential_path / "__init__.py").exists():
            return str((potential_path / "__init__.py").relative_to(self.project_root))

        return None

    def _relative_path(self, path: Path) -> str:
        """Get path relative to project root."""
        try:
            return str(path.relative_to(self.project_root))
        except ValueError:
            return str(path)

    def analyze_file(self, file_path: str) -> ImpactResult:
        """Analyze the impact of changing a file."""
        path = Path(file_path)
        if not path.is_absolute():
            path = self.project_root / path

        result = ImpactResult(target=self._relative_path(path), target_type="file")

        # Find files that import this module
        module_name = self._path_to_module(path)
        if module_name:
            for importer, modules in self.import_graph.items():
                for mod in modules:
                    if mod == module_name or mod.startswith(f"{module_name}."):
                        result.direct_dependents.append(importer)

        # Parse the file for classes and events
        tree = self._parse_file(path)
        if tree:
            # Find events
            event_visitor = EventVisitor()
            event_visitor.visit(tree)

            for event, line in event_visitor.publishes:
                result.event_publishers.append(
                    f"{self._relative_path(path)}:{line} publishes {event}"
                )

            for event, line in event_visitor.subscribes:
                result.event_subscribers.append(
                    f"{self._relative_path(path)}:{line} subscribes {event}"
                )

            # Find classes
            class_visitor = ClassVisitor()
            class_visitor.visit(tree)

            for class_name, info in class_visitor.classes.items():
                if info["init_params"]:
                    result.di_consumers.append(
                        f"{class_name}.__init__ receives: {', '.join(info['init_params'])}"
                    )

        # Find related tests
        result.test_files = self._find_related_tests(path)

        return result

    def _path_to_module(self, path: Path) -> str | None:
        """Convert file path to module name."""
        try:
            rel = path.relative_to(self.src_dir.parent)
            parts = list(rel.parts)
            if parts[-1] == "__init__.py":
                parts = parts[:-1]
            elif parts[-1].endswith(".py"):
                parts[-1] = parts[-1][:-3]
            return ".".join(parts)
        except ValueError:
            return None

    def analyze_class(self, class_name: str) -> ImpactResult:
        """Analyze the impact of changing a class."""
        result = ImpactResult(target=class_name, target_type="class")

        # Find all files that reference this class
        pattern = re.compile(rf"\b{class_name}\b")

        for file_path in self._get_all_python_files():
            content = self._read_file(file_path)
            if content and pattern.search(content):
                rel_path = self._relative_path(file_path)

                # Check if it's definition or usage
                tree = self._parse_file(file_path)
                if tree:
                    class_visitor = ClassVisitor()
                    class_visitor.visit(tree)

                    if class_name in class_visitor.classes:
                        info = class_visitor.classes[class_name]
                        if info["init_params"]:
                            result.di_consumers.append(
                                f"DEFINITION: {rel_path} - __init__({', '.join(info['init_params'])})"
                            )
                    else:
                        result.direct_dependents.append(rel_path)

        # Find related tests
        result.test_files = self._find_tests_for_class(class_name)

        return result

    def analyze_function(self, func_name: str) -> ImpactResult:
        """Analyze the impact of changing a function."""
        result = ImpactResult(target=func_name, target_type="function")

        pattern = re.compile(rf"\b{func_name}\b")

        for file_path in self._get_all_python_files():
            content = self._read_file(file_path)
            if content and pattern.search(content):
                rel_path = self._relative_path(file_path)
                result.direct_dependents.append(rel_path)

        # Find tests
        for test_file in self._get_all_test_files():
            content = self._read_file(test_file)
            if content and pattern.search(content):
                result.test_files.append(self._relative_path(test_file))

        return result

    def analyze_event(self, event_name: str) -> ImpactResult:
        """Analyze the impact of an event."""
        result = ImpactResult(target=event_name, target_type="event")

        # Search for the event in all files
        patterns = [
            re.compile(rf"Events\.{event_name}\b"),
            re.compile(rf"'{event_name}'"),
            re.compile(rf'"{event_name}"'),
            re.compile(rf"UIEvents\.{event_name}\b"),
        ]

        for file_path in self._get_all_python_files():
            content = self._read_file(file_path)
            if not content:
                continue

            for pattern in patterns:
                if pattern.search(content):
                    rel_path = self._relative_path(file_path)

                    # Parse to find if it's publish or subscribe
                    tree = self._parse_file(file_path)
                    if tree:
                        visitor = EventVisitor()
                        visitor.visit(tree)

                        for event, line in visitor.publishes:
                            if event_name in event:
                                result.event_publishers.append(f"{rel_path}:{line}")

                        for event, line in visitor.subscribes:
                            if event_name in event:
                                result.event_subscribers.append(f"{rel_path}:{line}")

                    break

        # Check SYSTEM_INTEGRATION_MAP for documentation
        sim_path = self.project_root / "docs" / "architecture" / "SYSTEM_INTEGRATION_MAP.md"
        if sim_path.exists():
            content = self._read_file(sim_path)
            if content and event_name in content:
                result.warnings.append(
                    "Event is documented in SYSTEM_INTEGRATION_MAP.md - update if payload changes"
                )

        return result

    def analyze_settings(self, setting_path: str) -> ImpactResult:
        """Analyze the impact of a settings change."""
        result = ImpactResult(target=setting_path, target_type="settings")

        # Search for settings usage
        patterns = [
            re.compile(rf"settings\.{setting_path.replace('.', r'\.')}\b"),
            re.compile(rf"settings_obj\.{setting_path.replace('.', r'\.')}\b"),
            re.compile(rf'"{setting_path}"'),
            re.compile(rf"'{setting_path}'"),
        ]

        for file_path in self._get_all_python_files():
            content = self._read_file(file_path)
            if not content:
                continue

            for pattern in patterns:
                if pattern.search(content):
                    rel_path = self._relative_path(file_path)
                    result.di_consumers.append(rel_path)
                    break

        # Check if defined in settings.py
        settings_path = self.src_dir / "settings.py"
        settings_content = self._read_file(settings_path)
        if settings_content:
            first_part = setting_path.split(".")[0]
            if first_part not in settings_content:
                result.warnings.append(f"Setting '{first_part}' may not be defined in settings.py")

        # Check config.yaml
        config_path = self.project_root / "config.yaml"
        config_content = self._read_file(config_path)
        if config_content:
            if setting_path.split(".")[0] not in config_content:
                result.warnings.append("Setting may not have default in config.yaml")

        return result

    def analyze_di(self) -> ImpactResult:
        """Analyze the dependency injection chain."""
        result = ImpactResult(target="Composition Root", target_type="di")

        main_path = self.src_dir / "__main__.py"
        content = self._read_file(main_path)

        if content:
            # Find all service instantiations
            pattern = re.compile(r"(\w+)\s*=\s*(\w+)\(")
            for match in pattern.finditer(content):
                var_name, class_name = match.groups()
                result.di_consumers.append(f"{var_name} = {class_name}(...)")

            # Find settings_obj injections
            settings_pattern = re.compile(r"settings_obj\s*=\s*(\w+)")
            for match in settings_pattern.finditer(content):
                result.serialization_chain.append(f"settings_obj injection: {match.group(0)}")

        # Find all classes that accept settings_obj
        for file_path in self._get_all_python_files():
            tree = self._parse_file(file_path)
            if not tree:
                continue

            visitor = ClassVisitor()
            visitor.visit(tree)

            for class_name, info in visitor.classes.items():
                if "settings_obj" in info["init_params"]:
                    rel_path = self._relative_path(file_path)
                    result.di_consumers.append(f"{class_name} accepts settings_obj ({rel_path})")

        return result

    def generate_graph(self) -> str:
        """Generate a DOT format dependency graph."""
        lines = ["digraph Dependencies {", "  rankdir=LR;", "  node [shape=box];"]

        # Add nodes and edges from import graph
        seen_edges = set()
        for importer, modules in self.import_graph.items():
            importer_short = Path(importer).stem
            for module in modules:
                module_short = module.split(".")[-1]
                edge = (importer_short, module_short)
                if edge not in seen_edges:
                    lines.append(f'  "{importer_short}" -> "{module_short}";')
                    seen_edges.add(edge)

        lines.append("}")
        return "\n".join(lines)

    def _find_related_tests(self, file_path: Path) -> list[str]:
        """Find test files related to a source file."""
        tests = []
        stem = file_path.stem

        for test_file in self._get_all_test_files():
            test_content = self._read_file(test_file)
            if test_content:
                # Check if the test imports or mentions the file
                if stem in test_content or str(file_path.name) in test_content:
                    tests.append(self._relative_path(test_file))

        return tests

    def _find_tests_for_class(self, class_name: str) -> list[str]:
        """Find test files that test a specific class."""
        tests = []
        pattern = re.compile(rf"\b{class_name}\b")

        for test_file in self._get_all_test_files():
            content = self._read_file(test_file)
            if content and pattern.search(content):
                tests.append(self._relative_path(test_file))

        return tests


def main():
    parser = argparse.ArgumentParser(
        description="Analyze the impact of code changes in ZebTrack-AI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    subparsers = parser.add_subparsers(dest="command", help="Analysis type")

    # File analysis
    file_parser = subparsers.add_parser("file", help="Analyze impact of changing a file")
    file_parser.add_argument("filepath", help="Path to the file")

    # Class analysis
    class_parser = subparsers.add_parser("class", help="Analyze impact of changing a class")
    class_parser.add_argument("classname", help="Name of the class")

    # Function analysis
    func_parser = subparsers.add_parser("function", help="Analyze impact of changing a function")
    func_parser.add_argument("funcname", help="Name of the function")

    # Event analysis
    event_parser = subparsers.add_parser("event", help="Analyze impact of an event")
    event_parser.add_argument("eventname", help="Name of the event")

    # Settings analysis
    settings_parser = subparsers.add_parser("settings", help="Analyze impact of a settings change")
    settings_parser.add_argument(
        "setting_path", help="Settings path (e.g., behavioral_analysis.perspective)"
    )

    # DI analysis
    subparsers.add_parser("di", help="Show dependency injection chain")

    # Graph generation
    graph_parser = subparsers.add_parser("graph", help="Generate dependency graph")
    graph_parser.add_argument("--output", "-o", help="Output file (DOT format)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    analyzer = ImpactAnalyzer()

    if args.command == "file":
        result = analyzer.analyze_file(args.filepath)
        print(result.to_report())

    elif args.command == "class":
        result = analyzer.analyze_class(args.classname)
        print(result.to_report())

    elif args.command == "function":
        result = analyzer.analyze_function(args.funcname)
        print(result.to_report())

    elif args.command == "event":
        result = analyzer.analyze_event(args.eventname)
        print(result.to_report())

    elif args.command == "settings":
        result = analyzer.analyze_settings(args.setting_path)
        print(result.to_report())

    elif args.command == "di":
        result = analyzer.analyze_di()
        print(result.to_report())

    elif args.command == "graph":
        graph = analyzer.generate_graph()
        if args.output:
            with open(args.output, "w") as f:
                f.write(graph)
            print(f"Graph written to {args.output}")
        else:
            print(graph)

    return 0


if __name__ == "__main__":
    sys.exit(main())
