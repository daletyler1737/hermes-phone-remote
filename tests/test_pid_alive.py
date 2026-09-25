# -*- coding: utf-8 -*-
"""_pid_alive 的最小自检：死 pid 不许抛异常（Windows 上 os.kill(pid,0) 会抛 SystemError）。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dashboard"))
import plugin_api as api


def main() -> int:
    assert api._pid_alive(os.getpid()) is True, "本进程应存活"
    for dead in (0, -1, 999999):
        assert api._pid_alive(dead) is False, "pid=%r 应判为不存活且不抛异常" % (dead,)
    print("ok: pid 探活四项通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
