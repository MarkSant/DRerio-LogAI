"""
Script para limpar templates de ROI órfãos (sem arquivo válido).

Uso:
    poetry run python scripts/cleanup_templates.py
"""

from zebtrack.core.project.roi_template_manager import ROITemplateManager


def main():
    """Limpa templates inválidos."""
    print("=" * 60)
    print("Limpeza de Templates de ROI Órfãos")
    print("=" * 60)

    manager = ROITemplateManager()
    templates_dir = manager.global_templates_dir

    print(f"\nDiretório de templates: {templates_dir}")
    print("Verificando templates...\n")

    # List current templates
    templates = manager.list_global_templates()
    print(f"Templates válidos encontrados: {len(templates)}")
    for t in templates:
        print(f"  ✓ {t['name']} ({t['file']})")

    # Cleanup orphaned
    print("\nLimpando templates órfãos...")
    result = manager.cleanup_orphaned_templates()

    print("\n" + "=" * 60)
    print("Resultado:")
    print(f"  Templates mantidos: {result['kept']}")
    print(f"  Templates removidos: {result['removed']}")
    print("=" * 60)

    if result["removed"] > 0:
        print("\n✓ Templates órfãos foram removidos com sucesso!")
    else:
        print("\n✓ Nenhum template órfão encontrado.")


if __name__ == "__main__":
    main()
