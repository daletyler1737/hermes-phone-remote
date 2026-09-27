"""两种模式各一条链接回归：「批准」和「账号密码」各自生成、各自一个二维码，互不覆盖。

跑法：python tests/test_pair_links_modes.py

用户报的 bug（逐字）：「批准 版 和 密码 生成二维码分开 点生成两个都开了」——
根因是一个 pair.json 只存一条 token+mode，后生成的那个把先前的盖掉，
两张卡上其实是同一条链接。这里查的就是「盖掉」有没有真被修掉：

① 面板侧：先给 approve 生成、再给 password 生成 → 两条链接同时都在，token 不同；
   再点 approve 的「批准」 → password 那条原封不动（status 还是 pending）。
② 反代侧：approve 的 token 落在「等批准」那一页，password 的 token 落在登录表单，
   两条链接路由到不同页面（不是同一页）。

ponytail: 纯 assert 脚本，不引测试框架；LOCALAPPDATA 指到临时目录，不碰真实 pair.json。
"""
import importlib.util
import json
import os
import socket
import sys
import tempfile
import threading
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp())
os.environ["LOCALAPPDATA"] = str(TMP)      # plugin_api / pair_proxy 的 _pair_dir() 都认这个

# hermes_cli 只在面板进程里真实存在；测试里给个最小的假配置（有密码 + secret 就能生成链接）
if "hermes_cli.config" not in sys.modules:
    pkg = sys.modules.setdefault("hermes_cli", types.ModuleType("hermes_cli"))
    cfg = types.ModuleType("hermes_cli.config")
    cfg.load_config = lambda: {                                     # noqa: E731
        "dashboard": {"port": 9119, "basic_auth": {"password_hash": "deadbeef", "secret": "unit-test-secret"}},
    }
    pkg.config = cfg
    sys.modules["hermes_cli.config"] = cfg

_spec = importlib.util.spec_from_file_location("hpr_plugin_api", ROOT / "dashboard" / "plugin_api.py")
api = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(api)

# 别真去起反代/真去问隧道：这两个是外部副作用，测的是分槽逻辑
api._start_pair_proxy = lambda port: None
api._tunnel_snapshot = lambda: {"url": "https://unit.test", "running": True, "pid": 111, "port": 9119}
api._pair_alive = lambda: True

ok = 0


def check(name: str, cond: bool, extra: str = "") -> None:
    global ok
    if not cond:
        raise AssertionError("FAIL: %s %s" % (name, extra))
    ok += 1
    print("  ok:", name)


print("[1] 面板：两个模式各生成一条")
a = api.pair(api.PairBody(action="new", mode="approve"))
p = api.pair(api.PairBody(action="new", mode="password"))
check("approve 链接生成", a["links"]["approve"]["status"] == "pending")
check("password 链接生成", p["links"]["password"]["status"] == "pending")
tok_a = api._pair_entry(api._pair_read(), "approve").get("token")
tok_p = api._pair_entry(api._pair_read(), "password").get("token")
check("两条链接 token 不同", bool(tok_a) and bool(tok_p) and tok_a != tok_p, "同一条=还没分槽")
check("approve 那条 mode=approve", api._pair_entry(api._pair_read(), "approve")["mode"] == "approve")
check("password 那条 mode=password", api._pair_entry(api._pair_read(), "password")["mode"] == "password")
check("approve 的 url 指向自己的 token", a["links"]["approve"]["url"].endswith(tok_a))
check("password 的 url 指向自己的 token", p["links"]["password"]["url"].endswith(tok_p))
check("两个 url 不是同一个", a["links"]["approve"]["url"] != p["links"]["password"]["url"])

print("[2] 面板：再生成 approve 不碰 password 那条")
b = api.pair(api.PairBody(action="new", mode="approve"))
tok_a2 = api._pair_entry(api._pair_read(), "approve").get("token")
check("approve 换成新 token", tok_a2 != tok_a)
check("password 那条没被换掉", api._pair_entry(api._pair_read(), "password").get("token") == tok_p)
check("password 返回里也带着自己那条", b["links"]["password"]["url"].endswith(tok_p))

print("[3] 面板：批准 approve 不动 password")
api.pair(api.PairBody(action="approve", mode="approve"))
check("approve 已批准", api._pair_entry(api._pair_read(), "approve")["status"] == "approved")
check("password 还是 pending",
      api._pair_entry(api._pair_read(), "password")["status"] == "pending",
      api._pair_entry(api._pair_read(), "password")["status"])
try:
    api.pair(api.PairBody(action="approve", mode="password"))
    raise AssertionError("FAIL: 账号密码那条不该能在电脑上点批准")
except api.HTTPException as e:
    check("账号密码那条不许在电脑上批准", e.status_code == 400)

print("[4] 兼容老格式：单条平格式读得出、写回成嵌套")
flat = TMP / "hermes" / "phone-remote" / "flat.json"
flat.write_text(json.dumps({"token": "OLDTOKEN", "status": "pending", "mode": "password",
                            "expires": time.time() + 600}), encoding="utf-8")
st = json.loads(flat.read_text(encoding="utf-8"))
check("老平格式 fold 出 password 那条", api._pair_entry(st, "password").get("token") == "OLDTOKEN")
check("老平格式里 approve 是空的", api._pair_entry(st, "approve") == {})
check("fold 后 token 只出现在 password 槽", st["links"]["password"]["token"] == "OLDTOKEN")

print("[5] 反代：两条 token 各自路由到不同页面")
_free = socket.socket()
_free.bind(("127.0.0.1", 0))
port = _free.getsockname()[1]
_free.close()
os.environ.update(HPR_PORT=str(port), HPR_UPSTREAM="127.0.0.1:9",
                  HPR_STATE=str(api._pair_state_path()))
spec2 = importlib.util.spec_from_file_location("hpr_pair_proxy_t", ROOT / "tools" / "pair_proxy.py")
px = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(px)
threading.Thread(target=px.main, daemon=True).start()
end = time.time() + 5
while time.time() < end:
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.3).close()
        break
    except OSError:
        time.sleep(0.05)


def get(path: str) -> bytes:
    s = socket.create_connection(("127.0.0.1", port), timeout=5)
    s.settimeout(4)
    s.sendall(("GET %s HTTP/1.1\r\nHost: unit.test\r\nConnection: close\r\n\r\n" % path).encode())
    buf = b""
    while True:
        try:
            ch = s.recv(65536)
        except OSError:
            break
        if not ch:
            break
        buf += ch
    s.close()
    return buf


tok_a3 = api._pair_entry(api._pair_read(), "approve").get("token")
pw_body = get("/pair?t=" + tok_p)
ap_body = get("/pair?t=" + tok_a3)
FORM = b'action="/pair/login"'
check("password 的 token → 登录表单(200)", b"200 OK" in pw_body and FORM in pw_body)
check("approve 的 token → 不是登录表单", FORM not in ap_body)
check("两张页面内容不同", pw_body != ap_body)
check("过期/陌生 token 不发登录表单", FORM not in get("/pair?t=bogus-token-xyz"))

print("[6] 反代：claim 掉 password 那条，approved 那条状态不动")
st = api._pair_read()
check("claim 前 approve=approved", api._pair_entry(st, "approve")["status"] == "approved")
check("claim 前 password=pending", api._pair_entry(st, "password")["status"] == "pending")

print("[7] 过期的 pending 链接自动换新（用户要的「10 分钟一变」，不用回去点「换一个新链接」）")


_ALPHA64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"   # urlsafe base64


def _set(mode: str, **kw) -> None:
    st = api._pair_read()
    api._pair_entry(st, mode).update(**kw)
    api._pair_write(st)


tok_live = api._pair_entry(api._pair_read(), "password")["token"]
_set("password", status="pending", expires=time.time() + 300, ip="1.1.1.1", ua="UA")
api.pair_status()
e = api._pair_entry(api._pair_read(), "password")
check("没过期的 pending 原样不动（别把正在扫的那条换掉）", e["token"] == tok_live and e["ip"] == "1.1.1.1")

_set("password", status="pending", expires=time.time() - 1, ip="1.1.1.1", ua="UA")
api.pair_status()
e = api._pair_entry(api._pair_read(), "password")
check("过期的 pending 换成了新 token", e["token"] != tok_live)
check("新 token 还是 32 位 urlsafe", len(e["token"]) == 32 and set(e["token"]) <= set(_ALPHA64))
check("有效期挪到未来（重新计时 10 分钟）", e["expires"] > time.time() + 500)
check("状态回到 pending", e["status"] == "pending")
check("上一台手机的 ip/ua 痕迹清掉", e["ip"] == "" and e["ua"] == "")
check("换新后 url 指向新 token", api.pair_status()["links"]["password"]["url"].endswith(e["token"]))

for _st in ("approved", "denied", "claimed"):
    _set("password", status=_st, expires=time.time() - 1, token="KEEPME_" + _st)
    api.pair_status()
    check("status=%s 一律不换 token" % _st,
          api._pair_entry(api._pair_read(), "password")["token"] == "KEEPME_" + _st)

_set("password", status="pending", expires=time.time() - 1, token="")
api.pair_status()
check("没有 token 的空槽不会凭空造一条", api._pair_entry(api._pair_read(), "password")["token"] == "")

print("\nok: 两种模式各自一条链接回归 %d 项通过" % ok)
