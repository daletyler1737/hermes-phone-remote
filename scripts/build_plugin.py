#!/usr/bin/env python3
"""从模板 + vendor 内联库生成 plugin.js；--install 同步到 Hermes 桌面插件目录。

用法 / Usage:
    python scripts/build_plugin.py                 # 只构建到 ./plugin.js
    python scripts/build_plugin.py --install       # 构建并安装到 desktop-plugins/
    python scripts/build_plugin.py --install --ip 192.168.1.50 --port 9119 --user dale
"""
from __future__ import annotations

import argparse
import os
import pathlib
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


def build(ip: str | None = None, port: str | None = None, user: str | None = None) -> str:
    tpl = TPL.read_text(encoding="utf-8")
    lib = LIB.read_text(encoding="utf-8")
    if "/*__QR_INLINE__*/" not in tpl:
        raise SystemExit("模板缺少 /*__QR_INLINE__*/ 占位符")
    out = tpl.replace("/*__QR_INLINE__*/", lib)
    if ip:
        out = out.replace("ip: '192.168.1.34'", "ip: '%s'" % ip)
    if port:
        out = out.replace("port: '9119'", "port: '%s'" % port)
    if user:
        out = out.replace("user: 'dale'", "user: '%s'" % user)
    if not out.startswith("/**") or "export default" not in out:
        raise SystemExit("生成结果不像插件文件，已中止")
    OUT.write_text(out, encoding="utf-8", newline=LF)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", action="store_true",
                    help="同步到 desktop-plugins/phone-remote/plugin.js")
    ap.add_argument("--ip", help="局域网 IP（写入插件默认值）")
    ap.add_argument("--port", help="端口，默认 9119")
    ap.add_argument("--user", help="dashboard 用户名，默认 dale")
    a = ap.parse_args()

    out = build(a.ip, a.port, a.user)
    print("构建完成: %s (%d bytes, LF)" % (OUT, len(out.encode("utf-8"))))

    if a.install:
        dest = hermes_home() / "desktop-plugins" / "phone-remote" / "plugin.js"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(out, encoding="utf-8", newline=LF)
        print("已安装: %s" % dest)
        print("桌面版里按 Ctrl+K 搜 \"Reload desktop plugins\" 让宿主重新扫描。")


if __name__ == "__main__":
    main()
