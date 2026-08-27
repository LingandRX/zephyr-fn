"""文件与目录 IO 辅助工具函数。"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any


def fsync_directory(directory: Path) -> None:
    """尽力持久化目录项；Windows/部分文件系统不支持时不抛异常。"""
    try:
        fd = os.open(str(directory), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except (OSError, ValueError):
        pass


def atomic_write_json(path: Path, data: Any) -> None:
    """原子化写入 JSON 文件并确保持久化落盘。"""
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        encoded = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        with temp_path.open("wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        fsync_directory(path.parent)
    finally:
        temp_path.unlink(missing_ok=True)
