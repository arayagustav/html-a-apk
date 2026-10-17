"""Utilidades compartidas por los scripts de APK Factory."""
import json
import re
from pathlib import Path

COLORS = {
    "blue": "#2F80ED",
    "red": "#EB5757",
    "pink": "#F472B6",
    "purple": "#8B5CF6",
    "green": "#22C55E",
    "orange": "#F59E0B",
    "beige": "#D4B483",
    "grey": "#8E96A3",
}
ORIENTATIONS = {"auto", "portrait", "landscape"}
EMAIL_RE = re.compile(r"^[^@\s<>\"',;]+@[^@\s<>\"',;]+\.[^@\s<>\"',;]+$")


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {} if default is None else default


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def clean_name(value, default="Mi App"):
    value = re.sub(r"[\x00-\x1f\x7f<>&\"'`$\\]", "", str(value or "")).strip()
    return value[:30] or default


def app_id(slug):
    s = re.sub(r"[^a-z0-9]", "", str(slug).lower()) or "app"
    if s[0].isdigit():
        s = "a" + s
    return f"com.apkfactory.{s}"


def effective_config(job_dir):
    """meta.json (lo que eligió la persona) + overrides.json (lo que cambió la IA)."""
    job_dir = Path(job_dir)
    meta = read_json(job_dir / "meta.json")
    over = read_json(job_dir / "overrides.json")
    cfg = {**meta, **{k: v for k, v in over.items() if v}}
    cfg["id"] = meta.get("id") or job_dir.name
    cfg["name"] = clean_name(cfg.get("app_name") or cfg.get("name"))
    if cfg.get("orientation") not in ORIENTATIONS:
        cfg["orientation"] = "auto"
    theme = cfg.get("theme_color")
    if not (isinstance(theme, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", theme)):
        theme = COLORS.get(str(cfg.get("color", "")).lower(), COLORS["green"])
    cfg["theme_hex"] = theme
    return cfg
