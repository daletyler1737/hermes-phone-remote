"""连接手机插件的后端 —— 「面板里改密码 / 重启面板」真正下手的地方。

为什么要有这个文件
------------------
面板（plugin.js）跑在桌面版渲染进程里，只能画界面：它碰不到 config.yaml，
也杀不掉进程。Hermes 给插件的后端通道是 ``ctx.rest`` → ``/api/plugins/phone-remote/``，
这条路走桌面版自己的 IPC 桥（同源、免 CORS），落点就是这个文件里的 ``router``。

为什么不在面板里直接 fetch ``/api/config``
-----------------------------------------
那是另一个源（浏览器页面 → dashboard），预检直接 401，响应里没有
``access-control-allow-origin``，走不通。

装到哪
------
``<HERMES_HOME>/plugins/phone-remote/dashboard/{manifest.json, plugin_api.py}``
并且 config.yaml 的 ``plugins.enabled`` 里要有 ``phone-remote``。
桌面版后端只在启动时 import 插件路由（``web_server.py`` 的
``_mount_plugin_api_routes``），所以装完要重启一次桌面版，
之后面板上的按钮就永久可用。
"""
from __future__ import annotations

import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

MIN_PASSWORD_LEN = 6
DEFAULT_PORT = 9119
DEFAULT_TTL_SECONDS = 12 * 60 * 60
START_WAIT_SECONDS = 45.0


class PasswordBody(BaseModel):
    password: str
    username: Optional[str] = None


class RestartBody(BaseModel):
    port: Optional[int] = None
    host: Optional[str] = None


# ─── 小工具 ───────────────────────────────────────────────────────────────
def _lan_ip() -> str:
    """本机在局域网里的 IP（UDP 探路，不发包）。"""
    for probe in ("223.5.5.5", "8.8.8.8"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect((probe, 80))
            ip = s.getsockname()[0]
            s.close()
            if not ip.startswith("127."):
                return ip
        except OSError:
            pass
    try:
        return socket.gethostbyname(socket.gethostname())
    except OSError:
        return "127.0.0.1"


def _port_open(port: int, host: str = "127.0.0.1", timeout: float = 1.0) -> bool:
    with socket.socket() as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0


def _hermes_exe() -> str:
    """优先用当前进程同目录的 hermes（后端就跑在 venv 里）。"""
    name = "hermes.exe" if os.name == "nt" else "hermes"
    cand = Path(sys.executable).with_name(name)
    if cand.exists():
        return str(cand)
    found = shutil.which("hermes")
    if found:
        return found
    raise HTTPException(500, detail="找不到 hermes 可执行文件，无法重启面板")


def _run(cmd: List[str], timeout: float = 25.0) -> str:
    """跑命令取输出；text=True 在 Windows 上遇到不可解码输出会给 None，统一兜成空串。"""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=timeout)
        return proc.stdout or ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _listeners(port: int) -> List[int]:
    """监听该端口的进程 PID（Windows 先问 PowerShell，再退回 netstat；其它平台走 lsof）。"""
    if os.name == "nt":
        out = _run([
            "powershell", "-NoProfile", "-Command",
            "(Get-NetTCPConnection -LocalPort %d -State Listen -ErrorAction SilentlyContinue).OwningProcess" % port,
        ])
        pids = sorted({int(x) for x in out.split() if x.strip().isdigit()})
        if pids:
            return pids
        out = _run(["netstat", "-ano", "-p", "TCP"])
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[0].upper() == "TCP" and parts[3].upper() == "LISTENING":
                if parts[1].rsplit(":", 1)[-1] == str(port):
                    try:
                        pids.append(int(parts[4]))
                    except ValueError:
                        pass
        return sorted(set(pids))
    out = _run(["lsof", "-nP", "-iTCP:%d" % port, "-sTCP:LISTEN", "-t"])
    return sorted({int(x) for x in out.split() if x.strip().isdigit()})
    try:
        out = subprocess.run(
            ["lsof", "-nP", "-iTCP:%d" % port, "-sTCP:LISTEN", "-t"],
            capture_output=True, text=True, timeout=20,
        ).stdout
        return [int(x) for x in out.split() if x.strip().isdigit()]
    except (OSError, subprocess.SubprocessError):
        return pids


def _kill(pid: int) -> bool:
    if pid == os.getpid():
        return False
    try:
        if os.name == "nt":
            # 不用 taskkill：参数经 MSYS/编码层容易被吃掉，实机踩过。PowerShell 按 PID 停最稳。
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Stop-Process -Id %d -Force" % pid],
                capture_output=True, timeout=25,
            )
        else:
            os.kill(pid, signal.SIGTERM)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def _log_path() -> Path:
    try:
        from hermes_cli.config import get_hermes_home

        base = get_hermes_home() / "logs"
    except Exception:
        base = Path.home() / ".hermes" / "logs"
    base.mkdir(parents=True, exist_ok=True)
    return base / "dashboard-restart.log"


def _dashboard_env() -> Dict[str, str]:
    """桌面版后端 env 里的 HERMES_WEB_DIST 指向 Electron 渲染层（app.asar/dist），
    继承给独立 dashboard 后，浏览器打开的就是 Electron 前端 → 报
    「Desktop IPC bridge is unavailable」。剥掉它，让 CLI 用 web UI 的 dist。"""
    env = os.environ.copy()
    if "app.asar" in env.get("HERMES_WEB_DIST", "").replace("\\", "/"):
        env.pop("HERMES_WEB_DIST", None)
    return env


def _start_dashboard(port: int, host: str) -> int:
    """后台拉一个 dashboard（不弹窗、关掉终端也活着）。返回 PID。"""
    flags = 0
    if os.name == "nt":
        flags = int(getattr(subprocess, "DETACHED_PROCESS", 0)) | int(
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )
    log = _log_path()
    with open(log, "ab") as fh:
        fh.write(("\n--- %s restart ---\n" % time.strftime("%Y-%m-%d %H:%M:%S")).encode("utf-8"))
        proc = subprocess.Popen(
            [_hermes_exe(), "dashboard", "--host", host, "--port", str(port), "--no-open", "--skip-build"],
            stdout=fh, stderr=fh, stdin=subprocess.DEVNULL,
            creationflags=flags, start_new_session=(os.name != "nt"),
            env=_dashboard_env(),
        )
    return proc.pid


def _hash_password(password: str) -> str:
    """复用官方 dashboard_auth/basic 的 hash（和 CLI 改出来的一模一样）。"""
    for loader in (
        lambda: __import__("plugins.dashboard_auth.basic", fromlist=["hash_password"]).hash_password,
        lambda: __import__("hermes_cli.main_dashboard", fromlist=["hash_password"]).hash_password,
    ):
        try:
            fn = loader()
        except Exception:
            continue
        if callable(fn):
            return str(fn(password))
    raise HTTPException(500, detail="拿不到官方的密码哈希函数（dashboard_auth/basic 未装？）")


def _basic_auth(config: Dict[str, Any]) -> Dict[str, Any]:
    dash = config.get("dashboard")
    if not isinstance(dash, dict):
        dash = config["dashboard"] = {}
    basic = dash.get("basic_auth")
    if not isinstance(basic, dict):
        basic = dash["basic_auth"] = {}
    return basic


# ─── 面板按钮调的三个接口 ──────────────────────────────────────────────────
@router.get("/status")
def status() -> Dict[str, Any]:
    """面板要显示的东西：账号、有没有设过密码、服务在不在跑、手机该扫哪个地址。"""
    from hermes_cli.config import load_config

    config = load_config() or {}
    dash = config.get("dashboard") if isinstance(config.get("dashboard"), dict) else {}
    basic = (dash.get("basic_auth") or {}) if isinstance(dash.get("basic_auth"), dict) else {}
    raw_port = str(dash.get("port") or "").strip()      # 端口在 dashboard.port，不在 basic_auth 里
    port = int(raw_port) if raw_port.isdigit() else DEFAULT_PORT
    ip = _lan_ip()
    return {
        "username": str(basic.get("username") or "admin"),
        "hash_set": bool(str(basic.get("password_hash") or "").strip()),
        "plaintext_set": bool(str(basic.get("password") or "").strip()),
        "session_ttl_seconds": basic.get("session_ttl_seconds"),
        "min_length": MIN_PASSWORD_LEN,
        "port": port,
        "running": _port_open(port),
        "lan_ip": ip,
        "url": "http://%s:%d/" % (ip, port),
    }


@router.get("/login-log")
def login_log() -> Dict[str, Any]:
    """谁连过 —— 桌面版自己的登录日志尾巴，验手机到底通没通。"""
    path = _log_path().with_name("dashboard-auth.log")
    out: Dict[str, Any] = {"path": str(path), "entries": []}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return out
    for line in lines[-60:]:
        line = line.strip()
        if not line:
            continue
        ok = "login_success" in line
        ip = ""
        for tok in line.split():
            if tok.startswith("ip="):
                ip = tok[3:]
        if ok or "invalid" in line or "failed" in line:
            out["entries"].append({"ok": ok, "ip": ip, "line": line})
    out["entries"] = out["entries"][-6:]
    return out


@router.post("/password")
def set_password(body: PasswordBody) -> Dict[str, Any]:
    """写 dashboard.basic_auth。

    坑：官方是 ``password_hash`` 优先，明文 ``password`` 只在 hash 为空时才被读。
    所以这里一次写全 —— hash 写入、明文清空 —— 否则面板改了密码手机还是能拿旧密码登。
    """
    from hermes_cli.config import load_config, save_config

    password = (body.password or "").strip()
    if len(password) < MIN_PASSWORD_LEN:
        raise HTTPException(400, detail="密码至少 %d 位" % MIN_PASSWORD_LEN)

    config = load_config() or {}
    basic = _basic_auth(config)
    username = (body.username or basic.get("username") or "admin").strip() or "admin"

    basic["username"] = username
    basic["password_hash"] = _hash_password(password)
    basic["password"] = ""          # 明文留空：hash 已经够用，留着等于多一份没人看的副本
    if not str(basic.get("secret") or "").strip():
        basic["secret"] = secrets.token_urlsafe(32)
    if not basic.get("session_ttl_seconds"):
        basic["session_ttl_seconds"] = DEFAULT_TTL_SECONDS

    try:
        save_config(config)
    except Exception as exc:
        raise HTTPException(500, detail="写 config.yaml 失败：%s" % exc)
    return {
        "ok": True,
        "username": username,
        "restart_required": True,   # 密码是 register() 时读进内存的，必须重启面板才生效
    }


@router.post("/restart")
def restart(body: RestartBody) -> Dict[str, Any]:
    """重启面板服务：杀掉占用端口的进程，再原地拉起一个。

    改完密码必须走这一步，否则旧密码在进程内存里继续有效。
    桌面版自己 → 请用面板上的「重启面板」而不是重启整个桌面版：
    这个接口只动 dashboard 进程。
    """
    port = int(body.port or 0) or DEFAULT_PORT
    host = (body.host or "0.0.0.0").strip() or "0.0.0.0"

    killed = [pid for pid in _listeners(port) if _kill(pid)]
    if killed:
        time.sleep(1.5)

    pid = _start_dashboard(port, host)

    healthy = False
    waited = 0.0
    while waited < START_WAIT_SECONDS:
        if _port_open(port):
            healthy = True
            break
        time.sleep(1.0)
        waited += 1.0

    result: Dict[str, Any] = {
        "ok": healthy,
        "port": port,
        "killed": killed,
        "pid": pid,
        "waited_seconds": round(waited, 1),
        "lan_url": "http://%s:%d/" % (_lan_ip(), port) if healthy else "",
        "log": str(_log_path()),
    }
    if not healthy:
        result["detail"] = "面板 45 秒内没起来，看日志尾部"
        try:
            tail = _log_path().read_text(encoding="utf-8", errors="replace").splitlines()[-15:]
            result["tail"] = "\n".join(tail)
        except OSError:
            pass
    return result
