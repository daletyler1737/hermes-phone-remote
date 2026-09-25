#!/usr/bin/env bash
# 面板改动后的回归自测：把编译产物丢进 react-dom 真渲染一次，看会不会炸、卡片在不在。
# 用法：bash tools/render-test/run.sh          （默认拿桌面版里已安装的那份）
#      bash tools/render-test/run.sh <plugin.js 路径>
set -e
cd "$(dirname "$0")"
SRC="${1:-$LOCALAPPDATA/hermes/desktop-plugins/phone-remote/plugin.js}"
[ -f "$SRC" ] || { echo "找不到 $SRC —— 先跑 python scripts/build_plugin.py --install"; exit 1; }
cp -f "$SRC" ./plugin.mjs
node harness.mjs
