# -*- coding: utf-8 -*-
import os, subprocess, sys, time
sys.path.insert(0, r"E:\zip\agent file big\01_项目代码\hermes-phone-remote\dashboard")
import plugin_api as api
res = api.tunnel(api.TunnelBody(action="start"))
url = res.get("url", "")
time.sleep(4)
print("URL =", url)
for path in ("/", "/login", "/api/plugins/phone-remote/status"):
    p = subprocess.run(["curl", "-s", "-o", "NUL", "-w", "%{http_code}", "--max-time", "30", url + path],
                       capture_output=True, text=True)
    print("curl %-40s -> %s" % (path, (p.stdout or "").strip()))
print("stop:", api._stop_tunnel())
