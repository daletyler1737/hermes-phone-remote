# v0.3.2 — Switchable phone page · the pairing door can now open onto the third-party WebUI

English (this page) · **[中文说明 ↓](#chinese)** · Released 2026-10-17

---

## What changed

| # | Change |
|---|---|
| 1 | **The pairing door's upstream is now a setting, not a hard-coded port.** Before: `cloudflared → :9121 (pair proxy) → :9119 (stock panel)`. Now the last hop is selectable: **WebUI** (the third-party one, default) or **panel** (previous behaviour). |
| 2 | **Default = the third-party WebUI.** A phone that gets through pairing lands on the page that was actually built for phones, instead of the desktop dashboard in a narrow window. |
| 3 | **New "Phone page" switcher** in the WebUI card (panel): `网页版 WebUI` / `自带面板`, with the effective upstream shown next to it. Switching it **replaces the running pair proxy** — a proxy only reads its upstream once, at startup. |
| 4 | **`/webui` accepts `phone_page`** (`"webui"` \| `"panel"`); it stores the choice in `phone-page.json` under the plugin state dir and returns the new upstream. Unknown values are rejected with `400` — a bad value can never corrupt the stored choice. |
| 5 | **The WebUI is started on demand.** If the phone page is the WebUI and nothing is listening on its port, the gate starts it before handing the phone over (otherwise the door opens onto an empty room). |
| 6 | **The pair proxy now reports its upstream** in `/pair/_ver` (`"upstream": "127.0.0.1:8787"`). The panel uses it to decide whether the running proxy is stale: different upstream **or** an older proxy that does not report one → kill and respawn. |

## What did NOT change

* **The door is exactly the same.** Same `cloudflared → :9121`, same one-shot pairing token, same approved-device cookie. The setting only decides **what an already-approved phone sees**. Unapproved devices still get `403 this device is not paired` and never see a sign-in page.
* The WebUI still binds to `127.0.0.1` only. The trusted identity header (`Remote-User`) is still injected by the proxy and still only honoured from loopback.

## Live verification (this machine)

```
$ HPR_UPSTREAM=127.0.0.1:8787 python tools/pair_proxy.py       # gate in front of the WebUI
/pair/_ver            -> {"mtime": …, "pid": 21784, "upstream": "127.0.0.1:8787"}
GET /  (unapproved)   -> 403 forbidden: this device is not paired
GET http://127.0.0.1:8787/ -> 200 <title>Hermes — Sign in</title>   # WebUI is up and is the target
```

## Install

Download **`phone-remote-v0.3.2-plugin.zip`** (full package):

1. `plugin.js` → `%LOCALAPPDATA%\hermes\desktop-plugins\phone-remote\plugin.js`
2. `dashboard\` → `%LOCALAPPDATA%\hermes\plugins\phone-remote\dashboard\`
3. `tools\pair_proxy.py` and `tools\dashboard_respawn.py` → `%LOCALAPPDATA%\hermes\plugins\phone-remote\dashboard\tools\`
4. Restart the desktop app (the desktop UI's "Connect phone" button uses the desktop app's own backend)

Or, from a clone: `python scripts/build_plugin.py --install`

---

## Updating from v0.3.1

Download **`phone-remote-v0.3.1-to-v0.3.2-update.zip`** (only the changed files) and copy them over the same three locations. `更新说明-UPDATE.txt` inside the package repeats this in both languages.

**After updating: restart the panel once** (panel → "Restart panel"), then pick 手机页面 in the WebUI card. The first pairing request after that swaps the pair proxy automatically.

---

## Checksums

```
61b6e0fbb9f5a60fcbe6d827a5cb75d2adac4e7396806f278d502fb1228251b3  phone-remote-v0.3.2-plugin.zip
3724095648a8ae518fad94408364163680a9619c06fe0e439e387eb524384236  phone-remote-v0.3.1-to-v0.3.2-update.zip
```

---

## Requirements

- Hermes desktop (which ships the dashboard). Verified on Windows; other platforms untested.
- **Internet mode** needs `cloudflared` (reused from a local DSH desktop install if present).
- Same Wi-Fi → **LAN mode** is enough; no public address needed.
- The third-party WebUI is optional: `手机页面 → 网页版 WebUI` without the WebUI installed is refused with a clear 400 instead of quietly opening the door onto nothing — switch back to `自带面板` and it still works.

---

## Tests

`python tests/test_phone_page.py` — 7 checks (default is the WebUI, switching persists, invalid values rejected with 400, upstream comparison drives the proxy replacement, unknown upstream / old proxy both count as stale, missing WebUI directory is a 400 when starting the gate but only "unknown" for status, switching back to the panel needs no WebUI directory).
`tests/test_pair_proxy_ver.py` additionally asserts the proxy now reports `upstream`.
Full suite: **14/14 passed** (run with `PYTHONPATH` pointing at the Hermes agent dir, as `test_tunnel*.py` import `hermes_yaml`).

<a id="chinese"></a>

---

# v0.3.2 — 手机页面可切换 · 配对门禁后面可以接第三方网页版

中文（本页） · **[English ↑](#v032--switchable-phone-page--the-pairing-door-can-now-open-onto-the-third-party-webui)** · 发布 2026-10-17

## 本次改动

| # | 改动 |
|---|---|
| 1 | **门禁上游从写死的端口变成了一个设置。** 以前是 `cloudflared → :9121 配对反代 → :9119 自带面板`；现在最后一段可选：**网页版 WebUI**（第三方，默认）或**自带面板**（原行为）。 |
| 2 | **默认走第三方网页版。** 手机过了配对之后，看到的是本来就为手机做的那个界面，而不是挤在窄屏里的桌面 dashboard。 |
| 3 | **网页版卡里新增「手机页面」切换**：`网页版 WebUI` / `自带面板`，旁边直接显示当前生效的上游。切换会**换掉正在跑的门禁反代**——反代只在启动时读一次上游，不换就等于没切。 |
| 4 | **`/webui` 接口支持 `phone_page`**（`"webui"` \| `"panel"`）：选择存到插件状态目录的 `phone-page.json`，并返回新上游。非法值一律 400 拒绝，写坏不了已存的选择。 |
| 5 | **网页版按需拉起。** 手机页面选了网页版而它的端口没人听，门禁会在放行前把它起来，免得「开了门里面没人」。 |
| 6 | **反代现在会自报上游**：`/pair/_ver` 里多了 `"upstream": "127.0.0.1:8787"`。面板靠它判断在跑的进程是不是过期的——上游不一样**或**是改造前不报上游的旧进程，就杀掉重拉。 |

## 没有改的东西

* **门禁一模一样。** 还是 `cloudflared → :9121`、还是一次性配对 token、还是已批准设备 cookie。这个设置只决定**已经批准的手机进门后看到谁**。没批准的设备照样 `403 this device is not paired`，连登录页都看不到。
* 网页版依旧只绑 `127.0.0.1`；可信身份头（`Remote-User`）依旧由反代注入、只认来自回环的请求。

## 本机实测

```
$ HPR_UPSTREAM=127.0.0.1:8787 python tools/pair_proxy.py       # 门禁接在网页版前面
/pair/_ver            -> {"mtime": …, "pid": 21784, "upstream": "127.0.0.1:8787"}
GET /  （未批准设备）  -> 403 forbidden: this device is not paired
GET http://127.0.0.1:8787/ -> 200 <title>Hermes — Sign in</title>   # 网页版在跑，且就是目标
```

## 安装

下载 **`phone-remote-v0.3.2-plugin.zip`**（全量包），覆盖三个位置后重启桌面版；只升级用 **`phone-remote-v0.3.1-to-v0.3.2-update.zip`**（只含改动文件，包内 `更新说明-UPDATE.txt` 中英双文）。

**升完先重启一次面板**（面板里点「重启面板」），然后在网页版卡里选「手机页面」。之后第一次配对请求会自动把门禁反代换过来。

## 校验

```
61b6e0fbb9f5a60fcbe6d827a5cb75d2adac4e7396806f278d502fb1228251b3  phone-remote-v0.3.2-plugin.zip
3724095648a8ae518fad94408364163680a9619c06fe0e439e387eb524384236  phone-remote-v0.3.1-to-v0.3.2-update.zip
```

## 测试

`python tests/test_phone_page.py` —— 7 项（默认网页版、切换持久化、非法值 400、上游比对驱动反代换届、没报上游/旧进程都算过期、缺网页版目录时起门禁报 400 而状态查询只是「不知道」、切回自带面板不依赖网页版目录）。
`tests/test_pair_proxy_ver.py` 追加断言：反代 `_ver` 必须带 `upstream`。
全量回归 **14/14 通过**（跑 `test_tunnel*.py` 时 `PYTHONPATH` 要指向 Hermes agent 目录，它要 import `hermes_yaml`）。
