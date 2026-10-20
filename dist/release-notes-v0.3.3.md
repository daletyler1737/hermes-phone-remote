# v0.3.3 — The LAN card follows the phone page

English (this page) · <a id="chinese">中文说明 ↓</a> · Released 2026-10-20

The pairing door already let you choose **which page an approved phone lands on**
(third-party WebUI, default, or the stock panel). v0.3.3 closes the last gap: the
**LAN card in the plugin now follows that choice**.

## What changed

| # | Change | Where |
|---|---|---|
| 1 | The LAN card's **QR code, address and password** point at the **WebUI port (8787)** when the phone page is "webui" — the panel port (9119) is used only when the page is "panel" | `src/plugin.template.js` |
| 2 | The **account row is hidden** in WebUI mode: the WebUI asks for one password only, and it is the same string as the panel password | `src/plugin.template.js` |
| 3 | Selecting "webui" now **opens the WebUI up to the local network** (`HERMES_WEBUI_HOST=0.0.0.0`) and restarts it — a loopback-only WebUI is invisible to the phone on the same WiFi | `dashboard/plugin_api.py` |
| 4 | The WebUI card shows **"已允许同网段访问"** when the WebUI is network-visible | `src/plugin.template.js` |

## Unchanged (deliberately)

- The pairing door itself is untouched: one-shot token, approved-device cookie, everything
  else gets **403** and never sees a login page.
- The WebUI still trusts only `Remote-User` coming from `127.0.0.1/32` — a phone that
  forges the header by itself is rejected.
- One password for both places: the panel password is written into the WebUI `.env`.

## Install

- Full package: `phone-remote-v0.3.3-plugin.zip`
- Incremental (from v0.3.2): `phone-remote-v0.3.1-to-v0.3.2-update.zip` → rename to
  `phone-remote-v0.3.2-to-v0.3.3-update.zip`

Drop `plugin.js` into `%LOCALAPPDATA%\hermes\desktop-plugins\phone-remote\`,
`dashboard\plugin_api.py` + `dashboard\manifest.json` into
`%LOCALAPPDATA%\hermes\plugins\phone-remote\dashboard\`, and `tools\pair_proxy.py`
into `%LOCALAPPDATA%\hermes\plugins\phone-remote\dashboard\tools\`.

## SHA256

```
43b08a9462acbf3ce93b56424478a0e18b5e47f1c5b0d266faffeacf9fe6bf12  phone-remote-v0.3.3-plugin.zip
56734de284b83ae5e3439253640145ea46c004fa9e667fb967d121d68055ccb2  phone-remote-v0.3.2-to-v0.3.3-update.zip
```

---

<a id="chinese"></a>

# v0.3.3 — 局域网卡跟着「手机页面」走

配对门禁本来就能选**批准的手机进门后看到谁**（三方网页版，默认；或自带面板）。
v0.3.3 把最后一处补上：**插件里那张局域网卡也跟着这个选择走**。

## 改了什么

| # | 改动 | 在哪 |
|---|---|---|
| 1 | 选了「网页版」时，局域网卡的**二维码、地址、密码**全指向**网页版端口（8787）**；只有选「自带面板」才用 9119 | `src/plugin.template.js` |
| 2 | 网页版模式下**隐藏「账号」行** —— 网页版只要一串密码，而且和面板密码是同一个 | `src/plugin.template.js` |
| 3 | 选「网页版」时，后端顺手把网页版**放开到局域网**（`HERMES_WEBUI_HOST=0.0.0.0`）并重启 —— 只绑回环的话同网段手机根本看不到 | `dashboard/plugin_api.py` |
| 4 | 网页版那张卡在已放开时显示「已允许同网段访问」 | `src/plugin.template.js` |

## 故意没动的

- **门禁本身零改动**：一次性 token、已批准设备 cookie，其它一律 403、拿不到登录页。
- 网页版仍然只信**来自 127.0.0.1/32 的 `Remote-User`** —— 手机自己伪造这个头一样进不去。
- 两处一个密码：面板密码会写进网页版的 `.env`。

## 安装

- 全量包：`phone-remote-v0.3.3-plugin.zip`
- 增量包（从 v0.3.2 升）：`phone-remote-v0.3.1-to-v0.3.2-update.zip` → 改名为
  `phone-remote-v0.3.2-to-v0.3.3-update.zip`

落点：`plugin.js` → `%LOCALAPPDATA%\hermes\desktop-plugins\phone-remote\`；
`dashboard\plugin_api.py` + `dashboard\manifest.json` → `%LOCALAPPDATA%\hermes\plugins\phone-remote\dashboard\`；
`tools\pair_proxy.py` → `%LOCALAPPDATA%\hermes\plugins\phone-remote\dashboard\tools\`。

## SHA256

```
43b08a9462acbf3ce93b56424478a0e18b5e47f1c5b0d266faffeacf9fe6bf12  phone-remote-v0.3.3-plugin.zip
56734de284b83ae5e3439253640145ea46c004fa9e667fb967d121d68055ccb2  phone-remote-v0.3.2-to-v0.3.3-update.zip
```
