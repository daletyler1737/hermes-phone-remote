"""隧道到期逻辑回归：过期的当场关掉，没过期的认领回来并带上到期时间。

不起真隧道、不碰真进程 —— _kill / _pid_alive / state 文件路径都换掉。
"""
import importlib.util
import json
import sys
import tempfile
import time
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "plugin_api.py"
spec = importlib.util.spec_from_file_location("phone_remote_api", SRC)
A = importlib.util.module_from_spec(spec)
sys.modules["phone_remote_api"] = A
spec.loader.exec_module(A)

killed = []
tmp = Path(tempfile.mkdtemp()) / "phone-tunnel.json"
A._tunnel_state_path = lambda: tmp
A._kill = lambda pid: (killed.append(pid), True)[1]


def state(expires_at):
    tmp.write_text(
        json.dumps({"pid": 4242, "url": "https://x.trycloudflare.com", "port": 9119, "expires_at": expires_at}),
        encoding="utf-8",
    )


A._pid_alive = lambda pid: True

# 1) 过期 → 关掉、删状态文件、杀掉隧道进程
state(time.time() - 1)
snap = A._tunnel_snapshot()
assert snap["running"] is False, snap
assert killed == [4242], killed
assert not tmp.exists(), "过期隧道不应该留下状态文件"

# 2) 没过期 → 认领回来、带上到期时间、重挂定时器（面板重启后自动关还得继续算）
killed.clear()
exp = time.time() + 120
state(exp)
snap = A._tunnel_snapshot()
assert snap["running"] is True and abs(snap["expires_at"] - exp) < 1, snap
assert A._TUNNEL_TIMER is not None, "认领后必须重挂到期定时器"
A._TUNNEL_TIMER.cancel()
A._TUNNEL_TIMER = None

# 3) 进程没了 → 不认领
A._pid_alive = lambda pid: False
state(time.time() + 120)
assert A._tunnel_snapshot()["running"] is False

# 4) 开多久：不选/选 0 → 默认 2 小时；显式给分钟数照用
assert A._ttl_seconds(0) == A.TUNNEL_TTL_SECONDS
assert A._ttl_seconds(30) == 1800.0

print("OK tunnel ttl")
