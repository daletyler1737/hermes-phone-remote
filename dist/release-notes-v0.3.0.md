# v0.3.0 — Close panel · one-step restart · self-renewing pairing QR

English (this page) · **[中文说明 ↓](#chinese)** · Released 2026-09-27

---

## What changed

| # | Change |
|---|---|
| 1 | **New: Close panel.** A close button appears next to "service running" in the status bar. It kills the process holding the port, and tears down the public tunnel with it — otherwise the tunnel outlives the panel and the public URL keeps pointing at a dead page. If the port is held by the desktop app itself, it refuses with **409** instead of taking the desktop app down. |
| 2 | **Restart is now one step.** Previously it only shut down and you had to click "start" again. Now it shuts down and respawns in a single action, with progress shown in the UI. |
| 3 | **Pairing QR renews itself.** A pending link that passes its 10-minute TTL is replaced in place — new token, timer restarted, and the card refreshes on the UI's own poll. No more dead codes, and no trip back to the PC to press "new link". `approved` / `claimed` / `denied` are never touched. |
| 4 | Fixed the "restart" button label not matching what it actually did. |
| 5 | **No more terminal windows flashing** on start or restart (every child process now uses `CREATE_NO_WINDOW`). |
| 6 | Port detection uses the socket table instead of parsing `netstat` text, which silently returned 0 here (the panel could not find the process holding the port). |
| 7 | Tunnel notices report the real expiry timestamp instead of a hard-coded "extended by 2 hours". |
| 8 | Security: `/pair/_ver` version handshake (the panel replaces a reverse proxy still running old code), token allow-list + Host escaping, client IP taken from `CF-Connecting-IP`, and **403 for any unapproved device** under the tunnel — unapproved devices do not even get the login page. |

Pairing tokens are stdlib `secrets.token_urlsafe(24)` — 192 bit, 32 characters, 10-minute TTL, `hmac.compare_digest` comparison, one-shot on claim — with "no `random.` in the source" locked into the regression suite.

### Why a 10-minute token does not drop your phone

The pairing token only covers the moment you scan. Devices that are already paired authenticate with the official **session cookie** (access 12 h, refresh 30 days, sliding), and the gate never looks at the token — so "rotating every 10 minutes" and "the device stays connected" do not conflict.

The one real exception: a free quick tunnel gets a new `trycloudflare.com` slug every time it restarts, and browsers do not send cookies across domains — so after a tunnel restart the phone must scan once more. Only a named tunnel on your own domain avoids that.

---

## Install

Download **`phone-remote-v0.3.0-plugin.zip`** (full package, 68 KB):

1. `plugin.js` → `%LOCALAPPDATA%\hermes\desktop-plugins\phone-remote\plugin.js`
2. `dashboard\` → `%LOCALAPPDATA%\hermes\plugins\phone-remote\dashboard\`
3. `tools\pair_proxy.py` and `tools\dashboard_respawn.py` → `%LOCALAPPDATA%\hermes\plugins\phone-remote\dashboard\tools\`
4. Restart the desktop app (the "Connect phone" button in the desktop UI uses the desktop app's own backend)

Or, from a clone: `python scripts/build_plugin.py --install`

---

## Updating from v0.2.0

Download **`phone-remote-v0.2.0-to-v0.3.0-update.zip`** (67 KB — only the 5 changed files), copy them over the 3 locations listed inside `更新说明-UPDATE.txt`, then click **Restart panel** in the panel.

> The incremental package is barely smaller than the full one (67 KB vs 68 KB): `plugin.js` alone is 110 KB and changed as a whole. Its value is telling you exactly which 5 files to overwrite, not saving bandwidth.

---

## Checksums

```
61a21e4ec89d67b56457d868c10b04ffa4e8c1eb46ef550174cb30a72e4e17e3  phone-remote-v0.3.0-plugin.zip
c9510994268eb2b348f6faa185a16b97c6781643665adfc393d60506a4b7bebc  phone-remote-v0.2.0-to-v0.3.0-update.zip
```

---

## Requirements

- Hermes desktop (which ships the dashboard). Verified on Windows; other platforms untested.
- **Internet mode** needs `cloudflared` (reused from a local DSH desktop install if present).
- Same Wi-Fi → **LAN mode** is enough; no public address needed.
- The stock dashboard's mobile portrait layout is not adapted (use landscape or "desktop site").

<a id="chinese"></a>

---

# 中文说明 / Chinese

**[English ↑](#v030--close-panel--one-step-restart--self-renewing-pairing-qr)** · 发布于 2026-09-27

## 本次变更

| # | 变更 |
|---|---|
| 1 | **新增「关闭面板」**：状态栏「服务运行中」旁出现关闭按钮，点掉的是**占端口的那个进程**；公网隧道一起收（面板一死隧道就没人管，公开地址会一直挂着指向死页面）。占端口的是桌面版本体时 **409 拒绝**，绝不把桌面版一起带走。 |
| 2 | **「重启面板」一步到位**：以前是「只关掉、还要再点一次启动」，现在是关掉 + 自动拉起一气呵成，前端显示进度。 |
| 3 | **配对二维码过期自动换新**：`pending` 链接一过期就地换新 token 并重新计时，前端每 2.5 s 轮询后卡片自己刷新 —— 不再变成死码，也不用回电脑点「换一个新链接」。`approved / claimed / denied` 一律不碰。 |
| 4 | 修复「重新启动」按钮文案与真实行为不符。 |
| 5 | 插件运行/重启**不再闪任何终端窗口**（子进程一律 `CREATE_NO_WINDOW`）。 |
| 6 | 端口探测改走 socket 列表：`netstat` 文本解析在本机会静默返回 0，导致「找不到占用端口的进程」。 |
| 7 | 隧道提示不再出现写死的「已延长 2 小时」，只报**真实到期时刻**。 |
| 8 | 安全：反代 `/pair/_ver` 版本握手（面板启动时自动换掉跑旧代码的反代进程）、token 白名单 + Host 转义、客户端 IP 以 `CF-Connecting-IP` 为准、**隧道下未批准设备一律 403**（连登录页都拿不到）。 |

配对 token 为 stdlib `secrets.token_urlsafe(24)`（192 bit、32 字符、10 分钟 TTL、`hmac.compare_digest` 比较、claim 即焚），并已把「源码里不许出现 `random.`」锁进回归测试。

### 为什么 token 10 分钟一变、手机不会掉线

配对 token 只管扫码那一下。已配对的设备凭的是**官方 session cookie**（access 12 h / refresh 30 天且滑动续期），门禁从不看 token —— 所以「每 10 分钟轮换」和「设备长期稳定在线」本来就不冲突。

唯一的真实例外：免费 quick tunnel 每次重启都换一个 `trycloudflare.com` 域名，浏览器不会把旧域名的 cookie 发到新域名 —— 隧道重开后手机要重扫一次。要「重开也不掉」只能自有域名 + named tunnel。

## 安装

下载 **`phone-remote-v0.3.0-plugin.zip`**（全量，68 KB）：

1. `plugin.js` → `%LOCALAPPDATA%\hermes\desktop-plugins\phone-remote\plugin.js`
2. `dashboard\` → `%LOCALAPPDATA%\hermes\plugins\phone-remote\dashboard\`
3. `tools\pair_proxy.py`、`tools\dashboard_respawn.py` → `%LOCALAPPDATA%\hermes\plugins\phone-remote\dashboard\tools\`
4. 重启桌面版（桌面上的「连接手机」按钮走桌面版自己的后端）

或从仓库装：`python scripts/build_plugin.py --install`

## 从 v0.2.0 更新

下载 **`phone-remote-v0.2.0-to-v0.3.0-update.zip`**（增量，67 KB，只含本次改动的 5 个文件），按包内 `更新说明-UPDATE.txt` 覆盖 3 个位置，然后点面板里的「重启面板」。

> 增量包并不比全量小多少（67 KB vs 68 KB）—— 变动的大头 `plugin.js` 本身就有 110 KB 且整体变了。增量包的价值在于「明确告诉你只需覆盖这 5 个文件」，而不是省下载量。

## 环境要求

- Hermes 桌面版（自带 dashboard）；Windows 实测通过，其他平台未测
- **互联网模式**需要 `cloudflared`（本机装了 DSH desktop 会自动借用）
- 手机与电脑同一 Wi-Fi 用**局域网模式**即可，不需要公网
- 手机竖屏未适配官方 dashboard 布局，建议横屏或浏览器「桌面版网站」
