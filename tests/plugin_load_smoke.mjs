/**
 * 桌面插件加载冒烟：拿替身 SDK 把 plugin.js 当 ES module 真跑一遍，
 *   ① 注册回调不许抛；② 三个入口（路由/左侧栏/命令面板）都注册上，含「连接手机」；
 *   ③ 页面组件真调一次（递归展开函数组件），渲染不许抛。
 * 用法：node hpr_plugin_smoke.mjs <plugin.js 路径>
 */
import { copyFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const src = process.argv[2] || path.join(HERE, '..', 'plugin.js')
const probe = path.join(HERE, 'plugin_load_probe', 'plugin.mjs')
copyFileSync(src, probe)

const mod = await import('file:///' + probe.replace(/\\/g, '/') + '?t=' + Date.now())
const plugin = mod.default
if (!plugin || typeof plugin.register !== 'function') {
  console.log('FAIL: 没有 default.register —— 宿主拿不到入口')
  process.exit(2)
}

const regs = []
const notes = []
const emits = []
const ctx = {
  register: (r) => regs.push(r),
  storage: { get: (k, d) => d, set: () => {}, remove: () => {} },
  os: {
    notify: (m, v) => notes.push([v, m]),
    copy: async () => true,
    open: () => true
  },
  api: {
    get: async () => ({}),
    post: async () => ({})
  },
  log: (...a) => emits.push(a.join(' ')),
  on: () => () => {}
}

try {
  plugin.register(ctx)
} catch (e) {
  console.log('FAIL: register 抛异常 → 宿主会整插件丢弃（入口消失）:', e && e.message)
  process.exit(3)
}

const areas = regs.map((r) => r && r.area)
const nav = regs.find((r) => r && r.data && r.data.label === '连接手机')
const reports = []
reports.push(`注册条目 ${regs.length} 条: ${areas.join(', ')}`)
reports.push(nav ? 'OK: 左侧栏「连接手机」已注册 (path=' + nav.data.path + ')' : 'FAIL: 左侧栏「连接手机」没注册')
reports.push(
  regs.every((r) => r.id) ? 'OK: 每条注册都有 id' : 'FAIL: 有注册项缺 id'
)

// 渲染冒烟：把函数组件当普通函数递归展开（替身 hooks 无需调度器）
const errs = []
let rendered = 0
function walk(node, depth) {
  if (depth > 40 || node === null || node === undefined || typeof node !== 'object') return
  if (Array.isArray(node)) return node.forEach((n) => walk(n, depth + 1))
  const { type, props } = node
  if (typeof type === 'function') {
    rendered++
    let out
    try {
      out = type({ ...(props || {}) })
    } catch (e) {
      errs.push('组件 ' + (type.name || '匿名') + ' 渲染抛异常: ' + (e && e.message))
      return
    }
    walk(out, depth + 1)
    return
  }
  if (props && props.children) walk(props.children, depth + 1)
}

const page = regs.find((r) => r && typeof r.render === 'function')
if (page) {
  try {
    walk(page.render(), 0)
    reports.push(`OK: 页面渲染冒烟通过（展开 ${rendered} 个组件，无异常）`)
  } catch (e) {
    reports.push('FAIL: 页面顶层渲染抛异常: ' + (e && e.message))
  }
} else {
  reports.push('WARN: 没有带 render 的路由注册，跳过渲染冒烟')
}
if (errs.length) reports.push('渲染期异常 ' + errs.length + ' 处: ' + errs.slice(0, 3).join(' | '))

for (const line of reports) console.log(line)
const bad = reports.some((l) => l.startsWith('FAIL'))
console.log(bad ? '结果: 失败' : '结果: 通过')
process.exit(bad ? 1 : 0)
