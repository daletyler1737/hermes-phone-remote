#!/usr/bin/env python3
"""从模板 + vendor 内联库生成 plugin.js；--install 同步到 Hermes 桌面插件目录。

用法 / Usage:
    python scripts/build_plugin.py                 # 只构建到 ./plugin.js
    python scripts/build_plugin.py --install       # 构建并安装到 desktop-plugins/
    python scripts/build_plugin.py --install --ip 192.168.1.50 --port 9119
"""
import argparse
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent.parent
TPL = HERE / "src" / "plugin.template.js"
LIB = HERE / "vendor" / "qrcode-generator.js"
OUT = HERE / "plugin.js"


def hermes_home() -> pathlib.Path:
    """HERMES_HOME 优先，否则用平台默认（Windows: %LOCALAPPDATA%\hermes）。"""
    env = os.environ.get("HERMES_HOME")
    if env:
        return pathlib.Path(env)
    if sys.platform == "win32":
        return pathlib.Path(os.environ.get("LOCALAPPDATA", pathlib.Path.home() / "AppData/Local")) / "hermes"
    return pathlib.Path.home() / ".hermes"


def build(ip: str | None = None, port: str | None = None, user: str | None = None) -> str:
    tpl = TPL.read_text(encoding="utf-8")
    lib = LIB.read_text(encoding="utf-8")
    assert "/*__QR_INLINE__*/" in tpl, "模板缺少 /*__QR_INLINE__*/ 占位符"
    out = tpl.replace("/*__QR_INLINE__*/", lib)
    if ip:
        out = out.replace("ip: '192.168.1.34'", f"ip: '{ip}'")
    if port:
        out = out.replace("port: '9119'", f"port: '{port}'")
    if user:
        out = out.replace("user: 'dale'", f"user: '{user}'")
    if not out.startswith("/**") or "export default" not in out:
        raise SystemExit("生成结果不像插件文件，已中止")
    OUT.write_text(out, encoding="utf-8")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", action="store_true", help="同步到 desktop-plugins/phone-remote/plugin.js")
    ap.add_argument("--ip"); ap.add_argument("--port"); ap.add_argument("--user")
    a = ap.parse_args()
    out = build(a.ip, a.port, a.user)
    print(f"构建完成: {OUT} ({len(out.encode('utf-8'))} bytes)")
    if a.install:
        dest = hermes_home() / "desktop-plugins" / "phone-remote" / "plugin.js"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(out, encoding="utf-8")
        print(f"已安装: {dest}")
        print("在桌面版里按 Ctrl+K 搜 “Reload desktop plugins” 让宿主重新扫描。")


if __name__ == "__main__":
    main()
