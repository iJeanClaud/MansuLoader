"""Gera o ícone oficial do MansuLoader (YouTube -> MP3) em PNG e ICO multi-resolução."""

from pathlib import Path
from PIL import Image, ImageDraw


def create_icon(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    size = 512
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Fundo escuro arredondado
    draw.rounded_rectangle(
        (16, 16, size - 16, size - 16),
        radius=110,
        fill=(23, 26, 35, 255),
        outline=(255, 59, 92, 255),
        width=12,
    )

    # Retângulo arredondado estilo player do YouTube no centro superior
    draw.rounded_rectangle(
        (96, 108, 416, 316),
        radius=54,
        fill=(255, 59, 92, 255),
    )

    # Triângulo de Play branco
    play_triangle = [(222, 164), (222, 260), (308, 212)]
    draw.polygon(play_triangle, fill=(255, 255, 255, 255))

    # Seta de download + barra de áudio na parte inferior
    # Haste da seta
    draw.rounded_rectangle((238, 286, 274, 378), radius=10, fill=(255, 255, 255, 255))
    # Ponta da seta
    arrow_head = [(194, 354), (318, 354), (256, 424)]
    draw.polygon(arrow_head, fill=(255, 255, 255, 255))

    # Barrinhas de equalizador/áudio nas laterais inferiores
    draw.rounded_rectangle((112, 366, 136, 424), radius=8, fill=(255, 59, 92, 255))
    draw.rounded_rectangle((150, 342, 174, 424), radius=8, fill=(255, 59, 92, 255))
    draw.rounded_rectangle((338, 342, 362, 424), radius=8, fill=(255, 59, 92, 255))
    draw.rounded_rectangle((376, 366, 400, 424), radius=8, fill=(255, 59, 92, 255))

    png_path = output_dir / "mansuloader.png"
    ico_path = output_dir / "mansuloader.ico"

    img.save(png_path, format="PNG")
    img.save(
        ico_path,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )


if __name__ == "__main__":
    create_icon(Path("assets"))
