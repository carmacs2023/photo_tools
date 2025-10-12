#!/usr/bin/env python3
import argparse, os, sys
from pathlib import Path
from PIL import Image, ImageColor

"""Photo converter and squaring utility.

This script processes images from a source directory and writes squared versions
to a destination directory by placing the resized image onto a solid-color
square canvas. The longest side is scaled to the requested width while
preserving the original aspect ratio. Output can be saved as JPG or PNG, with
quality/compression controlled via a 1–10 scale.

Key behavior:
- Optionally traverse subfolders and (optionally) mirror the directory layout
  under the destination.
- Skip files by extension and/or by filename substrings.
- For images with alpha, the image is flattened against the chosen background
  color when producing the squared canvas.

Use cases (kept from the original script, rewritten in English):

# Recursively process, mirror folder structure, exclude webp and any filename
# containing "con_fondo" or "sin_fondo"; output JPG, 6000×6000, white background:
# python convert_photo.py -s "/abs/source" -d "/abs/destination" -r -m \
#   -ef webp --exclude_filenames "con_fondo,sin_fondo" -w 6000 -f jpg -q 10 -c ffffff

# Process only the current folder (no subfolders), output PNG 2000×2000, light gray background:
# python convert_photo.py -s "/abs/source" -d "/abs/destination" -w 2000 -f png -q 8 -c eeeeee

# Exclude multiple formats (webp,jpg) and any name containing "preview" or "tmp":
# python convert_photo.py -s "/abs/source" -d "/abs/destination" -r -m \
#   -ef webp,jpg --exclude_filenames "preview,tmp" -w 6000 -f png -q 9 -c ffffff
"""

def parse_args():
    """Create and parse CLI arguments.

    Returns:
        argparse.Namespace: Parsed options as attributes.
    """
    p = argparse.ArgumentParser(
        description="Square images on a solid-color canvas, maintaining aspect ratio by scaling the long side to --width."
    )
    # Required options
    # - Absolute path to the source directory containing input images
    p.add_argument("-s", "--source", required=True, help="Ruta absoluta de origen.")
    # - Absolute path to the destination directory where outputs will be written
    p.add_argument("-d", "--destination", required=True, help="Ruta absoluta de destino.")
    # - Final square size (pixels). Output width and height will both equal this value
    p.add_argument("-w", "--width", required=True, type=int, help="Tamaño final (px) del lado (ancho=alto).")
    # - Output format for saved files (jpg or png)
    p.add_argument("-f", "--output_format", required=True, choices=["jpg", "png"], help="Formato de salida: jpg o png.")
    # - Background color for the square canvas, provided as hex (e.g. ffffff)
    p.add_argument("-c", "--output_color", default="ffffff", help="Color de fondo en hex (por defecto ffffff).")
    # Optional behavior flags
    # - Process subdirectories recursively under the source path
    p.add_argument("-r", "--recursive", action="store_true", help="Procesar recursivamente subcarpetas.")
    # - Mirror the source directory structure under the destination directory
    p.add_argument("-m", "--mirror_destination", action="store_true",
                   help="Replicar la misma estructura de carpetas dentro del destino.")
    # - Comma-separated list of extensions to exclude (e.g. webp,jpg)
    p.add_argument("-ef", "--exclude_format", default="",
                   help="Excluir extensiones separadas por coma, ej: webp,jpg")
    # - Comma-separated list of substrings; any filename containing any substring will be skipped
    #   (Long option kept; short -x also available)
    p.add_argument("-x", "--exclude_filenames", default="",
                   help="Excluir archivos que contengan estas cadenas (coma), ej: con_fondo,sin_fondo")

    # - Output quality scale (1–10). For JPG maps to Pillow quality, for PNG maps to compress level
    p.add_argument("-q", "--output_quality", type=int, default=10,
                   help="Calidad 1–10 (solo JPG/PNG). Por defecto 10 (máxima).")
    return p.parse_args()

def quality_maps(fmt, q10):
    """Map a 1–10 quality scale to Pillow encoder parameters.

    Args:
        fmt (str): Output format, either "jpg" or "png".
        q10 (int): Quality scale from 1 (lowest) to 10 (highest).

    Returns:
        int | None: For JPG, a Pillow JPEG quality (approx. 30–95). For PNG,
        a compress_level (0–9). Returns None for unsupported formats.
    """
    q10 = max(1, min(10, q10))
    if fmt == "jpg":
        # Mapear 1–10 a 30–95 aprox.
        return int(30 + (q10 - 1) * (65/9))
    if fmt == "png":
        # Pillow usa compress_level 0–9 (menor = más grande, mayor = más comprimido).
        # Aproximamos: q10=10 => comp=9 (máxima), q10=1 => comp=0.
        return 9 - int(round((q10 - 1) * (9/9)))
    return None

def should_skip(file: Path, exclude_exts, exclude_substrings):
    """Check if a file should be skipped based on extension or name substrings.

    Args:
        file (Path): Candidate file path.
        exclude_exts (list[str]): Extensions (lowercase, without dot) to skip.
        exclude_substrings (list[str]): Substrings; if present in filename (lowercase), skip.

    Returns:
        bool: True if the file should be skipped.
    """
    name_lower = file.name.lower()
    ext = file.suffix.lower().lstrip(".")
    if ext in exclude_exts:
        return True
    for sub in exclude_substrings:
        if sub and sub in name_lower:
            return True
    return False

def ensure_dir(path: Path):
    """Ensure a directory exists (mkdir -p equivalent).

    Args:
        path (Path): Directory path to create if missing.
    """
    path.mkdir(parents=True, exist_ok=True)

def pad_to_square(img: Image.Image, target: int, bg_rgb):
    """Resize an image to fit into a square canvas of size target x target.

    The image is resized preserving aspect ratio so that the long side equals
    target, then centered on a new RGB canvas of size (target, target) with
    the provided background color.

    Args:
        img (PIL.Image.Image): Input image.
        target (int): Target side length in pixels for the square canvas.
        bg_rgb (tuple[int, int, int]): Background RGB color for the canvas.

    Returns:
        PIL.Image.Image: The squared image on an RGB canvas.
    """
    # Escalar manteniendo AR para que el lado LARGO == target
    w, h = img.size
    scale = target / float(max(w, h))
    new_w, new_h = int(round(w * scale)), int(round(h * scale))
    img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    # Crear lienzo cuadrado y centrar
    if img_resized.mode in ("RGBA", "LA"):
        # Si tiene alpha, aplanamos contra el color de fondo
        base = Image.new("RGB", (target, target), bg_rgb)
        base.paste(img_resized, ((target - new_w)//2, (target - new_h)//2), img_resized)
    else:
        base = Image.new("RGB", (target, target), bg_rgb)
        base.paste(img_resized, ((target - new_w)//2, (target - new_h)//2))
    return base

def convert_photo(in_path: Path, out_path: Path, target_w: int, bg_hex: str,
                  out_fmt: str, q10: int):
    """Convert a single image to a squared image and save it.

    Steps:
    1) Load the image, 2) parse background color, 3) normalize mode depending
    on output format, 4) pad to square at requested size, 5) save using mapped
    quality/compression for JPG/PNG.

    Args:
        in_path (Path): Input image path.
        out_path (Path): Output path WITHOUT extension; extension is added based on out_fmt.
        target_w (int): Target square side in pixels.
        bg_hex (str): Background color in hex without leading '#'.
        out_fmt (str): Output format, "jpg" or "png".
        q10 (int): Quality scale 1–10 (higher is better quality / higher PNG compression).

    Returns:
        bool: True on success, False otherwise.
    """
    # Cargar
    try:
        img = Image.open(in_path)
    except Exception as e:
        print(f"[WARN] No se pudo abrir {in_path}: {e}", file=sys.stderr)
        return False

    # Color de fondo
    try:
        bg_rgb = ImageColor.getrgb("#" + bg_hex.strip().lstrip("#"))
    except Exception:
        print(f"[WARN] Color inválido {bg_hex}, usando blanco.", file=sys.stderr)
        bg_rgb = (255, 255, 255)

    # Convertir a modo compatible con salida
    if out_fmt == "jpg":
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
        else:
            img = img.convert("RGB")
    else:  # png
        if img.mode == "P":
            img = img.convert("RGBA")

    # Redimensionar + cuadrar
    canvas = pad_to_square(img, target_w, bg_rgb)

    # Guardar
    ensure_dir(out_path.parent)
    try:
        if out_fmt == "jpg":
            q = quality_maps("jpg", q10)
            canvas = canvas.convert("RGB")
            canvas.save(out_path.with_suffix(".jpg"),
                        format="JPEG",
                        quality=q,
                        optimize=True,
                        progressive=True)
        else:
            comp = quality_maps("png", q10)
            # Para PNG, optimize True y compress_level
            canvas.save(out_path.with_suffix(".png"),
                        format="PNG",
                        optimize=True,
                        compress_level=comp)
        return True
    except Exception as e:
        print(f"[WARN] Error al guardar {out_path}: {e}", file=sys.stderr)
        return False

def main():
    """CLI entrypoint: walk source directory, filter, convert, and report.

    Uses parsed CLI options to collect eligible images, optionally recursing
    subdirectories and optionally mirroring the destination structure. Each
    selected image is converted via convert_photo.
    """
    args = parse_args()
    src_root = Path(args.source).expanduser().resolve()
    dst_root = Path(args.destination).expanduser().resolve()

    if not src_root.exists():
        print(f"[ERROR] Origen no existe: {src_root}", file=sys.stderr)
        sys.exit(1)

    # Preparar exclusiones
    exclude_exts = [e.strip().lower().lstrip(".") for e in args.exclude_format.split(",") if e.strip()]
    exclude_substrings = [s.strip().lower() for s in args.exclude_filenames.split(",") if s.strip()]

    total, ok = 0, 0

    # Recolección de archivos
    if args.recursive:
        iterator = src_root.rglob("*")
    else:
        iterator = src_root.iterdir()

    for item in iterator:
        if not item.is_file():
            continue

        # Detectar extensión de entrada
        ext = item.suffix.lower().lstrip(".")
        # Si no se excluye, seguimos
        if should_skip(item, exclude_exts, exclude_substrings):
            continue

        # Solo procesamos formatos de imagen comunes que Pillow suele abrir
        if ext not in ("jpg", "jpeg", "png", "tif", "tiff", "bmp", "webp", "heic"):
            continue

        # Ruta de salida
        if args.mirror_destination:
            rel = item.parent.relative_to(src_root)
            out_dir = dst_root.joinpath(rel)
        else:
            out_dir = dst_root

        out_base = out_dir.joinpath(item.stem)  # mismo nombre base

        total += 1
        if convert_photo(
            in_path=item,
            out_path=out_base,
            target_w=args.width,
            bg_hex=args.output_color,
            out_fmt=args.output_format.lower(),
            q10=(args.output_quality or 10),
        ):
            ok += 1

    print(f"[DONE] Procesadas correctamente: {ok}/{total}")

if __name__ == "__main__":
    main()
