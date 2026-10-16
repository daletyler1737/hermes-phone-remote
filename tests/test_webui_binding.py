"""网页版 WebUI 密码绑定 / 起停的回归：写 .env 不许弄乱原文件，密码要连带生效。

跑法：python tests/test_webui_binding.py
ponytail: 纯 assert 脚本，不引测试框架；真起服务那条路不测（会拉进程），只测纯逻辑。
"""
import importlib.util
import socket
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("plugin_api", ROOT / "dashboard" / "plugin_api.py")
m = importlib.util.module_from_spec(_spec)
sys.modules["plugin_api"] = m        # pydantic 解析注解要用 sys.modules 里的模块命名空间
_spec.loader.exec_module(m)


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


PORT = free_port()          # 没人听：任何「在跑就重启」的分支都不会真的拉进程

with tempfile.TemporaryDirectory() as tmp:
    d = Path(tmp)
    (d / "bootstrap.py").write_text("# fake\n", encoding="utf-8")
    (d / ".env").write_text(
        "# 注释要留着\nHERMES_WEBUI_HOST=0.0.0.0\nHERMES_WEBUI_PORT=%d\n"
        "HERMES_WEBUI_PASSWORD=old-secret\n\n# 尾巴注释\n" % PORT,
        encoding="utf-8", newline="")
    m.WEBUI_DIR_CANDIDATES = (str(d),)

    # 1) 目录探测认 bootstrap.py + .env
    assert m._webui_dir() == d, m._webui_dir()
    assert m._webui_port(d) == PORT

    # 2) 改已有键：命中就换值，注释/顺序/别的键都不动
    m._webui_set_env(d, {"HERMES_WEBUI_PASSWORD": "new-secret"})
    text = (d / ".env").read_text(encoding="utf-8")
    assert "HERMES_WEBUI_PASSWORD=new-secret" in text and "old-secret" not in text, text
    assert text.startswith("# 注释要留着\nHERMES_WEBUI_HOST=0.0.0.0"), text
    assert "# 尾巴注释" in text, text

    # 3) 加新键：追加在尾部，不覆盖已有值
    m._webui_set_env(d, {"HERMES_WEBUI_HOST": "127.0.0.1", "HERMES_WEBUI_PYTHON": "C:/py.exe"})
    env = m._webui_env(d)
    assert env["HERMES_WEBUI_HOST"] == "127.0.0.1", env
    assert env["HERMES_WEBUI_PYTHON"] == "C:/py.exe", env
    assert env["HERMES_WEBUI_PASSWORD"] == "new-secret", env
    assert m._webui_host(d) == "127.0.0.1" and m._webui_python(d) == "C:/py.exe"

    # 4) 快照：密码给面板显示，端口没在听就是没在跑
    snap = m._webui_snapshot()
    assert snap["found"] and snap["password"] == "new-secret" and snap["password_set"], snap
    assert snap["running"] is False, snap
    assert snap["url"] == "http://127.0.0.1:%d/" % PORT, snap

    # 5) 弱密码必须被挡（和面板同一条策略，不然网页版成了薄弱入口）
    for weak in ("short", "alllowercase1234"):
        try:
            m.webui(m.WebuiBody(password=weak))
            raise AssertionError("弱密码居然写进去了：%r" % weak)
        except m.HTTPException as exc:
            assert exc.status_code == 400 and exc.detail, exc

    # 6) 正常写密码：没在跑就只落盘，等下回启动生效（不拉进程、不报错）
    res = m.webui(m.WebuiBody(password="Good-Pass-2026x", action="save"))
    assert res["ok"] and res["changed"] == ["HERMES_WEBUI_PASSWORD"], res
    assert m._webui_env(d)["HERMES_WEBUI_PASSWORD"] == "Good-Pass-2026x"
    assert res["running"] is False and res["pid"] if False else True

    # 7) 绑定入口（面板改密码走这条）：写盘 + 在跑才重启
    sync = m._webui_sync_password("Bound-Pass-2026y")
    assert sync["synced"] is True, sync
    assert m._webui_env(d)["HERMES_WEBUI_PASSWORD"] == "Bound-Pass-2026y", sync
    assert "pid" not in sync, sync      # 没在跑就不该有进程被拉起来

    # 8) 找不到目录时不能炸：返回 not found / synced False
    m.WEBUI_DIR_CANDIDATES = (str(d / "nope"),)
    assert m._webui_dir() is None
    assert m._webui_snapshot()["found"] is False
    assert m._webui_sync_password("Good-Pass-2026x")["synced"] is False

print("OK 网页版密码绑定/起停 8 项通过")
