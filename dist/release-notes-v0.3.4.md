# v0.3.4 - The status probe follows the phone page too

English (this page) · <a id="chinese">中文说明 ↓</a> · Released 2026-10-20

v0.3.3 moved the LAN card (QR / address / password) to the WebUI port. The **status line
below it still probed 9119**, so with the WebUI selected the card said
*"未检测到服务（9119 没在跑）"* while the WebUI was happily serving on 8787.

**Fix:** the probe target now follows the phone page — the WebUI root on 8787, or the
panel `/api/status` on 9119 when the phone page is the stock panel. The offline hint
names the port it actually probed.

## SHA256

```
5d9edbb7f95b8081747f3320bff305df50d3d31f6be9845214abe3a3dbb91c07  phone-remote-v0.3.4-plugin.zip
70826233d5be58d3198e6ddf5d97a636451ba2bbfc0d4e3480cfb3b51ae4d570  phone-remote-v0.3.3-to-v0.3.4-update.zip
```

---

<a id="chinese"></a>

# v0.3.4 - 状态探测也跟着手机页面走

v0.3.3 把局域网卡（二维码/地址/密码）换到了网页版端口，但**下面那行状态还在探 9119**，
于是选了网页版之后，卡片一边显示 8787 的地址，一边报「未检测到服务（9119 没在跑）」。

**改法**：探测目标跟着手机页面走 —— 网页版就探 8787 的根路径，选自带面板才探 9119 的
`/api/status`；离线提示里写的是它真正探的那个端口。

## SHA256

```
5d9edbb7f95b8081747f3320bff305df50d3d31f6be9845214abe3a3dbb91c07  phone-remote-v0.3.4-plugin.zip
70826233d5be58d3198e6ddf5d97a636451ba2bbfc0d4e3480cfb3b51ae4d570  phone-remote-v0.3.3-to-v0.3.4-update.zip
```
