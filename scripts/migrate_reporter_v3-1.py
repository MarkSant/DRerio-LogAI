#!/usr/bin/env python3
"""Script de migração automática para Reporter v3.0 (Versão Corrigida).

Limitações:
- Gera uma nova instância do AnalysisService para cada Reporter.
- A heurística para 'settings_obj' vs 'mock_settings' baseia-se no nome do arquivo.

Correções (v3.0.1):
1. [FIX] Usa 'end_lineno' do AST para remover/comentar o BLOCO inteiro
         da chamada antiga, prevenindo SyntaxError.
2. [FIX] Adiciona heurística para usar 'mock_settings' em arquivos de teste
         e 'settings_obj' em outros, prevenindo NameError.
3. [FIX] Passa TODOS os parâmetros do construtor antigo para o DTO,
         em vez de uma lista fixa.
4. [FIX] Traduz nomes de parâmetros obsoletos (ex: freezing_threshold).
5. [FIX] Adiciona salvaguarda para não migrar arquivos '...compatibility.py'.
"""

import argparse
import ast
from pathlib import Path
from typing import Optional


class ReporterMigrator(ast.NodeVisitor):
    """AST visitor para encontrar e migrar instanciações de Reporter."""

    def __init__(self):
        self.migrations = []

    def visit_Call(self, node):
        """Visita chamadas de função."""
        # Verificar se é Reporter(...) com trajectory_df
        if (
            isinstance(node.func, ast.Name)
            and node.func.id == "Reporter"
            and any(kw.arg == "trajectory_df" for kw in node.keywords)
        ):
            self.migrations.append(
                {
                    "line": node.lineno,
                    "end_line": node.end_lineno,  # <-- FIX 1: Captura linha final
                    "col": node.col_offset,
                    "parameters": self._extract_parameters(node),
                }
            )

        self.generic_visit(node)

    def _extract_parameters(self, node) -> dict[str, str]:
        """Extrai parâmetros do construtor Reporter."""
        params = {}
        for kw in node.keywords:
            if kw.arg:  # Ignora *args e **kwargs
                params[kw.arg] = ast.unparse(kw.value)
        return params


def generate_migrated_code(params: dict[str, str], indent_str: str, file_path: Path) -> str:
    """Gera o novo bloco de código v3.0."""

    # FIX 2: Heurística para nome do objeto de settings
    settings_var_name = "mock_settings" if "test" in file_path.name else "settings_obj"

    # FIX 3: Mapeamento de parâmetros obsoletos para nomes da v3.0 DTO
    param_map = {
        "freezing_threshold": "freezing_vel_threshold",
        "freezing_duration": "freezing_min_duration",
        # Adicione outras traduções se necessário
    }

    # Parâmetros a excluir (não fazem parte do DTO)
    excluded_params = {"settings_obj"}  # 'settings_obj' vai para AnalysisService

    analysis_params = []
    for key, value in params.items():
        if key in excluded_params:
            continue

        # Traduz o nome da chave, se necessário
        new_key = param_map.get(key, key)
        analysis_params.append(f"{indent_str}    {new_key}={value},")

    # Ordena para consistência
    analysis_params_str = "\n".join(sorted(analysis_params))

    # Gera o bloco de código final
    new_code = f"""{indent_str}# MIGRADO PARA v3.0: Usar AnalysisService + Reporter.from_analysis()
{indent_str}service = AnalysisService(settings_obj={settings_var_name})
{indent_str}analysis = service.run_full_analysis_as_dto(
{analysis_params_str}
{indent_str})
{indent_str}reporter = Reporter.from_analysis(analysis)"""

    return new_code


def migrate_file(file_path: Path, dry_run: bool = True) -> Optional[str]:
    """
    Migra um arquivo Python para usar Reporter.from_analysis().
    """
    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content)
    except Exception as e:
        print(f"❌ Erro ao processar {file_path}: {e}")
        return None

    migrator = ReporterMigrator()
    migrator.visit(tree)

    if not migrator.migrations:
        return None

    lines = content.splitlines()
    new_lines = []

    migrations_by_line = {m["line"]: m for m in migrator.migrations}
    skip_until_line = 0  # <-- FIX 1: Tracker para pular linhas antigas

    for i, line in enumerate(lines, start=1):
        # Se esta linha já foi consumida por uma migração anterior, pule
        if i < skip_until_line:
            continue

        migration = migrations_by_line.get(i)

        if migration:
            indent = " " * migration["col"]
            params = migration["parameters"]

            # Gera o novo código
            new_code_block = generate_migrated_code(params, indent, file_path)

            # Comenta o bloco de código antigo inteiro
            start_idx = migration["line"] - 1
            end_idx = migration["end_line"]
            for old_line_idx in range(start_idx, end_idx):
                new_lines.append(f"# OLD: {lines[old_line_idx]}")

            # Adiciona o novo código
            new_lines.extend(new_code_block.splitlines())

            # Define até onde pular
            skip_until_line = migration["end_line"] + 1  # <-- FIX 1
        else:
            new_lines.append(line)  # Mantém a linha como está

    new_content = "\n".join(new_lines)

    if not dry_run:
        file_path.write_text(new_content, encoding="utf-8")
        print(f"✅ Migrado: {file_path}")
    else:
        print(f"📝 Preview: {file_path}")
        # Mostra as mudanças (apenas as linhas alteradas para clareza)
        old_lines_set = set(lines)
        new_lines_set = set(new_lines)

        diff_added = new_lines_set - old_lines_set
        diff_removed = old_lines_set - new_lines_set

        print("\n--- DIFF (Resumo) ---")
        for line in diff_removed:
            if not line.strip().startswith("# OLD:"):
                print(f"- {line}")
        for line in diff_added:
            if not line.strip().startswith("# OLD:"):
                print(f"+ {line}")
        print("=" * 80)

    return new_content


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Migrar Reporter para v3.0 (Corrigido)")
    parser.add_argument("files", nargs="*", help="Arquivos a migrar (default: todos em tests/)")
    parser.add_argument("--dry-run", action="store_true", help="Mostrar mudanças sem aplicar")
    parser.add_argument("--apply", action="store_true", help="Aplicar mudanças")

    args = parser.parse_args()

    if args.files:
        files = [Path(f) for f in args.files]
    else:
        # Migrar todos os testes por padrão
        files = list(Path("tests").rglob("*.py"))
        # Adicione outros diretórios se necessário
        # files.extend(list(Path("src").rglob("*.py")))

    dry_run = not args.apply
    migrated_count = 0

    for file_path in files:
        # FIX 4: Salvaguarda para não migrar testes de compatibilidade
        if "compatibility.py" in str(file_path):
            print(f"⚠️ Ignorado (Teste de Compatibilidade): {file_path}")
            continue

        if file_path.exists() and file_path.is_file():
            result = migrate_file(file_path, dry_run=dry_run)
            if result:
                migrated_count += 1
        elif not file_path.exists():
            print(f"❌ Arquivo não encontrado: {file_path}")

    mode_msg = "📝 Preview" if dry_run else "✅ Aplicado"
    print(f"\n{mode_msg}: {migrated_count} arquivo(s) alterado(s).")

    if dry_run and migrated_count > 0:
        print("\nPara aplicar mudanças, execute com --apply")
        print("  poetry run python scripts/migrate_reporter_v3.py --apply")
    elif migrated_count == 0:
        print("Nenhuma instanciação obsoleta do Reporter foi encontrada.")


if __name__ == "__main__":
    main()
