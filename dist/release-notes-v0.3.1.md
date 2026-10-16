# v0.3.1 — WebUI password binding · approved phones enter with no password

English (this page) · **[中文说明 ↓](#chinese)** · Released 2026-10-16

---

## What changed

| # | Change |
|---|---|
| 1 | **The third-party WebUI password is now managed here.** Changing the panel password writes the same string into the WebUI `.env` and restarts the WebUI, so there is exactly **one password to remember**. If the sync fails it is swallowed and reported — it never breaks the password change itself. |
| 2 | **New "WebUI" card** in the panel: show / hide the password, copy it, **bind it to the panel password**, start, restart and stop the WebUI, with the live state (`running` / `stopped`) and the loopback URL. |
| 3 | **New `/webui` API.** `GET` returns directory, host, port, running state, password and the trusted-header settings; `POST` writes password/host/port and runs `start` / `stop` / `restart`. A restart **really kills the old process and waits for the port** before respawning — the old "closed but not restarted" failure mode again. |
| 4 | **Trusted identity is wired up.** The pair proxy is now started with `HPR_TRUSTED_USER` (the panel login name), so an **approved phone enters the WebUI with no password at all**. The proxy strips any same-named header sent by the client and writes its own, and the WebUI only honours that header from `127.0.0.1` — a LAN device cannot forge it. |
| 5 | **The WebUI binds to loopback only** (`127.0.0.1`). Other devices on the LAN can no longer reach its sign-in page; the only way in from outside is the pairing door. |
| 6 | Fixed: the panel could previously expose the WebUI on `0.0.0.0` and leak sign-in pages to the whole subnet. |

## How the password binding works

```
panel password (one string, changed in the panel)
        ├── config.yaml      dashboard.basic_auth  → hash + secret  (panel login)
        └── WebUI .env       HERMES_WEBUI_PASSWORD → same string    (web UI login)
```

* Changing the password in the panel triggers `_webui_sync_password()`; if the WebUI is running it is restarted so the new string takes effect immediately.
* The plaintext is never stored twice in `config.yaml` (hash only) — the WebUI copy is the single place the string is kept for you.
* **Phones never use this password.** A paired device is authenticated by the panel session and gets its identity injected by the proxy.

### Why the identity header is safe

`Remote-User` is only accepted by the WebUI when the request comes from `127.0.0.1`. The proxy runs on the same machine, so it is the only writer. The proxy also removes any `Remote-User` header a client sends before adding its own, so a paired-but-malicious client cannot pick a different name.

## Install

Download **`phone-remote-v0.3.1-plugin.zip`** (full package):

1. `plugin.js` → `%LOCALAPPDATA%\hermes\desktop-plugins\phone-remote\plugin.js`
2. `dashboard\` → `%LOCALAPPDATA%\hermes\plugins\phone-remote\dashboard\`
3. `tools\pair_proxy.py` and `tools\dashboard_respawn.py` → `%LOCALAPPDATA%\hermes\plugins\phone-remote\dashboard\tools\`
4. Restart the desktop app (the "Connect phone" button in the desktop UI uses the desktop app's own backend)

Or, from a clone: `python scripts/build_plugin.py --install`

---

## Updating from v0.3.0

Download **`phone-remote-v0.3.0-to-v0.3.1-update.zip`** (only the changed files) and copy them over the same three locations. `更新说明-UPDATE.txt` inside the package repeats this in both languages.

---

## Checksums

```
864444f18d83015fafab2e00d3ff60c3c8842051b2fdb96dead2bfbbf84c5124  phone-remote-v0.3.1-plugin.zip
c1e799dd6118f7f344e94ecb48b8258dc69604fdf8fe7cbe285be953c6776583  phone-remote-v0.3.0-to-v0.3.1-update.zip
```

---

## Requirements

- Hermes desktop (which ships the dashboard). Verified on Windows; other platforms untested.
- **Internet mode** needs `cloudflared` (reused from a local DSH desktop install if present).
- Same Wi-Fi → **LAN mode** is enough; no public address needed.
- The third-party WebUI is optional — the card simply reports "not found" when it is not installed.

---

## Tests

`python tests/test_webui_binding.py` — 8 checks (env rewrite keeps comments/order, weak passwords rejected, password lands in `.env`, sync does not spawn a process when the WebUI is stopped, missing directory degrades gracefully).
Full suite: **13/13 passed**, including `test_trusted_identity_header.py` (the forged header is stripped) and `test_restart_flow.py` (restart really replaces the port holder).

<a id="chinese"></a>

---

# v0.3.1 — 网页版密码绑定 · 已批准的手机免密进网页版

中文（本页） · **[English ↑](#v0.3.1-webui-password-binding--approved-phones-enter-with-no-password)** · 发布 2026-10-16

## 本次改动

| # | 改动 |
|---|---|
| 1 | **第三方网页版（WebUI）的密码改由插件统一管。** 面板上改密码时，同一串会写进网页版的 `.env` 并重启网页版——**只需要记一个密码**。同步失败会被兜住并在界面上报出来，绝不让「改密码」这一步挂掉。 |
| 2 | **面板新增「网页版 WebUI」卡**：显示/隐藏密码、复制、**与面板密码绑定**、启动、重启、停止；状态（运行中/未运行）和本机地址都直接显示。 |
| 3 | **新增 `/webui` 接口**：`GET` 返回目录、主机、端口、运行状态、当前密码与可信头配置；`POST` 可写密码/主机/端口，并执行 `start` / `stop` / `restart`。重启是**真杀旧进程、等端口真空再拉起**——不是「只关闭、还得再点一次启动」。 |
| 4 | **可信身份接线完成**：起门禁反代时带上 `HPR_TRUSTED_USER`（面板登录名），**已批准的手机进网页版完全不需要密码**。反代会先剥掉客户端自带的同名头再写自己的；网页版只认来自 `127.0.0.1` 的这个头，局域网设备伪造不了。 |
| 5 | **网页版只绑回环**（`127.0.0.1`）：同网段的别的设备连它的登录页都看不到，对外入口只剩配对门禁。 |
| 6 | 修掉一个安全口子：网页版此前可能监听在 `0.0.0.0`，等于把登录页摊给整个网段。 |

## 密码绑定是怎么绑的

```
面板密码（一处在面板上改）
        ├── config.yaml      dashboard.basic_auth  → 哈希 + secret （面板登录）
        └── 网页版 .env      HERMES_WEBUI_PASSWORD → 同一串      （网页版登录）
```

* 在面板改密码会触发 `_webui_sync_password()`；网页版在跑就顺手重启，立刻生效。
* `config.yaml` 里不会留第二份明文（只存哈希）——网页版那份就是留给你看的那份。
* **手机永远不用这串密码**：已配对的设备靠面板会话认证，身份由反代注入。

## 安装

下载 **`phone-remote-v0.3.1-plugin.zip`**（全量包），覆盖三个位置后重启桌面版；只升级用 **`phone-remote-v0.3.0-to-v0.3.1-update.zip`**（只含改动文件，包内 `更新说明-UPDATE.txt` 中英双文）。

## 校验

```
864444f18d83015fafab2e00d3ff60c3c8842051b2fdb96dead2bfbbf84c5124  phone-remote-v0.3.1-plugin.zip
c1e799dd6118f7f344e94ecb48b8258dc69604fdf8fe7cbe285be953c6776583  phone-remote-v0.3.0-to-v0.3.1-update.zip
```
