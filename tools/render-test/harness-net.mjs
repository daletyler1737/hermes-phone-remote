// 互联网模式布局回归：默认 mode=lan，这里渲染前把默认值偷换成 net —— 只改内存里的副本，不动源码和产物。
// 只验「哪张卡片在 / 不在」。地址、二维码、批准按钮都是 REST 异步拿的，SSR 里永远停在 loading 态，这里查不到。
import fs from 'node:fs'
import { createElement } from 'react'
import ReactDOMServer from 'react-dom/server'

const base = fs.readFileSync('./plugin.mjs', 'utf8')

const swap = (src, from, to) => {
  const n = src.split(from).length - 1
  if (n !== 1) throw new Error('预期替换 1 处，实际 ' + n + ' 处：' + from)
  return src.split(from).join(to)
}

const variants = [
  {
    name: '折叠态（默认）',
    src: swap(base, "useState('lan')", "useState('net')"),
    want: { 公网链接卡片: true, '配对卡片（主路径）': true, 折叠入口: true, '账号密码卡（大二维码）': false }
  },
  {
    name: '展开态（点了兜底入口）',
    src: swap(swap(base, "useState('lan')", "useState('net')"), '[pwFallback, setPwFallback] = useState(false)', '[pwFallback, setPwFallback] = useState(true)'),
    want: { 公网链接卡片: true, '配对卡片（主路径）': true, 折叠入口: false, '账号密码卡（大二维码）': true }
  }
]

const probe = {
  公网链接卡片: '公网链接',
  '配对卡片（主路径）': '手机连接 · 免密配对',
  折叠入口: '扫不了码？改用账号密码登录',
  '账号密码卡（大二维码）': '以后手机上就能聊天'
}

let bad = 0
for (const v of variants) {
  const file = './plugin.net.' + Math.random().toString(36).slice(2) + '.mjs'
  fs.writeFileSync(file, v.src)
  const plugin = (await import(file)).default
  const regs = []
  plugin.register({
    storage: { get: () => null, set: () => {}, remove: () => {} },
    rest: (p) =>
      p === '/status'
        ? Promise.resolve({ username: 'dale', hash_set: true, port: 9119, running: true, lan_ip: '192.168.1.10', url: 'http://192.168.1.10:9119/' })
        : p === '/tunnel'
          ? Promise.resolve({ ok: true, running: true, url: 'https://demo.trycloudflare.com', expires_at: Math.floor(Date.now() / 1000) + 7200 })
          : p === '/pair'
            ? Promise.resolve({ ok: true, status: 'pending', url: 'https://demo.trycloudflare.com/pair?t=demo', proxy: true, port: 9121 })
            : Promise.resolve({ ok: true }),
    os: { notify: () => {}, openExternal: () => {}, revealPath: () => {}, writeClipboard: () => {} },
    register: (r) => regs.push(r),
    registerCommand: (r) => regs.push(r)
  })
  const page = regs.find((r) => r.id === 'phoneRemote.page')
  const html = ReactDOMServer.renderToStaticMarkup(createElement(page.render))

  console.log('== 互联网模式 · ' + v.name + ' ==')
  for (const [label, key] of Object.entries(probe)) {
    const got = html.includes(key)
    const ok = got === v.want[label]
    if (!ok) bad++
    console.log('  ', label.padEnd(20), got ? '在' : '不在', ok ? '✓' : '✗ 期望' + (v.want[label] ? '在' : '不在'))
  }
  fs.unlinkSync(file)
}

console.log(bad ? '\n!! ' + bad + ' 项不对' : '\n== 互联网模式布局回归全绿 ==')
process.exit(bad ? 1 : 0)
