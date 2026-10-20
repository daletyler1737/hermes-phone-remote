"""密码绑定回归：网页版那串能不能当面板密码用（_panel_hash_ok 是纯函数，直接怼）。

背景（用户原话「必须跟面板绑定好」）：v0.3.1 起改面板密码会把同一串写进网页版 .env，
但两处一旦漂移，卡片照样显示「已绑定」就是骗人的 —— 所以后端每次快照真去验 scrypt hash。

跑：python tests/test_bound_password.py
ponytail: 只测纯函数 + 真 hash；不测 config 读取（那是 load_config 的事）。
"""
import base64
import hashlib
import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("plugin_api", ROOT / "dashboard" / "plugin_api.py")
m = importlib.util.module_from_spec(_spec)
sys.modules["plugin_api"] = m
_spec.loader.exec_module(m)


def make_hash(password: str, n: int = 16384, r: int = 8, p: int = 1) -> str:
    """官方格式：scrypt$n$r$p$b64(salt)$b64(digest)。"""
    salt = b"0123456789abcdef"
    dk = hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, dklen=32)
    return "scrypt$%d$%d$%d$%s$%s" % (
        n, r, p, base64.b64encode(salt).decode(), base64.b64encode(dk).decode())


h = make_hash("Panel-Pass-1234!")
assert m._panel_hash_ok("Panel-Pass-1234!", h) is True
assert m._panel_hash_ok("panel-pass-1234!", h) is False      # 大小写敏感
assert m._panel_hash_ok("Panel-Pass-1234", h) is False       # 少一个字符就不认
assert m._panel_hash_ok("", h) is False
assert m._panel_hash_ok("Panel-Pass-1234!", "") is False     # 还没设密码
assert m._panel_hash_ok("x", "garbage") is False             # 坏 hash 不炸
assert m._panel_hash_ok("x", "bcrypt$1$2$3$4$5") is False    # 不认识的算法

h2 = make_hash("ab", n=1024)                                 # 老/短密码、不同 n 也要能验
assert m._panel_hash_ok("ab", h2) is True and m._panel_hash_ok("abc", h2) is False

print("OK 密码绑定 8 项通过")
