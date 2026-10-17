#!/usr/bin/env python3
"""Explica en español por qué falló la creación del APK.

Uso: ai_diagnose.py build/build.log build/diagnosis.json
Primero usa reglas conocidas (siempre funciona). Si hay ANTHROPIC_API_KEY, agrega una explicación de la IA.
"""
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from common import write_json  # noqa: E402

MODEL = os.environ.get("AI_MODEL", "claude-sonnet-5-5")

RULES = [
    (r"No encontré (un archivo )?index\.html", "Tu ZIP no tiene un index.html. Renombrá tu página principal a index.html y volvé a subir el ZIP."),
    (r"ZIP|BadZipFile", "El ZIP parece dañado o inválido. Comprimilo de nuevo y subilo otra vez."),
    (r"Keystore was tampered|bad decrypt|password was incorrect|keystore", "La contraseña de firma (secreto SIGNING_PASSWORD) cambió o es incorrecta. Poné la misma contraseña que usaste la primera vez."),
    (r"Could not (resolve|GET|download)|Connection (reset|timed out)|UnknownHost|Read timed out|Network is unreachable", "Falló una descarga de internet en el servidor de GitHub (suele ser pasajero). Volvé a apretar Crear en unos minutos."),
    (r"Unsupported class file major version|invalid source release|requires Java", "Problema de versión de Java en el servidor. Avisá a quien mantiene esta herramienta."),
    (r"Duplicate class", "Hay librerías duplicadas en el proyecto Android. Probá con un ZIP más simple."),
    (r"AAPT|resource linking failed|Android resource", "Un recurso de Android es inválido (nombre o icono). Probá con otro nombre sin símbolos raros o con otro icono PNG."),
    (r"No space left", "Se llenó el disco del servidor. Probá con un ZIP más liviano."),
    (r"OutOfMemoryError|Java heap space", "La app es demasiado pesada para el servidor gratuito. Probá reducir imágenes o videos."),
    (r"Falta source|meta\.json|tipo inválido|Tipo de origen", "Faltan datos de la app en el repositorio. Volvé a crearla desde la interfaz."),
    (r"La dirección web debe empezar", "La dirección web debe empezar con http:// o https://"),
]

STAGES = {
    "validar": "al validar los datos de la app",
    "preparar": "al preparar tus archivos (HTML/ZIP/URL)",
    "ia": "al aplicar tus cambios con IA",
    "proyecto": "al crear el proyecto Android",
    "npm": "al instalar Capacitor",
    "android": "al generar la carpeta Android",
    "ajustes": "al ajustar nombre, icono y versión",
    "gradle": "al compilar la app",
    "firma": "al firmar el APK",
}


def call_ai(key, log_tail, stage):
    prompt = (
        "Eres el soporte técnico de una fábrica de APK de Android (Capacitor + Gradle en GitHub Actions). "
        "El usuario habla español y no es técnico. Lee el final del registro de compilación y responde en "
        "español, máximo 6 líneas: 1) causa más probable, 2) qué puede hacer la persona para arreglarlo. "
        "Sin jerga innecesaria, sin markdown.\n\n"
        f"Etapa que falló: {stage}\n\n<log>\n{log_tail}\n</log>"
    )
    body = json.dumps(
        {"model": MODEL, "max_tokens": 700, "messages": [{"role": "user", "content": prompt}]}
    ).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "content-type": "application/json",
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        data = json.loads(resp.read())
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()


def main():
    log_path, out_path = Path(sys.argv[1]), sys.argv[2]
    log = log_path.read_text(encoding="utf-8", errors="ignore") if log_path.is_file() else ""
    lines = log.splitlines()
    tail = "\n".join(lines[-150:])[-12000:]
    stage_file = Path("build/failed_stage")
    stage = stage_file.read_text().strip() if stage_file.is_file() else "desconocida"

    hints = []
    for pattern, message in RULES:
        if re.search(pattern, log, re.I) and message not in hints:
            hints.append(message)
    if not hints:
        hints.append(
            f"Falló {STAGES.get(stage, 'durante la creación')}. Abrí el registro de la ejecución "
            "(enlace en el mensaje) para ver el detalle, o escribí el problema en la casilla de cambios."
        )

    ai_text = ""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key and tail:
        try:
            ai_text = call_ai(key, tail, stage)
        except Exception as exc:  # noqa: BLE001
            print("Diagnóstico IA no disponible:", exc)

    write_json(out_path, {"stage": stage, "hints": hints[:4], "ai": ai_text})
    print("Diagnóstico:", hints[:4], ai_text[:200])


if __name__ == "__main__":
    main()
