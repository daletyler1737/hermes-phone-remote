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


def build() -> str:
    tpl = TPL.read_text(encoding="utf-8")
    lib = LIB.read_text(encoding="utf-8")
    if "/*__QR_INLINE__*/" not in tpl:
        raise SystemExit("模板缺少 /*__QR_INLINE__*/ 占位符")
    out = tpl.replace("/*__QR_INLINE__*/", lib)
    if not out.startswith("/**") or "export default" not in out:
        raise SystemExit("生成结果不像插件文件，已中止")
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
    print("已安装后端: %s" % dest)


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
