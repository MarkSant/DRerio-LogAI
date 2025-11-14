#!/usr/bin/env python3
"""
Script para análise detalhada do MainViewModel usando AST.

Extrai informações sobre:
- Todos os métodos (nome, linhas, tamanho)
- Dependências entre métodos
- Estatísticas gerais
"""

import ast
import re
from pathlib import Path
from typing import Dict, List
import json


class MethodAnalyzer(ast.NodeVisitor):
    """Visitor para extrair informações de métodos."""

    def __init__(self, source_lines: List[str]):
        self.source_lines = source_lines
        self.methods = []
        self.class_name = None

    def visit_ClassDef(self, node):
        """Visita definição de classe."""
        self.class_name = node.name
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        """Visita definição de função/método."""
        # Só processa métodos da classe (não funções aninhadas)
        if self.class_name:
            method_info = self._extract_method_info(node)
            self.methods.append(method_info)

    def _extract_method_info(self, node: ast.FunctionDef) -> dict:
        """Extrai informações de um método."""

        # Linha inicial e final
        start_line = node.lineno
        end_line = node.end_lineno or start_line

        # Contar linhas
        line_count = end_line - start_line + 1

        # Extrair conteúdo
        content_lines = self.source_lines[start_line - 1:end_line]
        content = ''.join(content_lines)

        # Detectar decorators
        decorators = [d.id if isinstance(d, ast.Name) else str(d) for d in node.decorator_list]

        # Detectar properties
        is_property = any('property' in str(d) for d in decorators)
        is_setter = any('setter' in str(d) for d in decorators)
        is_deleter = any('deleter' in str(d) for d in decorators)

        # Encontrar chamadas a métodos (self.xxx())
        called_methods = self._find_method_calls(node)

        return {
            'name': node.name,
            'start_line': start_line,
            'end_line': end_line,
            'line_count': line_count,
            'content': content,
            'decorators': decorators,
            'is_property': is_property,
            'is_setter': is_setter,
            'is_deleter': is_deleter,
            'called_methods': called_methods,
        }

    def _find_method_calls(self, node: ast.FunctionDef) -> List[str]:
        """Encontra chamadas a métodos self.xxx()."""

        called_methods = []

        for child in ast.walk(node):
            # Procura por chamadas do tipo self.method_name()
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Attribute):
                    if isinstance(child.func.value, ast.Name) and child.func.value.id == 'self':
                        method_name = child.func.attr
                        if method_name not in called_methods:
                            called_methods.append(method_name)

        return called_methods


def categorize_method(method: dict) -> str:
    """Categoriza um método baseado em seu nome e características."""

    name = method['name']

    # Properties e setters
    if method['is_property'] or method['is_setter'] or method['is_deleter']:
        return "property"

    # Métodos privados/internos (começam com _)
    if name.startswith('_'):
        if '_ui' in name.lower() or 'refresh' in name.lower() or 'update' in name.lower():
            return "ui_internal"
        elif 'handle' in name.lower() or 'on_' in name:
            return "event_handler_internal"
        elif 'process' in name.lower() or 'prepare' in name.lower() or 'run' in name.lower():
            return "orchestration_internal"
        else:
            return "utility_internal"

    # Métodos públicos
    # Event handlers (on_xxx, handle_xxx)
    if name.startswith('on_') or name.startswith('handle_'):
        return "event_handler"

    # UI methods (update, refresh, show, etc.)
    if any(keyword in name.lower() for keyword in ['update', 'refresh', 'show', 'display', 'render', 'draw']):
        return "ui_method"

    # Processing/Orchestration (start, process, run, execute, generate)
    if any(keyword in name.lower() for keyword in ['start', 'process', 'run', 'execute', 'generate', 'create', 'build']):
        return "orchestration"

    # Project/State management (load, save, close, open, setup)
    if any(keyword in name.lower() for keyword in ['load', 'save', 'close', 'open', 'setup', 'init', 'apply']):
        return "state_management"

    # Getters/Queries (get, is, has, can)
    if any(name.startswith(prefix) for prefix in ['get_', 'is_', 'has_', 'can_']):
        return "query"

    # Setters (set, add, delete, remove)
    if any(name.startswith(prefix) for prefix in ['set_', 'add_', 'delete_', 'remove_']):
        return "mutator"

    # Default
    return "other"


def analyze_mainviewmodel(file_path: Path) -> Dict:
    """Análise completa do MainViewModel usando AST."""

    print(f"Analisando {file_path}...")

    # Ler arquivo
    with open(file_path, 'r', encoding='utf-8') as f:
        source = f.read()
        source_lines = source.splitlines(keepends=True)

    # Parse AST
    tree = ast.parse(source)

    # Extrair métodos
    analyzer = MethodAnalyzer(source_lines)
    analyzer.visit(tree)

    methods = analyzer.methods

    # Categorizar métodos
    for method in methods:
        method['category'] = categorize_method(method)

    # Estatísticas
    total_methods = len(methods)
    total_lines = sum(m['line_count'] for m in methods)
    avg_lines = total_lines / total_methods if total_methods > 0 else 0

    # Métodos por categoria
    by_category = {}
    for method in methods:
        category = method['category']
        if category not in by_category:
            by_category[category] = []
        by_category[category].append(method)

    # Top 20 maiores métodos
    largest_methods = sorted(methods, key=lambda m: m['line_count'], reverse=True)[:30]

    # Métodos mais chamados (dependers)
    call_counts = {}
    for method in methods:
        for called in method['called_methods']:
            call_counts[called] = call_counts.get(called, 0) + 1

    most_called = sorted(call_counts.items(), key=lambda x: x[1], reverse=True)[:30]

    # Métodos que mais chamam outros (callers)
    caller_counts = [(m['name'], len(m['called_methods'])) for m in methods]
    most_callers = sorted(caller_counts, key=lambda x: x[1], reverse=True)[:30]

    return {
        'file_path': str(file_path),
        'total_methods': total_methods,
        'total_lines': total_lines,
        'average_lines_per_method': avg_lines,
        'methods': methods,
        'by_category': by_category,
        'largest_methods': largest_methods,
        'most_called_methods': most_called,
        'most_caller_methods': most_callers,
    }


def print_summary(analysis: Dict):
    """Imprime resumo da análise."""

    print("\n" + "="*80)
    print("ANÁLISE DO MAINVIEWMODEL")
    print("="*80)

    print(f"\nTotal de métodos: {analysis['total_methods']}")
    print(f"Total de linhas (em métodos): {analysis['total_lines']}")
    print(f"Média de linhas por método: {analysis['average_lines_per_method']:.1f}")

    print("\n" + "-"*80)
    print("MÉTODOS POR CATEGORIA")
    print("-"*80)

    for category, methods in sorted(analysis['by_category'].items()):
        total_lines = sum(m['line_count'] for m in methods)
        print(f"{category:30s}: {len(methods):3d} métodos, {total_lines:5d} linhas")

    print("\n" + "-"*80)
    print("TOP 30 MAIORES MÉTODOS (Candidatos para Extração)")
    print("-"*80)
    print(f"{'#':<4} {'Método':<50} {'Linhas':<8} {'Categoria':<25} {'Linha'}")
    print("-"*80)

    for i, method in enumerate(analysis['largest_methods'], 1):
        print(f"{i:<4} {method['name']:<50} {method['line_count']:<8} {method['category']:<25} {method['start_line']}")

    print("\n" + "-"*80)
    print("TOP 30 MÉTODOS MAIS CHAMADOS (Alto Acoplamento)")
    print("-"*80)
    print(f"{'#':<4} {'Método':<50} {'Chamado por':<12}")
    print("-"*80)

    for i, (method_name, count) in enumerate(analysis['most_called_methods'], 1):
        print(f"{i:<4} {method_name:<50} {count:<12}")

    print("\n" + "-"*80)
    print("TOP 30 MÉTODOS QUE MAIS CHAMAM OUTROS (Alto Fan-out)")
    print("-"*80)
    print(f"{'#':<4} {'Método':<50} {'Chama':<12}")
    print("-"*80)

    for i, (method_name, count) in enumerate(analysis['most_caller_methods'], 1):
        print(f"{i:<4} {method_name:<50} {count:<12}")


def save_detailed_report(analysis: Dict, output_dir: Path):
    """Salva relatório detalhado em JSON."""

    output_dir.mkdir(exist_ok=True)

    # Remove 'content' dos métodos para o JSON (muito grande)
    methods_for_json = []
    for m in analysis['methods']:
        m_copy = m.copy()
        # Mantém apenas info essencial
        methods_for_json.append({
            'name': m_copy['name'],
            'start_line': m_copy['start_line'],
            'end_line': m_copy['end_line'],
            'line_count': m_copy['line_count'],
            'category': m_copy['category'],
            'called_methods': m_copy['called_methods'],
            'decorators': m_copy['decorators'],
            'is_property': m_copy['is_property'],
        })

    report = {
        'file_path': analysis['file_path'],
        'total_methods': analysis['total_methods'],
        'total_lines': analysis['total_lines'],
        'average_lines_per_method': analysis['average_lines_per_method'],
        'methods': methods_for_json,
        'category_summary': {
            category: {
                'count': len(methods),
                'total_lines': sum(m['line_count'] for m in methods),
                'methods': [m['name'] for m in methods]
            }
            for category, methods in analysis['by_category'].items()
        },
        'largest_methods': [
            {
                'name': m['name'],
                'line_count': m['line_count'],
                'category': m['category'],
                'start_line': m['start_line'],
                'end_line': m['end_line'],
                'called_methods': m['called_methods'],
            }
            for m in analysis['largest_methods']
        ],
        'most_called_methods': [
            {'method': name, 'call_count': count}
            for name, count in analysis['most_called_methods']
        ],
        'most_caller_methods': [
            {'method': name, 'calls_count': count}
            for name, count in analysis['most_caller_methods']
        ],
    }

    output_file = output_dir / 'mainviewmodel_analysis.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Relatório detalhado salvo em: {output_file}")

    return report


if __name__ == '__main__':
    file_path = Path('/home/user/ZebTrack-AI/src/zebtrack/core/main_view_model.py')
    output_dir = Path('/home/user/ZebTrack-AI/analysis_output')

    analysis = analyze_mainviewmodel(file_path)
    print_summary(analysis)
    report = save_detailed_report(analysis, output_dir)
