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

import json
import os
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

MIN_PASSWORD_LEN = 12         # 面板是公网可达的（互联网模式），弱密码等于把整台机器送人


def password_problem(password: str):
    """密码策略：长度 + 四类字符。返回中文原因；合规返回 None。

    前端「随机密码」按同一套规则生成（src/plugin.template.js），改这里要一起改。
    """
    if len(password) < MIN_PASSWORD_LEN:
        return "密码至少 %d 位" % MIN_PASSWORD_LEN
    missing = []
    if not any(c.islower() for c in password):
        missing.append("小写字母")
    if not any(c.isupper() for c in password):
        missing.append("大写字母")
    if not any(c.isdigit() for c in password):
        missing.append("数字")
    if not any(not c.isalnum() for c in password):
        missing.append("符号")
    if missing:
        return "密码还要包含：" + "、".join(missing)
    return None


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
        # DETACHED_PROCESS=脱离控制台（关掉桌面版也活着）；CREATE_NO_WINDOW=连
        # 那一闪而过的黑窗口都不要（实机反馈：点「重启面板」不该弹终端）。
        flags = (
            int(getattr(subprocess, "DETACHED_PROCESS", 0))
            | int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
            | int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
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
    problem = password_problem(password)
    if problem:
        raise HTTPException(400, detail=problem)

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


# ─── 互联网模式：Cloudflare 快速隧道（公网访问）─────────────────────────────
# 做法与 dsh-web 的 dsh-remote-web-ui 同源：起一个 cloudflared quick tunnel，
# 从它的输出里抓 https://xxx.trycloudflare.com，面板拿这个地址出二维码。
# 免费隧道的地每次重启都换（cloudflare 的固有属性，dsh 那边也一样）——
# 所以面板上写清楚：手机收藏的那个地址会失效，重开一次扫新的即可。
TUNNEL_WAIT_SECONDS = 60.0
# 开一次公网链接自动活 2 小时 —— 忘了关是这类地址最大的风险，到点自己断，要续再点「延长」。
# ponytail: 固定 2 小时，真要可调再挪进 TunnelBody。
TUNNEL_TTL_SECONDS = 2 * 3600.0
TUNNEL_TTL_MAX_SECONDS = 72 * 3600.0   # 上限：前端最高档 72 小时，后端也兜一道


def _ttl_seconds(minutes: int) -> float:
    """面板选的开多久（分钟）；没选就用默认 2 小时。不给「永不」，地址不该长期挂着。"""
    if not minutes or minutes <= 0:
        return TUNNEL_TTL_SECONDS
    return min(float(minutes) * 60.0, TUNNEL_TTL_MAX_SECONDS)
_TUNNEL_URL_RE = re.compile(r"https://(?!api\.)[a-z0-9-]+\.trycloudflare\.com")
# cloudflared 会把控制面域名 api.trycloudflare.com 打在日志开头，先按这句提示定位再抓，
# 否则会把控制面当成隧道地址发给手机（真踩过：面板显示 https://api.trycloudflare.com）。
_TUNNEL: Dict[str, Any] = {"proc": None, "url": "", "port": 0, "expires_at": 0.0}
_TUNNEL_TIMER: Optional[threading.Timer] = None


def _arm_tunnel_timer(expires_at: float) -> None:
    """到点自己关隧道。面板重启过也照旧：认领时按剩下的时间重挂一次。"""
    global _TUNNEL_TIMER
    if _TUNNEL_TIMER is not None:
        _TUNNEL_TIMER.cancel()
    _TUNNEL_TIMER = threading.Timer(max(1.0, float(expires_at) - time.time()), _stop_tunnel)
    _TUNNEL_TIMER.daemon = True
    _TUNNEL_TIMER.start()


class TunnelBody(BaseModel):
    action: str = "start"          # start | stop | extend
    ttl_minutes: int = 0           # 0 = 用默认 2 小时
    port: Optional[int] = None


def _cloudflared_exe() -> str:
    """找现成的 cloudflared；找不到就直说丢一个 exe 进来（不自动下 30MB）。"""
    exe = "cloudflared.exe" if os.name == "nt" else "cloudflared"
    cands = [
        Path(__file__).with_name(exe),                                              # 插件自带
        Path.home() / ".cloudflared" / exe,
        Path(os.environ.get("APPDATA", "") or ".") / "dsh-desktop" / "bin" / exe,   # DSH Desktop 自带的那份
    ]
    found = shutil.which("cloudflared")
    if found:
        cands.append(Path(found))
    for c in cands:
        try:
            if c.is_file():
                return str(c)
        except OSError:
            continue
    raise HTTPException(
        500,
        detail="本机没有 cloudflared。装过 DSH Desktop 的话它自带一份；否则去 Cloudflare 官网下 "
               "cloudflared-windows-amd64.exe，改名 cloudflared.exe 放进插件目录（和 plugin_api.py 同一个文件夹），再点一次。",
    )


def _tunnel_url_in(text: str) -> str:
    """从 cloudflared 日志里挑出真正的公网地址。"""
    i = text.lower().find("your quick tunnel has been created")
    scope = text[i:] if i >= 0 else text
    m = _TUNNEL_URL_RE.search(scope)
    if not m and i >= 0:
        m = _TUNNEL_URL_RE.search(text)
    return m.group(0) if m else ""


def _tunnel_state_path() -> Path:
    return _log_path().with_name("phone-tunnel.json")


def _tunnel_log_path() -> Path:
    return _log_path().with_name("phone-tunnel.log")


def _pid_alive(pid: int) -> bool:
    if not pid or pid <= 0:
        return False
    if os.name == "nt":
        # Windows 上 os.kill(pid, 0) 探已死的 pid 会抛 SystemError（C 层异常没清干净，
        # 不是 OSError，catch 不住）—— 真踩过：认领隧道时把面板请求打成 500。
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        ctypes.windll.kernel32.CloseHandle(h)
        return True
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _tunnel_snapshot() -> Dict[str, Any]:
    """当前隧道状态。面板自己重启过（子进程还活着）时，靠小 json 认领它。"""
    proc = _TUNNEL.get("proc")
    if proc is not None and proc.poll() is None:
        return {"running": True, "url": _TUNNEL["url"], "pid": proc.pid, "port": _TUNNEL["port"],
                "expires_at": _TUNNEL.get("expires_at", 0.0)}
    try:
        saved = json.loads(_tunnel_state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"running": False, "url": "", "pid": 0, "port": 0}
    pid = int(saved.get("pid") or 0)
    if _pid_alive(pid):
        expires_at = float(saved.get("expires_at") or 0.0)
        if expires_at and time.time() >= expires_at:
            # 面板没在跑的那段时间就到点了：当场关掉，别让过期隧道悄悄留着。
            # 这里不能调 _stop_tunnel（它会再读快照，绕回这个分支）；直接杀。
            _TUNNEL.update(proc=None, url="", port=0, expires_at=0.0)
            try:
                _tunnel_state_path().unlink()
            except OSError:
                pass
            _kill(pid)
            return {"running": False, "url": "", "pid": 0, "port": 0, "expires_at": 0.0}
        _TUNNEL.update(proc=None, url=str(saved.get("url") or ""), port=int(saved.get("port") or 0), expires_at=expires_at)
        _arm_tunnel_timer(expires_at)
        return {"running": True, "url": _TUNNEL["url"], "pid": pid, "port": _TUNNEL["port"], "expires_at": expires_at}
    return {"running": False, "url": "", "pid": 0, "port": 0, "expires_at": 0.0}


def _stop_tunnel() -> Dict[str, Any]:
    global _TUNNEL_TIMER
    if _TUNNEL_TIMER is not None:
        _TUNNEL_TIMER.cancel()
        _TUNNEL_TIMER = None
    snap = _tunnel_snapshot()
    proc = _TUNNEL.get("proc")
    if proc is not None and proc.poll() is None:
        try:
            proc.kill()
        except OSError:
            pass
    elif snap.get("pid"):
        _kill(int(snap["pid"]))
    _TUNNEL.update(proc=None, url="", port=0, expires_at=0.0)
    try:
        _tunnel_state_path().unlink()
    except OSError:
        pass
    return {"ok": True, "running": False, "url": "", "pid": 0}


# ---------------------------------------------------------------------------
# 扫码配对（pair token）—— 「批准此手机」免密进面板
#
# 为什么要有反代：官方 auth gate 把插件路由全拦在登录之后，公网隧道域名下没有一个
# 「谁都能打开」的页面能给手机种 cookie。所以 /pair* 交给 tools/pair_proxy.py：
# 反代自己渲染「等待批准」页，批准后签发一个官方认的 session cookie，其它请求原样
# 透传给 dashboard（SSE / WebSocket 都不受影响）。
#
# token 一次性：每次「生成配对链接」都是新 token，用过即废、10 分钟不批也废
# （用户原话「每次 token 要变」）。
# ---------------------------------------------------------------------------

PAIR_PORT = 9121              # 反代只听 127.0.0.1，只有 cloudflared 连得到
PAIR_TTL_SECONDS = 600.0      # 配对链接有效期
PAIR_APPROVE_WINDOW = 120.0   # 批准后手机必须在这段时间内 claim
_PAIR: Dict[str, Any] = {"proc": None, "log": None}


def _pair_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".hermes")
    d = Path(base) / "hermes" / "phone-remote"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _pair_state_path() -> Path:
    return _pair_dir() / "pair.json"


def _pair_read() -> Dict[str, Any]:
    try:
        data = json.loads(_pair_state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _pair_write(state: Dict[str, Any]) -> Dict[str, Any]:
    p = _pair_state_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)
    return state


def _pair_script() -> Path:
    here = Path(__file__).resolve().parent
    for cand in (here / "tools" / "pair_proxy.py", here.parent / "tools" / "pair_proxy.py",
                 here / "pair_proxy.py"):
        if cand.is_file():
            return cand
    raise HTTPException(500, detail="插件里没有 pair_proxy.py（安装包不完整），重装一次插件")


def _pair_alive() -> bool:
    return _port_open(PAIR_PORT)


def _pair_log_path() -> Path:
    return _pair_dir() / "pair-proxy.log"


def _start_pair_proxy(port: int) -> None:
    """起配对反代；已经在跑（或端口已有人听）就不动它。"""
    proc = _PAIR.get("proc")
    if proc is not None and proc.poll() is None:
        return
    if _port_open(PAIR_PORT):
        _PAIR["proc"] = None
        return
    log = _pair_log_path()
    log.parent.mkdir(parents=True, exist_ok=True)
    flags = 0
    if os.name == "nt":
        flags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) | int(getattr(subprocess, "DETACHED_PROCESS", 0))
    env = dict(os.environ)
    env.update(HPR_PORT=str(PAIR_PORT), HPR_UPSTREAM="127.0.0.1:%d" % port, HPR_STATE=str(_pair_state_path()))
    with open(log, "ab") as fh:
        _PAIR["proc"] = subprocess.Popen(
            [sys.executable, str(_pair_script())], env=env, stdout=fh, stderr=fh,
            stdin=subprocess.DEVNULL, creationflags=flags)
    _PAIR["log"] = log
    waited = 0.0
    while waited < 8.0 and not _port_open(PAIR_PORT):
        time.sleep(0.25)
        waited += 0.25
    if not _port_open(PAIR_PORT):
        raise HTTPException(500, detail="配对反代没起来，看日志：%s" % log)


def _pair_snapshot() -> Dict[str, Any]:
    state = _pair_read()
    now = time.time()
    token = str(state.get("token") or "")
    status = str(state.get("status") or "") if token else "none"
    if token and status in ("pending", "approved") and float(state.get("expires") or 0) <= now:
        status = "expired"
    return {
        "status": status,
        "token_tail": ("…" + token[-4:]) if token else "",
        "ip": str(state.get("ip") or ""),
        "ua": str(state.get("ua") or ""),
        "created": float(state.get("created") or 0.0),
        "expires_at": float(state.get("expires") or 0.0),
        "approved_at": float(state.get("approved_at") or 0.0),
    }


class PairBody(BaseModel):
    action: str = "new"


@router.get("/pair")
def pair_status() -> Dict[str, Any]:
    snap = _tunnel_snapshot()
    out = _pair_snapshot()
    tunnel = str(snap.get("url") or "")
    out.update(ok=True, proxy=bool(_pair_alive()), port=PAIR_PORT, ttl_seconds=PAIR_TTL_SECONDS,
               tunnel=tunnel, tunnel_running=bool(snap.get("running")), log=str(_pair_log_path()))
    if out["status"] in ("pending", "approved") and tunnel:
        out["url"] = "%s/pair?t=%s" % (tunnel.rstrip("/"), _pair_read().get("token", ""))
    else:
        out["url"] = ""
    return out


@router.post("/pair")
def pair(body: PairBody) -> Dict[str, Any]:
    """生成 / 批准 / 拒绝 一次扫码配对。"""
    import secrets as _secrets  # noqa: PLC0415
    from hermes_cli.config import load_config  # noqa: PLC0415

    action = (body.action or "new").strip().lower()
    if action in ("approve", "deny", "cancel"):
        state = _pair_read()
        if not state.get("token"):
            raise HTTPException(400, detail="没有等着的配对请求：先点「生成配对链接」")
        if action != "approve":
            # deny 保留 token：手机那边要看到「已被拒绝」，而不是「链接失效」。
            # 状态不是 pending 就签不出 cookie（反代只在 approved 时签发），留着没风险。
            state.update(status="denied" if action == "deny" else "none")
            if action != "deny":
                state.pop("token", None)   # cancel：面板自己收尾，链接立刻作废
            _pair_write(state)
            return {"ok": True, "status": state["status"]}
        if float(state.get("expires") or 0) <= time.time():
            raise HTTPException(400, detail="这个配对链接已经过期了，重新生成一个")
        if state.get("status") != "pending":
            raise HTTPException(400, detail="这个配对链接已经用过了，重新生成一个")
        state.update(status="approved", approved_at=time.time(), expires=time.time() + PAIR_APPROVE_WINDOW)
        _pair_write(state)
        return {"ok": True, **{k: v for k, v in _pair_snapshot().items()}}

    # action == new（默认）：一次一个 token，旧的立刻作废
    config = load_config() or {}
    basic = _basic_auth(config)
    if not str(basic.get("password_hash") or basic.get("password") or "").strip():
        raise HTTPException(400, detail="先给面板设个登录密码：配对就是把登录态塞给手机，没密码等于全公开")
    if not str(basic.get("secret") or "").strip():
        raise HTTPException(400, detail="面板 basic_auth 里没有 secret（签名密钥），配对签不出登录态")
    dash = config.get("dashboard") if isinstance(config.get("dashboard"), dict) else {}
    raw_port = str(dash.get("port") or "").strip()
    port = int(raw_port) if raw_port.isdigit() else DEFAULT_PORT
    _start_pair_proxy(port)

    snap = _tunnel_snapshot()
    tunnel = str(snap.get("url") or "")
    token = _secrets.token_urlsafe(24)
    _pair_write({"token": token, "status": "pending", "created": time.time(),
                 "expires": time.time() + PAIR_TTL_SECONDS, "ip": "", "ua": "", "tunnel": tunnel})
    out = _pair_snapshot()
    out.update(ok=True, proxy=True, port=PAIR_PORT, ttl_seconds=PAIR_TTL_SECONDS,
               tunnel=tunnel, tunnel_running=bool(snap.get("running")))
    out["url"] = "%s/pair?t=%s" % (tunnel.rstrip("/"), token) if tunnel else ""
    out["note"] = ("公网隧道没开：开了隧道手机才打得开这个链接" if not tunnel
                   else "手机扫码/打开链接 → 在这台电脑上点「批准」→ 手机自动进去，不用输密码")
    return out


@router.get("/tunnel")
def tunnel_status() -> Dict[str, Any]:
    snap = _tunnel_snapshot()
    snap["ok"] = True
    snap["log"] = str(_tunnel_log_path())
    snap["cloudflared"] = ""
    try:
        snap["cloudflared"] = _cloudflared_exe()
    except HTTPException:
        pass
    return snap


@router.post("/tunnel")
def tunnel(body: TunnelBody) -> Dict[str, Any]:
    """开/关公网隧道。开之前必须已经有面板密码 —— 公网地址是裸的。"""
    from hermes_cli.config import load_config

    action = (body.action or "start").strip().lower()
    if action == "stop":
        return _stop_tunnel()

    snap = _tunnel_snapshot()
    if action == "extend":
        if not snap["running"]:
            raise HTTPException(400, detail="隧道没在跑，直接开一个就行")
        expires_at = time.time() + _ttl_seconds(body.ttl_minutes)
        _TUNNEL["expires_at"] = expires_at
        _arm_tunnel_timer(expires_at)
        _tunnel_state_path().write_text(
            json.dumps({"pid": int(snap["pid"]), "url": snap["url"], "port": int(snap["port"]), "expires_at": expires_at}),
            encoding="utf-8")
        return {"ok": True, "running": True, **snap, "expires_at": expires_at}

    if snap["running"] and snap["url"]:
        return {"ok": True, "running": True, "already": True, **snap}

    config = load_config() or {}
    basic = _basic_auth(config)
    if not str(basic.get("password_hash") or basic.get("password") or "").strip():
        raise HTTPException(400, detail="先给面板设个登录密码：公网地址谁拿到谁就能开，没密码等于全公开")
    dash = config.get("dashboard") if isinstance(config.get("dashboard"), dict) else {}
    raw_port = str(dash.get("port") or "").strip()
    port = int(body.port or 0) or (int(raw_port) if raw_port.isdigit() else DEFAULT_PORT)

    # 隧道指向配对反代（而不是裸 dashboard）：反代把 /pair* 拦下来自己处理，
    # 其余请求原样透传 —— 没有它，公网域名下就没有「谁都能打开」的配对页。
    _start_pair_proxy(port)
    exe = _cloudflared_exe()
    log = _tunnel_log_path()
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("", encoding="utf-8")
    flags = 0
    if os.name == "nt":
        flags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) | int(getattr(subprocess, "DETACHED_PROCESS", 0))
    with open(log, "ab") as fh:
        proc = subprocess.Popen(
            # --protocol http2：默认 auto 会优先 QUIC，在 fake-ip/TUN 代理下会一直连不上（dsh 同款坑）
            [exe, "tunnel", "--no-autoupdate", "--protocol", "http2", "--url", "http://127.0.0.1:%d" % PAIR_PORT],
            stdout=fh, stderr=fh, stdin=subprocess.DEVNULL, creationflags=flags,
        )
    _TUNNEL.update(proc=proc, url="", port=port)

    url = ""
    waited = 0.0
    while waited < TUNNEL_WAIT_SECONDS:
        time.sleep(0.5)
        waited += 0.5
        try:
            text = log.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        url = _tunnel_url_in(text)
        if url:
            break
        if proc.poll() is not None:
            break

    if not url:
        _stop_tunnel()
        detail = "隧道 %d 秒内没拿到公网地址" % int(TUNNEL_WAIT_SECONDS)
        try:
            detail += "：\\n" + "\\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-8:])
        except OSError:
            pass
        raise HTTPException(502, detail=detail)

    _TUNNEL["url"] = url
    expires_at = time.time() + _ttl_seconds(body.ttl_minutes)
    _TUNNEL["expires_at"] = expires_at
    _arm_tunnel_timer(expires_at)
    _tunnel_state_path().write_text(
        json.dumps({"pid": proc.pid, "url": url, "port": port, "expires_at": expires_at}), encoding="utf-8")
    return {
        "ok": True, "running": True, "url": url, "pid": proc.pid, "port": port, "expires_at": expires_at,
        "note": "临时地址：cloudflared 一重启就换新的；这一条到点自动关闭（cloudflare 免费隧道没有固定地址，也不会长期挂着）",
        "log": str(log),
    }

