#!/usr/bin/env python3
"""Download Linux cp312 wheels into app/backend/vendor for fnOS (python312).

Must not use the pack-machine's own pip target: Windows/macOS wheels cannot
run on the NAS. Cross-install manylinux wheels instead.

Versions are resolved from uv.lock (the project lockfile) so that every build
produces identical wheels regardless of when it runs.  The loose constraints in
requirements.txt are used only as a fallback when uv.lock is absent.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = REPO_ROOT / "app" / "backend" / "requirements.txt"
UV_LOCK = REPO_ROOT / "uv.lock"
VENDOR_ROOT = REPO_ROOT / "app" / "backend" / "vendor"
PYTHON_VERSION = "312"

PLATFORMS = (
    "manylinux2014_x86_64",
    "manylinux2014_aarch64",
)

MARKER_PACKAGES = ("flask", "flask_sqlalchemy", "flask_migrate", "alembic")

# Runtime-only packages declared in pyproject.toml [project].dependencies.
# Used to walk the uv.lock dependency graph and collect the full closure.
RUNTIME_ROOTS = {"flask", "flask-sqlalchemy", "flask-migrate"}


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


def _parse_uv_lock(lock_path: Path) -> dict[str, str]:
    """Return {normalised-name: version} for every package in uv.lock."""
    packages: dict[str, str] = {}
    name = version = None
    for line in lock_path.read_text(encoding="utf-8").splitlines():
        if line == "[[package]]":
            name = version = None
        elif line.startswith("name = "):
            name = line.split("=", 1)[1].strip().strip('"')
        elif line.startswith("version = ") and name is not None:
            version = line.split("=", 1)[1].strip().strip('"')
            packages[re.sub(r"[-_.]+", "-", name).lower()] = version
            name = version = None
    return packages


def _collect_closure(lock_path: Path, roots: set[str]) -> set[str]:
    """Walk uv.lock and return the full transitive dependency closure of *roots*.

    Only follows ``dependencies`` blocks (not optional-dependencies / dev).
    Packages whose name normalises to one of the dev-only extras are excluded
    automatically because they never appear as a dependency of a runtime root.
    """
    # Build adjacency: name -> set of direct dep names
    adj: dict[str, set[str]] = {}
    current: str | None = None
    in_deps = False
    dep_re = re.compile(r'\{\s*name\s*=\s*"([^"]+)"')

    for line in lock_path.read_text(encoding="utf-8").splitlines():
        if line == "[[package]]":
            current = None
            in_deps = False
        elif line.startswith("name = ") and current is None:
            current = re.sub(r"[-_.]+", "-", line.split("=", 1)[1].strip().strip('"')).lower()
            adj.setdefault(current, set())
        elif line.strip() == "dependencies = [":
            in_deps = True
        elif in_deps:
            if line.strip() == "]":
                in_deps = False
            else:
                m = dep_re.search(line)
                if m and current:
                    dep = re.sub(r"[-_.]+", "-", m.group(1)).lower()
                    adj[current].add(dep)

    # BFS from roots
    visited: set[str] = set()
    queue = list(roots)
    while queue:
        node = queue.pop()
        if node in visited:
            continue
        visited.add(node)
        queue.extend(adj.get(node, set()))
    return visited


def resolve_pinned_requirements(lock_path: Path) -> list[str]:
    """Return a list of ``pkg==version`` strings for the runtime closure.

    Reads *lock_path* (uv.lock) and returns pinned specifiers for every
    package in the transitive closure of RUNTIME_ROOTS.  The result is
    suitable for passing directly to ``pip install`` instead of requirements.txt.
    """
    all_versions = _parse_uv_lock(lock_path)
    closure = _collect_closure(lock_path, RUNTIME_ROOTS)
    pinned: list[str] = []
    for pkg in sorted(closure):
        if pkg not in all_versions:
            raise SystemExit(f"错误：uv.lock 中找不到包 '{pkg}'，请先运行 'uv lock'")
        pinned.append(f"{pkg}=={all_versions[pkg]}")
    return pinned


def vendor_ok(dest: Path) -> bool:
    return all((dest / name).is_dir() for name in MARKER_PACKAGES)


def prune_vendor(dest: Path) -> None:
    """清理测试套件、字节码缓存、文档以及 dist-info 中非运行必需的文件，大幅减少小文件数量。"""
    removed_files = 0
    removed_dirs = 0

    # 1. 递归删除测试目录与 __pycache__
    for p in list(dest.rglob("*")):
        if not p.exists():
            continue
        if p.is_dir() and p.name in ("__pycache__", "testing", "tests", "test"):
            shutil.rmtree(p, ignore_errors=True)
            removed_dirs += 1
            continue

        if p.is_file():
            # 删除编译缓存、类型存根、说明文档
            if p.suffix.lower() in (".pyc", ".pyo", ".pyi"):
                p.unlink(missing_ok=True)
                removed_files += 1
                continue

            # dist-info 中仅保留 METADATA / entry_points.txt / top_level.txt
            if p.parent.name.endswith(".dist-info"):  # noqa: SIM102
                if p.name not in ("METADATA", "entry_points.txt", "top_level.txt"):
                    if p.is_dir():
                        shutil.rmtree(p, ignore_errors=True)
                        removed_dirs += 1
                    else:
                        p.unlink(missing_ok=True)
                        removed_files += 1

    # 删除 dist-info 内部可能残留的空目录（如 licenses 等）
    for dist in dest.glob("*.dist-info"):
        for sub in list(dist.iterdir()):
            if sub.is_dir():
                shutil.rmtree(sub, ignore_errors=True)
                removed_dirs += 1

    eprint(f"    瘦身完成: {dest.name} (清理了 {removed_dirs} 个目录, {removed_files} 个文件)")


def install_platform(platform: str, pinned: list[str]) -> None:
    dest = VENDOR_ROOT / platform
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    # Write a temporary requirements file with exact pinned versions so pip
    # does not resolve or upgrade anything beyond what uv.lock specifies.
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write("\n".join(pinned) + "\n")
        tmp_path = Path(tmp.name)

    try:
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
            "--no-deps",  # versions are already fully resolved from uv.lock
            "--no-compile",
            "--disable-pip-version-check",
            "--no-warn-script-location",
            "-r",
            str(tmp_path),
        ]
        eprint(f"==> pip install --target {dest.name} ({platform}, cp{PYTHON_VERSION})")
        eprint(f"    锁定版本: {', '.join(pinned)}")
        subprocess.run(cmd, check=True)
    finally:
        tmp_path.unlink(missing_ok=True)

    # pip may drop launcher scripts; NAS only needs importable packages
    for extra in ("bin", "Scripts", "share", "include"):
        extra_dir = dest / extra
        if extra_dir.is_dir():
            shutil.rmtree(extra_dir)

    prune_vendor(dest)

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

    # Resolve pinned versions from uv.lock for reproducible builds.
    if UV_LOCK.is_file():
        pinned = resolve_pinned_requirements(UV_LOCK)
        eprint(f"==> 从 uv.lock 解析到 {len(pinned)} 个锁定依赖")
    else:
        # Fallback: uv.lock absent (e.g. CI without lockfile), use requirements.txt.
        # This path allows --upgrade behaviour implicitly via loose constraints.
        if not REQUIREMENTS.is_file():
            raise SystemExit(f"错误：找不到 {REQUIREMENTS} 且 uv.lock 不存在")
        eprint(f"警告：未找到 uv.lock，回退到 {REQUIREMENTS}（版本不固定）")
        pinned = [
            line.strip()
            for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        ]

    VENDOR_ROOT.mkdir(parents=True, exist_ok=True)
    platforms = [item.strip() for item in args.platforms.split(",") if item.strip()]
    for platform in platforms:
        install_platform(platform, pinned)
    eprint("==> vendor 依赖已就绪（仅 Linux 轮子，供飞牛 python312 使用）")


if __name__ == "__main__":
    main()
