#!/usr/bin/env python3
"""Script de migração automática para Reporter v3.0."""

import argparse
import ast
import re
from pathlib import Path
from typing import Optional


class ReporterMigrator(ast.NodeVisitor):
    """AST visitor para encontrar e migrar instanciações de Reporter."""
    
    def __init__(self):
        self.migrations = []
        self.current_file = None
    
    def visit_Call(self, node):
        """Visita chamadas de função."""
        # Verificar se é Reporter(...) com trajectory_df
        if (isinstance(node.func, ast.Name) and 
            node.func.id == "Reporter" and
            any(kw.arg == "trajectory_df" for kw in node.keywords)):
            
            self.migrations.append({
                "line": node.lineno,
                "col": node.col_offset,
                "old_code": ast.unparse(node),
                "parameters": self._extract_parameters(node),
            })
        
        self.generic_visit(node)
    
    def _extract_parameters(self, node):
        """Extrai parâmetros do construtor Reporter."""
        params = {}
        for kw in node.keywords:
            params[kw.arg] = ast.unparse(kw.value)
        return params


def migrate_file(file_path: Path, dry_run: bool = True) -> Optional[str]:
    """
    Migra um arquivo Python para usar Reporter.from_analysis().
    
    Args:
        file_path: Caminho do arquivo a migrar
        dry_run: Se True, apenas mostra mudanças sem aplicar
        
    Returns:
        Novo conteúdo do arquivo ou None se nenhuma mudança
    """
    content = file_path.read_text(encoding="utf-8")
    tree = ast.parse(content)
    
    migrator = ReporterMigrator()
    migrator.current_file = file_path
    migrator.visit(tree)
    
    if not migrator.migrations:
        return None
    
    # Gerar código migrado
    lines = content.splitlines()
    new_lines = []
    
    for i, line in enumerate(lines, start=1):
        migration = next((m for m in migrator.migrations if m["line"] == i), None)
        
        if migration:
            # Gerar código equivalente
            params = migration["parameters"]
            indent = " " * migration["col"]
            
            new_code = f"""{indent}# MIGRADO PARA v3.0: Usar AnalysisService + Reporter.from_analysis()
{indent}service = AnalysisService(settings_obj=settings)
{indent}analysis = service.run_full_analysis_as_dto(
{indent}    trajectory_df={params.get('trajectory_df', 'df')},
{indent}    pixelcm_x={params.get('pixelcm_x', '10.0')},
{indent}    pixelcm_y={params.get('pixelcm_y', '10.0')},
{indent}    video_height_px={params.get('video_height_px', '480')},
{indent}    arena_polygon_px={params.get('arena_polygon_px', 'polygon')},
{indent}    rois={params.get('rois', '[]')},
{indent}    fps={params.get('fps', '30.0')},
{indent})
{indent}reporter = Reporter.from_analysis(analysis)"""
            
            new_lines.append(f"# OLD: {line}")
            new_lines.extend(new_code.splitlines())
        else:
            new_lines.append(line)
    
    new_content = "\n".join(new_lines)
    
    if not dry_run:
        file_path.write_text(new_content, encoding="utf-8")
        print(f"✅ Migrado: {file_path}")
    else:
        print(f"📝 Preview: {file_path}")
        print(new_content)
        print("=" * 80)
    
    return new_content


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Migrar Reporter para v3.0")
    parser.add_argument(
        "files",
        nargs="*",
        help="Arquivos a migrar (default: todos em tests/)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostrar mudanças sem aplicar"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Aplicar mudanças"
    )
    
    args = parser.parse_args()
    
    if args.files:
        files = [Path(f) for f in args.files]
    else:
        # Migrar todos os testes
        files = list(Path("tests").rglob("*.py"))
    
    dry_run = not args.apply
    
    migrated_count = 0
    for file_path in files:
        if file_path.exists():
            result = migrate_file(file_path, dry_run=dry_run)
            if result:
                migrated_count += 1
    
    print(f"\n{'📝 Preview' if dry_run else '✅ Aplicado'}: {migrated_count} arquivo(s)")
    
    if dry_run:
        print("\nPara aplicar mudanças, execute:")
        print("  poetry run python scripts/migrate_reporter_v3.py --apply")


if __name__ == "__main__":
    main()
