"""手机页面（门禁上游）回归：默认就是三方网页版，能切回自带面板，切了反代必须跟上。

背景（用户原话「用三方 webui」）：门禁链路是 cloudflared → 9121 配对反代 → 上游。
上游以前写死自带面板 9119；现在由「手机页面」这个设置决定，默认第三方网页版（8787）。
换上游必须换进程 —— 反代只在启动时读一次 HPR_UPSTREAM，不换 = 手机进门后还看到旧页面。

跑：python tests/test_phone_page.py
ponytail: 纯 assert 脚本；真起进程那条路不测（_webui_start / _start_pair_proxy 被打桩）。
"""
import importlib.util
import json
import os
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
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


with tempfile.TemporaryDirectory() as tmp:
    tmpd = Path(tmp)
    os.environ["LOCALAPPDATA"] = tmp          # 设置文件落在临时目录，不碰用户真配置
    webui = tmpd / "webui"
    webui.mkdir()
    (webui / "bootstrap.py").write_text("# fake\n", encoding="utf-8")
    WPORT = free_port()                       # 没人听：任何「在跑就重启」的分支都不该拉进程
    (webui / ".env").write_text("HERMES_WEBUI_HOST=127.0.0.1\nHERMES_WEBUI_PORT=%d\n" % WPORT,
                                encoding="utf-8", newline="")
    m.WEBUI_DIR_CANDIDATES = (str(webui),)
    m._panel_port = lambda: 9119
    started = []                              # 起网页版要打桩：手机页面就是它，没跑就该顺手拉起来
    m._webui_start = lambda d: started.append(str(d))

    # 1) 默认 = 三方网页版（用户明确要的），上游就是网页版端口
    assert m.PHONE_PAGE_DEFAULT == "webui", m.PHONE_PAGE_DEFAULT
    assert m._phone_page() == "webui", m._phone_page()
    assert m._phone_upstream() == WPORT, m._phone_upstream()
    assert started == [str(webui)], started               # 没在跑 → 拉起来（手机进门得有人）
    assert m._phone_upstream_label() == "127.0.0.1:%d" % WPORT, m._phone_upstream_label()
    assert m._phone_upstream(ensure=False) == WPORT      # 只读状态不拉进程
    assert len(started) == 1, started

    # 2) 切自带面板 → 上游回面板端口，选择落盘能读回
    assert m._phone_page_set("panel") == "panel"
    assert m._phone_page() == "panel" and m._phone_upstream() == 9119
    saved = json.loads((tmpd / "hermes" / "phone-remote" / "phone-page.json").read_text(encoding="utf-8"))
    assert saved["page"] == "panel", saved

    # 3) 非法值怼回去（400），不会把已存的选择写坏
    try:
        m._phone_page_set("bogus")
        raise AssertionError("非法值居然写进去了")
    except m.HTTPException as exc:
        assert exc.status_code == 400 and exc.detail, exc
    assert m._phone_page() == "panel", m._phone_page()

    # 4) 反代上游比对：上游不一样 / 旧版反代不报上游 → 都得换进程
    m._pair_proxy_probe = lambda: {"mtime": 1.0, "deps": True, "upstream": "127.0.0.1:9119"}
    assert m._pair_upstream_ok(9119) is True
    assert m._pair_upstream_ok(WPORT) is False
    m._pair_proxy_probe = lambda: {"mtime": 1.0, "deps": True}     # 改造前的旧进程：不说上游
    assert m._pair_upstream_ok(9119) is False

    # 5) POST /webui phone_page=webui：存下 + 让门禁反代跟上（打桩，不真起）
    seen = []
    m._start_pair_proxy = lambda port=None: seen.append(port)
    res = m.webui(m.WebuiBody(phone_page="webui"))
    assert res["ok"] and res["phone_page"] == "webui" and res["pair"]["ok"], res
    assert seen == [None], seen                                  # 不传端口 → 后端自己解析上游
    assert m._webui_snapshot()["phone_page"] == "webui", m._webui_snapshot()
    assert res["phone_upstream"] == "127.0.0.1:%d" % WPORT, res

    # 6) 没找到网页版目录：起反代要报 400（别悄悄把门开给空气），只读状态只是「不知道」
    m.WEBUI_DIR_CANDIDATES = (str(tmpd / "nope"),)
    assert m._phone_upstream(ensure=False) == 0
    try:
        m._phone_upstream()
        raise AssertionError("没网页版目录还让它起反代")
    except m.HTTPException as exc:
        assert exc.status_code == 400, exc

    # 7) 切回自带面板：不依赖网页版目录，照样给出面板端口
    m._phone_page_set("panel")
    assert m._phone_upstream() == 9119, m._phone_upstream()

print("OK 手机页面（门禁上游）7 项通过")
