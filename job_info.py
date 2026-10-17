#!/usr/bin/env python3
"""Calcula versión, etiqueta y nombre del APK. Escribe build/job.env y GITHUB_ENV."""
import os
import re
import shlex
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from common import EMAIL_RE, effective_config, read_json  # noqa: E402


def main():
    job = Path(sys.argv[1])
    cfg = effective_config(job)
    if cfg.get("type") not in ("html", "zip", "url"):
        raise SystemExit("meta.json no existe o tiene un tipo inválido (html, zip o url).")
    history = read_json(job / "history.json", [])
    n = sum(1 for h in history if h.get("status") == "success") + 1
    slug = cfg["id"]
    mail = (os.environ.get("MAIL_TO_INPUT") or cfg.get("email") or "").strip()
    if not EMAIL_RE.match(mail):
        mail = ""
    values = {
        "SLUG": slug,
        "APP_NAME": cfg["name"],
        "SRC_TYPE": cfg["type"],
        "VERSION_N": str(n),
        "TAG": f"{slug}-v{n}",
        "APK_NAME": f"{slug}-v{n}.apk",
        "MAIL_TO": mail,
    }
    for k, v in values.items():
        if re.search(r"[\r\n]", v):
            raise SystemExit(f"Valor inválido en {k}")
    Path("build").mkdir(exist_ok=True)
    Path("build/job.env").write_text(
        "".join(f"{k}={shlex.quote(v)}\n" for k, v in values.items()), encoding="utf-8"
    )
    gh_env = os.environ.get("GITHUB_ENV")
    if gh_env:
        with open(gh_env, "a", encoding="utf-8") as fh:
            for k, v in values.items():
                fh.write(f"{k}={v}\n")
    print("Versión", n, "->", values["TAG"])


if __name__ == "__main__":
    main()
