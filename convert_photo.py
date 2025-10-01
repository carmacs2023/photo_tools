#!/usr/bin/env python3
import argparse, os, sys
from pathlib import Path
from PIL import Image, ImageColor

# Ejemplos de uso

# Procesar recursivamente, replicando estructura, excl. webp y que contengan “con_fondo” o “sin_fondo”; salida JPG, 6000×6000, fondo blanco:
# python convert_photo.py -s "/abs/origen" -d "/abs/destino" -r -m \
#   -ef webp --exclude_filenames "con_fondo,sin_fondo" -w 6000 -f jpg -q 10 -c ffffff

# Procesar solo la carpeta actual (sin subcarpetas), salida PNG 2000×2000, fondo gris claro:
# python convert_photo.py -s "/abs/origen" -d "/abs/destino" -w 2000 -f png -q 8 -c eeeeee

# Excluir múltiples formatos (webp,jpg) y cualquier nombre que contenga “preview” o “tmp”:
# python convert_photo.py -s "/abs/origen" -d "/abs/destino" -r -m \
#   -ef webp,jpg --exclude_filenames "preview,tmp" -w 6000 -f png -q 9 -c ffffff

def parse_args():
    p = argparse.ArgumentParser(
        description="Cuadra imágenes en lienzo de color, manteniendo AR y escalando el lado largo a --width."
    )
    # Mandatorios
    p.add_argument("-s", "--source", required=True, help="Ruta absoluta de origen.")
    p.add_argument("-d", "--destination", required=True, help="Ruta absoluta de destino.")
    p.add_argument("-w", "--width", required=True, type=int, help="Tamaño final (px) del lado (ancho=alto).")
    p.add_argument("-f", "--output_format", required=True, choices=["jpg", "png"], help="Formato de salida: jpg o png.")
    p.add_argument("-c", "--output_color", default="ffffff", help="Color de fondo en hex (por defecto ffffff).")
    # Opcionales
    p.add_argument("-r", "--recursive", action="store_true", help="Procesar recursivamente subcarpetas.")
    p.add_argument("-m", "--mirror_destination", action="store_true",
                   help="Replicar la misma estructura de carpetas dentro del destino.")
    p.add_argument("-ef", "--exclude_format", default="",
                   help="Excluir extensiones separadas por coma, ej: webp,jpg")
    # (Colisión resuelta) se mantiene la forma larga especificada y se añade -x:
    p.add_argument("-x", "--exclude_filenames", default="",
                   help="Excluir archivos que contengan estas cadenas (coma), ej: con_fondo,sin_fondo")

    p.add_argument("-q", "--output_quality", type=int, default=10,
                   help="Calidad 1–10 (solo JPG/PNG). Por defecto 10 (máxima).")
    return p.parse_args()

def quality_maps(fmt, q10):
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
    name_lower = file.name.lower()
    ext = file.suffix.lower().lstrip(".")
    if ext in exclude_exts:
        return True
    for sub in exclude_substrings:
        if sub and sub in name_lower:
            return True
    return False

def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)

def pad_to_square(img: Image.Image, target: int, bg_rgb):
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
