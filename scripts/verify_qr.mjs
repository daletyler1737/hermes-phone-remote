// scripts/verify_qr.mjs
// 从构建产物 plugin.js 里抽出内联的二维码段并真的编码一次（验证内联库没坏、占位符已替换）。
// 三个运行时任选：
//   node scripts/verify_qr.mjs [url]
//   bun  scripts/verify_qr.mjs [url]
//   deno run --allow-read scripts/verify_qr.mjs [url]
import { readFileSync } from 'node:fs'

const src = readFileSync(new URL('../plugin.js', import.meta.url), 'utf8')
const head = 'const makeQr = (function () {'
const tail = '\n  return module.exports\n})()'
const a = src.indexOf(head)
const b = src.indexOf(tail, a)
if (a < 0 || b < 0) {
  throw new Error('plugin.js 里找不到二维码段 —— 占位符没被替换？先跑 scripts/build_plugin.py')
}
const seg = src.slice(a, b + tail.length)
// ponytail: 直接执行构建产物里的那一段，比为了验证再搭一套打包链便宜得多
const makeQr = new Function(seg + '\nreturn makeQr')()

const url = process.argv[2] || 'http://192.168.1.34:9119/'
// 这段导出的是二维码库构造函数本身：qrcode(typeNumber, errorCorrectionLevel)
const qr = makeQr(0, 'M')
qr.addData(url)
qr.make()
const size = qr.getModuleCount()
if (!Number.isInteger(size) || size < 21 || size > 177) {
  throw new Error('二维码尺寸异常: ' + size)
}
let dark = 0
for (let y = 0; y < size; y++) {
  for (let x = 0; x < size; x++) if (qr.isDark(y, x)) dark++
}
if (dark === 0 || dark === size * size) throw new Error('矩阵异常：dark=' + dark)
console.log('OK  url=' + url + '  modules=' + size + 'x' + size + '  dark=' + dark + '/' + (size * size))
