"""「重启面板」两条回归 —— 都是实机踩过的坑。

1) 重启/启动一律走脱离式助手。曾经按「os.getpid() 在不在监听者里」分两条路：
   桌面版挂载插件路由时当前进程并不监听 9119 → 走「直接 kill 监听者」那条 →
   面板被关掉，紧随其后的拉起又撞端口占用 → 用户看到「点重新启动，只是关闭了，
   要我再次点启动」。
2) 要换届的是「占着端口的那个 PID」，不是当前进程 —— 传错就等于没杀掉旧面板。

不碰真进程、不碰真端口：_respawn_self / subprocess.Popen / 日志路径全换掉。
"""
import importlib.util
import sys
import tempfile
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "plugin_api.py"
spec = importlib.util.spec_from_file_location("phone_remote_api_restart", SRC)
A = importlib.util.module_from_spec(spec)
sys.modules["phone_remote_api_restart"] = A
spec.loader.exec_module(A)

A._log_path = lambda: Path(tempfile.mkdtemp()) / "restart.log"

calls = []


def fake_respawn(port, host):
    calls.append((port, host))
    return 4321


real_respawn = A._respawn_self
A._respawn_self = fake_respawn
try:
    # 1) 当前进程是/不是/没有监听者 —— 三种身份都必须走助手，且都不能在这儿动手
    for listeners in ([__import__("os").getpid()], [999999], []):
        del calls[:]
        A._listeners = lambda port, L=listeners: list(L)
        A._kill = lambda pid: (_ for _ in ()).throw(AssertionError("重启请求里不该直接杀进程: %s" % pid))
        res = A.restart(A.RestartBody(port=9119))
        assert res["ok"] is True and res["mode"] == "respawn", res
        assert calls == [(9119, "0.0.0.0")], (listeners, calls)
        assert res["helper_pid"] == 4321, res
        assert res["lan_url"].startswith("http://"), res

    # 端口可以自己指定；host 传空串要落回 0.0.0.0（否则面板只绑本机）
    del calls[:]
    A.restart(A.RestartBody(port=9200, host="   "))
    assert calls == [(9200, "0.0.0.0")], calls
finally:
    A._respawn_self = real_respawn

# 2) --old-pid 必须是「监听该端口的那个」，不是 os.getpid()
cap = {}


class _FakeProc:
    pid = 777


real_popen, real_listeners, real_exe, real_script = A.subprocess.Popen, A._listeners, A._hermes_exe, A._respawn_script
A.subprocess.Popen = lambda argv, **kw: (cap.setdefault("argv", list(argv)), _FakeProc())[1]
A._listeners = lambda port: [555]
A._hermes_exe = lambda: "hermes.exe"
A._respawn_script = lambda: Path("dashboard_respawn.py")
try:
    pid = A._respawn_self(9119, "0.0.0.0")
    argv = cap["argv"]
    assert pid == 777, pid
    assert argv[argv.index("--old-pid") + 1] == "555", argv
    assert argv[argv.index("--port") + 1] == "9119", argv
finally:
    A.subprocess.Popen, A._listeners, A._hermes_exe, A._respawn_script = real_popen, real_listeners, real_exe, real_script

print("重启回归 OK：一律走助手（3 种 PID 身份）+ 换届的是端口占用者")
