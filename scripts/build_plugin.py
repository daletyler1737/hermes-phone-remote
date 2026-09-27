#!/usr/bin/env python3
"""从模板 + vendor 内联库生成 plugin.js；--install 同步到 Hermes 桌面插件目录。

用法 / Usage:
    python scripts/build_plugin.py             # 只构建到 ./plugin.js
    python scripts/build_plugin.py --install   # 构建并安装到 desktop-plugins/
"""
from __future__ import annotations

import argparse
import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent.parent
TPL = HERE / "src" / "plugin.template.js"
LIB = HERE / "vendor" / "qrcode-generator.js"
OUT = HERE / "plugin.js"
# 统一 LF：Windows 上 write_text 默认写 CRLF，会让仓库出现整文件的假变更
LF = chr(10)


def hermes_home() -> pathlib.Path:
    """HERMES_HOME 优先，否则按平台默认（Windows: %LOCALAPPDATA%\\hermes）。"""
    env = os.environ.get("HERMES_HOME")
    if env:
        return pathlib.Path(env)
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(pathlib.Path.home() / "AppData" / "Local")
        return pathlib.Path(base) / "hermes"
    return pathlib.Path.home() / ".hermes"


def check_module_syntax(code: str) -> None:
    """语法闸门：桌面宿主是按 ES module 加载 plugin.js 的，必须用 module 模式解析。

    坑：`node --check plugin.js` 会当**脚本**解析，坏文件能溜过去（实测漏掉过一整块
    重复的 `style: S.card, children: [`），宿主却报 SyntaxError 整插件加载失败 ——
    表现是左侧栏「连接手机」入口直接消失。所以这里一律走 .mjs 解析。
    """
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False, encoding="utf-8", newline=LF) as fh:
        fh.write(code)
        tmp = fh.name
    try:
        r = subprocess.run(["node", "--check", tmp], capture_output=True, text=True)
    finally:
        pathlib.Path(tmp).unlink(missing_ok=True)
    if r.returncode != 0:
        raise SystemExit("语法不过（module 模式，与桌面宿主一致）:\n" + (r.stderr or r.stdout))


def run_load_smoke() -> None:
    """加载冒烟：拿替身 SDK 把 plugin.js 真跑一遍，确认三个入口都注册上。

    语法过关 ≠ 能加载（register 里抛异常宿主一样丢弃整插件）。桌面日志里
    `[plugins] runtime load failed (phone-remote)` 就是这个下场：左侧栏入口消失。
    """
    harness = HERE / "tests" / "plugin_load_smoke.mjs"
    if not harness.exists():
        print("! 没找到加载冒烟脚本，跳过: %s" % harness)
        return
    r = subprocess.run(["node", str(harness), str(OUT)], cwd=str(HERE), capture_output=True, text=True)
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    for line in out.splitlines():
        print("  " + line)
    if r.returncode != 0:
        raise SystemExit("加载冒烟没过 —— 别安装（宿主会把整插件丢掉，左侧栏入口会消失）")


def build() -> str:
    tpl = TPL.read_text(encoding="utf-8")
    lib = LIB.read_text(encoding="utf-8")
    if "/*__QR_INLINE__*/" not in tpl:
        raise SystemExit("模板缺少 /*__QR_INLINE__*/ 占位符")
    out = tpl.replace("/*__QR_INLINE__*/", lib)
    if not out.startswith("/**") or "export default" not in out:
        raise SystemExit("生成结果不像插件文件，已中止")
    check_module_syntax(out)
    OUT.write_text(out, encoding="utf-8", newline=LF)
    return out


def install_backend() -> None:
    """插件后端：<HERMES_HOME>/plugins/phone-remote/dashboard/
    面板上「改密码 / 重启面板」两个按钮下手的地方，缺了它按钮只会报错。"""
    src = HERE / "dashboard"
    dest = hermes_home() / "plugins" / "phone-remote" / "dashboard"
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("manifest.json", "plugin_api.py"):
        (dest / name).write_text((src / name).read_text(encoding="utf-8"), encoding="utf-8", newline=LF)
    # 扫码配对反代：后端会拿 venv python 跑它（<dashboard>/tools/pair_proxy.py）
    tools_dest = dest / "tools"
    tools_dest.mkdir(parents=True, exist_ok=True)
    (tools_dest / "pair_proxy.py").write_text(
        (HERE / "tools" / "pair_proxy.py").read_text(encoding="utf-8"), encoding="utf-8", newline=LF)
    # 重启面板用的脱离助手：漏装它会留下会闪终端的旧版
    (tools_dest / "dashboard_respawn.py").write_text(
        (HERE / "tools" / "dashboard_respawn.py").read_text(encoding="utf-8"), encoding="utf-8", newline=LF)
    print("已安装后端: %s" % dest)
    print("已安装配对反代: %s" % (tools_dest / "pair_proxy.py"))
    print("已安装重启助手: %s" % (tools_dest / "dashboard_respawn.py"))


# 用户插件的 Python 后端只有进了 plugins.enabled 白名单才会被 dashboard 导入
# （hermes_cli/web_server_dashboard.py::_plugin_api_mount_skip_reason，安全闸门），
# 而 `hermes plugins enable` 只认从仓库装进来的插件、不认手动放进 plugins/ 的目录 ——
# 所以直接调官方那个写入函数，它自己会保留 config.yaml 里的注释。
ENABLE_SNIPPET = (
    "from hermes_cli.plugins_cmd import _get_enabled_set, _set_plugin_enabled\n"
    "s = _get_enabled_set()\n"
    "if 'phone-remote' in s:\n"
    "    print('已在 plugins.enabled 里')\n"
    "else:\n"
    "    _set_plugin_enabled('phone-remote', enable=True)\n"
    "    print('已加入 plugins.enabled')\n"
    "print('plugins.enabled =', sorted(_get_enabled_set()))\n"
)


def enable_plugin() -> None:
    """把 phone-remote 写进 config.yaml 的 plugins.enabled（走官方 writer，保留注释）。"""
    agent = pathlib.Path(os.environ.get("HERMES_AGENT_DIR") or (hermes_home() / "hermes-agent"))
    py = agent / "venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not py.exists():
        print("! 没找到 Hermes 的 python: %s" % py)
        print("! 请手动执行: python -c \"from hermes_cli.plugins_cmd import _set_plugin_enabled as f; f('phone-remote', enable=True)\"")
        return
    r = subprocess.run([str(py), "-c", ENABLE_SNIPPET], cwd=str(agent), capture_output=True, text=True)
    for line in ((r.stdout or "") + (r.stderr or "")).strip().splitlines()[-4:]:
        print("  " + line)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", action="store_true",
                    help="同步到 desktop-plugins/phone-remote/plugin.js")
    a = ap.parse_args()

    out = build()
    print("构建完成: %s (%d bytes, LF)" % (OUT, len(out.encode("utf-8"))))
    print("加载冒烟:")
    run_load_smoke()

    if a.install:
        dest = hermes_home() / "desktop-plugins" / "phone-remote" / "plugin.js"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(out, encoding="utf-8", newline=LF)
        print("已安装: %s" % dest)
        install_backend()
        enable_plugin()
        print("桌面版里按 Ctrl+K 搜 \"Reload desktop plugins\" 让宿主重新扫描。")
        print("插件后端只在桌面版启动时挂载：装完重启一次 Hermes 桌面版，面板上的按钮就永久可用。")


if __name__ == "__main__":
    main()
