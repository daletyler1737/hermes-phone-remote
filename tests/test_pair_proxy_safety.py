"""配对反代安全回归：XSS 收敛 / 客户端 IP 不可伪造 / token 一次性语义。

跑法：python tests/test_pair_proxy_safety.py
ponytail: 纯 assert 脚本，不引测试框架。
"""
import importlib.util
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("pair_proxy", ROOT / "tools" / "pair_proxy.py")
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)

# 1) 带引号/尖括号的 token 不能落进页面（反射型 XSS 入口）
bad = '"><script>alert(1)</script>'
page = m._page(bad, "127.0.0.1").decode()
assert "<script>alert(1)" not in page, page
assert 'var t=""' in page, page            # 不合法 token 清成空串

# 2) 合法 token 原样嵌入（不能把正常配对弄坏）
good = "Abc-123_xyzDEF456ghi"
assert good in m._page(good, "127.0.0.1").decode()

# 3) Host 头是客户端可控的，必须转义
h = m._page(good, 'evil"><script>x</script>').decode()
assert "<script>x" not in h and "&lt;script&gt;x" in h, h

# 4) 客户端 IP：CF-Connecting-IP 优先（客户端伪造不了），XFF 只是兜底
hd = (b"GET / HTTP/1.1\r\nHost: x\r\nX-Forwarded-For: 6.6.6.6\r\n"
      b"CF-Connecting-IP: 1.2.3.4\r\nUser-Agent: UA/1\r\n\r\n")
assert m._client_of(hd) == ("1.2.3.4", "UA/1"), m._client_of(hd)
assert m._client_of(b"GET / HTTP/1.1\r\nHost: x\r\nX-Forwarded-For: 6.6.6.6\r\n\r\n")[0] == "6.6.6.6"

# 5) token 状态语义：错 token / 过期 / 已被领走
now = time.time()
st = {"token": good, "status": "pending", "expires": now + 60}
assert m._token_status(st, good) == "pending"
assert m._token_status(st, good + "x") == "invalid"
assert m._token_status(st, "") == "invalid"
assert m._token_status({**st, "expires": now - 1}, good) == "expired"
assert m._token_status({**st, "status": "claimed"}, good) == "claimed"

# 6) 配对 token 的随机性：必须来自密码学随机源（用户红线「保护 token 随机性」）
import secrets as _std                                        # noqa: E402
import sys                                                    # noqa: E402
_api_src = (ROOT / "dashboard" / "plugin_api.py").read_text(encoding="utf-8")
assert "token_urlsafe(24)" in _api_src, "配对 token 生成点没了？"
assert "random." not in _api_src, "配对 token 不许走非密码学随机源"
_s2 = importlib.util.spec_from_file_location("phone_remote_api", ROOT / "dashboard" / "plugin_api.py")
A = importlib.util.module_from_spec(_s2)
sys.modules["phone_remote_api"] = A
_s2.loader.exec_module(A)
assert A.secrets is _std, "必须是 stdlib secrets（不是 random / 自研）"
assert A.PAIR_TTL_SECONDS <= 900, f"配对链接 TTL 太宽：{A.PAIR_TTL_SECONDS}s"
_N = 20000
_ALPHA64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
toks = {A.secrets.token_urlsafe(24) for _ in range(_N)}
assert len(toks) == _N, f"{_N} 次生成有撞车"
assert all(len(t) == 32 for t in toks), "长度必须恒为 32 字符（24 字节 → 192 bit）"
assert all(set(t) <= set(_ALPHA64) for t in toks), "字符集必须落在 urlsafe base64"

print("ok: 配对反代安全回归 17 项通过")