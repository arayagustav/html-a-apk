#!/usr/bin/env python3
"""Ajusta el proyecto Android generado: nombre, versión, colores, orientación e iconos."""
import os
import re
import shutil
import sys
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, os.path.dirname(__file__))
from common import effective_config  # noqa: E402

DENSITIES = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]


def sub_file(path, pattern, repl, count=1, flags=0):
    if not path.is_file():
        print(f"  (no existe {path.name}, se omite)")
        return False
    text = path.read_text(encoding="utf-8")
    new, n = re.subn(pattern, repl, text, count=count, flags=flags)
    if n:
        path.write_text(new, encoding="utf-8")
    else:
        print(f"  (patrón no encontrado en {path.name}: {pattern[:40]})")
    return bool(n)


def initials(name):
    words = [w for w in re.split(r"\s+", name.strip()) if w]
    if not words:
        return "A"
    if len(words) == 1:
        return words[0][:2].upper()
    return (words[0][0] + words[1][0]).upper()


def load_font(size):
    from PIL import ImageFont

    for p in FONT_PATHS:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def base_icon(job, cfg, size=512):
    from PIL import Image, ImageDraw

    uploaded = job / "icon.png"
    if uploaded.is_file():
        try:
            im = Image.open(uploaded).convert("RGBA")
            side = min(im.size)
            left, top = (im.width - side) // 2, (im.height - side) // 2
            return im.crop((left, top, left + side, top + side)).resize(
                (size, size), Image.LANCZOS
            )
        except Exception as exc:  # noqa: BLE001
            print("  (icono subido inválido, uso uno generado):", exc)
    im = Image.new("RGBA", (size, size), cfg["theme_hex"])
    d = ImageDraw.Draw(im)
    text = initials(cfg["name"])
    font = load_font(int(size * 0.47))
    box = d.textbbox((0, 0), text, font=font)
    w, h = box[2] - box[0], box[3] - box[1]
    d.text(((size - w) / 2 - box[0], (size - h) / 2 - box[1]), text, font=font, fill="white")
    return im


def write_icons(job, cfg, res):
    from PIL import Image, ImageDraw

    S = 512
    im = base_icon(job, cfg, S)
    square = Image.new("L", (S, S), 0)
    ImageDraw.Draw(square).rounded_rectangle([0, 0, S - 1, S - 1], radius=int(S * 0.22), fill=255)
    circle = Image.new("L", (S, S), 0)
    ImageDraw.Draw(circle).ellipse([0, 0, S - 1, S - 1], fill=255)

    def masked(mask):
        out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        out.paste(im, (0, 0), mask)
        return out

    sq, rd = masked(square), masked(circle)
    # Quitamos los iconos adaptativos para que Android use estos PNG en todas las versiones.
    shutil.rmtree(res / "mipmap-anydpi-v26", ignore_errors=True)
    for dens, px in DENSITIES.items():
        folder = res / f"mipmap-{dens}"
        folder.mkdir(parents=True, exist_ok=True)
        sq.resize((px, px), Image.LANCZOS).save(folder / "ic_launcher.png")
        rd.resize((px, px), Image.LANCZOS).save(folder / "ic_launcher_round.png")
        (folder / "ic_launcher_foreground.png").unlink(missing_ok=True)


def main():
    job, proj = Path(sys.argv[1]), Path(sys.argv[2])
    version_code, version_name = sys.argv[3], sys.argv[4]
    cfg = effective_config(job)
    android = proj / "android"
    app = android / "app"
    res = app / "src/main/res"
    name_xml = escape(cfg["name"])

    # Nombre visible
    strings = res / "values/strings.xml"
    sub_file(strings, r'(<string name="app_name">).*?(</string>)', rf"\g<1>{name_xml}\g<2>")
    sub_file(strings, r'(<string name="title_activity_main">).*?(</string>)', rf"\g<1>{name_xml}\g<2>")

    # Versión (necesaria para poder actualizar encima de una instalación previa)
    gradle = app / "build.gradle"
    sub_file(gradle, r"versionCode\s+\d+", f"versionCode {int(version_code)}")
    sub_file(gradle, r'versionName\s+"[^"]*"', f'versionName "{version_name}"')

    # Color del tema
    colors = res / "values/colors.xml"
    if colors.is_file():
        hexv = cfg["theme_hex"]
        for key in ("colorPrimary", "colorPrimaryDark", "colorAccent"):
            sub_file(colors, rf'(<color name="{key}">).*?(</color>)', rf"\g<1>{hexv}\g<2>")

    # Manifest: orientación, http y permisos de red
    manifest = app / "src/main/AndroidManifest.xml"
    if cfg["orientation"] in ("portrait", "landscape"):
        sub_file(manifest, r"(<activity\b)", rf'\1 android:screenOrientation="{cfg["orientation"]}"')
    if cfg.get("type") == "url" and str(cfg.get("url", "")).startswith("http://"):
        sub_file(manifest, r"(<application\b)", r'\1 android:usesCleartextTraffic="true"')
    if manifest.is_file() and "ACCESS_NETWORK_STATE" not in manifest.read_text(encoding="utf-8"):
        sub_file(
            manifest,
            r"(</manifest>)",
            '    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />\n\\1',
        )

    # Memoria para Gradle
    props = android / "gradle.properties"
    if props.is_file():
        text = props.read_text(encoding="utf-8")
        text = re.sub(r"^org\.gradle\.jvmargs=.*$", "", text, flags=re.M)
        props.write_text(
            text.rstrip() + "\norg.gradle.jvmargs=-Xmx3g -Dfile.encoding=UTF-8\n", encoding="utf-8"
        )

    write_icons(job, cfg, res)
    print(f"Android ajustado: {cfg['name']} v{version_name} ({version_code}), tema {cfg['theme_hex']}")


if __name__ == "__main__":
    main()
