#!/usr/bin/env python3
"""Aplica con IA (Claude) los cambios o reparaciones que la persona escribió.

Uso: ai_edit.py <job_dir> <www_dir> "<texto de la persona>"
Necesita el secreto ANTHROPIC_API_KEY. Escribe build/ai_result.json.
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from common import ORIENTATIONS, clean_name, read_json, write_json  # noqa: E402

API_URL = "https://api.anthropic.com/v1/messages"
MODEL = os.environ.get("AI_MODEL", "claude-sonnet-5-5")
TEXT_EXT = {".html", ".htm", ".js", ".css", ".json", ".svg", ".txt", ".md"}
MAX_FILE_CHARS = 250_000
MAX_TOTAL_CHARS = 400_000
ATTEMPTS = 3

SYSTEM = """You are the repair-and-edit engine of an app factory that turns web apps (HTML/CSS/JS) \
into Android APKs using Capacitor (the app runs inside an Android WebView, mostly offline, on phones).

The user (a Spanish speaker, not necessarily technical) describes a change or a problem. \
You receive the app's text files and must answer with ONE JSON object and nothing else:

{
  "answer": "1-4 sentences in Spanish telling the user what you did or what they should do",
  "edits": [{"path": "index.html", "find": "exact existing text", "replace": "new text"}],
  "new_files": [{"path": "extra.css", "content": "..."}],
  "config": {"theme_color": "#RRGGBB", "orientation": "auto|portrait|landscape", "app_name": "..."}
}

Rules:
- "edits": each "find" must match EXACTLY ONE place in that file (copy it character by character, \
including indentation). Use short but unique snippets; never rewrite whole files.
- All of "edits", "new_files" and "config" are optional. Omit what is not needed.
- If the user reports an error or a bug, find the cause in the code and fix it. If you cannot find \
the cause from the code, say so honestly in "answer" and suggest what to check.
- If the request is about installing the APK (e.g. "no se instala"), do not touch code: explain in \
"answer" the likely causes (allow installs from unknown sources, app of the same name signed \
differently must be uninstalled first, not enough storage, phone too old: needs Android 6+) \
and how to fix them.
- "config.theme_color" changes the Android status/toolbar colour and the default icon colour; \
"orientation" locks screen rotation; "app_name" renames the app on the phone (max 30 chars).
- Keep the existing code style and language. Do not add external dependencies or CDN links.
- Never include secrets, tracking or anything malicious. Refuse harmful requests in "answer".
- Output raw JSON only: no markdown fences, no commentary."""


def call_api(api_key, messages):
    body = json.dumps(
        {"model": MODEL, "max_tokens": 16000, "system": SYSTEM, "messages": messages}
    ).encode()
    headers = {
        "content-type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    last = None
    for attempt in range(4):
        req = urllib.request.Request(API_URL, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                data = json.loads(resp.read())
            return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "ignore")[:400]
            last = f"HTTP {exc.code}: {detail}"
            if exc.code not in (429, 500, 502, 503, 529):
                break
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
        time.sleep(4 * (attempt + 1))
    raise RuntimeError(last or "error desconocido llamando a la IA")


def collect(www):
    files, other, total = {}, [], 0
    for p in sorted(www.rglob("*")):
        rel = p.relative_to(www)
        if p.is_dir() or "vendor" in rel.parts:
            continue
        if p.suffix.lower() not in TEXT_EXT:
            other.append(str(rel))
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            other.append(str(rel))
            continue
        if len(text) > MAX_FILE_CHARS or total + len(text) > MAX_TOTAL_CHARS:
            other.append(f"{rel} (demasiado grande para mostrar)")
            continue
        files[str(rel).replace(os.sep, "/")] = text
        total += len(text)
    return files, other


def parse_json(text):
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def safe_rel(path):
    path = str(path or "").replace("\\", "/").lstrip("/")
    parts = path.split("/")
    if not path or ".." in parts or "vendor" in parts or Path(path).suffix.lower() not in TEXT_EXT:
        return None
    return path


def apply_to_memory(data, files):
    """Aplica en memoria. Devuelve (errores, archivos_cambiados)."""
    work = dict(files)
    errors = []
    for i, e in enumerate(data.get("edits") or [], 1):
        path = safe_rel(e.get("path"))
        find, repl = e.get("find"), e.get("replace")
        if path is None or path not in work:
            errors.append(f"Edición {i}: el archivo '{e.get('path')}' no existe.")
            continue
        if not isinstance(find, str) or not find or not isinstance(repl, str):
            errors.append(f"Edición {i}: 'find' o 'replace' inválidos.")
            continue
        n = work[path].count(find)
        if n != 1:
            errors.append(
                f"Edición {i}: el texto 'find' aparece {n} veces en {path} (debe aparecer exactamente 1). "
                f"Empieza con: {find[:80]!r}"
            )
            continue
        work[path] = work[path].replace(find, repl, 1)
    for nf in data.get("new_files") or []:
        path = safe_rel(nf.get("path"))
        content = nf.get("content")
        if path is None or not isinstance(content, str) or len(content) > 300_000:
            errors.append(f"Archivo nuevo inválido: {nf.get('path')!r}")
            continue
        work[path] = content
    changed = [p for p in work if work[p] != files.get(p)]
    return errors, work, changed


def merge_config(job, cfg):
    if not isinstance(cfg, dict):
        return {}
    clean = {}
    color = cfg.get("theme_color")
    if isinstance(color, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        clean["theme_color"] = color
    if cfg.get("orientation") in ORIENTATIONS:
        clean["orientation"] = cfg["orientation"]
    if isinstance(cfg.get("app_name"), str) and cfg["app_name"].strip():
        clean["app_name"] = clean_name(cfg["app_name"])
    if clean:
        over = read_json(job / "overrides.json")
        over.update(clean)
        write_json(job / "overrides.json", over)
    return clean


def main():
    job, www, notes = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3].strip()
    out = {"ok": False, "answer": "", "changed": [], "config": {}, "error": ""}
    Path("build").mkdir(exist_ok=True)

    def finish():
        write_json("build/ai_result.json", out)
        print(json.dumps(out, ensure_ascii=False)[:600])

    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        out["error"] = (
            "No hay clave de IA configurada (secreto ANTHROPIC_API_KEY), por eso tus cambios "
            "no se aplicaron. La app se construyó igual, sin modificar."
        )
        return finish()

    files, other = collect(www)
    listing = "\n".join(f'<file path="{p}">\n{t}\n</file>' for p, t in files.items())
    prompt = (
        f"<files>\n{listing}\n</files>\n"
        f"<other_files>{', '.join(other) or 'none'}</other_files>\n"
        f"<user_request>\n{notes[:6000]}\n</user_request>"
    )
    messages = [{"role": "user", "content": prompt}]

    for attempt in range(1, ATTEMPTS + 1):
        try:
            reply = call_api(key, messages)
        except Exception as exc:  # noqa: BLE001
            out["error"] = f"No pude hablar con la IA: {exc}"
            return finish()
        data = parse_json(reply)
        if data is None:
            feedback = "Tu respuesta no fue un objeto JSON válido. Responde SOLO con el JSON."
        else:
            errors, work, changed = apply_to_memory(data, files)
            if not errors:
                for rel in changed:
                    target = www / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(work[rel], encoding="utf-8")
                out.update(
                    ok=True,
                    answer=str(data.get("answer", ""))[:1200],
                    changed=changed,
                    config=merge_config(job, data.get("config")),
                )
                if changed:
                    Path("build/edited.flag").write_text("1")
                return finish()
            feedback = (
                "Algunas ediciones no se pudieron aplicar, no se guardó nada:\n- "
                + "\n- ".join(errors)
                + "\nVuelve a enviar el JSON completo con las ediciones corregidas."
            )
        print(f"Intento {attempt} falló: {feedback[:300]}")
        messages += [
            {"role": "assistant", "content": reply},
            {"role": "user", "content": feedback},
        ]

    out["error"] = "La IA no logró aplicar el cambio de forma segura. La app se construyó sin modificar."
    finish()


if __name__ == "__main__":
    main()
