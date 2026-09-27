# -*- coding: utf-8 -*-
"""实测互联网模式：真起 cloudflared，真从公网拉一次，再关掉。

⚠️ 这个测试会真的 start/stop 隧道。面板正开着的隧道不能被它掐了（真踩过：手机正在用的
时候跑测试 → 隧道被关、手机直接断）。所以：正在跑隧道时默认跳过；确实要跑就设
HPR_LIVE_TUNNEL_TEST=1，且「测试之前就在跑的隧道」不会被关掉。
"""
import os, sys, ssl, urllib.request, urllib.error

sys.path.insert(0, r"E:\zip\agent file big\01_项目代码\hermes-phone-remote\dashboard")
import plugin_api as api

_was_running = bool((api.tunnel_status() or {}).get("running"))
if _was_running and os.environ.get("HPR_LIVE_TUNNEL_TEST") != "1":
    print("跳过：隧道正在运行（要强制跑请设 HPR_LIVE_TUNNEL_TEST=1）")
    sys.exit(0)

print("1) 面板 9119 在跑吗:", api._port_open(api.DEFAULT_PORT))
print("2) cloudflared 路径:", api._cloudflared_exe())
print("3) 开之前的隧道状态:", api.tunnel_status())

res = api.tunnel(api.TunnelBody(action="start"))
url = res.pop("url", "")
print("4) 起隧道:", res)
print("   URL =", url)
assert url.startswith("https://") and url.endswith(".trycloudflare.com"), "URL 不对"

ctx = ssl.create_default_context()
for path in ("/", "/login"):
    try:
        r = urllib.request.urlopen(url + path, timeout=30, context=ctx)
        print("5) 公网 GET %-6s -> %s" % (path, r.status))
    except urllib.error.HTTPError as e:
        print("5) 公网 GET %-6s -> %s" % (path, e.code))
    except Exception as e:
        print("5) 公网 GET %-6s -> 失败 %s: %s" % (path, type(e).__name__, e))

print("6) 开之后的隧道状态:", api.tunnel_status())
print("7) 关隧道:", api._stop_tunnel() if not _was_running else "跳过（这条隧道测试之前就在跑，不动它）")
print("8) 关之后:", api.tunnel_status())
