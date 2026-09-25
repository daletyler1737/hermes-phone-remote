# -*- coding: utf-8 -*-
"""实测互联网模式：真起 cloudflared，真从公网拉一次，再关掉。"""
import sys, ssl, urllib.request, urllib.error

sys.path.insert(0, r"E:\zip\agent file big\01_项目代码\hermes-phone-remote\dashboard")
import plugin_api as api

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
print("7) 关隧道:", api._stop_tunnel())
print("8) 关之后:", api.tunnel_status())
