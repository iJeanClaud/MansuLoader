"""Prepara os recursos visuais (ícone sem fundo preto e imagem da splash screen)."""

from collections import deque
from pathlib import Path
from PIL import Image


def remove_black_background(src_path: Path, png_out: Path, ico_out: Path) -> None:
    img = Image.open(src_path).convert("RGBA")
    w, h = img.size
    pixels = img.load()

    visited = bytearray(w * h)
    queue: deque[tuple[int, int]] = deque()

    def is_dark(r: int, g: int, b: int, threshold: int = 28) -> bool:
        return r <= threshold and g <= threshold and b <= threshold

    # Inicia flood-fill pelas bordas da imagem
    for x in range(w):
        for y in (0, h - 1):
            r, g, b, _ = pixels[x, y]
            if is_dark(r, g, b):
                idx = y * w + x
                if not visited[idx]:
                    visited[idx] = 1
                    queue.append((x, y))

    for y in range(h):
        for x in (0, w - 1):
            r, g, b, _ = pixels[x, y]
            if is_dark(r, g, b):
                idx = y * w + x
                if not visited[idx]:
                    visited[idx] = 1
                    queue.append((x, y))

    while queue:
        cx, cy = queue.popleft()
        pixels[cx, cy] = (0, 0, 0, 0)
        for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
            if 0 <= nx < w and 0 <= ny < h:
                idx = ny * w + nx
                if not visited[idx]:
                    r, g, b, _ = pixels[nx, ny]
                    if is_dark(r, g, b):
                        visited[idx] = 1
                        queue.append((nx, ny))

    # Suaviza a borda entre pixels transparentes e o logo
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            r, g, b, a = pixels[x, y]
            if a == 0:
                continue
            lum = max(r, g, b)
            if lum < 46:
                has_transparent_neighbor = any(
                    pixels[nx, ny][3] == 0
                    for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))
                )
                if has_transparent_neighbor:
                    new_alpha = int((lum / 46) * 200)
                    pixels[x, y] = (r, g, b, new_alpha)

    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)

    # Centraliza em um canvas quadrado com pequena margem
    side = max(img.size)
    pad = int(side * 0.04)
    canvas_size = side + pad * 2
    canvas = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    offset = ((canvas_size - img.width) // 2, (canvas_size - img.height) // 2)
    canvas.paste(img, offset, img)

    canvas.resize((512, 512), Image.Resampling.LANCZOS).save(png_out, format="PNG")
    icon_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    frames = [canvas.resize(sz, Image.Resampling.LANCZOS) for sz in icon_sizes]
    frames[-1].save(
        ico_out,
        format="ICO",
        append_images=frames[:-1],
    )


def prepare_splash(src_path: Path, out_path: Path) -> None:
    img = Image.open(src_path).convert("RGB")
    target_w = 440
    target_h = int(img.height * (target_w / img.width))
    resized = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
    resized.save(out_path, format="PNG", optimize=True)


if __name__ == "__main__":
    assets_dir = Path("assets")
    assets_dir.mkdir(parents=True, exist_ok=True)
    remove_black_background(
        Path("Ícone Neon do MansuLoader.png"),
        assets_dir / "mansuloader.png",
        assets_dir / "mansuloader.ico",
    )
    prepare_splash(
        Path("MansuLoader_ Download Musical em Neon.png"),
        assets_dir / "splash.png",
    )
    print("Assets preparados com sucesso.")
