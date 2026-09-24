# Phone Remote (Hermes desktop plugin)

> English ｜ 中文: [README.md](README.md)

Adds a **Connect phone** entry to the Hermes desktop app: show a QR code, scan it with your phone,
and keep chatting with Hermes from the phone. A free, self-hosted stand-in for paid
"scan-to-pair + remote chat" features such as ekko — **no extra service, no bespoke backend**;
it simply reuses the dashboard that ships with Hermes.

## Status

**Work in progress, v0.1.0** (2026-09-24). The plugin is complete and statically verified
(ESM syntax check, real QR decode via OpenCV, host contract matched against the bundled
`wallpaper` plugin), but has **not yet been exercised end-to-end on a real phone**.
Mobile portrait layout of the stock dashboard is not adapted.

## How it works

- Phone page = the stock dashboard: `hermes dashboard --host 0.0.0.0 --port 9119`
- Chat transport = dashboard `/api/pty` WebSocket (ConPTY on Windows)
- Auth = dashboard `basic_auth`; gated mode mints a one-shot ticket for the WebSocket
- QR = [qrcode-generator](https://github.com/kazuhikoarase/qrcode-generator) (MIT) inlined,
  because desktop plugins may only import `@hermes/plugin-sdk`, `react`, `react/jsx-runtime`
- Entry points = `PALETTE_AREA` (Ctrl+K), `ROUTES_AREA` (full page), `SIDEBAR_NAV_AREA`

There is **no scan-to-login**: the dashboard exposes no magic-link/invite-token endpoint,
so the phone logs in once by hand and then relies on its session cookie.

## Install

```bash
python scripts/build_plugin.py --install     # build + copy into the desktop plugins dir
scripts\start_dashboard.bat                  # start a LAN-reachable dashboard
# then, as admin once:
# New-NetFirewallRule -DisplayName "Hermes Phone Chat 9119" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 9119
# then in the app: Ctrl+K -> "Reload desktop plugins" -> Ctrl+K -> "Connect phone"
```

Credentials are never stored in this repo. Read the current ones with:

```bash
hermes config get dashboard.basic_auth
```

## Host contracts worth remembering

- `render` belongs at the **top level** of `ctx.register({...})`, not inside `data`.
- Notifications use the object form: `host.notify({ kind, message })`.
- Sidebar nav items take `data: { path, label, codicon }`.
- Only the SDK, react and react/jsx-runtime may be imported; everything else gets inlined.
- Saving a plugin file does not reliably hot-reload a **newly added** folder — use
  `Reload desktop plugins` from the command palette.
- The QR SVG must stay black-on-white (never theme-tinted) or phones fail to scan.

## JS runtimes

Build and verify scripts use only standard ESM plus `node:fs` — **no npm dependencies**,
so any of the three runtimes runs them unchanged:

```bash
node scripts/verify_qr.mjs
bun  scripts/verify_qr.mjs
deno run --allow-read scripts/verify_qr.mjs
```

All three produce an identical matrix for the default URL (25x25, dark=332/625).
Verified on node 22.22.3 / bun 1.4.2 / deno 2.9.6
(`npm i -g bun deno --registry=https://registry.npmmirror.com`).

## Repo layout

```
src/plugin.template.js       maintainable source (QR library kept as /*__QR_INLINE__*/ placeholder)
vendor/qrcode-generator.js   MIT QR library, inlined at build time
scripts/build_plugin.py      template + vendor -> plugin.js  (--install copies into the plugins dir)
scripts/start_dashboard.bat  start a LAN-reachable dashboard
plugin.js                    build output (= what Hermes loads)
```

## License

MIT. Contains no credentials; secrets and LAN-bearing artifacts are gitignored.
