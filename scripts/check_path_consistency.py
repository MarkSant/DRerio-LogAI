#!/usr/bin/env python
"""
Pre-commit hook script para validar consistência de paths.

Este script verifica se novos métodos/funções que contêm "path" no nome dos
parâmetros estão usando a anotação de tipo Path | str conforme o padrão do projeto.

Retorna:
    0: Todos os parâmetros de path estão corretamente anotados
    1: Encontrou parâmetros de path sem anotação correta
"""

import ast
import sys
from pathlib import Path


class PathParameterChecker(ast.NodeVisitor):
    """Verifica se parâmetros de path estão usando Path | str."""

    def __init__(self, filepath: Path):
        self.filepath = filepath
        self.violations: list[dict] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visita definições de função."""
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

            # Ignora self, cls
            if param_name in ("self", "cls"):
                continue

            # Verifica se é um parâmetro relacionado a path
            if self._is_path_parameter(param_name):
                type_hint = self._get_type_annotation(arg)

                # Verifica se a anotação é aceitável
                if not self._is_acceptable_annotation(type_hint, param_name):
                    self.violations.append(
                        {
                            "file": str(self.filepath),
                            "line": arg.lineno,
                            "function": node.name,
                            "parameter": param_name,
                            "type": type_hint,
                        }
                    )

    def _is_path_parameter(self, param_name: str) -> bool:
        """Verifica se o nome do parâmetro sugere que é um path."""
        path_indicators = [
            "path",
            "filepath",
            "file_path",
            "dir",
            "directory",
            "folder",
        ]
        return any(indicator in param_name.lower() for indicator in path_indicators)

    def _get_type_annotation(self, arg: ast.arg) -> str:
        """Extrai anotação de tipo do argumento."""
        if arg.annotation is None:
            return "no_annotation"

        return ast.unparse(arg.annotation)

    def _is_acceptable_annotation(self, type_hint: str, param_name: str) -> bool:
        """Verifica se a anotação de tipo é aceitável."""
        # Sem anotação não é aceitável
        if type_hint == "no_annotation":
            return False

        # Anotações aceitáveis
        acceptable_patterns = [
            "Path",
            "Path | str",
            "str | Path",
            "Path | None",
            "str | Path | None",
            "Path | str | None",
        ]

        # Verifica se contém algum dos padrões aceitáveis
        for pattern in acceptable_patterns:
            if pattern in type_hint:
                return True

        # Se for apenas 'str' ou 'str | None', não é aceitável
        # (deveria ser Path | str)
        if type_hint in ("str", "str | None"):
            return False

        # Outros casos (tipos complexos, genéricos, etc.) são aceitáveis
        # para não gerar falsos positivos
        return True


def check_file(filepath: Path) -> list[dict]:
    """Verifica um arquivo Python."""
    try:
        with open(filepath, encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(filepath))

        checker = PathParameterChecker(filepath)
        checker.visit(tree)
        return checker.violations

    except SyntaxError:
        # Ignora erros de sintaxe (podem ser arquivos em edição)
        return []
    except Exception:
        # Ignora outros erros
        return []


def main() -> int:
    """Função principal do pre-commit hook."""
    # Obtém os arquivos modificados do git
    import subprocess

    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            capture_output=True,
            text=True,
            check=True,
        )
        changed_files = result.stdout.strip().split("\n")
    except subprocess.CalledProcessError:
        print("Erro ao obter arquivos modificados do git")
        return 1

    # Filtra apenas arquivos Python no src/zebtrack
    python_files = [
        Path(f)
        for f in changed_files
        if f.endswith(".py") and f.startswith("src/zebtrack/")
    ]

    if not python_files:
        return 0

    # Verifica cada arquivo
    all_violations: list[dict] = []
    for filepath in python_files:
        if filepath.exists():
            violations = check_file(filepath)
            all_violations.extend(violations)

    if not all_violations:
        return 0

    # Reporta violações
    print("=" * 80)
    print("ERRO: Parâmetros de path sem anotação Path | str encontrados!")
    print("=" * 80)
    print()

    for violation in all_violations:
        rel_path = Path(violation["file"]).relative_to(Path.cwd())
        print(f"{rel_path}:{violation['line']}")
        print(f"  Função: {violation['function']}")
        print(f"  Parâmetro: {violation['parameter']}")
        print(f"  Tipo atual: {violation['type']}")
        print()

    print("Por favor, atualize os parâmetros acima para usar 'Path | str':")
    print()
    print("  def method(self, path: Path | str) -> ...:")
    print("      path = Path(path) if isinstance(path, str) else path")
    print("      # Usar path (sempre Path) daqui pra frente")
    print()
    print(f"Total de violações: {len(all_violations)}")
    print("=" * 80)

    return 1


if __name__ == "__main__":
    sys.exit(main())
