import { chromium } from '@playwright/test'
import fs from 'node:fs'
const browser = await chromium.launch({ channel: 'msedge', headless: true })
try {
  const page = await browser.newPage()
  const video = await page.evaluate(async () => {
    const canvas = document.createElement('canvas')
    canvas.width = 960
    canvas.height = 540
    const ctx = canvas.getContext('2d'),
      chunks = []
    const recorder = new MediaRecorder(canvas.captureStream(20), {
      mimeType: 'video/webm;codecs=vp8',
      videoBitsPerSecond: 700000,
    })
    recorder.ondataavailable = (e) => chunks.push(e.data)
    const result = new Promise((resolve) => {
      recorder.onstop = async () => {
        const bytes = new Uint8Array(await new Blob(chunks, { type: 'video/webm' }).arrayBuffer())
        let text = ''
        for (const byte of bytes) text += String.fromCharCode(byte)
        resolve(btoa(text))
      }
    })
    let frame = 0
    const timer = setInterval(() => {
      frame++
      const seconds = frame / 20
      ctx.fillStyle = '#e8ede3'
      ctx.fillRect(0, 0, 960, 540)
      ctx.textAlign = 'center'
      ctx.fillStyle = '#24664f'
      ctx.font = 'bold 32px Microsoft YaHei'
      ctx.fillText('词汇翻牌 · 交互示意', 480, 90)
      ctx.font = '20px Microsoft YaHei'
      ctx.fillStyle = '#6a776e'
      ctx.fillText('点击卡片，查看词义与反馈', 480, 135)
      for (let i = 0; i < 3; i++) {
        ctx.fillStyle = seconds > 3 + i * 2 ? '#f4ead7' : '#fff'
        ctx.fillRect(115 + i * 250, 200, 220, 140)
        ctx.fillStyle = '#24362e'
        ctx.font = '28px Microsoft YaHei'
        ctx.fillText(
          seconds > 3 + i * 2 ? ['苹果', '香蕉', '橙子'][i] : ['apple', 'banana', 'orange'][i],
          225 + i * 250,
          280,
        )
      }
      ctx.font = '18px Microsoft YaHei'
      ctx.fillStyle = '#738077'
      ctx.fillText('示例仅展示形式，正式作品请采用真实教材单元词汇。', 480, 435)
      ctx.fillStyle = '#24664f'
      ctx.fillRect(115, 480, 730 * Math.min(seconds / 12, 1), 4)
      if (frame >= 240) {
        clearInterval(timer)
        recorder.stop()
      }
    }, 50)
    recorder.start()
    return result
  })
  fs.writeFileSync('../config/examples/demo.webm', Buffer.from(video, 'base64'))
  console.log('Created 12-second local example video')
} finally {
  await browser.close()
}
