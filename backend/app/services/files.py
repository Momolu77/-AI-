import hashlib
import os
import tempfile
from pathlib import Path


def digest(data: str | bytes):
    return hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()


def atomic_write(path: Path, data: str | bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = data.encode("utf-8") if isinstance(data, str) else data
    fd, name = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def resolve_ref(root: Path, ref: str):
    target = (root / ref).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError("非法文件引用")
    return target
