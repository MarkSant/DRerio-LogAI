"""Script temporário para redimensionar logos para diferentes usos."""

from pathlib import Path

from PIL import Image

# Caminhos
assets_dir = Path("src/zebtrack/ui/assets")
source_logo = assets_dir / "logo_source.png"

# Configurações de redimensionamento
sizes = {
    "logo_welcome.png": 300,  # Janela inicial
    "logo_about.png": 128,  # Janela Sobre
    "logo_readme.png": 256,  # Documentação
}

# Carregar imagem original
img = Image.open(source_logo)
print(f"Logo original: {img.size[0]}x{img.size[1]}px")

# Redimensionar para cada uso
for filename, size in sizes.items():
    resized = img.resize((size, size), Image.Resampling.LANCZOS)
    output_path = assets_dir / filename
    resized.save(output_path, "PNG", optimize=True)
    print(f"Criado: {filename} ({size}x{size}px)")

print("\nTodas as imagens otimizadas criadas com sucesso!")
