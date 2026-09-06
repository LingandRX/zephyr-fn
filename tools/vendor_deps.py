#!/usr/bin/env python3
"""Download Linux cp312 wheels into app/backend/vendor for fnOS (python312).

Must not use the pack-machine's own pip target: Windows/macOS wheels cannot
run on the NAS. Cross-install manylinux wheels instead.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = REPO_ROOT / "app" / "backend" / "requirements.txt"
VENDOR_ROOT = REPO_ROOT / "app" / "backend" / "vendor"
PYTHON_VERSION = "312"

PLATFORMS = (
    "manylinux2014_x86_64",
    "manylinux2014_aarch64",
)

MARKER_PACKAGES = ("flask", "flask_sqlalchemy", "flask_migrate", "alembic")


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


def vendor_ok(dest: Path) -> bool:
    return all((dest / name).is_dir() for name in MARKER_PACKAGES)


def install_platform(platform: str) -> None:
    dest = VENDOR_ROOT / platform
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--target",
        str(dest),
        "--platform",
        platform,
        "--python-version",
        PYTHON_VERSION,
        "--implementation",
        "cp",
        "--only-binary",
        ":all:",
        "--upgrade",
        "--no-compile",
        "--disable-pip-version-check",
        "--no-warn-script-location",
        "-r",
        str(REQUIREMENTS),
    ]
    eprint(f"==> pip install --target {dest.name} ({platform}, cp{PYTHON_VERSION})")
    subprocess.run(cmd, check=True)

    # pip may drop launcher scripts; NAS only needs importable packages
    for extra in ("bin", "Scripts", "share", "include"):
        extra_dir = dest / extra
        if extra_dir.is_dir():
            shutil.rmtree(extra_dir)

    if not vendor_ok(dest):
        raise SystemExit(f"错误：{dest} 缺少 Flask 依赖，vendor 不完整")
    eprint(f"    完成: {dest}")


def main() -> None:
    parser = argparse.ArgumentParser(description="为 fnOS 预置 Linux vendor 依赖")
    parser.add_argument(
        "--platforms",
        default=",".join(PLATFORMS),
        help="逗号分隔的 pip --platform 值",
    )
    args = parser.parse_args()
    if not REQUIREMENTS.is_file():
        raise SystemExit(f"错误：找不到 {REQUIREMENTS}")

    VENDOR_ROOT.mkdir(parents=True, exist_ok=True)
    platforms = [item.strip() for item in args.platforms.split(",") if item.strip()]
    for platform in platforms:
        install_platform(platform)
    eprint("==> vendor 依赖已就绪（仅 Linux 轮子，供飞牛 python312 使用）")


if __name__ == "__main__":
    main()
