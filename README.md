# 连接手机 · Phone Remote

> Hermes 官方桌面版插件 ｜ English: [README.en.md](README.en.md)

在 Hermes 桌面版里加一个「连接手机」入口：**出二维码 → 手机扫码 → 在手机上继续和 Hermes 对话**。
对标 ekko 等付费的「扫码配对 + 手机远程聊天」功能，**零额外服务、零自研后端** —— 直接复用 Hermes 自带的 dashboard。

---

## 状态 / Status

**半成品 v0.1.0**（2026-09-24）。插件代码已完成，通过以下静态验证，但**尚未经过真人手机端到端使用**：

- ✅ ESM 语法检查（`node --check`）
- ✅ 二维码真扫验证：从成品文件里抽出编码段运行，用 OpenCV `QRCodeDetector` 解出正确 URL
- ✅ 与宿主契约逐项对齐（对照官方自带插件 `wallpaper/plugin.js` 的写法）
- ✅ 服务侧实测：`/api/status` 200、`/` 302、走局域网 IP 也返回 302（0.0.0.0 绑定生效）、防火墙规则 Allow

**未验证**：手机浏览器实际扫码登录 + 长时间对话体验；官方 dashboard 在手机竖屏下的排版未做适配层。

## 它做什么 / 不做什么

| | |
|---|---|
| **做** | Ctrl+K 搜「连接手机」→ 整页二维码 + 地址 + 账号信息 → 手机扫码打开 Hermes Web UI → 在手机上继续对话、切换会话 |
| **不做** | 不做独立手机 App；不自研 Web 聊天后端；不触碰会话数据库（全部走官方 dashboard 链路） |

## 原理 / How it works

| 层 | 用什么 | 说明 |
|---|---|---|
| 手机页面 | Hermes 自带 dashboard | `hermes dashboard --host 0.0.0.0 --port 9119` |
| 对话通道 | dashboard 的 `/api/pty` WebSocket | Windows 下走 ConPTY，手机上的输入直接进入终端会话 |
| 鉴权 | dashboard `basic_auth` | gated 模式下一次 ticket 换 WS 连接，不用长期 token |
| 二维码 | 内联 `qrcode-generator` (MIT) | 桌面插件不能 import 外部 npm 包，故把库源码内联进 `plugin.js` |
| 入口注册 | 插件 SDK 三个区域 | `PALETTE_AREA`（Ctrl+K）、`ROUTES_AREA`（整页）、`SIDEBAR_NAV_AREA`（侧栏） |

扫码即登录**做不到**：Hermes dashboard 没有 magic-link / invite token 端点（`login_page.py` 明确不注入 token），所以手机上**首次要手动登录一次**，之后靠会话 Cookie 记住。

## 安装 / Install

```bash
# 1) 构建并安装到 Hermes 桌面插件目录
python scripts/build_plugin.py --install
#    （可带 --ip 192.168.1.50 --port 9119 --user dale 覆盖默认值）

# 2) 启动手机可访问的 dashboard
scripts\start_dashboard.bat

# 3) 放行防火墙（管理员 PowerShell，只需一次）
New-NetFirewallRule -DisplayName "Hermes Phone Chat 9119" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 9119

# 4) 桌面版里加载插件
#    Ctrl+K → 搜 "Reload desktop plugins" → 回车
#    Ctrl+K → 搜 "连接手机" → 回车
```

## 使用 / Usage

打开「连接手机」页后：

1. 手机相机 / 微信扫左侧二维码（手机要和电脑在**同一个 Wi-Fi**）
2. 首次打开会看到登录页 —— 输入下面显示的账号和密码，勾选「记住」
3. 之后手机上就能接着对话了

密码不写在插件里。查看当前 dashboard 凭据：

```bash
hermes config get dashboard.basic_auth        # 显示用户名与密码
```

页面「设置」区可把密码粘贴一次，插件只存到**本机** `ctx.storage`，方便以后直接点「复制」。

## 参数速查 / Settings

| 项 | 默认值 | 说明 |
|---|---|---|
| 局域网 IP | `192.168.1.34` | 插件设置区可改；命令行 `ipconfig` 查；换网络后要更新 |
| 端口 | `9119` | 与 dashboard 启动参数一致 |
| 用户名 | `dale` | 即 `dashboard.basic_auth.username` |
| 密码 | 空 | 不预置；粘贴一次后由插件本地保存 |
| 启动脚本目录 | `05_工具脚本\hermes-phone` | 页面「打开启动脚本文件夹」按钮指向它，可按需改 |

## 故障排查 / Troubleshooting

| 现象 | 原因与处理 |
|---|---|
| Ctrl+K 搜不到「连接手机」 | 插件没被扫描 → Ctrl+K 搜 **"Reload desktop plugins"**；仍没有就重载窗口（Ctrl+R）或重启桌面版 |
| 手机打不开地址 | ① 服务在跑吗：`curl http://127.0.0.1:9119/api/status` 应为 200；② 防火墙是否放行 9119；③ 手机与电脑是否同一 Wi-Fi；④ 电脑 IP 是否变了（设置区更新） |
| 扫码后登录失败 | 用户名/密码不对 → `hermes config get dashboard.basic_auth` 核对 |
| 手机页面排版挤 | 官方 dashboard 是桌面版 Web UI，竖屏未适配；可用横屏或浏览器「桌面版网站」 |
| 电脑重启后失效 | dashboard 不会自启 → 双击 `scripts\start_dashboard.bat`（或做成开机任务） |

## 开发 / Development

```
hermes-phone-remote/
├─ src/plugin.template.js     # 可维护源码（QR 库处留 /*__QR_INLINE__*/ 占位符）
├─ vendor/qrcode-generator.js # MIT 许可的二维码库，构建时内联
├─ scripts/build_plugin.py    # 模板 + vendor → plugin.js（--install 同步到插件目录）
├─ scripts/start_dashboard.bat
└─ plugin.js                  # 构建产物（= Hermes 实际加载的文件）
```

### 宿主契约（踩过的坑，已对齐）

- **`render` 放在 `ctx.register({...})` 顶层**，不是塞在 `data` 里 —— 放错位置页面静默不显示。
- **通知用对象形式**：`host.notify({ kind: 'info', message: '...' })`；位置参数形式在部分版本不生效。
- 区域常量从 SDK 导入：`import { PALETTE_AREA, ROUTES_AREA, SIDEBAR_NAV_AREA } from '@hermes/plugin-sdk'`；侧栏条目的 `data` 是 `{ path, label, codicon }`。
- 插件**只能** `import` `@hermes/plugin-sdk` / `react` / `react/jsx-runtime`，其他 npm 包必须内联。
- **保存文件不保证热重载**：官方 `runtime-loader` 对「已存在插件」的文件改动有 fs-watch，但新建目录要走轮询 —— 可靠做法是手动 `Reload desktop plugins`。
- 二维码 SVG 是功能元素，**必须**保持白底黑码（不能用主题变量），否则手机扫不出。

### 验证手段（本项目实际用过）

```bash
node --check plugin.js                     # ESM 语法
# 二维码：把 makeQr 段抽出来在 node 里跑 → 矩阵 → OpenCV 解码比对
# 加载证明：插件 register 里打一行 console.log，
#           宿主会把 renderer console 转发到 <HERMES_HOME>/logs/desktop.log
```

## 致谢 / Credits

- 二维码库：[qrcode-generator](https://github.com/kazuhikoarase/qrcode-generator) © Kazuhiko Arase，MIT，见 `vendor/`。
- 思路参考：DeepSeek Harness 的 `dsh-remote-web-ui` 插件（其做法是删掉自研移动端页面，二维码直指官方 Web GUI —— 本项目沿用同一路线）。

## 许可 / License

MIT。**注意：本仓库不含任何凭据**；`.env`、二维码图片（含本机内网地址）等一律在 `.gitignore` 里。
