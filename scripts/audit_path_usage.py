"""
Script de auditoria para identificar uso de parâmetros de path no código.

Este script analisa todos os arquivos Python do projeto e identifica:
- Parâmetros de função/método que contêm "path" no nome
- Tipo atual do parâmetro (Path, str, Path | str, etc.)
- Localização (arquivo:linha:função:parâmetro)

Gera relatório para guiar a padronização pathlib.
"""

import ast
import sys
from pathlib import Path
from typing import Any


class PathParameterVisitor(ast.NodeVisitor):
    """Visitor AST para encontrar parâmetros relacionados a paths."""

    def __init__(self, filepath: Path):
        self.filepath = filepath
        self.findings: list[dict[str, Any]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visita definições de função/método."""
        self._check_parameters(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Visita definições de função async."""
        self._check_parameters(node)
        self.generic_visit(node)

    def _check_parameters(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Verifica parâmetros de uma função."""
        for arg in node.args.args:
            param_name = arg.arg
            if "path" in param_name.lower() or param_name in [
                "filepath",
                "file_path",
                "dir",
                "directory",
                "folder",
            ]:
                type_hint = self._get_type_annotation(arg)
                self.findings.append(
                    {
                        "file": str(self.filepath),
                        "line": arg.lineno,
                        "function": node.name,
                        "parameter": param_name,
                        "type": type_hint,
                    }
                )

    def _get_type_annotation(self, arg: ast.arg) -> str:
        """Extrai anotação de tipo do argumento."""
        if arg.annotation is None:
            return "no_annotation"

        return ast.unparse(arg.annotation)


def analyze_file(filepath: Path) -> list[dict[str, Any]]:
    """Analisa um arquivo Python e retorna findings."""
    try:
        with open(filepath, encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(filepath))

        visitor = PathParameterVisitor(filepath)
        visitor.visit(tree)
        return visitor.findings

    except SyntaxError as e:
        print(f"Erro de sintaxe em {filepath}: {e}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"Erro ao processar {filepath}: {e}", file=sys.stderr)
        return []


def audit_codebase(root_dir: Path) -> list[dict[str, Any]]:
    """Audita toda a codebase buscando parâmetros de path."""
    all_findings: list[dict[str, Any]] = []

    # Buscar todos os arquivos .py no src/zebtrack
    src_dir = root_dir / "src" / "zebtrack"
    if not src_dir.exists():
        print(f"Diretório {src_dir} não encontrado!", file=sys.stderr)
        return []

    python_files = sorted(src_dir.rglob("*.py"))
    print(f"Analisando {len(python_files)} arquivos Python...\n")

    for filepath in python_files:
        findings = analyze_file(filepath)
        all_findings.extend(findings)

    return all_findings


def categorize_findings(findings: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Categoriza findings por tipo de anotação."""
    categories: dict[str, list[dict[str, Any]]] = {
        "Path": [],
        "str": [],
        "Path | str": [],
        "str | Path": [],
        "Optional[Path]": [],
        "Path | None": [],
        "str | None": [],
        "no_annotation": [],
        "other": [],
    }

    for finding in findings:
        type_hint = finding["type"]

        # Normalizar variações
        if type_hint in categories:
            categories[type_hint].append(finding)
        elif "Path" in type_hint and "str" in type_hint:
            categories["Path | str"].append(finding)
        elif "Path" in type_hint:
            categories["Path"].append(finding)
        elif type_hint == "str":
            categories["str"].append(finding)
        elif type_hint == "no_annotation":
            categories["no_annotation"].append(finding)
        else:
            categories["other"].append(finding)

    return categories


def print_report(categories: dict[str, list[dict[str, Any]]]) -> None:
    """Imprime relatório formatado."""
    print("=" * 100)
    print("RELATÓRIO DE AUDITORIA DE PATHS")
    print("=" * 100)
    print()

    total_findings = sum(len(findings) for findings in categories.values())
    print(f"Total de parâmetros relacionados a path encontrados: {total_findings}")
    print()

    for category, findings in categories.items():
        if not findings:
            continue

        print(f"\n{'=' * 100}")
        print(f"Categoria: {category} ({len(findings)} ocorrências)")
        print("=" * 100)

        # Agrupar por arquivo
        by_file: dict[str, list[dict[str, Any]]] = {}
        for finding in findings:
            file = finding["file"]
            if file not in by_file:
                by_file[file] = []
            by_file[file].append(finding)

        for file, file_findings in sorted(by_file.items()):
            # Mostrar caminho relativo
            rel_path = Path(file).relative_to(Path.cwd())
            print(f"\n{rel_path}:")

            for f in sorted(file_findings, key=lambda x: x["line"]):
                print(f"  Linha {f['line']:4d}: {f['function']}({f['parameter']})")

    # Estatísticas finais
    print(f"\n{'=' * 100}")
    print("ESTATÍSTICAS")
    print("=" * 100)

    # Já estão usando Path corretamente
    correct = len(categories["Path"]) + len(categories["Path | str"]) + len(categories["str | Path"])
    # Precisam ser atualizados
    needs_update = (
        len(categories["str"])
        + len(categories["no_annotation"])
        + len(categories["str | None"])
    )
    # Casos especiais (Optional, etc.)
    special = len(categories["Optional[Path]"]) + len(categories["Path | None"]) + len(
        categories["other"]
    )

    print(f"[OK] Ja usando Path ou Path | str: {correct}")
    print(f"[!]  Precisam atualizacao (str/no_annotation): {needs_update}")
    print(f"[?] Casos especiais para revisar: {special}")
    print()

    if needs_update > 0:
        print("PRIORIDADE: Atualizar parâmetros 'str' e 'no_annotation' para 'Path | str'")


def main() -> None:
    """Função principal."""
    root_dir = Path.cwd()

    print("Auditando uso de parâmetros de path na codebase...")
    print(f"Diretório raiz: {root_dir}\n")

    findings = audit_codebase(root_dir)

    if not findings:
        print("Nenhum parâmetro relacionado a path encontrado.")
        return

    categories = categorize_findings(findings)
    print_report(categories)

    # Salvar relatório em arquivo
    report_file = root_dir / "path_audit_report.txt"
    with open(report_file, "w", encoding="utf-8") as f:
        # Redirecionar stdout temporariamente
        import sys
        from io import StringIO

        old_stdout = sys.stdout
        sys.stdout = StringIO()

        print_report(categories)

        report_content = sys.stdout.getvalue()
        sys.stdout = old_stdout

        f.write(report_content)

    print(f"\nRelatorio salvo em: {report_file}")


if __name__ == "__main__":
    main()
