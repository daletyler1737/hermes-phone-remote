"""透传时注入可信身份头（WebUI 免密接入）的回归：必须剥掉客户端自带的同名头。

跑法：python tests/test_trusted_identity_header.py
ponytail: 纯 assert 脚本，不引测试框架。
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("pair_proxy", ROOT / "tools" / "pair_proxy.py")
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)

HEAD = (b"GET / HTTP/1.1\r\nHost: x\r\nRemote-User: hacker\r\nCookie: a=b")

# 1) 默认不配就不注入：行为与改动前完全一致
m.TRUSTED_USER = ""
assert m._with_identity(HEAD) == HEAD

# 2) 配了身份：注入自己的值，且客户端伪造的那份必须被剥掉（否则手机能冒充身份跳过登录）
m.TRUSTED_USER = "dale"
out = m._with_identity(HEAD)
assert out.count(b"Remote-User:") == 1, out
assert b"Remote-User: dale" in out and b"hacker" not in out, out
assert b"Cookie: a=b" in out, out                      # 其它头原样保留

# 3) 自定义头名（大小写不敏感地剥）
m.TRUSTED_HEADER = "X-Auth-User"
out2 = m._with_identity(HEAD)
assert b"X-Auth-User: dale" in out2 and b"Remote-User: hacker" in out2, out2

# 4) 与 _one_shot 串起来仍合法：仍然只有一组 CRLF 结尾，Upgrade 不被破坏
m.TRUSTED_HEADER, m.TRUSTED_USER = "Remote-User", "dale"
ws = b"GET /ws HTTP/1.1\r\nHost: x\r\nUpgrade: websocket\r\nConnection: Upgrade"
assert b"Upgrade: websocket" in m._with_identity(m._one_shot(ws))
print("OK 透传身份头注入/剥伪造 4 项通过")
