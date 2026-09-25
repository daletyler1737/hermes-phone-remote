"""「重启面板」的脱离式助手 —— 面板不能自己杀自己。

背景（实机踩过）：插件跑在 dashboard 进程里，点「重启面板」要杀的正是自己那把
PID；``_kill(os.getpid())`` 只能 return False（杀完自己，后面的代码就不会再跑了），
于是旧进程继续占着端口，新进程撞上 ``BACKEND_PORT_IN_USE`` —— 面板上看着"重启
成功"，实际什么都没换，改了密码也还是旧密码在生效。

所以把这件事交给本脚本：面板先 fork 出我（DETACHED，跟面板一起死的那种不算），
把 HTTP 响应发完，我再：
  1. 停掉旧的面板进程（含占着该端口的别的 PID）；
  2. 等端口真的空出来；
  3. 用同样的参数拉起新面板（剥掉指向 Electron app.asar 的 HERMES_WEB_DIST）。

用法（一般由 plugin_api._respawn_self 拉起，也可手动跑）::

    python dashboard_respawn.py --port 9119 --host 0.0.0.0 --old-pid 1234 [--wait 2] [--exe <hermes.exe>] [--log <file>]
"""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

STILL_ACTIVE = 259


def _alive(pid: int) -> bool:
    """PID 还活着吗。Windows 不能 os.kill(pid, 0)（那等于 TerminateProcess）。"""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        k = ctypes.windll.kernel32
        handle = k.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if not k.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == STILL_ACTIVE
        finally:
            k.CloseHandle(handle)
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def _kill(pid: int) -> bool:
    if pid <= 0 or pid == os.getpid():
        return False
    try:
        if os.name == "nt":
            subprocess.run(["powershell", "-NoProfile", "-Command",
                            "Stop-Process -Id %d -Force" % pid],
                           capture_output=True, timeout=25)
        else:
            os.kill(pid, 15)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def _listeners(port: int) -> list[int]:
    """还在监听该端口的 PID（Windows：PowerShell，退回 netstat）。"""
    if os.name == "nt":
        try:
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-NetTCPConnection -LocalPort %d -State Listen -ErrorAction SilentlyContinue).OwningProcess" % port],
                capture_output=True, text=True, timeout=25).stdout
            pids = sorted({int(x) for x in out.split() if x.strip().isdigit()})
            if pids:
                return pids
        except (OSError, subprocess.SubprocessError):
            pass
        try:
            out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True,
                                 timeout=25).stdout
        except (OSError, subprocess.SubprocessError):
            return []
        pids = []
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[1].rsplit(":", 1)[-1] == str(port) and parts[3].upper() == "LISTENING":
                pids.append(int(parts[4]))
        return sorted(set(pids))
    return []


def _port_busy(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket() as s:
        s.settimeout(1.0)
        return s.connect_ex((host, port)) == 0


def _wait(pred, seconds: float, step: float = 0.5) -> bool:
    end = time.time() + seconds
    while time.time() < end:
        if pred():
            return True
        time.sleep(step)
    return pred()


def _log(path: Path, text: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "ab") as fh:
            fh.write((text.rstrip("\n") + "\n").encode("utf-8", "replace"))
    except OSError:
        pass


def _dashboard_env() -> dict:
    """桌面版后端会把 HERMES_WEB_DIST 指到 Electron 的 app.asar/dist；继承给独立
    dashboard 后浏览器打开的是 Electron 前端（报 Desktop IPC bridge is unavailable）。
    剥掉它，让 CLI 用 web UI 的 dist。"""
    env = os.environ.copy()
    if "app.asar" in env.get("HERMES_WEB_DIST", "").replace("\\", "/"):
        env.pop("HERMES_WEB_DIST", None)
    return env


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--old-pid", type=int, default=0)
    ap.add_argument("--wait", type=float, default=2.0, help="先等一会儿，让面板把响应发完")
    ap.add_argument("--exe", default="", help="hermes 可执行文件；默认用同目录的 hermes")
    ap.add_argument("--log", default="")
    args = ap.parse_args()

    log = Path(args.log) if args.log else Path.home() / ".hermes" / "logs" / "dashboard-restart.log"
    exe = args.exe
    if not exe:
        name = "hermes.exe" if os.name == "nt" else "hermes"
        cand = Path(sys.executable).with_name(name)
        exe = str(cand) if cand.exists() else "hermes"

    _log(log, "--- %s respawn helper: old_pid=%d port=%d wait=%.1fs ---"
         % (time.strftime("%Y-%m-%d %H:%M:%S"), args.old_pid, args.port, args.wait))

    time.sleep(max(0.0, args.wait))          # 让面板先把 HTTP 响应写回浏览器

    if args.old_pid:
        _kill(args.old_pid)
        if not _wait(lambda: not _alive(args.old_pid), 20.0):
            _log(log, "respawn: 旧进程 %d 还活着，再杀一次" % args.old_pid)
            _kill(args.old_pid)
            _wait(lambda: not _alive(args.old_pid), 10.0)

    # 端口上还赖着别的（比如之前点重启留下的空壳实例）：一并清掉，否则新进程绑不上
    if not _wait(lambda: not _port_busy(args.port), 15.0):
        extra = [p for p in _listeners(args.port) if p != os.getpid()]
        if extra:
            _log(log, "respawn: 端口 %d 还被 %s 占着，清掉" % (args.port, extra))
            for pid in extra:
                _kill(pid)
            _wait(lambda: not _port_busy(args.port), 15.0)

    flags = 0
    if os.name == "nt":
        flags = (int(getattr(subprocess, "DETACHED_PROCESS", 0))
                 | int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
                 | int(getattr(subprocess, "CREATE_NO_WINDOW", 0)))
    with open(log, "ab") as fh:
        fh.write(("\n--- %s restart (by respawn helper) ---\n" % time.strftime("%Y-%m-%d %H:%M:%S")).encode("utf-8"))
        proc = subprocess.Popen(
            [exe, "dashboard", "--host", args.host, "--port", str(args.port), "--no-open", "--skip-build"],
            stdout=fh, stderr=fh, stdin=subprocess.DEVNULL,
            creationflags=flags, start_new_session=(os.name != "nt"),
            env=_dashboard_env(), close_fds=True,
        )
    _log(log, "respawn: 已拉起新面板 pid=%d（端口 %d）" % (proc.pid, args.port))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
