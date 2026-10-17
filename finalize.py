#!/usr/bin/env python3
"""Guarda el resultado (result.json), el historial y la versión modificada por la IA."""
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from common import effective_config, read_json, write_json  # noqa: E402


def main():
    job = Path(sys.argv[1])
    if not (job / "meta.json").is_file():
        print("Sin meta.json: nada que guardar.")
        return
    cfg = effective_config(job)
    status = os.environ.get("STATUS", "failure")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    tag = os.environ.get("TAG", "")
    apk_name = os.environ.get("APK_NAME", "")
    history = read_json(job / "history.json", [])
    version = int(os.environ.get("VERSION_N") or (sum(h.get("status") == "success" for h in history) + 1))
    notes = os.environ.get("NOTES", "").strip()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    ai = read_json("build/ai_result.json")
    diag = read_json("build/diagnosis.json")
    warnings = read_json("build/warnings.json", [])
    apk_path = Path("build/out") / apk_name if apk_name else None
    size = apk_path.stat().st_size if apk_path and apk_path.is_file() else 0

    result = {
        "job_id": cfg["id"],
        "name": cfg["name"],
        "status": status,
        "version": version if status == "success" else None,
        "finished_at": now,
        "run_url": os.environ.get("RUN_URL", ""),
        "release_url": f"{server}/{repo}/releases/tag/{tag}" if status == "success" and repo and tag else "",
        "apk_url": f"{server}/{repo}/releases/download/{tag}/{apk_name}" if status == "success" and repo and tag else "",
        "apk_size": size,
        "notes": notes,
        "warnings": warnings,
        "ai_ok": ai.get("ok") if notes else None,
        "ai_answer": ai.get("answer", ""),
        "ai_error": ai.get("error", "") if notes else "",
        "ai_changed": ai.get("changed", []),
        "diagnosis": diag if status != "success" else {},
    }
    write_json(job / "result.json", result)

    history.append(
        {
            "date": now,
            "status": status,
            "version": result["version"],
            "notes": notes[:500],
            "ai_answer": result["ai_answer"][:500],
            "apk_url": result["apk_url"],
            "run_url": result["run_url"],
        }
    )
    write_json(job / "history.json", history[-50:])

    if Path("build/edited.flag").is_file() and Path("build/proj/www").is_dir():
        cur = job / "current"
        shutil.rmtree(cur, ignore_errors=True)
        shutil.copytree("build/proj/www", cur)
        (cur / ".rev").write_text(str(cfg.get("source_rev")), encoding="utf-8")
        print("Guardada la versión modificada para futuros cambios.")

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            if status == "success":
                fh.write(f"## ✅ {cfg['name']} v{version}\n\n[Descargar APK]({result['apk_url']})\n")
            else:
                fh.write(f"## ❌ No se pudo crear {cfg['name']}\n\n")
                for hint in diag.get("hints", []):
                    fh.write(f"- {hint}\n")
    print("Resultado guardado:", status)


if __name__ == "__main__":
    main()
