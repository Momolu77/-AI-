import os
from contextlib import contextmanager


@contextmanager
def data_lock(root):
    """One API or maintenance writer per data directory; released by OS on crashes."""
    root.mkdir(parents=True, exist_ok=True)
    stream = (root / "runtime.lock").open("a+b")
    stream.seek(0, os.SEEK_END)
    if stream.tell() == 0:
        stream.write(b"0")
        stream.flush()
    stream.seek(0)
    locked = False
    try:
        if os.name == "nt":
            import msvcrt

            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise RuntimeError(
                    "数据目录正在使用。请停止本地后端后再执行备份，或为服务指定独立数据目录。"
                ) from None
        else:
            import fcntl

            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        locked = True
        yield
    finally:
        if locked:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)
        stream.close()
