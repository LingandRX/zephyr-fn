#!/usr/bin/env python3
"""Prepare a clean fnpack staging tree and verify/finalize the produced .fpk.

fnpack packages everything under app/ into app.tgz and does not honor .gitignore.
Windows venv/symlinks and CRLF shell scripts are stripped here so the NAS
installer can extract and run the package.
"""
from __future__ import annotations

import argparse
import io
import os
import re
import shutil
import sys
import tarfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STAGE = REPO_ROOT / ".tmp" / "fpk-stage"

IGNORE_DIR_NAMES = {
    ".git",
    ".idea",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    ".vscode",
    "__pycache__",
    "env",
    "instance",
    "node_modules",
    "venv",
}
IGNORE_FILE_NAMES = {
    ".DS_Store",
    ".gitignore",
    "Desktop.ini",
    "Thumbs.db",
    "REFACTORING.md",
}
IGNORE_SUFFIXES = {
    ".db",
    ".db-shm",
    ".db-wal",
    ".log",
    ".pyc",
    ".pyo",
    ".swp",
}
FORBIDDEN_APP_PARTS = (
    ".idea",
    ".venv",
    "__pycache__",
    "node_modules",
    "site-packages",
)
TEXT_ROOTS = ("cmd", "config", "wizard")
TEXT_NAMES = {"manifest", "config"}
MAX_APP_ENTRIES = 8000
MAX_APP_TGZ_BYTES = 40 * 1024 * 1024
MAX_SYMLINKS = 0

STAGE_TOP_LEVEL = (
    "manifest",
    "ICON.PNG",
    "ICON_256.PNG",
    "cmd",
    "config",
    "wizard",
    "app",
)


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


def read_appname(manifest: Path) -> str:
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if line.startswith("appname="):
            return line.split("=", 1)[1].strip()
    return "app"


def read_version(manifest: Path) -> str:
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if line.startswith("version="):
            return line.split("=", 1)[1].strip()
    return ""


def is_ignored_file(path: Path) -> bool:
    name = path.name
    if name in IGNORE_FILE_NAMES:
        return True
    if name.startswith("._"):
        return True
    suffix = path.suffix.lower()
    if suffix in IGNORE_SUFFIXES:
        return True
    if name.endswith(".db-shm") or name.endswith(".db-wal"):
        return True
    return False


def should_normalize(rel: Path) -> bool:
    if rel.parts and rel.parts[0] in TEXT_ROOTS:
        return True
    if rel.name in TEXT_NAMES:
        return True
    return rel.suffix.lower() == ".sh"


def write_lf_text(src: Path, dst: Path) -> None:
    data = src.read_bytes()
    if b"\0" in data[:8192]:
        dst.write_bytes(data)
        return
    text = data.decode("utf-8-sig")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if text and not text.endswith("\n"):
        text += "\n"
    dst.write_bytes(text.encode("utf-8"))


def copy_filtered_tree(src: Path, dst: Path, rel_base: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for entry in src.iterdir():
        rel = rel_base / entry.name
        if entry.is_symlink():
            eprint(f"    skip symlink: {rel.as_posix()}")
            continue
        if entry.is_dir():
            if entry.name in IGNORE_DIR_NAMES:
                eprint(f"    skip dir: {rel.as_posix()}")
                continue
            copy_filtered_tree(entry, dst / entry.name, rel)
            continue
        if not entry.is_file():
            eprint(f"    skip special: {rel.as_posix()}")
            continue
        if is_ignored_file(entry):
            eprint(f"    skip file: {rel.as_posix()}")
            continue
        target = dst / entry.name
        if should_normalize(rel):
            write_lf_text(entry, target)
        else:
            shutil.copy2(entry, target)


def bump_manifest_file(path: Path) -> tuple[str, str] | None:
    content = path.read_text(encoding="utf-8")
    state = {"old": "", "new": ""}

    def repl(match: re.Match[str]) -> str:
        old_ver = match.group(1).strip()
        parts = old_ver.split(".")
        try:
            parts[-1] = str(int(parts[-1]) + 1)
        except ValueError:
            parts.append("1")
        new_ver = ".".join(parts)
        state["old"] = old_ver
        state["new"] = new_ver
        return f"version={new_ver}"

    new_content, count = re.subn(
        r"^version=(.+)$", repl, content, count=1, flags=re.MULTILINE
    )
    if count == 0:
        eprint("    警告：manifest 中未找到 version= 字段，跳过自增")
        return None
    path.write_text(new_content, encoding="utf-8")
    eprint(f"    暂存版本号: {state['old']} -> {state['new']}（打包成功后才写回仓库）")
    return state["old"], state["new"]


def prepare(stage: Path, bump: bool = False) -> Path:
    if not (REPO_ROOT / "manifest").is_file():
        raise SystemExit("错误：仓库根目录缺少 manifest")
    www = REPO_ROOT / "app" / "www" / "index.html"
    if not www.is_file():
        raise SystemExit("错误：缺少 app/www/index.html，请先运行 build.sh / build.ps1")

    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)

    for name in STAGE_TOP_LEVEL:
        src = REPO_ROOT / name
        if not src.exists():
            raise SystemExit(f"错误：缺少打包必需路径 {name}")
        if src.is_file():
            rel = Path(name)
            if should_normalize(rel):
                write_lf_text(src, stage / name)
            else:
                shutil.copy2(src, stage / name)
        else:
            copy_filtered_tree(src, stage / name, Path(name))

    flag = bumped_path(stage)
    if flag.exists():
        flag.unlink()
    if bump:
        bumped = bump_manifest_file(stage / "manifest")
        if bumped:
            flag.write_text(f"{bumped[0]}->{bumped[1]}\n", encoding="utf-8")
    else:
        eprint(f"    保持版本号: {read_version(stage / 'manifest')}")

    vendor_flask = stage / "app" / "backend" / "vendor" / "manylinux2014_x86_64" / "flask"
    if not vendor_flask.is_dir():
        raise SystemExit(
            "错误：缺少 app/backend/vendor/manylinux2014_x86_64（请先运行 tools/vendor_deps.py）"
        )

    stamp_path(stage).write_text("ok\n", encoding="utf-8")
    eprint(f"==> 已生成干净打包目录: {stage}")
    return stage


def stamp_path(stage: Path) -> Path:
    return stage.parent / f"{stage.name}.stamp"


def bumped_path(stage: Path) -> Path:
    return stage.parent / f"{stage.name}.bumped"


def commit_version(stage: Path) -> None:
    flag = bumped_path(stage)
    if not flag.exists():
        return
    src = stage / "manifest"
    if not src.is_file():
        return
    shutil.copyfile(src, REPO_ROOT / "manifest")
    eprint(f"==> 已写回仓库版本号: {read_version(src)}")
    try:
        flag.unlink()
    except OSError:
        pass


def iter_fpk_candidates(stage: Path) -> list[Path]:
    found: list[Path] = []
    seen: set[Path] = set()
    for root in (stage, REPO_ROOT, Path.cwd()):
        if not root.exists():
            continue
        for item in root.glob("*.fpk"):
            resolved = item.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            found.append(item)
    return found


def newest_fpk(stage: Path) -> Path:
    staged = [p for p in stage.glob("*.fpk") if p.is_file()]
    if staged:
        staged.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return staged[0]

    stamp = stamp_path(stage)
    stamp_mtime = stamp.stat().st_mtime if stamp.exists() else 0.0
    candidates = []
    for item in iter_fpk_candidates(stage):
        try:
            mtime = item.stat().st_mtime
        except OSError:
            continue
        if mtime + 0.001 < stamp_mtime:
            continue
        candidates.append((mtime, item))
    if not candidates:
        found = iter_fpk_candidates(stage)
        detail = "无" if not found else ", ".join(
            f"{p} (mtime 早于本次 prepare)" for p in found
        )
        raise SystemExit(
            "错误：未找到本次 fnpack 产出的 .fpk（请确认 fnpack build 已成功）。"
            f" 已扫描: {detail}"
        )
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def is_windows_link_target(linkname: str) -> bool:
    if "\\" in linkname:
        return True
    if len(linkname) >= 3 and linkname[1] == ":" and linkname[0].isalpha():
        return True
    return False


def inspect_app_tgz(data: bytes) -> list[str]:
    errors: list[str] = []
    if len(data) > MAX_APP_TGZ_BYTES:
        errors.append(f"app.tgz 过大（{len(data)} bytes），通常说明打进了 venv 或其它无关文件")
    try:
        inner = tarfile.open(fileobj=io.BytesIO(data), mode="r:*")
    except tarfile.TarError as exc:
        return [f"app.tgz 不是合法 tar/gzip: {exc}"]

    members = inner.getmembers()
    if len(members) > MAX_APP_ENTRIES:
        errors.append(f"app.tgz 条目过多（{len(members)}），上限 {MAX_APP_ENTRIES}")

    names = [m.name.replace("\\", "/") for m in members]
    if not any(name == "www/index.html" or name.endswith("/www/index.html") for name in names):
        errors.append("app.tgz 缺少 www/index.html（前端未构建或未同步）")
    if not any("backend/" in name and name.endswith(".py") for name in names):
        errors.append("app.tgz 缺少 backend Python 源码")
    if not any(name.endswith("vendor/manylinux2014_x86_64/flask/__init__.py") for name in names):
        errors.append("app.tgz 缺少 Linux x86_64 vendor（请先运行 tools/vendor_deps.py）")
    if any("/vendor/" in name and (name.endswith(".pyd") or "win32" in name.lower()) for name in names):
        errors.append("app.tgz vendor 含 Windows 二进制，飞牛无法导入")

    symlink_count = 0
    for member in members:
        name = member.name.replace("\\", "/")
        parts = set(name.split("/"))
        if parts & set(FORBIDDEN_APP_PARTS) or any(p in name for p in FORBIDDEN_APP_PARTS):
            errors.append(f"app.tgz 含禁止路径: {name}")
        if member.issym() or member.islnk():
            symlink_count += 1
            if is_windows_link_target(member.linkname):
                errors.append(
                    f"app.tgz 含 Windows 符号链接: {name} -> {member.linkname}"
                )
    if symlink_count > MAX_SYMLINKS:
        errors.append(f"app.tgz 含 {symlink_count} 条符号/硬链接（飞牛解压常因此失败）")

    # de-dup while keeping order
    unique: list[str] = []
    seen_err: set[str] = set()
    for item in errors:
        if item in seen_err:
            continue
        seen_err.add(item)
        unique.append(item)
    if len(unique) > 12:
        extra = len(unique) - 12
        unique = unique[:12] + [f"... 另外 {extra} 条类似问题"]
    return unique


def verify_fpk(fpk: Path) -> None:
    if not fpk.is_file():
        raise SystemExit(f"错误：找不到 {fpk}")
    try:
        outer = tarfile.open(fpk, "r:gz")
    except tarfile.TarError as exc:
        raise SystemExit(f"错误：{fpk.name} 不是合法 tar.gz: {exc}") from exc

    names = [m.name.replace("\\", "/") for m in outer.getmembers()]
    required = ["app.tgz", "manifest", "cmd/main", "ICON.PNG"]
    missing = [name for name in required if name not in names]
    if missing:
        raise SystemExit(f"错误：fpk 缺少 {', '.join(missing)}")

    app_member = outer.getmember("app.tgz")
    data = outer.extractfile(app_member).read()
    errors = inspect_app_tgz(data)
    if errors:
        eprint(f"错误：{fpk.name} 校验失败：")
        for item in errors:
            eprint(f"  - {item}")
        raise SystemExit(1)

    inner = tarfile.open(fileobj=io.BytesIO(data), mode="r:*")
    files = [m for m in inner.getmembers() if m.isfile()]
    eprint(
        f"==> 校验通过: {fpk.name}  "
        f"({fpk.stat().st_size} bytes, app.tgz {len(data)} bytes, "
        f"{len(files)} files)"
    )


def patch_outer_modes(src: Path, dst: Path) -> None:
    tmp = dst.with_name(dst.name + ".rewriting")
    if tmp.exists():
        tmp.unlink()
    with tarfile.open(src, "r:gz") as inn:
        with tarfile.open(tmp, "w:gz", format=tarfile.USTAR_FORMAT, compresslevel=9) as out:
            for member in inn.getmembers():
                info = member
                name = info.name.replace("\\", "/")
                info.name = name
                info.uid = 0
                info.gid = 0
                info.uname = ""
                info.gname = ""
                if info.isdir():
                    info.mode = 0o755
                    out.addfile(info)
                    continue
                if info.isfile():
                    payload = inn.extractfile(member).read()
                    if name.startswith("cmd/") and name != "cmd/":
                        info.mode = 0o755
                    else:
                        info.mode = 0o644
                    info.size = len(payload)
                    out.addfile(info, io.BytesIO(payload))
                    continue
                out.addfile(info)
    os.replace(tmp, dst)


def finalize(stage: Path, skip_verify: bool) -> Path:
    src = newest_fpk(stage)
    staged_manifest = stage / "manifest"
    appname = read_appname(staged_manifest if staged_manifest.is_file() else REPO_ROOT / "manifest")
    dest = REPO_ROOT / f"{appname}.fpk"
    eprint(f"==> 规范化 fpk 权限: {src} -> {dest}")
    if src.resolve() == dest.resolve():
        patch_outer_modes(src, dest)
    else:
        patch_outer_modes(src, dest)
        if src.parent.resolve() == stage.resolve():
            try:
                src.unlink()
            except OSError:
                pass
    if not skip_verify:
        verify_fpk(dest)
    commit_version(stage)
    print(dest)
    return dest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="fnOS 打包暂存与校验")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_prep = sub.add_parser("prepare", help="生成干净的 fnpack 源目录")
    p_prep.add_argument("--out", type=Path, default=DEFAULT_STAGE)
    p_prep.add_argument(
        "--bump",
        action="store_true",
        help="仅在暂存目录自增 version，打包成功后才写回仓库 manifest",
    )

    p_ver = sub.add_parser("verify", help="校验已生成的 .fpk")
    p_ver.add_argument("fpk", type=Path)

    p_fin = sub.add_parser("finalize", help="定位本次 .fpk，修正权限并校验")
    p_fin.add_argument("--stage", type=Path, default=DEFAULT_STAGE)
    p_fin.add_argument("--skip-verify", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.cmd == "prepare":
        stage = prepare(args.out.resolve(), bump=args.bump)
        print(stage)
        return
    if args.cmd == "verify":
        verify_fpk(args.fpk)
        return
    if args.cmd == "finalize":
        skip = args.skip_verify or os.environ.get("SKIP_VERIFY") == "1"
        finalize(args.stage.resolve(), skip_verify=skip)
        return
    raise SystemExit(f"未知命令: {args.cmd}")


if __name__ == "__main__":
    main()
