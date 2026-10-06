/**
 * Klip Studyo - GERCEK ARAYUZ testi (uctan uca).
 *
 * `npm run test:smoke` sayfalari sadece "ciziliyor mu" diye gezer; bu betik
 * ise kullanicinin yaptigi seyi birebir yapar: uygulamayi gercek main-process
 * + gercek preload + gercek IPC ile acar, sol menuden Klip Studyo'ya gider,
 * forma gercek bir video linki yazar, ayarlari secer ve "Shorts uret"
 * butonuna basar. Ardindan gercek python isinin bitmesini bekler ve uretilen
 * dosyayi diskten dogrular.
 *
 * Ag ve gercek klipci.py kosusu gerektirir (~2-3 dk). Kotalara dokunmaz
 * (yt-dlp + ffmpeg + Whisper/altyazi; odeme gerektiren servis yok).
 *
 * Calistirma: npm run check:klip-ui   (KLIP_UI_LINK=... ile link degistirilebilir)
 */
import { app, BrowserWindow } from 'electron'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { registerIpc } from '../electron/ipc'
import { registerWindowIpc } from '../electron/core/window'
import { defaultBotPath, desktopDir } from '../electron/core/paths'
import { getSettings, setSettings } from '../electron/core/settings'
import { getState } from '../electron/python/runner'
import { execCapture } from '../electron/core/exec'

const ROOT = path.resolve(__dirname, '..')
const LINK = (process.env.KLIP_UI_LINK || 'https://www.youtube.com/watch?v=dQw4w9WgXcQ').trim()
const IS_BEKLE_MS = Number(process.env.KLIP_UI_TIMEOUT_MS || 12 * 60 * 1000)

let passed = 0
let failed = 0
const failures: string[] = []

function check(name: string, condition: boolean, detail = ''): void {
  if (condition) {
    passed++
    console.log(`  PASS  ${name}${detail ? `  (${detail})` : ''}`)
  } else {
    failed++
    failures.push(name)
    console.log(`  FAIL  ${name}${detail ? `  (${detail})` : ''}`)
  }
}

const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms))

/** React kontrollu <input>/<select> degerini gercek kullanici gibi degistirir. */
const SETTER = `
function vfSet(el, value, proto, evt) {
  const d = Object.getOwnPropertyDescriptor(proto.prototype, 'value');
  d.set.call(el, value);
  el.dispatchEvent(new Event(evt, { bubbles: true }));
}`

async function main(): Promise<void> {
  const userData = fs.mkdtempSync(path.join(os.tmpdir(), 'vf-klipui-'))
  app.setPath('userData', userData)
  app.on('window-all-closed', () => {
    /* test kendi kapanisini yonetir */
  })
  await app.whenReady()
  registerIpc()
  registerWindowIpc()

  const realBot = defaultBotPath()
  const settingsFile = path.join(app.getPath('userData'), 'settings.json')
  const originalSettingsRaw = fs.existsSync(settingsFile) ? fs.readFileSync(settingsFile, 'utf8') : null
  const originalSettings = getSettings()

  let win: BrowserWindow | null = null
  try {
    console.log('\n== Klip Studyo gercek arayuz testi ==')
    console.log(`   link: ${LINK}`)

    const klipci = path.join(realBot, 'functions', 'klipci.py')
    check('Klip motoru yerinde (functions/klipci.py)', fs.existsSync(klipci), klipci)

    setSettings({ videoForgePath: realBot })
    const distIndex = path.join(ROOT, 'dist', 'index.html')
    check('Uretim derlemesi hazir (dist/index.html)', fs.existsSync(distIndex), distIndex)
    const preload = path.join(ROOT, 'dist-electron', 'preload.cjs')
    check('Preload derlemesi hazir', fs.existsSync(preload), preload)

    win = new BrowserWindow({
      show: false,
      width: 1360,
      height: 900,
      webPreferences: { preload, contextIsolation: true, nodeIntegration: false, sandbox: false },
    })
    const rendererErrors: string[] = []
    win.webContents.on('console-message', (event) => {
      if (event.level === 'error') rendererErrors.push(event.message)
    })
    await win.loadFile(distIndex)
    await sleep(1500)

    check('Kopru yuklendi (window.vfgui)', (await win.webContents.executeJavaScript('typeof window.vfgui')) === 'object')

    /* ---------------- 1) Sol menuden Klip Studyo'ya git ---------------- */
    const nav = (await win.webContents.executeJavaScript(
      `(() => {
         const b = [...document.querySelectorAll('nav button')].find((x) => (x.textContent || '').trim().toLocaleLowerCase('tr').startsWith('klip'));
         if (!b) return false;
         b.click();
         return true;
       })()`,
    )) as boolean
    await sleep(900)
    const sayfa = (await win.webContents.executeJavaScript('document.body.textContent || ""')) as string
    check('Sol menuden Klip Studyo acildi', nav && sayfa.includes('Shorts üret'), nav ? 'menu butonu tiklandi' : 'menu butonu bulunamadi')

    /* ---------------- 2) Formu doldur: link + 1 klip + 20 sn ---------------- */
    const form = (await win.webContents.executeJavaScript(
      `(() => {
         ${SETTER}
         const link = document.querySelector('input[placeholder^="https://www.youtube.com"]');
         if (!link) return { ok: false, neden: 'link kutusu yok' };
         vfSet(link, ${JSON.stringify(LINK)}, window.HTMLInputElement, 'input');

         const etiketli = (metin) => [...document.querySelectorAll('label')].find((l) => (l.textContent || '').includes(metin));
         const adetL = etiketli('Klip sayısı');
         const sureL = etiketli('Hedef süre');
         const adetS = adetL && adetL.querySelector('select');
         const sureS = sureL && sureL.querySelector('select');
         if (!adetS || !sureS) return { ok: false, neden: 'select bulunamadi' };
         vfSet(adetS, '1', window.HTMLSelectElement, 'change');
         vfSet(sureS, '20', window.HTMLSelectElement, 'change');
         return { ok: true, linkDegeri: link.value, adet: adetS.value, sure: sureS.value };
       })()`,
    )) as { ok: boolean; neden?: string; linkDegeri?: string; adet?: string; sure?: string }
    check('Form dolduruldu (link + 1 klip + 20 sn)', form.ok === true, JSON.stringify(form))
    await sleep(400)

    /* ---------------- 3) "Shorts uret" butonuna bas ---------------- */
    const okDurum = (await win.webContents.executeJavaScript(
      `(async () => {
         const b = [...document.querySelectorAll('button')].find((x) => (x.textContent || '').trim().toLocaleLowerCase('tr') === 'shorts üret');
         if (!b) return { basildi: false };
         b.click();
         await new Promise((r) => setTimeout(r, 1200));
         const s = await window.vfgui.runState();
         const j = s.ok ? s.data : null;
         return { basildi: true, kind: j && j.kind, title: j && j.title, subtitle: j && j.subtitle, status: j && j.status, pid: j && j.pid, adim: j && j.stepLabel };
       })()`,
    )) as {
      basildi: boolean
      kind?: string
      title?: string
      subtitle?: string
      status?: string
      pid?: number
      adim?: string
    }
    check('Butona basinca gercek is basladi', okDurum.basildi === true && okDurum.status === 'running', JSON.stringify(okDurum))
    check('Is tipi "klip" ve baslik dogru', okDurum.kind === 'klip' && (okDurum.title || '').includes('Klip Stüdyo'), okDurum.title || '')
    check('Link istege gecti', (okDurum.subtitle || '').includes(LINK.slice(-11)), okDurum.subtitle || '')

    const st0 = getState()
    let pidCanli = false
    try {
      if (st0?.pid) {
        process.kill(st0.pid, 0)
        pidCanli = true
      }
    } catch {
      pidCanli = false
    }
    check('Python sureci gercekten canli (pid yasiyor)', pidCanli, `pid=${st0?.pid}`)
    const asamaAnahtarlari = (st0?.stages || []).map((s) => s.key)
    check(
      'Is asama listesi Klip Studyo icin kuruldu (konusmaci + yuz + render)',
      asamaAnahtarlari.includes('speaker') && asamaAnahtarlari.includes('face') && asamaAnahtarlari.includes('render'),
      asamaAnahtarlari.join(' > '),
    )

    /* ---------------- 4) Isin bitmesini bekle ---------------- */
    const basladi = Date.now()
    let son = getState()
    while (son && son.status === 'running' && Date.now() - basladi < IS_BEKLE_MS) {
      await sleep(3000)
      son = getState()
    }
    const sn = Math.round((Date.now() - basladi) / 1000)
    console.log(`   is bitti mi: ${son?.status} (${sn} sn, exit=${son?.exitCode})`)
    if (son && son.status !== 'done') {
      const kuyruk = (son.lines || []).slice(-8).map((l) => l.text).join(' | ')
      console.log(`   son satirlar: ${kuyruk}`)
    }

    check('Is zamaninda bitti (takilmadi)', son?.status === 'done', `durum=${son?.status} sure=${sn} sn`)
    check('Python exit kodu 0', son?.exitCode === 0, `exit=${son?.exitCode} hata=${son?.error || '-'}`)

    /* Runner'in gercekten kurdugu komut, uygulama gunlugunden okunur. */
    const gunlukYolu = path.join(app.getPath('userData'), 'videoforge-gui.log')
    let gunluk = ''
    try {
      gunluk = fs.readFileSync(gunlukYolu, 'utf8')
    } catch {
      gunluk = ''
    }
    const komutSatiri = (gunluk.match(/komut: ([^\n]+)/g) || []).pop() || ''
    check(
      'Arayuz dogru komutu kurdu (klipci.py + link + --klip 1 + --sure 20)',
      komutSatiri.includes('klipci.py') && komutSatiri.includes(LINK) && komutSatiri.includes('--klip 1') && komutSatiri.includes('--sure 20'),
      komutSatiri.replace(/^komut: /, '').trim(),
    )

    const tumSatirlar = (son?.lines || []).map((l) => l.text).join('\n')
    check('Python cikisi gercekten klipci motorundan', /KLIPCI/i.test(tumSatirlar), (tumSatirlar.match(/KLIPCI[^\n]*/) || [''])[0].slice(0, 60))
    check(
      'Motor analiz adimlarini gecti (indirme + transkript + skor + yuz)',
      /indiriliyor|Indirildi/i.test(tumSatirlar) && /skorlaniyor|Skorla/i.test(tumSatirlar) && /transkript|Transcript|Transkript/i.test(tumSatirlar),
    )
    const videoCiktilar = (son?.artifacts || []).filter((a) => a.kind === 'video')
    check('Is kaydi cikti dosyasini gordu (artifact)', videoCiktilar.length > 0, videoCiktilar.map((a) => a.name).join(', '))

    /* ---------------- 5) Uretilen klipler diskte mi ---------------- */
    const durum = (await win.webContents.executeJavaScript('(async () => { const r = await window.vfgui.klipDurum(); return r.ok ? r.data : null; })()')) as {
      klasorler: { ad: string; klipler: { baslik: string; dosyaVar: boolean; dosya: string | null; srt: string | null; qaPuan: number | null; sure: number; panelDagilimi: Record<string, number> }[] }[]
      toplamKlip: number
    } | null
    check('GUI cikti klasorunu okuyabildi (klip:durum IPC)', durum !== null && durum.klasorler.length > 0, `klasor=${durum?.klasorler.length ?? 0} klip=${durum?.toplamKlip ?? 0}`)

    const yeni = (durum?.klasorler || []).flatMap((k) => k.klipler).filter((i) => i.dosyaVar && (i.dosya || '').toLowerCase().endsWith('.mp4'))
    check('Uretilen mp4 diskte var', yeni.length > 0, yeni.map((y) => path.basename(y.dosya || '')).join(', ') || 'mp4 bulunamadi')
    check('QA puani olustu', yeni.some((y) => (y.qaPuan ?? 0) > 0), yeni.map((y) => `${y.qaPuan}/${y.sure}sn`).join(', '))
    check('SRT altyazisi yazildi', yeni.some((y) => Boolean(y.srt)), yeni[0]?.srt ? path.basename(yeni[0].srt as string) : 'srt yok')

    if (yeni[0]?.dosya) {
      const probe = await execCapture(
        'ffprobe',
        ['-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'csv=p=0', yeni[0].dosya],
        { timeoutMs: 30_000 },
      )
      const boyut = (probe.stdout || '').trim()
      check('Klip gercekten dikey 1080x1920', boyut.startsWith('1080,1920'), boyut || probe.stderr.trim())
    } else {
      check('Klip gercekten dikey 1080x1920', false, 'urea dosyasi yok')
    }

    /* ---------------- 6) Sayfa sonucu gosteriyor mu ---------------- */
    await win.webContents.executeJavaScript('window.scrollTo(0, document.body.scrollHeight)')
    await sleep(2500)
    const sonMetin = (await win.webContents.executeJavaScript('document.body.textContent || ""')) as string
    check('Sayfada "Uretilen klipler" bolumu klip gosteriyor', /Üretilen klipler/.test(sonMetin) && !/Henüz klip yok/i.test(sonMetin), 'liste dolu')
    check('Sayfada QA rozeti gorunuyor', /GECTI|ORTA|ZAYIF/.test(sonMetin))
    check('Arayuz konsol hatasi uretmedi', rendererErrors.length === 0, rendererErrors.slice(0, 2).join(' | '))

    const cikti = path.join(desktopDir, 'Klipler')
    console.log(`   cikti klasoru: ${cikti}`)
  } finally {
    setSettings({ videoForgePath: originalSettings.videoForgePath })
    try {
      if (originalSettingsRaw !== null) fs.writeFileSync(settingsFile, originalSettingsRaw, 'utf8')
      else if (fs.existsSync(settingsFile)) fs.rmSync(settingsFile, { force: true })
    } catch {
      /* yoksay */
    }
    if (win && !win.isDestroyed()) win.destroy()
  }

  console.log(`\n=========================================`)
  console.log(`  KLIP STUDYO ARAYUZ: ${passed} basarili, ${failed} basarisiz`)
  if (failures.length) console.log(`  Basarisiz: ${failures.join(' | ')}`)
  console.log(`=========================================\n`)

  app.exit(failed === 0 ? 0 : 1)
}

void main().catch((err) => {
  console.error('KLIP UI TEST CRASH:', err)
  app.exit(2)
})
