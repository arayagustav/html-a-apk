#!/usr/bin/env python3
"""Escribe package.json y capacitor.config.json del proyecto Android."""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from common import app_id, effective_config, write_json  # noqa: E402


def main():
    job = Path(sys.argv[1])
    proj = Path(sys.argv[2])
    cfg = effective_config(job)

    write_json(
        proj / "package.json",
        {
            "name": "apk-factory-app",
            "version": "1.0.0",
            "private": True,
            "dependencies": {
                "@capacitor/core": "^7.0.0",
                "@capacitor/android": "^7.0.0",
            },
            "devDependencies": {"@capacitor/cli": "^7.0.0"},
        },
    )

    conf = {
        "appId": app_id(cfg["id"]),
        "appName": cfg["name"],
        "webDir": "www",
        "server": {"androidScheme": "https"},
        "android": {"allowMixedContent": False},
    }
    if cfg.get("type") == "url":
        url = str(cfg["url"])
        conf["server"] = {
            "url": url,
            "cleartext": url.startswith("http://"),
            "allowNavigation": ["*"],
            "androidScheme": "https",
        }
    write_json(proj / "capacitor.config.json", conf)
    print("Proyecto:", conf["appId"], "-", conf["appName"])


if __name__ == "__main__":
    main()
