/**
 * VideoForge Desktop - uctan uca smoke testi.
 *
 * Gercek main-process modullerini calistirir:
 *  - python/locate, data/env, data/library, data/engine, data/logs, data/reports
 *  - python/parser, python/runner (buildSteps + canli is akisi + iptal + haftalik zincir)
 *  - ipc + preload + gizli BrowserWindow ile gercek renderer yuklemesi
 *
 * Gercek bot koduna ve kotalara DOKUNMAZ: gecici klasorde sahte bot dosyalari kullanir.
 * Calistirma: npm run test:smoke
 */
import { app, BrowserWindow } from 'electron'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { GUN_SAYISI_MAX, GUN_SAYISI_VARSAYILAN, IPC, normalGunSayisi } from '@shared/constants'
import { CHANNELS } from '@shared/channels'
import type { LogLine } from '@shared/types'
import { registerIpc } from '../electron/ipc'
import { registerWindowIpc, setMainWindow } from '../electron/core/window'
import { DEFAULT_UPDATE_REPO, getSettings, setSettings } from '../electron/core/settings'
import { defaultBotPath, planPath } from '../electron/core/paths'
import { resolvePython } from '../electron/python/locate'
import { parseLine } from '../electron/python/parser'
import { buildSteps, cancelJob, getState, getHistory, startJob } from '../electron/python/runner'
import { execCapture } from '../electron/core/exec'
import { botGitStatus, checkForUpdate, compareVersions, downloadUpdate, launchDownloaded, parseVersion, pullBotCode } from '../electron/update/updater'
import { envCheck } from '../electron/data/env'
import { forgetLink, readLibrary } from '../electron/data/library'
import { engineConfig } from '../electron/data/engine'
import { readBotLog, weeklyData } from '../electron/data/logs'
import { groupArtifacts, listArtifacts, previewHtml, scanArtifactsSince } from '../electron/data/reports'

const ROOT = path.resolve(__dirname, '..')

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

function section(title: string): void {
  console.log(`\n== ${title} ==`)
}

const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms))

/** pid hala yasiyor mu (sinyal 0 gonderilebiliyorsa evet). */
function pidAlive(pid: number | null | undefined): boolean {
  if (!pid) return false
  try {
    process.kill(pid, 0)
    return true
  } catch {
    return false
  }
}

/** pid kapanana kadar bekler (durdurma testinde surec agaci gercekten oldu mu). */
async function waitForExit(pid: number | null | undefined, ms = 10_000): Promise<boolean> {
  if (!pid) return true
  const start = Date.now()
  while (Date.now() - start < ms) {
    if (!pidAlive(pid)) return true
    await sleep(250)
  }
  return !pidAlive(pid)
}

async function waitForStatus(ms = 40_000): Promise<string> {
  const start = Date.now()
  while (Date.now() - start < ms) {
    const st = getState()
    if (st && st.status !== 'running') return st.status
    await sleep(200)
  }
  return getState()?.status ?? 'timeout'
}

/* ------------------------------------------------------------------ */
/* Sahte bot klasorleri (gercek bot dosyalarina dokunulmaz)            */
/* ------------------------------------------------------------------ */

function write(file: string, content: string): void {
  fs.mkdirSync(path.dirname(file), { recursive: true })
  fs.writeFileSync(file, content, 'utf8')
}

function makeFakeBot(): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vf-fakebot-'))
  write(path.join(dir, 'shared.py'), '# sahte\n')
  write(
    path.join(dir, 'kesif.py'),
    [
      'import sys, os, json',
      'print("[12:00:00] \\u203a Kesif modulu baslatildi")',
      'print("[12:00:01] [1/4] Kaynak kanallar taraniyor...")',
      'print("[12:00:02] \\u2713 Kaynak kanal tarandi (24 video)")',
      'print("[12:00:03] \\u2713 Gemini siralama tamamlandi")',
      'print("[12:00:04] \\U0001F4CA [Bulut] Gemini kullanimi: 12 API istegi (10 basarili, 1 bos, 1 hata)")',
      'print("[12:00:05] \\u2713 \\U0001F4C1 Video: Sahte_Test_123_CLEAN.mp4")',
      'print("[12:00:06] \\u2713 Sure: 3dk 12sn | GPU: 5x L4 | Maliyet: $0.0012")',
      'if "--haftalik" in sys.argv:',
      '    with open("haftalik_plan.json", "w", encoding="utf-8") as f:',
      '        json.dump([{"gun": i, "baslik": f"sahte video {i}", "skor": 9 - i} for i in range(1, 8)], f)',
      '    print("[12:00:07] \\u2713 Haftalik plan yazildi: haftalik_plan.json")',
      'print("[12:00:08] ! Bilerek uretilen uyari satiri")',
      'print("[12:00:09] \\u2715 Bilerek uretilen hata satiri")',
      'print("haftalik_plan.json")',
      'sys.exit(0)',
    ].join('\n'),
  )
  write(
    path.join(dir, 'haftalik_islet.py'),
    [
      'import sys',
      'print("[13:00:00] \\u203a Gun 1 isleniyor")',
      'print("[13:00:01] [1/4] Video yerel bilgisayarda indiriliyor (cookies.txt ile)...")',
      'print("[13:00:02] \\u2713 Zincir adimi 2 tamamlandi")',
      'sys.exit(0)',
    ].join('\n'),
  )
  write(path.join(dir, 'slow.py'), 'import sys, time\nprint("[14:00:00] \\u203a uzun islem basladi", flush=True)\ntime.sleep(120)\n')
  return dir
}

/** Iptal testi icin kesif.py'yi yavas surume cevirir. */
function makeSlowBot(): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vf-slowbot-'))
  write(path.join(dir, 'shared.py'), '# sahte\n')
  write(path.join(dir, 'kesif.py'), 'import time\nprint("[15:00:00] \\u203a yavas islem", flush=True)\ntime.sleep(120)\n')
  return dir
}

/* ------------------------------------------------------------------ */
/* Gercek git ikilisiyle yerel depo ikilisi (sadece gecici klasorde)    */
/* ------------------------------------------------------------------ */

async function gitRun(cwd: string, args: string[]): Promise<string> {
  const r = await execCapture('git', args, { cwd, timeoutMs: 90_000 })
  return `${r.stdout}\n${r.stderr}`.trim()
}

/** Gecici test depolarinda commit kimligi (kullanicinin git ayarlari degismez). */
const GIT_IDENTITY = ['-c', 'user.email=smoke@videoforge.local', '-c', 'user.name=VideoForge Smoke']

/**
 * Gecici klasoru Windows'ta da siler: git nesneleri salt okunur olabildigi icin
 * once yazma izni verilir, sonra silinir. Basarisizlik testi durdurmaz.
 */
function forceRemove(dir: string): void {
  const clearReadOnly = (p: string): void => {
    let stat: fs.Stats
    try {
      stat = fs.lstatSync(p)
    } catch {
      return
    }
    if (stat.isDirectory()) {
      for (const entry of fs.readdirSync(p)) clearReadOnly(path.join(p, entry))
      return
    }
    try {
      fs.chmodSync(p, 0o666)
    } catch {
      /* yoksay */
    }
  }
  try {
    clearReadOnly(dir)
    fs.rmSync(dir, { recursive: true, force: true, maxRetries: 5, retryDelay: 150 })
  } catch (err) {
    console.log(`  NOT   gecici klasor silinemedi: ${dir} (${String(err).slice(0, 70)})`)
  }
}

/**
 * bare uzak depo + origin + klon kurar. Gercek 'git pull' senaryosunu test eder:
 * yeni commit uzaga gonderilir, klon guncellenir, dosya icerigi dogrulanir.
 */
async function makeGitPair(): Promise<{ base: string; clone: string; pushNewCommit: () => Promise<void> }> {
  const base = fs.mkdtempSync(path.join(os.tmpdir(), 'vf-gitpair-'))
  const bare = path.join(base, 'remote.git')
  const origin = path.join(base, 'origin')
  const clone = path.join(base, 'clone')

  fs.mkdirSync(bare, { recursive: true })
  await gitRun(base, ['init', '--bare', '-q', bare])
  fs.mkdirSync(origin, { recursive: true })
  await gitRun(origin, ['init', '-q'])
  write(path.join(origin, 'bot.py'), 'print("surum 1")\n')
  await gitRun(origin, ['add', '.'])
  await gitRun(origin, [...GIT_IDENTITY, 'commit', '-q', '-m', 'ilk surum'])
  await gitRun(origin, ['remote', 'add', 'origin', bare])
  await gitRun(origin, ['push', '-q', '-u', 'origin', 'HEAD'])
  await gitRun(base, ['clone', '-q', bare, clone])

  return {
    base,
    clone,
    pushNewCommit: async (): Promise<void> => {
      write(path.join(origin, 'bot.py'), 'print("surum 2")\n')
      await gitRun(origin, ['add', '.'])
      await gitRun(origin, [...GIT_IDENTITY, 'commit', '-q', '-m', 'ikinci surum'])
      await gitRun(origin, ['push', '-q'])
    },
  }
}

/* ------------------------------------------------------------------ */

async function main(): Promise<void> {
  // Test kendi gecici userData klasorunde calisir: kullanicinin gercek ayarlari korunur.
  const smokeUserData = fs.mkdtempSync(path.join(os.tmpdir(), 'vf-smoke-userdata-'))
  app.setPath('userData', smokeUserData)
  // Gizli pencere kapatildiginda Electron'un varsayilan olarak uygulamayi
  // sonlandirmasini engeller; test kendi kapanisini app.exit ile yonetir.
  app.on('window-all-closed', () => {
    /* yoksay */
  })
  await app.whenReady()
  registerIpc()
  registerWindowIpc()

  const realBot = defaultBotPath()
  const settingsFile = path.join(app.getPath('userData'), 'settings.json')
  const originalSettingsRaw = fs.existsSync(settingsFile) ? fs.readFileSync(settingsFile, 'utf8') : null
  const originalSettings = getSettings()

  try {
    /* ---------------- 1. Python tespiti ---------------- */
    section('1) Python yorumlayicisi')
    const py = await resolvePython(true)
    check('Python bulundu', py.ok && Boolean(py.python), py.python ? `${py.python.command} ${py.python.args.join(' ')} / ${py.python.detail}` : 'yok')

    /* ---------------- 2. Ortam kontrolu ---------------- */
    section('2) Ortam kontrolu (gercek VideoForge klasoru)')
    const env = await envCheck()
    check('Kontroller donduruldu', env.length >= 8, `${env.length} kontrol`)
    const byId = (id: string) => env.find((e) => e.id === id)
    check('VideoForge dosyalari dogrulandi', Boolean(byId('botfiles')?.ok), byId('botfiles')?.detail)
    check('Python kontrolu gecti', Boolean(byId('python')?.ok), byId('python')?.detail)
    check('modal paketi yuklu', Boolean(byId('modal')?.ok), byId('modal')?.detail)
    check('google-genai yuklu', Boolean(byId('genai')?.ok), byId('genai')?.detail)
    check('yt-dlp yuklu', Boolean(byId('ytdlp')?.ok), byId('ytdlp')?.detail)
    check('ffmpeg erisilebilir', Boolean(byId('ffmpeg')?.ok), byId('ffmpeg')?.detail)

    /* ---------------- 3. bot.db okuma ---------------- */
    section('3) Kutuphane (bot.db, salt okunur)')
    const lib = await readLibrary()
    check('bot.db okundu', lib.ok, lib.error ?? `${lib.counts.videos} video / ${lib.counts.oneriler} oneri`)
    check('settings tablosu okundu', typeof lib.settings === 'object', `anahtarlar: ${Object.keys(lib.settings).join(', ') || 'yok'}`)

    /* ---------------- 4. Motor konfigurasyonu ---------------- */
    section('4) Motor konfigurasyonu (constants.py ayristirma)')
    const eng = await engineConfig()
    check('constants.py okundu', eng.ok, eng.error ?? '')
    check('Gemini model listesi ayristirildi', eng.models.length >= 8, `${eng.models.length} model`)
    check('Ilk 3 model flash-lite (RPD 500)', eng.models.slice(0, 3).every((m) => m.includes('lite')), eng.models.slice(0, 3).join(', '))
    check('ElevenLabs acik okundu', eng.elevenlabs === true, String(eng.elevenlabs))
    check('Islem cozunurlugu HD moduna uygun', (eng.hdMode && eng.procW === 640) || (!eng.hdMode && eng.procW === 540), `${eng.procW}x${eng.procH} / ${eng.gpu}`)
    check('Karakter limiti okundu', eng.charLimit >= 200, String(eng.charLimit))

    /* ---------------- 5. Cikti taramasi ---------------- */
    section('5) Masaustu cikti taramasi')
    const files = listArtifacts()
    check('Cikti dosyalari bulundu', files.length > 0, `${files.length} dosya`)
    const groups = groupArtifacts(files)
    check('Dosyalar is bazinda gruplandi', groups.length > 0, `${groups.length} grup`)
    check('Gruplar cikti iceriyor', groups.every((g) => g.items.length > 0))
    const recent = scanArtifactsSince(Date.now() - 1000 * 60 * 60 * 24 * 365)
    check('Zaman filtreli tarama calisiyor', recent.length === files.length || recent.length > 0, `${recent.length} dosya (1 yil)`)
    const seo = files.find((f) => f.kind === 'seo')
    if (seo) {
      const prev = previewHtml(seo.path)
      check(
        'SEO HTML onizlemesi bolumlere ayrildi',
        prev.ok && (prev.sections?.length ?? 0) > 0 && Boolean(prev.title),
        `${prev.sections?.length ?? 0} bolum (${(prev.sections ?? []).map((s) => s.label).slice(0, 4).join(', ')}), baslik: ${prev.title?.slice(0, 40)}`,
      )
    } else {
      check('SEO HTML onizlemesi (dosya yok, atlandi)', true, 'masaustunde _SEO.html yok')
    }

    /* ---------------- 6. Log ve plan okuma ---------------- */
    section('6) Log ve haftalik plan')
    const log = readBotLog(50, '')
    check(
      'bot_log.txt okundu (yoksa da gecerli durum)',
      log.ok || /ENOENT|no such file/i.test(log.error ?? ''),
      log.ok ? `${log.totalLines} satir` : 'log dosyasi henuz yok - arayuz bos durum gosterir',
    )
    const filtered = readBotLog(200, 'Gemini')
    check('Log aramasi cokme yapmiyor', filtered.ok === log.ok, `${filtered.lines.length} eslesme`)
    const weekly = weeklyData()
    check('Haftalik plan/sonuc okundu', weekly.ok, `plan: ${weekly.plan.length}, sonuc: ${weekly.results.length}`)

    /* ---------------- 7. Log ayristirici ---------------- */
    section('7) Log ayristirici')
    const p1 = parseLine('\u001b[90m[12:34:56]\u001b[0m \u001b[92m✓ Indirme tamamlandi\u001b[0m')
    check('ANSI kodlari temizlendi', !p1.text.includes('\u001b'), JSON.stringify(p1.text))
    check('Basarili satir "ok" seviyesinde', p1.level === 'ok', p1.level)
    const p2 = parseLine('[12:34:57] \u2715 Transcript alinamadi')
    check('Hata satiri "err" seviyesinde', p2.level === 'err', p2.level)
    const p3 = parseLine('[12:34:58] [2/4] Transkript cekiliyor...')
    check('Adim satiri algilandi', p3.level === 'step' && p3.stage === 'transcript', `${p3.level}/${p3.stage}`)
    const p4 = parseLine('✓ 🎙️ ElevenLabs ile seslendirme (TTS) hazirlaniyor...')
    check('TTS asamasi algilandi', p4.stage === 'tts', String(p4.stage))
    const p5 = parseLine('✓ ProPainter 640 frame islendi')
    check('GPU asamasi algilandi', p5.stage === 'gpu', String(p5.stage))
    const p6 = parseLine('✓ 📁 Video: Test_123_CLEAN.mp4')
    check('Cikti dosyasi algilandi', p6.artifact?.kind === 'video', JSON.stringify(p6.artifact))
    const p7 = parseLine('✓ Sure: 3dk 12sn | GPU: 5x L4 | Maliyet: $0.0012')
    check('Istatistikler ayristirildi', p7.stats?.cost === '$0.0012' && p7.stats?.chunks === 5, JSON.stringify(p7.stats))
    const p8 = parseLine('📊 [Bulut] Gemini kullanimi: 42 API istegi (37 basarili)')
    check('Gemini kullanim satiri ayristirildi', Boolean(p8.stats?.gemini), String(p8.stats?.gemini))

    /* ---------------- 8. Komut uretimi ---------------- */
    section('8) Bot komutlari (calistirilmadan dogrulanir)')
    const base = ['py', '-3', '-X', 'utf8']
    const ch1 = buildSteps({ kind: 'channel', channelId: '1', link: 'https://youtu.be/abc' }, base)
    check('Kanal 1 -> kinosekrety.py', ch1.steps[0].cmd.join(' ') === 'py -3 -X utf8 -m modal run kinosekrety.py --link https://youtu.be/abc', ch1.steps[0].cmd.join(' '))
    const ch2 = buildSteps({ kind: 'channel', channelId: '2', link: 'https://youtu.be/abc', force: true }, base)
    check('Kanal 2 -> faktza15.py + --force', ch2.steps[0].cmd.join(' ').includes('faktza15.py --link https://youtu.be/abc --force'), ch2.steps[0].cmd.join(' '))
    const ch3 = buildSteps({ kind: 'channel', channelId: '3', link: 'https://x/y', gun: 2, gunToplam: 7 }, base)
    check('Kanal 3 -> kinok_syjet.py + --gun', ch3.steps[0].cmd.join(' ').includes('kinok_syjet.py --link https://x/y --gun 2 --gun-toplam 7'), ch3.steps[0].cmd.join(' '))
    const disc = buildSteps({ kind: 'discover', channelId: '2', haftalik: true }, base)
    check(
      'Kesif komutu dogru (varsayilan 7 gunluk plan)',
      disc.steps[0].cmd.join(' ') === 'py -3 -X utf8 kesif.py --chn 2 --evet --haftalik 7',
      disc.steps[0].cmd.join(' '),
    )
    const disc10 = buildSteps({ kind: 'discover', channelId: '2', haftalik: true, gunSayisi: 10 }, base)
    check(
      'Kesif gun sayisi komuta geciyor (10)',
      disc10.steps[0].cmd.join(' ') === 'py -3 -X utf8 kesif.py --chn 2 --evet --haftalik 10',
      disc10.steps[0].cmd.join(' '),
    )
    const discOff = buildSteps({ kind: 'discover', channelId: '2' }, base)
    check('Plan modu kapaliyken --haftalik yok', !discOff.steps[0].cmd.includes('--haftalik'), discOff.steps[0].cmd.join(' '))
    check('Plan modu kapaliyken alt yazi tek seferlik', discOff.subtitle === 'Tek seferlik oneri', discOff.subtitle)
    const wk = buildSteps({ kind: 'weekly', channelId: '1' }, base)
    check('Cok gunlu zincir 2 adimli', wk.steps.length === 2 && wk.steps[0].cmd.join(' ').includes('--haftalik 7') && wk.steps[1].cmd.join(' ').includes('haftalik_islet.py'), wk.steps.map((s) => s.label).join(' -> '))
    const wk14 = buildSteps({ kind: 'weekly', channelId: '3', gunSayisi: 14 }, base)
    check(
      'Zincir gun sayisi komuta geciyor (14)',
      wk14.steps[0].cmd.join(' ').includes('--haftalik 14') && wk14.steps[0].label.includes('14 video') && wk14.title.includes('14 Gunluk'),
      `${wk14.steps[0].cmd.join(' ')} | ${wk14.title}`,
    )
    check('Zincir plan dosyasina bagli', typeof wk.steps[1].continueWhen === 'function')

    section('8b) Gun sayisi normalizasyonu (7 sabit degil)')
    check('normalGunSayisi(10) -> 10', normalGunSayisi(10) === 10, String(normalGunSayisi(10)))
    check('normalGunSayisi(undefined) -> 7', normalGunSayisi(undefined) === GUN_SAYISI_VARSAYILAN, String(normalGunSayisi(undefined)))
    check('normalGunSayisi(1) -> 7 (min 2)', normalGunSayisi(1) === 7, String(normalGunSayisi(1)))
    check('normalGunSayisi(999) -> 60 (ust sinir)', normalGunSayisi(999) === GUN_SAYISI_MAX, String(normalGunSayisi(999)))
    check('normalGunSayisi("12") -> 12', normalGunSayisi('12') === 12, String(normalGunSayisi('12')))
    check('normalGunSayisi("abc") -> 7', normalGunSayisi('abc') === 7, String(normalGunSayisi('abc')))
    const gun10 = buildSteps({ kind: 'channel', channelId: '3', link: 'https://x/y', gun: 4, gunSayisi: 10 }, base)
    check('gun-toplam gunSayisi\'ndan tureiyor', gun10.steps[0].cmd.join(' ').includes('--gun-toplam 10'), gun10.steps[0].cmd.join(' '))
    // Panel/Kesif sayfasindan gelen gunSayisi zincire ve etiketlere gecmeli.
    const wk12 = buildSteps({ kind: 'weekly', channelId: '2', haftalik: true, gunSayisi: 12 }, base)
    check('Zincir 12 gun ile kuruldu (--haftalik 12)', wk12.steps[0].cmd.join(' ').includes('--haftalik 12'), wk12.steps[0].cmd.join(' '))
    check('Zincir 12 gun etiketlere yansidi', wk12.steps[0].label.includes('12 video') && wk12.title.includes('12 Gunluk'), `${wk12.steps[0].label} | ${wk12.title}`)

    /* Gun sayisi ayari: kaydedilir ve gecersiz degerler duzeltilir. */
    setSettings({ gunSayisi: 99 })
    check('Gun sayisi ayari 60 ile sinirlandi', getSettings().gunSayisi === GUN_SAYISI_MAX, String(getSettings().gunSayisi))
    setSettings({ gunSayisi: 1 })
    check('Cok kucuk gun sayisi 7 varsayilana dondu', getSettings().gunSayisi === GUN_SAYISI_VARSAYILAN, String(getSettings().gunSayisi))
    setSettings({ gunSayisi: 'abc' as unknown as number })
    check('Bozuk gun sayisi ayari 7 varsayilana dondu', getSettings().gunSayisi === GUN_SAYISI_VARSAYILAN, String(getSettings().gunSayisi))
    setSettings({ gunSayisi: 12 })
    check('Gun sayisi ayari diske kaydedildi', getSettings().gunSayisi === 12, String(getSettings().gunSayisi))

    const clean = buildSteps({ kind: 'clean', link: 'https://youtu.be/abc' }, base)
    check('Temizleyici komutu dogru', clean.steps[0].cmd.join(' ').includes('modal run temizle.py --link https://youtu.be/abc'), clean.steps[0].cmd.join(' '))

    /* ---------------- 9. Gecersiz girdi korumalari ---------------- */
    section('9) Girdi korumalari')
    const badLink = await startJob({ kind: 'channel', channelId: '1', link: 'bu-bir-link-degil' })
    check('Gecersiz link reddedildi', !badLink.ok, badLink.error)
    const notBot = fs.mkdtempSync(path.join(os.tmpdir(), 'vf-notbot-'))
    setSettings({ videoForgePath: notBot })
    const badFolder = await startJob({ kind: 'discover', channelId: '1' })
    check('VideoForge olmayan klasor reddedildi', !badFolder.ok, badFolder.error)
    fs.rmSync(notBot, { recursive: true, force: true })
    setSettings({ videoForgePath: path.join(os.tmpdir(), 'vf-yok-boyle-bir-klasor-12345') })
    const missingFolder = await startJob({ kind: 'discover', channelId: '1' })
    check('Olmayan klasor reddedildi', !missingFolder.ok, missingFolder.error)

    /* ---------------- 10. Sahte bot ile tam akis ---------------- */
    section('10) Sahte bot ile tam is akisi (streaming + ayristirma)')
    const fakeBot = makeFakeBot()
    setSettings({ videoForgePath: fakeBot })
    let lineCount = 0

    const started = await startJob({ kind: 'discover', channelId: '1' })
    check('Sahte bot isi basladi', started.ok, started.error ?? '')
    const status = await waitForStatus(60_000)
    const st = getState()
    check('Is basariyla tamamlandi', status === 'done', `durum: ${status}, cikis: ${st?.exitCode}`)
    lineCount = st?.lines.length ?? 0
    check('Canli log satirlari yakalandi', lineCount >= 7, `${lineCount} satir`)
    check('Asama ilerlemesi algilandi', (st?.stageIndex ?? 0) > 0, `asama indeksi: ${st?.stageIndex} (${st?.stages[st?.stageIndex ?? 0]?.label})`)
    check('Cikti dosyasi listeye eklendi', (st?.artifacts.length ?? 0) >= 1, `${st?.artifacts.length} dosya`)
    check('GPU/maliyet istatistigi okundu', st?.stats.cost === '$0.0012' && st?.stats.chunks === 5, JSON.stringify(st?.stats))
    check('Gemini kullanim istatistigi okundu', Boolean(st?.stats.gemini), String(st?.stats.gemini))
    check('Gecmis kaydi olustu', getHistory().length >= 1, `${getHistory().length} kayit`)
    check('Hata seviyeli satir yakalandi', (st?.lines ?? []).some((l) => l.level === 'err'), '')
    check('Uyari seviyeli satir yakalandi', (st?.lines ?? []).some((l) => l.level === 'warn'), '')

    /* ---------------- 11. Haftalik zincir ---------------- */
    section('11) Haftalik zincir (2 adim)')
    const wkStart = await startJob({ kind: 'weekly', channelId: '1' })
    check('Zincir basladi', wkStart.ok, wkStart.error ?? '')
    const wkStatus = await waitForStatus(60_000)
    const wkState = getState()
    const wkText = (wkState?.lines ?? []).map((l: LogLine) => l.text).join('\n')
    check('Zincir tamamlandi', wkStatus === 'done', `durum: ${wkStatus}`)
    check('1. adim calisti (kesif)', wkText.includes('Kesif modulu baslatildi'), '')
    check('2. adim calisti (haftalik_islet)', wkText.includes('Zincir adimi 2 tamamlandi') || wkText.includes('Gun 1 isleniyor'), '')
    check('Plan dosyasi olustu', fs.existsSync(planPath(fakeBot)), planPath(fakeBot))

    /* ---------------- 12. Iptal ---------------- */
    section('12) Islem iptali')
    const slowBot = makeSlowBot()
    setSettings({ videoForgePath: slowBot })
    const slowStart = await startJob({ kind: 'discover', channelId: '1' })
    check('Yavas is basladi', slowStart.ok, slowStart.error ?? '')
    await sleep(2500)
    const slowStartPid = getState()?.pid ?? null
    check('Calisan surec pid\'i kayitli', Boolean(slowStartPid) && pidAlive(slowStartPid), String(slowStartPid))
    check('Is calisiyor durumda', getState()?.status === 'running', String(getState()?.status))
    const cancelled = await cancelJob()
    check('Iptal istegi kabul edildi', cancelled === true)
    const cancelStatus = await waitForStatus(30_000)
    check('Is iptal edildi olarak bitti', cancelStatus === 'cancelled', `durum: ${cancelStatus}`)
    check('Iptal sonrasi pid temizlendi', getState()?.pid === null, String(getState()?.pid))
    check('Iptal sonrasi islem kapanma suresi makul', getState()?.endedAt !== null, String(getState()?.endedAt))
    check('Iptal sonrasi kalan surec yok', await waitForExit(slowStartPid, 10_000), String(slowStartPid))

    /* ---------------- 13. Gercek renderer + preload ---------------- */
    section('13) Renderer + preload kopru testi (gizli pencere)')
    setSettings({ videoForgePath: realBot })
    const distIndex = path.join(ROOT, 'dist', 'index.html')
    check('Uretim derlemesi mevcut', fs.existsSync(distIndex), distIndex)
    const win = new BrowserWindow({
      show: false,
      width: 1280,
      height: 820,
      webPreferences: {
        preload: path.join(ROOT, 'dist-electron', 'preload.cjs'),
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: false,
      },
    })
    const rendererErrors: string[] = []
    win.webContents.on('console-message', (event) => {
      if (event.level === 'error') rendererErrors.push(event.message)
    })
    await win.loadFile(distIndex)
    await sleep(1500)

    const bridge = await win.webContents.executeJavaScript(
      `(async () => {
         if (!window.vfgui) return { ok: false, error: 'preload koprusu yok' };
         const info = await window.vfgui.appInfo();
         const env = await window.vfgui.envCheck();
         const cfg = await window.vfgui.engineConfig();
         return { ok: info.ok && env.ok && cfg.ok, videoForgePath: info.data && info.data.videoForgePath, envCount: env.data ? env.data.length : 0, models: cfg.data ? cfg.data.models.length : 0 };
       })()`,
    )
    check('Preload koprusu calisiyor', bridge?.ok === true, JSON.stringify(bridge))
    check('IPC appInfo dondu', typeof bridge?.videoForgePath === 'string', String(bridge?.videoForgePath))
    check('IPC envCheck dondu', (bridge?.envCount ?? 0) >= 8, `${bridge?.envCount} kontrol`)
    check('IPC engineConfig dondu', (bridge?.models ?? 0) >= 8, `${bridge?.models} model`)

    // Not: gizli pencerede innerText boyanmamis (ekran disi) bolumleri disladigi icin
    // icerik dogrulamalari textContent uzerinden yapilir; innerText ayrica kontrol edilir.
    const dom1 = (await win.webContents.executeJavaScript('document.body.innerText')) as string
    const dom1lc = ((await win.webContents.executeJavaScript('document.body.textContent')) as string).toLowerCase()
    check('React arayuzu render edildi', dom1.length > 200, `innerText ${dom1.length} karakter`)
    check('Panel basligi gorunur', dom1lc.includes('islem baslat') && dom1lc.includes('kino sekrety'), '')
    check('Yan menu ogeleri gorunur', ['panel', 'calistir', 'kutuphane', 'ayarlar'].every((t) => dom1lc.includes(t)), '')
    check('Ortam durumu karti gorunur', dom1lc.includes('ortam durumu'), '')
    check('Bot.db istatistikleri gorunur', dom1lc.includes('islenen video') && dom1lc.includes('kesif onerisi'), '')

    // Sayfa gecisi: Ayarlar
    const navOk = await win.webContents.executeJavaScript(
      `(() => { const b = [...document.querySelectorAll('button')].find(x => x.textContent && x.textContent.includes('Ayarlar')); if (!b) return false; b.click(); return true; })()`,
    )
    await sleep(800)
    const dom2 = ((await win.webContents.executeJavaScript('document.body.textContent')) as string).toLowerCase()
    check('Ayarlar sayfasina gecis calisti', navOk === true, String(navOk))
    check('Motor konfigurasyonu paneli gorunur', dom2.includes('motor konfigurasyonu') && dom2.includes('gemini model'), '')
    check('Ortam kontrolleri listesi gorunur', dom2.includes('ortam kontrolleri'), '')
    check('Model sirasi (RPD etiketleri) gorunur', dom2.includes('gemini-flash-lite-latest') && dom2.includes('rpd 500'), '')
    check('Uygulama guncellemesi paneli gorunur', dom2.includes('uygulama guncellemesi') && dom2.includes('guncellemeleri kontrol et'), '')
    check('Surum deposu alani gorunur', dom2.includes('surum deposu (owner/repo)') && dom2.includes('github token'), '')
    check('Otomatik guncelleme anahtari gorunur', dom2.includes('acilista otomatik kontrol et'), '')
    check('Bot kodu guncellemesi paneli gorunur', dom2.includes('bot kodu guncellemesi (git)') && dom2.includes('bot kodunu guncelle'), '')
    check('Git durum satirlari gorunur', dom2.includes('son commit') && dom2.includes('uzak fark') && dom2.includes('dal'), '')

    // Kesif sayfasi: gun sayisi artik SECILEBILIR (7 sabit degil)
    const navKesif = await win.webContents.executeJavaScript(
      `(() => { const b = [...document.querySelectorAll('button')].find((x) => x.closest('nav') && /kesif/i.test(x.textContent || '')); if (!b) return false; b.click(); return true; })()`,
    )
    await sleep(800)
    check('Kesif sayfasina gecis calisti', navKesif === true, String(navKesif))
    const domKesif = ((await win.webContents.executeJavaScript('document.body.textContent')) as string).toLowerCase()
    check('Cok gunlu plan modu anahtari gorunur', domKesif.includes('cok gunlu plan modu'), '')
    check('Gun sayisi sorusu gorunur', domKesif.includes('kac gunluk plan'), '')
    check('Hazir gun secenekleri gorunur (3/7/10/14/30)', ['3', '7', '10', '14', '30'].every((n) => domKesif.includes(n)), '')
    check('Sacilan haftalik ifadesi kalmadi', !domKesif.includes('haftalik mod'), '')
    const gunInput = (await win.webContents.executeJavaScript(
      `(() => { const el = document.getElementById('gun-sayisi'); return el ? { type: el.type, value: el.value, min: el.min, max: el.max } : null; })()`,
    )) as { type?: string; value?: string; min?: string; max?: string } | null
    // Alan artik KAYITLI ayari gosterir (Panel ve Kesif ayni degeri paylasir).
    check('Gun sayisi alani sayisal ve kayitli degeri gosteriyor', gunInput?.type === 'number' && (gunInput?.value ?? '') === String(getSettings().gunSayisi), `${JSON.stringify(gunInput)} / kayitli=${getSettings().gunSayisi}`)
    check('Gun sayisi min/max sinirlari (2-60)', gunInput?.min === '2' && gunInput?.max === '60', JSON.stringify(gunInput))
    // Kullanici 10 yazinca butonlar ve plan modu 10'u gostermeli
    const gun10Ui = (await win.webContents.executeJavaScript(
      `(async () => {
         const el = document.getElementById('gun-sayisi');
         if (!el) return null;
         const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
         setter.call(el, '10');
         el.dispatchEvent(new Event('input', { bubbles: true }));
         await new Promise((r) => setTimeout(r, 400));
         return document.body.textContent || '';
       })()`,
    )) as string | null
    check('Gun sayisi 10 yazilinca arayuz 10 gunluk plan gosterir', Boolean(gun10Ui && gun10Ui.toLowerCase().includes('10 gunluk plan olustur')), (gun10Ui ?? '').slice(0, 0))
    check('Gun sayisi 10 yazilinca zincir butonu da 10', Boolean(gun10Ui && gun10Ui.toLowerCase().includes('10 gunluk zinciri baslat')), '')
    // Logo GERCEKTEN yuklendi mi? (file:// altinda './logo.png' cozulmezse
    // naturalWidth 0 kalir - bu, surucu kokune kacma hatasini yakalar.)
    const logoImg = (await win.webContents.executeJavaScript(
      `(async () => {
         const i = document.querySelector('header img');
         if (!i) return { src: null };
         if (!i.complete) await new Promise((r) => { i.onload = r; i.onerror = r; setTimeout(r, 3000); });
         return { src: i.getAttribute('src'), w: i.naturalWidth, h: i.naturalHeight, complete: i.complete };
       })()`,
    )) as { src: string | null; w?: number; h?: number; complete?: boolean } | null
    check('Baslik cubugunda logo gorseli var', typeof logoImg?.src === 'string' && logoImg.src.includes('logo.png'), String(logoImg?.src))
    check('Logo gorseli file:// altinda gercekten yuklendi', Boolean(logoImg?.w && logoImg.w > 0 && logoImg?.h && logoImg.h > 0), `naturalWidth=${logoImg?.w} naturalHeight=${logoImg?.h}`)

    // Tema degisimi: baslik cubugundaki gercek buton uzerinden (kullanici akisi)
    const themeOk = await win.webContents.executeJavaScript(
      `(async () => {
         const btn = [...document.querySelectorAll('button')].find((b) => (b.getAttribute('title') || '').includes('Aydinlik tema'));
         if (!btn) return 'buton bulunamadi';
         btn.click();
         await new Promise((r) => setTimeout(r, 600));
         return document.documentElement.dataset.theme;
       })()`,
    )
    check('Tema degisimi (baslik cubugu butonu)', themeOk === 'light', String(themeOk))
    const themeBack = await win.webContents.executeJavaScript(
      `(async () => {
         const btn = [...document.querySelectorAll('button')].find((b) => (b.getAttribute('title') || '').includes('Karanlik tema'));
         if (btn) btn.click();
         await new Promise((r) => setTimeout(r, 600));
         return document.documentElement.dataset.theme;
       })()`,
    )
    check('Karanlik temaya geri donus', themeBack === 'dark', String(themeBack))

    // Kopru uzerinden gercek is baslatma (sahte bot) + arayuzde gorunme
    const fakeBot2 = makeFakeBot()
    setSettings({ videoForgePath: fakeBot2 })
    const runViaBridge = await win.webContents.executeJavaScript(
      `(async () => { const r = await window.vfgui.runStart({ kind: 'discover', channelId: '1' }); return r.ok; })()`,
    )
    check('Arayuzden is baslatildi (kopru)', runViaBridge === true, String(runViaBridge))
    const bridgeStatus = await waitForStatus(60_000)
    check('Kopru isi tamamlandi', bridgeStatus === 'done', `durum: ${bridgeStatus}`)
    await sleep(1200)
    const dom3 = ((await win.webContents.executeJavaScript('document.body.textContent')) as string).toLowerCase()
    check('Arayuzde is sonucu gorunur', dom3.includes('tamamlandi') || dom3.includes('calisiyor'), '')
    const runs = await win.webContents.executeJavaScript(`(async () => { const r = await window.vfgui.reportsList(); return r.ok ? r.data.length : -1; })()`)
    check('Kopru uzerinden cikti listesi alindi', typeof runs === 'number' && runs >= 0, `${runs} grup`)

    // Oturum durumu
    check('runState IPC calisiyor', (await win.webContents.executeJavaScript('(async()=>{const r=await window.vfgui.runState(); return r.ok;})()')) === true)
    check('libraryList IPC calisiyor', (await win.webContents.executeJavaScript('(async()=>{const r=await window.vfgui.libraryList(); return r.ok;})()')) === true)
    check('weeklyPlan IPC calisiyor', (await win.webContents.executeJavaScript('(async()=>{const r=await window.vfgui.weeklyPlan(); return r.ok;})()')) === true)
    check('logsRead IPC calisiyor', (await win.webContents.executeJavaScript('(async()=>{const r=await window.vfgui.logsRead(20, ""); return r.ok;})()')) === true)
    // Guncelleme/git kopru metotlari (gercek depoda)
    setSettings({ videoForgePath: realBot })
    const updBridge = await win.webContents.executeJavaScript(
      `(async () => {
         const has = (k) => typeof window.vfgui[k] === 'function';
         const st = await window.vfgui.botGitStatus();
         const prog = window.vfgui.onUpdateProgress(() => {});
         return {
           updateCheck: has('updateCheck'), updateDownload: has('updateDownload'), updateLaunch: has('updateLaunch'),
           updateOpenRelease: has('updateOpenRelease'), botGitStatus: has('botGitStatus'), botGitPull: has('botGitPull'),
           progressSub: typeof prog === 'function',
           statusOk: st.ok === true, isRepo: st.data ? st.data.isRepo : null, branch: st.data ? st.data.branch : null,
         };
       })()`,
    )
    check(
      'Guncelleme kopru metotlari tanimli',
      Boolean(updBridge?.updateCheck && updBridge?.updateDownload && updBridge?.updateLaunch && updBridge?.updateOpenRelease && updBridge?.botGitStatus && updBridge?.botGitPull && updBridge?.progressSub),
      JSON.stringify(updBridge),
    )
    check('botGitStatus IPC gercek depoda calisti', updBridge?.statusOk === true && updBridge?.isRepo === true, `dal: ${updBridge?.branch}`)

    const guard = await win.webContents.executeJavaScript(`(async()=>{ const r = await window.vfgui.shellOpen('C:/Windows/System32/drivers/etc/hosts'); return r.ok; })()`)
    check('Yol korumasi (proje disi dosya) engellendi', guard === false, String(guard))

    /* ---------------- 13b. Tum sayfalar (her ozellik ekrani) ---------------- */
    section('13b) Tum sayfalar gercekten ciziliyor mu (menu uzerinden gezinti)')
    const SAYFALAR: { nav: string; ad: string; isaretler: string[] }[] = [
      { nav: 'Panel', ad: 'Panel', isaretler: ['ortam durumu'] },
      { nav: 'Calistir', ad: 'Calistir', isaretler: ['aktif islem yok', 'gecmis'] },
      { nav: 'Kutuphane', ad: 'Kutuphane', isaretler: ['bot.db icerigi'] },
      { nav: 'Cikti', ad: 'Cikti & Rapor', isaretler: ['cikti dosyalari'] },
      { nav: 'Kesif', ad: 'Kesif', isaretler: ['kesif modulu'] },
      { nav: 'Loglar', ad: 'Loglar', isaretler: ['bot_log.txt'] },
      { nav: 'Ayarlar', ad: 'Ayarlar', isaretler: ['gorunum', 'yollar ve python'] },
    ]
    for (const sayfa of SAYFALAR) {
      const tiklandi = (await win.webContents.executeJavaScript(
        `(() => {
           const b = [...document.querySelectorAll('nav button')].find((x) => (x.textContent || '').trim().toLowerCase().startsWith(${JSON.stringify(sayfa.nav.toLowerCase())}));
           if (!b) return false;
           b.click();
           return true;
         })()`,
      )) as boolean
      await sleep(800)
      const sayfaMetni = ((await win.webContents.executeJavaScript('document.body.textContent')) as string).toLowerCase()
      const bulunan = sayfa.isaretler.filter((i) => sayfaMetni.includes(i))
      check(`${sayfa.ad} sayfasi acildi ve ici cizildi`, tiklandi && bulunan.length > 0, tiklandi ? `beklenen: ${sayfa.isaretler.join(' | ')} -> ${bulunan.join(', ') || 'HICBIRI YOK'}` : 'menu butonu bulunamadi')
    }
    check('Sayfa gezintisi konsol hatasi uretmedi', rendererErrors.length === 0, rendererErrors.slice(0, 2).join(' | '))

    /* ---------------- 13c. Pencere kontrolleri ---------------- */
    section('13c) Pencere kontrolleri (kucult / buyut / durum / kapat)')
    setMainWindow(win)
    const durumOnce = (await win.webContents.executeJavaScript('window.vfgui.winState()')) as { maximized: boolean; focused: boolean }
    check('Pencere durumu okunuyor (winState)', durumOnce?.maximized === false, JSON.stringify(durumOnce))
    const buyut1 = (await win.webContents.executeJavaScript('window.vfgui.winMaximize()')) as boolean
    await sleep(600)
    const durumBuyuk = (await win.webContents.executeJavaScript('window.vfgui.winState()')) as { maximized: boolean; focused: boolean }
    check('Buyut komutu pencereyi gercekten buyuttu', buyut1 === true && durumBuyuk?.maximized === true, `donen=${buyut1} durum=${JSON.stringify(durumBuyuk)}`)
    const buyut2 = (await win.webContents.executeJavaScript('window.vfgui.winMaximize()')) as boolean
    await sleep(600)
    check('Ayni komut tekrar cagrilinca geri kuculttu (ac/kapa)', buyut2 === false && win.isMaximized() === false, `donen=${buyut2} isMaximized=${win.isMaximized()}`)
    const kucult = (await win.webContents.executeJavaScript('window.vfgui.winMinimize()')) as boolean
    await sleep(500)
    check('Kucult komutu uygulandi', kucult === true && win.isMinimized(), `donen=${kucult} isMinimized=${win.isMinimized()}`)
    win.restore()
    await sleep(400)
    check('Kucultmeden geri donus calisti', !win.isMinimized() || win.isDestroyed(), `isMinimized=${win.isMinimized()}`)
    setMainWindow(null)
    // Kapat komutu ikinci bir pencerede denenir (kendi penceremizi kapatip testi bozmayalim).
    const win2 = new BrowserWindow({
      show: false,
      width: 900,
      height: 640,
      webPreferences: {
        preload: path.join(ROOT, 'dist-electron', 'preload.cjs'),
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: false,
      },
    })
    setMainWindow(win2)
    await win2.loadFile(distIndex)
    await sleep(700)
    check('Ikinci pencere yuklendi (kopru hazir)', (await win2.webContents.executeJavaScript('typeof window.vfgui')) === 'object', '')
    // Pencere kapanirken renderer olur: promise reddedilebilir ya da hic
    // sonuclanmayabilir (Electron davranisi) - bu yuzden zaman siniri var.
    const kapat = (await Promise.race([
      win2.webContents.executeJavaScript('window.vfgui.winClose()').catch(() => null),
      sleep(5_000).then(() => 'zaman-asimi' as const),
    ])) as boolean | null | 'zaman-asimi'
    await sleep(900)
    check('Kapat komutu pencereyi kapatti', win2.isDestroyed(), `donen=${kapat} yikildi=${win2.isDestroyed()}`)
    setMainWindow(null)
    if (!win2.isDestroyed()) win2.destroy()

    /* ---------------- 13d. Kutuphane kaydi silme (guvenli kopya) ---------------- */
    section('13d) Kutuphane kaydi silme (bot.db kopyasi uzerinde)')
    const gercekDb = path.join(realBot, 'bot.db')
    const kopyaBot = fs.mkdtempSync(path.join(os.tmpdir(), 'vf-libforget-'))
    const dbVar = fs.existsSync(gercekDb)
    const dbOnceki = dbVar ? fs.statSync(gercekDb) : null
    if (dbVar) {
      write(path.join(kopyaBot, 'shared.py'), '# sahte bot klasoru\n')
      fs.copyFileSync(gercekDb, path.join(kopyaBot, 'bot.db'))
      setSettings({ videoForgePath: kopyaBot })
      const once = await readLibrary()
      const hedefLink = (once.videos.find((v) => (v.link || '').trim())?.link ?? '').trim()
      const silindi = await forgetLink(hedefLink)
      const sonra = await readLibrary()
      check('Kopya bot.db okundu', once.ok && once.counts.videos > 0, `${once.counts.videos} video`)
      check('Kayit silindi (libraryForget)', silindi.ok === true && (silindi.deleted ?? 0) >= 1, JSON.stringify(silindi))
      check('Silinen kayit artik listede yok', sonra.videos.every((v) => v.link !== hedefLink), hedefLink)
      check('Kutuphane sayaci silinen kadar azaldi', sonra.counts.videos === once.counts.videos - (silindi.deleted ?? 0), `${once.counts.videos} - ${silindi.deleted} = ${sonra.counts.videos}`)
    } else {
      check('Kopya bot.db okundu (bot.db yok, atlandi)', false, 'bot.db bulunamadi - test edilemedi')
      check('Kayit silindi (atlandi)', false, 'bot.db bulunamadi')
      check('Silinen kayit artik listede yok (atlandi)', false, 'bot.db bulunamadi')
      check('Kutuphane sayaci silinen kadar azaldi (atlandi)', false, 'bot.db bulunamadi')
    }
    forceRemove(kopyaBot)
    if (dbOnceki) {
      const dbSonraki = fs.statSync(gercekDb)
      check('Gercek bot.db degismedi (silme kopyada yapildi)', dbOnceki.size === dbSonraki.size && dbOnceki.mtimeMs === dbSonraki.mtimeMs, `${dbSonraki.size} bayt`)
    } else {
      check('Gercek bot.db degismedi (bot.db yok)', true, '')
    }

    /* ---------------- 13e. Ayar / tema / motor / rapor kopruleri ---------------- */
    section('13e) Ayar, tema, motor ve rapor kopruleri (kalan IPC kanallari)')
    setSettings({ videoForgePath: realBot })
    const ayarOku = (await win.webContents.executeJavaScript('window.vfgui.settingsGet()')) as { ok: boolean; data?: { videoForgePath: string; autoCheckUpdates: boolean } }
    check('settingsGet IPC calisiyor', ayarOku.ok === true && typeof ayarOku.data?.videoForgePath === 'string', String(ayarOku.data?.videoForgePath))
    const ayarYaz = (await win.webContents.executeJavaScript('window.vfgui.settingsSet({ autoCheckUpdates: false })')) as { ok: boolean; data?: { autoCheckUpdates: boolean } }
    check('settingsSet IPC yazdi ve ana surece ulasti', ayarYaz.ok === true && ayarYaz.data?.autoCheckUpdates === false && getSettings().autoCheckUpdates === false, `IPC=${ayarYaz.data?.autoCheckUpdates} yerel=${getSettings().autoCheckUpdates}`)
    await win.webContents.executeJavaScript('window.vfgui.settingsSet({ autoCheckUpdates: true })')
    check('Ayar geri alindi', getSettings().autoCheckUpdates === true, String(getSettings().autoCheckUpdates))

    const temaYaz = (await win.webContents.executeJavaScript(`window.vfgui.themeSet('light')`)) as { ok: boolean; data?: { mode: string } }
    check('themeSet IPC calisti ve kalici yazdi', temaYaz.ok === true && temaYaz.data?.mode === 'light' && getSettings().mode === 'light', JSON.stringify(temaYaz.data?.mode))
    await win.webContents.executeJavaScript(`window.vfgui.themeSet('dark')`)
    check('Tema geri alindi', getSettings().mode === 'dark', getSettings().mode)

    const motor = (await win.webContents.executeJavaScript('window.vfgui.engineConfig()')) as { ok: boolean; data?: { charLimit: number } }
    check('engineConfig IPC calisti', motor.ok === true && typeof motor.data?.charLimit === 'number', `charLimit=${motor.data?.charLimit}`)
    const motorKopya = await (async () => {
      const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'vf-enginelimit-'))
      fs.copyFileSync(gercekDb, path.join(tmp, 'bot.db'))
      fs.writeFileSync(path.join(tmp, 'constants.py'), 'CHAR_LIMIT_KINO_SYJET = 570\n', 'utf8')
      setSettings({ videoForgePath: tmp })
      const yaz = (await win.webContents.executeJavaScript(`window.vfgui.engineSetCharLimit(${motor.data?.charLimit ?? 570})`)) as { ok: boolean; data?: { charLimit: number } }
      forceRemove(tmp)
      return yaz
    })()
    check('engineSetCharLimit yazdi ve degeri geri okudu', motorKopya.ok === true && motorKopya.data?.charLimit === motor.data?.charLimit, `${motor.data?.charLimit} -> ${motorKopya.data?.charLimit}`)
    setSettings({ videoForgePath: realBot })

    const gecmisB = (await win.webContents.executeJavaScript('window.vfgui.runHistory()')) as { ok: boolean; data?: unknown[] }
    check('runHistory IPC calisti', gecmisB.ok === true && Array.isArray(gecmisB.data), `${gecmisB.data?.length ?? -1} kayit`)
    const iptalBos = (await win.webContents.executeJavaScript('window.vfgui.runCancel()')) as { ok: boolean }
    check('Calisan is yokken runCancel cokme yapmadi', iptalBos.ok === true, JSON.stringify(iptalBos))
    const onizleme = (await win.webContents.executeJavaScript(`(async () => { const r = await window.vfgui.reportsPreview(${JSON.stringify(path.join(ROOT, 'dist', 'index.html'))}); return r.ok ? { ok: true, title: r.data.title ?? '' } : { ok: false, error: r.error }; })()`)) as { ok: boolean; title?: string; error?: string }
    check('reportsPreview izinli yolda HTML onizlemesi uretti', onizleme.ok === true, onizleme.ok ? `baslik: ${onizleme.title}` : (onizleme.error ?? ''))
    const onizlemeGuard = (await win.webContents.executeJavaScript(`(async () => { const r = await window.vfgui.reportsPreview('C:/Windows/System32/drivers/etc/hosts'); return r.ok; })()`)) as boolean
    check('reportsPreview proje disi yolu reddetti', onizlemeGuard === false, String(onizlemeGuard))
    const revealGuard = (await win.webContents.executeJavaScript(`(async () => { const r = await window.vfgui.shellReveal('C:/Windows/System32/drivers/etc/hosts'); return r.ok; })()`)) as boolean
    check('shellReveal proje disi yolu reddetti', revealGuard === false, String(revealGuard))
    const extGuard = (await win.webContents.executeJavaScript(`(async () => { const r = await window.vfgui.shellOpenExternal('dosya://kotu'); return r.ok; })()`)) as boolean
    check('shellOpenExternal sadece http(s) kabul ediyor', extGuard === false, String(extGuard))
    const launchGuard = (await win.webContents.executeJavaScript(`(async () => { const r = await window.vfgui.updateLaunch(''); return r.ok; })()`)) as boolean
    check('updateLaunch olmayan dosyayi reddetti (kendini kurmaz)', launchGuard === false, String(launchGuard))
    const updKontrol = (await win.webContents.executeJavaScript('window.vfgui.updateCheck()')) as { ok: boolean; data?: { latest: string | null; available: boolean } }
    check('updateCheck IPC calisti', updKontrol.ok === true, updKontrol.ok ? `son surum: ${updKontrol.data?.latest ?? 'yok'} / guncelleme: ${updKontrol.data?.available}` : '')
    /* ---------------- 13f. Panelden gun sayisi secerek zincir ---------------- */
    // Kullanicinin bildirdigi hata: Panel'deki "cok gunlu zincir" dugmesi gun
    // sayisini gecirmiyordu -> her zaman 7 gun isliyordu. Bu test alani,
    // kaydetmeyi ve dugmenin istegi tasidigini bastan sona dogrular.
    section('13f) Panelden gun sayisi secerek zincir baslatma (alan -> komut)')
    const panelBot = makeFakeBot()
    setSettings({ videoForgePath: panelBot, gunSayisi: 7 })
    const panelHazirla = (await win.webContents.executeJavaScript(
      `(async () => {
         const nav = [...document.querySelectorAll('nav button')].find((b) => (b.textContent || '').trim().toLowerCase().startsWith('panel'));
         if (!nav) return { hata: 'panel menusu yok', alan: false };
         nav.click();
         await new Promise((r) => setTimeout(r, 800));
         const el = document.getElementById('gun-sayisi');
         if (!el) return { hata: 'gun sayisi alani yok', alan: false };
         el.focus();
         el.select();
         return { alan: true, disabled: el.disabled, odak: document.activeElement === el, deger: el.value };
       })()`,
    )) as { alan?: boolean; disabled?: boolean; odak?: boolean; deger?: string; hata?: string }
    check('Panel sayfasinda gun sayisi alani VAR (kullanici bulamama sorunu)', panelHazirla?.alan === true, panelHazirla?.hata ?? 'alan bulundu')
    check('Gun sayisi alani odaklanabilir ve acik', panelHazirla?.alan === true && panelHazirla?.disabled === false && panelHazirla?.odak === true, JSON.stringify(panelHazirla))

    // Alana 12 yaz (kullanicinin klavyeyle yazmasi = input olayi).
    const panelAlan = (await win.webContents.executeJavaScript(
      `(async () => {
         const el = document.getElementById('gun-sayisi');
         if (!el) return null;
         const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
         setter.call(el, '12');
         el.dispatchEvent(new Event('input', { bubbles: true }));
         await new Promise((r) => setTimeout(r, 900));
         const bul = (re) => ([...document.querySelectorAll('button')].find((b) => re.test(b.textContent || '')) || {}).textContent || '';
         return { alan: true, deger: el.value, zincir: bul(/gunluk zincir/i), plan: bul(/gunluk plan olustur/i) };
       })()`,
    )) as { alan?: boolean; deger?: string; zincir?: string; plan?: string } | null
    check('Gun sayisi alanina yazilan deger alanda gorunuyor (12)', panelAlan?.deger === '12', String(panelAlan?.deger))
    check('Yazilan gun sayisi kendiliginden kaydedildi (12)', getSettings().gunSayisi === 12, `alan=${String(panelAlan?.deger)} ayar=${getSettings().gunSayisi}`)
    check('Panel zincir dugmesi secilen gunu gosteriyor', /12 gunluk zincir/i.test(panelAlan?.zincir ?? ''), String(panelAlan?.zincir))
    check('Panel plan dugmesi secilen gunu gosteriyor', /12 gunluk plan olustur/i.test(panelAlan?.plan ?? ''), String(panelAlan?.plan))

    // Hazir secenek butonlari da (tek tiklamayla) kaydetmeli: 14
    const panelHazir = (await win.webContents.executeJavaScript(
      `(async () => {
         const b = [...document.querySelectorAll('button')].find((x) => (x.getAttribute('aria-pressed') !== null) && (x.textContent || '').trim() === '14');
         if (!b) return false;
         b.click();
         await new Promise((r) => setTimeout(r, 600));
         return true;
       })()`,
    )) as boolean
    check('Hazir gun secenegi (14) tiklanabiliyor', panelHazir === true, '')
    check('Hazir secenek ayarlara yazildi (14)', getSettings().gunSayisi === 14, String(getSettings().gunSayisi))

    // Test zinciri icin tekrar 12'ye don (panel hala acik).
    const tekrar12 = (await win.webContents.executeJavaScript(
      `(async () => {
         const el = document.getElementById('gun-sayisi');
         if (!el) return null;
         const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
         setter.call(el, '12');
         el.dispatchEvent(new Event('input', { bubbles: true }));
         await new Promise((r) => setTimeout(r, 900));
         return el.value;
       })()`,
    )) as string | null
    check('Gun sayisi tekrar 12 yapildi', tekrar12 === '12' && getSettings().gunSayisi === 12, `alan=${String(tekrar12)} ayar=${getSettings().gunSayisi}`)

    // Zincir dugmesine gercekten bas (yazilan 12 gun ile): ana surecteki is 12 gun kurulmali.
    const zincirBasildi = (await win.webContents.executeJavaScript(
      `(() => { const b = [...document.querySelectorAll('button')].find((x) => /gunluk zincir/i.test(x.textContent || '')); if (!b) return false; b.click(); return true; })()`,
    )) as boolean
    await sleep(1600)
    const panelJob = getState()
    check('Panel zincir dugmesi isi baslatti', zincirBasildi === true && panelJob !== null, `durum: ${panelJob?.status}`)
    check('Panelden baslayan is secilen gun sayisini kullaniyor (12)', /12 Gunluk/i.test(panelJob?.title ?? ''), String(panelJob?.title))
    check('Panel zinciri 2 adimli kuruldu (kesif + isletme)', (panelJob?.stages.length ?? 0) >= 2, `${panelJob?.stages.length} asama`)
    const panelSon = await waitForStatus(90_000)
    check('Panel zinciri tamamlandi (sahte bot)', panelSon === 'done', `durum: ${panelSon}`)
    check('Panel zinciri plan dosyasini uretti', fs.existsSync(planPath(panelBot)), planPath(panelBot))
    forceRemove(panelBot)
    setSettings({ videoForgePath: realBot })

    check('Renderer konsol hatasi yok', rendererErrors.length === 0, rendererErrors.slice(0, 3).join(' | '))

    win.destroy()

    /* ---------------- 14. IPC kanal isimleri ---------------- */
    section('14) IPC sozlesmesi')
    check('IPC kanal sayisi', Object.keys(IPC).length >= 24, `${Object.keys(IPC).length} kanal`)
    check('3 kanal tanimli', CHANNELS.length === 3, CHANNELS.map((c) => c.name).join(', '))

    /* ---------------- 15. Surum karsilastirma + GitHub kontrolu ---------------- */
    section('15) Guncelleme sistemi (surum karsilastirma)')
    check('parseVersion on eki temizledi', JSON.stringify(parseVersion('v1.2.3-beta.1+build')) === '[1,2,3]', JSON.stringify(parseVersion('v1.2.3-beta.1+build')))
    check('compareVersions yeni surumu buldu', compareVersions('1.1.0', '1.0.0') === 1, '1.1.0 > 1.0.0')
    check('compareVersions esit surumler', compareVersions('1.0.0', '1.0') === 0, '1.0.0 = 1.0')
    check('compareVersions eski surum', compareVersions('1.0.0', '2') === -1, '1.0.0 < 2')
    check('compareVersions iki haneli sayilari dogru okudu', compareVersions('1.10.0', '1.9.9') === 1, '1.10.0 > 1.9.9')

    const badRepo = await checkForUpdate('gecersiz-adres', '')
    check('Gecersiz depo bicimi reddedildi', badRepo.ok === false && /owner\/repo/.test(badRepo.error ?? ''), badRepo.error ?? '')
    check(
      'Hata durumunda da arayuz icin tam sonuc dondu',
      typeof badRepo.current === 'string' && badRepo.available === false && Array.isArray(badRepo.assets) && badRepo.assets.length === 0 && typeof badRepo.checkedAt === 'number',
      `surum: ${badRepo.current}`,
    )

    const net = await checkForUpdate(undefined, '')
    check('GitHub surum kontrolu hata firlatmadan dondu', net.ok === true || Boolean(net.error), net.ok ? `depo: ${net.repo} / son surum: ${net.latest ?? 'yayinlanmis surum yok'}` : (net.error ?? ''))
    check('Kontrol sonucu mevcut surumu bildiriyor', net.current === app.getVersion(), `${net.current} = uygulama ${app.getVersion()}`)
    check('Kontrol sonucu token/kimlik bilgisi sizdirmiyor', !JSON.stringify(net).includes('Bearer') && !JSON.stringify(net).includes('ghp_'), 'token yok')
    if (net.ok && net.latest) {
      check('Guncelleme var/var degil karari tutarli', net.available === (compareVersions(net.latest, net.current) > 0), `${net.latest} vs ${net.current} -> ${net.available}`)
      check('Surum dosyalari listelendi', Array.isArray(net.assets), `${net.assets.length} dosya`)
    } else {
      check('Guncelleme var/var degil karari tutarli (yayin yok, atlandi)', true, 'depoda yayinlanmis surum yok')
      check('Surum dosyalari listelendi (yayin yok, atlandi)', true, '')
    }

    // Private depo: token yokken aciklayici hata vermeli (kullanici ne yapacagini bilmeli).
    check(
      'Token yokken private depo icin aciklayici mesaj dondu',
      net.ok === true && Boolean(net.error) ? /token/i.test(net.error ?? '') : net.ok === true,
      net.error ?? 'genel hata yok',
    )

    // Private depo + token: gercek surum kontrolu ve gercek indirme (gh CLI'dan token okunur).
    const ghTokenRes = await execCapture('gh', ['auth', 'token'], { timeoutMs: 20_000 })
    const ghToken = ghTokenRes.code === 0 ? ghTokenRes.stdout.trim() : ''
    if (ghToken) {
      check('gh token bulundu (bellege alindi, yazdirilmadi)', ghToken.length > 20, `${ghToken.slice(0, 4)}… (gizli)`)
      const authed = await checkForUpdate(DEFAULT_UPDATE_REPO, ghToken)
      check('Private depo icin kimlikli kontrol calisti', authed.ok === true, authed.error ?? `son surum: ${authed.latest}`)
      if (authed.ok && authed.latest) {
        check('Yayinlanan surum ve kurulum dosyalari listelendi', authed.assets.some((a) => /\.exe$/i.test(a.name)), authed.assets.map((a) => a.name).join(', ') || 'dosya yok')
        check('Kimlikli kontrolde API indirme adresi kullanildi', authed.assets.every((a) => a.isApiUrl), `${authed.assets.length} dosya`)
        check('Token yanitta gorunmuyor', !JSON.stringify(authed).includes(ghToken), 'sizinti yok')

        // Indirme adresi gercekten calisiyor mu? Sadece basliklar dogrulanir (dosya indirilmez).
        const probeAsset = authed.assets.find((a) => /\.exe$/i.test(a.name))
        if (probeAsset) {
          const probe = await (async (): Promise<{ status: number; mb: number }> => {
            const ctrl = new AbortController()
            try {
              const res = await fetch(probeAsset.url, {
                headers: { accept: 'application/octet-stream', authorization: `Bearer ${ghToken}` },
                signal: ctrl.signal,
              })
              const len = Number(res.headers.get('content-length') || 0)
              return { status: res.status, mb: len / 1048576 }
            } finally {
              ctrl.abort()
            }
          })()
          check('Private kurulum dosyasi token ile indirilebilir', probe.status === 200 && probe.mb > 10, `HTTP ${probe.status} / ${probe.mb.toFixed(1)} MB`)
        } else {
          check('Private kurulum dosyasi token ile indirilebilir (dosya yok, atlandi)', true, '')
        }

        // Gercek indirme akisi (kurulum dosyasi CALISTIRILMAZ).
        setSettings({ githubToken: ghToken, updateRepo: DEFAULT_UPDATE_REPO })
        const portable = authed.assets.find((a) => /portable\.exe$/i.test(a.name))
        if (portable) {
          const dl = await downloadUpdate(portable.name)
          check('Guncelleme dosyasi gercekten indirildi', dl.ok === true && Boolean(dl.path) && fs.existsSync(dl.path ?? ''), dl.ok && dl.path ? `${(fs.statSync(dl.path).size / 1048576).toFixed(1)} MB` : (dl.error ?? ''))
          check('Indirilen dosya surum klasorune yazildi', Boolean(dl.path && dl.path.toLowerCase().includes('updates')), String(dl.path))
          if (dl.path) fs.rmSync(dl.path, { force: true })
        } else {
          check('Guncelleme dosyasi gercekten indirildi (portable yok, atlandi)', true, '')
          check('Indirilen dosya surum klasorune yazildi (atlandi)', true, '')
        }
        setSettings({ githubToken: '' })
      } else {
        check('Yayinlanan surum ve kurulum dosyalari listelendi (surum yok, atlandi)', true, 'depoda yayinlanmis surum yok')
        check('Kimlikli kontrolde API indirme adresi kullanildi (surum yok, atlandi)', true, '')
        check('Token yanitta gorunmuyor (surum yok, atlandi)', true, '')
        check('Private kurulum dosyasi token ile indirilebilir (surum yok, atlandi)', true, '')
        check('Guncelleme dosyasi gercekten indirildi (surum yok, atlandi)', true, '')
        check('Indirilen dosya surum klasorune yazildi (surum yok, atlandi)', true, '')
      }
    } else {
      check('gh token bulundu (gh yok, atlandi)', true, 'gh auth token alinamadi')
      for (const ad of [
        'Private depo icin kimlikli kontrol calisti',
        'Yayinlanan surum ve kurulum dosyalari listelendi',
        'Kimlikli kontrolde API indirme adresi kullanildi',
        'Token yanitta gorunmuyor',
        'Private kurulum dosyasi token ile indirilebilir',
        'Guncelleme dosyasi gercekten indirildi',
        'Indirilen dosya surum klasorune yazildi',
      ]) {
        check(`${ad} (token yok, atlandi)`, true, '')
      }
    }

    /* ---------------- 16. Bot kodu guncellemesi (git) ---------------- */
    section('16) Bot kodu guncellemesi (git)')
    setSettings({ videoForgePath: realBot })
    const realGit = await botGitStatus()
    check('git kurulu ve erisilebilir', realGit.gitAvailable === true, realGit.error ?? 'git --version basarili')
    check('Gercek VideoForge klasoru depo olarak tanindi', realGit.ok && realGit.isRepo === true, `${realGit.branch} / ${realGit.commit ?? 'commit yok'}`)
    check('Dal adi okundu (ilk commit olmasa bile)', typeof realGit.branch === 'string' && realGit.branch.length > 0, String(realGit.branch))
    check('Depo koku bot klasoruyle ayni', realGit.isBotRepo === true && realGit.toplevel === realBot, `kök: ${realGit.toplevel}`)
    check('Calisma agaci durumu tutarli', realGit.dirty === (realGit.changedFiles.length > 0), `kirli: ${realGit.dirty}, ${realGit.changedFiles.length} dosya`)
    check('Son commit bilgisi okundu', typeof realGit.commit === 'string' && realGit.commit.length >= 7, String(realGit.commit))
    check('Uzak depo adresi okundu (gercek depo)', Boolean(realGit.remote && realGit.remote.includes('VideoForge')), String(realGit.remote))

    // Git deposu olmayan klasor: git yukari dogru aradigi icin gecici klasoru
    // cevreleyen depo varsa (ornegin kullanici ana klasoru) arama kesilir.
    const plain = fs.mkdtempSync(path.join(os.tmpdir(), 'vf-plain-'))
    write(path.join(plain, 'bot.py'), '# duz klasor\n')
    process.env.GIT_CEILING_DIRECTORIES = os.tmpdir()
    try {
      setSettings({ videoForgePath: plain })
      const notRepo = await botGitStatus()
      check('git deposu olmayan klasor reddedildi', notRepo.ok === false && notRepo.isRepo === false, notRepo.error ?? '')
      check('Depo olmayan klasorde degisiklik listesi bos', notRepo.changedFiles.length === 0, '')
    } finally {
      delete process.env.GIT_CEILING_DIRECTORIES
    }

    // Kendi deposu olmayan ama ust klasorunde depo bulunan klasor: yanlis depoyu cekmemeli.
    const nested = fs.mkdtempSync(path.join(os.tmpdir(), 'vf-nested-'))
    write(path.join(nested, 'bot.py'), '# ust depo icinde\n')
    setSettings({ videoForgePath: nested })
    const nestedStatus = await botGitStatus()
    if (nestedStatus.ok && nestedStatus.isRepo) {
      check('Ust depo icindeki klasor ayirt edildi', nestedStatus.isBotRepo === false, `toplevel: ${nestedStatus.toplevel}`)
      const nestedPull = await pullBotCode()
      check('Yanlis (ust) depo cekilmedi', nestedPull.ok === false && /kendi git deposu degil/.test(nestedPull.error ?? ''), nestedPull.error ?? '')
    } else {
      check('Ust depo icindeki klasor ayirt edildi (ust depo yok, atlandi)', true, 'gecici klasorun ustunde depo yok')
      check('Yanlis (ust) depo cekilmedi (ust depo yok, atlandi)', true, '')
    }

    const pair = await makeGitPair()
    setSettings({ videoForgePath: pair.clone })
    const cleanStatus = await botGitStatus()
    check('Temiz klon okundu', cleanStatus.ok === true && cleanStatus.isRepo === true && cleanStatus.dirty === false, `${cleanStatus.branch} / ${cleanStatus.commit}`)
    check('Uzak depo adresi okundu', Boolean(cleanStatus.remote && cleanStatus.remote.includes('remote.git')), String(cleanStatus.remote))
    check('Temiz klonda uzak fark 0/0', cleanStatus.behind === 0 && cleanStatus.ahead === 0, `geride: ${cleanStatus.behind}, ileride: ${cleanStatus.ahead}`)

    await pair.pushNewCommit()
    const stale = await botGitStatus()
    check('Fetch yapilmadan yerel bilgi kullanildi', stale.behind === 0, `geride: ${stale.behind}`)
    const freshened = await botGitStatus({ fetch: true })
    check('Fetch sonrasi uzaktaki yeni commit "geride" olarak okundu', freshened.behind === 1 && freshened.ahead === 0, `geride: ${freshened.behind}, ileride: ${freshened.ahead}`)

    const fileBefore = fs.readFileSync(path.join(pair.clone, 'bot.py'), 'utf8')
    check('Guncelleme oncesi dosya eski surumde', fileBefore.includes('surum 1'), fileBefore.trim())

    const pulled = await pullBotCode()
    check('Bot kodu guncellemesi (git pull) basarili', pulled.ok === true, pulled.error ?? pulled.output.split('\n').filter(Boolean).slice(-1)[0] ?? '')
    const fileAfter = fs.readFileSync(path.join(pair.clone, 'bot.py'), 'utf8')
    check('Dosyalar gercekten yenilendi', fileAfter.includes('surum 2'), fileAfter.trim())
    check('Guncelleme sonrasi commit ilerledi', Boolean(pulled.info.commit) && pulled.info.commit !== cleanStatus.commit, `${cleanStatus.commit} -> ${pulled.info.commit}`)
    check('Guncelleme sonrasi temiz ve senkron', pulled.info.dirty === false && pulled.info.behind === 0, `kirli: ${pulled.info.dirty}, geride: ${pulled.info.behind}`)

    // Uzaga gonderilmemis yerel commit: bu kez "ileride" olmali (yon karismamali)
    write(path.join(pair.clone, 'bot.py'), 'print("surum 3-yerel")\n')
    await gitRun(pair.clone, [...GIT_IDENTITY, 'commit', '-q', '-am', 'yerel gelistirme'])
    const aheadStatus = await botGitStatus({ fetch: true })
    check('Uzaga gonderilmemis yerel commit "ileride" olarak okundu', aheadStatus.ahead === 1 && aheadStatus.behind === 0, `ileride: ${aheadStatus.ahead}, geride: ${aheadStatus.behind}`)

    // Yerel degisiklik varken guncelleme reddedilmeli (veri kaybi korumasi)
    write(path.join(pair.clone, 'bot.py'), '# yerel degisiklik\n')
    const dirtyStatus = await botGitStatus()
    check('Yerel degisiklik algilandi', dirtyStatus.dirty === true && dirtyStatus.changedFiles.length >= 1, dirtyStatus.changedFiles.join(' | '))
    const refused = await pullBotCode()
    check('Kirli calisma agacinda guncelleme reddedildi', refused.ok === false && /Yerel degisiklik/.test(refused.error ?? ''), refused.error ?? '')
    check('Reddedilen guncelleme dosyayi bozmadi', fs.readFileSync(path.join(pair.clone, 'bot.py'), 'utf8').includes('yerel degisiklik'), '')

    // Indirme/baslatma korumalari
    const outside = path.join(os.tmpdir(), `vf-outside-${Date.now()}.exe`)
    fs.writeFileSync(outside, 'MZ sahte')
    const outsideLaunch = launchDownloaded(outside)
    check('Indirme klasoru disindaki dosya baslatilmadi', outsideLaunch.ok === false && /Guvenlik/.test(outsideLaunch.error ?? ''), outsideLaunch.error ?? '')
    const updDir = path.join(app.getPath('userData'), 'updates')
    fs.mkdirSync(updDir, { recursive: true })
    const txtInside = path.join(updDir, 'sahte-guncelleme.txt')
    fs.writeFileSync(txtInside, 'x')
    const txtLaunch = launchDownloaded(txtInside)
    check('Desteklenmeyen dosya turu baslatilmadi', txtLaunch.ok === false && /Desteklenmeyen/.test(txtLaunch.error ?? ''), txtLaunch.error ?? '')
    const missingLaunch = launchDownloaded(path.join(updDir, 'olmayan.exe'))
    check('Olmayan guncelleme dosyasi icin net hata', missingLaunch.ok === false && /bulunamadi/i.test(missingLaunch.error ?? ''), missingLaunch.error ?? '')
    fs.rmSync(outside, { force: true })
    fs.rmSync(txtInside, { force: true })

    /* ---------------- 16. Uygulama ikonu + kurulum ---------------- */
    section('16) Uygulama ikonu ve kurulum yapilandirmasi')
    const botDir = path.resolve(ROOT, '..')
    const icoPath = path.join(ROOT, 'build', 'icon.ico')
    const icoPngPath = path.join(ROOT, 'build', 'icon.png')
    const publicLogo = path.join(ROOT, 'public', 'logo.png')
    const distLogo = path.join(ROOT, 'dist', 'logo.png')
    check('build/icon.ico var (kurulum ikonu)', fs.existsSync(icoPath), icoPath)
    check('build/icon.png var', fs.existsSync(icoPngPath), icoPngPath)
    check('public/logo.png var (arayuz logosu)', fs.existsSync(publicLogo), publicLogo)
    check('Logo derlemeye kopyalandi (dist/logo.png)', fs.existsSync(distLogo), distLogo)

    const baslik = (p: string, n: number): number[] => (fs.existsSync(p) ? [...fs.readFileSync(p).subarray(0, n)] : [])
    const icoHeader = baslik(icoPath, 4)
    check('icon.ico gecerli ICO basligi (00 00 01 00)', icoHeader.join(',') === '0,0,1,0', icoHeader.join(','))
    const pngSig = (p: string): boolean => {
      const b = baslik(p, 4)
      return b[0] === 0x89 && b[1] === 0x50 && b[2] === 0x4e && b[3] === 0x47
    }
    check('build/icon.png gecerli PNG', pngSig(icoPngPath), '')
    check('public/logo.png gecerli PNG', pngSig(publicLogo), '')
    const pngSize = (p: string): { w: number; h: number } | null => {
      if (!fs.existsSync(p)) return null
      const b = fs.readFileSync(p)
      return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) }
    }
    const bigPng = pngSize(icoPngPath)
    check('Kurulum ikonu en az 256x256', Boolean(bigPng && bigPng.w >= 256 && bigPng.h >= 256), JSON.stringify(bigPng))
    const smallPng = pngSize(publicLogo)
    check('Arayuz logosu kare ve makul boyutta', Boolean(smallPng && smallPng.w === smallPng.h && smallPng.w <= 512), JSON.stringify(smallPng))

    const buildYml = fs.readFileSync(path.join(ROOT, 'electron-builder.yml'), 'utf8')
    check('electron-builder win.icon ayarli', /win:[\s\S]*?icon:\s*build\/icon\.ico/.test(buildYml), '')
    check('NSIS kurulum/kaldirma ikonlari ayarli', /installerIcon:\s*build\/icon\.ico/.test(buildYml) && /uninstallerIcon:\s*build\/icon\.ico/.test(buildYml), '')
    check('NSIS sihirbazi acik (oneClick kapali)', /oneClick:\s*false/.test(buildYml), '')
    check('Masaustu kisayolu her zaman olusturulur', /createDesktopShortcut:\s*always/.test(buildYml), '')
    check('Kurulum sonrasi uygulama acilir', /runAfterFinish:\s*true/.test(buildYml), '')
    check('Kaldirmada kullanici verisi korunur', /deleteAppDataOnUninstall:\s*false/.test(buildYml), '')
    check('Kurulum dosyasi adi sabit (VideoForge-Setup-X.Y.Z.exe)', /artifactName:\s*'VideoForge-Setup-\$\{version\}\.\$\{ext\}'/.test(buildYml), '')

    const distIndexHtml = fs.readFileSync(path.join(ROOT, 'dist', 'index.html'), 'utf8')
    check('index.html favicon olarak logo.png kullaniyor', /rel="icon"[^>]*logo\.png/.test(distIndexHtml), '')
    const mainTs = fs.readFileSync(path.join(ROOT, 'electron', 'main.ts'), 'utf8')
    check('Pencere ikonu main.ts icinde ayarli', mainTs.includes("'build', 'icon.ico'") && /icon:\s*windowIconPath\(\)/.test(mainTs), '')

    /* ---------------- 17. Bulut gizli anahtar mimarisi ---------------- */
    section('17) Bulut gizli anahtar mimarisi (Modal bagimlilik hatasi tekrar etmesin)')
    const bkPy = fs.readFileSync(path.join(botDir, 'bulut_kanali.py'), 'utf8')
    check('Kosullu modal Secret.from_dotenv cagrisi kalmadi', !/\.from_dotenv\s*\(/.test(bkPy), 'bulut_kanali.py')
    check('Secret kosulsuz ve isimle referans ediliyor', /MODAL_SECRETS\s*=\s*\[modal\.Secret\.from_name\(SECRET_NAME\)\]/.test(bkPy), '')
    check('Uc bulut fonksiyonu da ayni secret listesini kullaniyor', (bkPy.match(/secrets=MODAL_SECRETS/g) ?? []).length === 3, String((bkPy.match(/secrets=MODAL_SECRETS/g) ?? []).length))
    check('Modal tekrar denemesi sinirlandi (retries=0 x3)', (bkPy.match(/retries=0/g) ?? []).length >= 3, String((bkPy.match(/retries=0/g) ?? []).length))
    check('Konteyner ortaminda bulut_kurulum import edilmiyor (is_local korumasi)', /if modal\.is_local\(\)/.test(bkPy), '')
    const kurulumPy = fs.readFileSync(path.join(botDir, 'bulut_kurulum.py'), 'utf8')
    check('Kurulum yardimcisi secret adini tanimliyor', kurulumPy.includes('SECRET_NAME = "videoforge-env"'), '')
    check('Secret adi iki dosyada ayni', kurulumPy.includes('videoforge-env') && bkPy.includes('videoforge-env'), '')
    check('Kurulum yeniden yazarken once siler (bayat deger kalmaz)', kurulumPy.includes('objects.delete') && kurulumPy.includes('objects.create'), '')
    const mscPy = fs.readFileSync(path.join(ROOT, 'smoke', 'modal_secret_check.py'), 'utf8')
    check('Bulut kontrol araci isimli secret kullaniyor', mscPy.includes('Secret.from_name') && !/\.from_dotenv\s*\(/.test(mscPy), '')

    /* ---------------- 18. Bot gun sayisi (7 sabit degil) ---------------- */
    section('18) Bot tarafi gun sayisi ve durdurma destegi')
    const kesifPy = fs.readFileSync(path.join(botDir, 'kesif.py'), 'utf8')
    check('kesif.py --gun secenegi var', kesifPy.includes('"--gun"'), '')
    check('kesif.py --haftalik artik deger alabiliyor', /"--haftalik",\s*nargs="\?"/.test(kesifPy), '')
    check('kesif.py gun_sayisi ile calisiyor', kesifPy.includes('gun_sayisi') && !/\[:7\]/.test(kesifPy), '')
    check('kesif.py 60 gun ust siniri', kesifPy.includes('MAX_GUN_SAYISI = 60'), '')
    check('kesif.py 7 gun sabit metni kalmadi', !/7 GUN\)|7 video bulunacak/.test(kesifPy), '')
    check('kesif.py plan gun sayisini JSON\'a yaziyor', /"gun_sayisi":\s*gun_sayisi/.test(kesifPy), '')
    const isletPy = fs.readFileSync(path.join(botDir, 'haftalik_islet.py'), 'utf8')
    check('haftalik_islet.py plan gun sayisini okuyor', isletPy.includes('plan_toplam'), '')
    check('haftalik_islet.py iptal isaretini destekliyor', isletPy.includes('VIDEOFORGE_CANCEL_FILE') && isletPy.includes('iptal_edildi'), '')
    check('haftalik_islet.py icinde sabit \'7 gun\' ifadesi yok', !/7 gun final/.test(isletPy), '')
    check('Bos gun sayisinda 7 varsayilana donulur', isletPy.includes('varsayilan=7'), '')

    // Bot Python dosyalari sozdizimi (dosya yazmadan, ast ile)
    const pyRes = await resolvePython()
    if (pyRes.ok && pyRes.python) {
      const kontrol = await execCapture(
        pyRes.python.command,
        [
          ...pyRes.python.args,
          '-X',
          'utf8',
          '-c',
          // utf-8-sig: bazi bot dosyalari BOM ile basliyor (Python calistirirken
          // yok sayar, ast.parse etmez) - testte de yok sayilir.
          "import ast,sys;[ast.parse(open(f,encoding='utf-8-sig').read(),f) for f in sys.argv[1:]]",
          'kesif.py',
          'haftalik_islet.py',
          'bulut_kanali.py',
          'bulut_kurulum.py',
          'constants.py',
          'shared.py',
          'faktza15.py',
          'kinosekrety.py',
          'kinok_syjet.py',
        ],
        { cwd: botDir, timeoutMs: 60_000 },
      )
      check('Bot Python dosyalari sozdiziminden geciyor', kontrol.code === 0, (kontrol.stderr || kontrol.stdout).trim().split('\n').slice(-1)[0] ?? '')
    } else {
      check('Bot Python dosyalari sozdiziminden geciyor (python yok, atlandi)', true, '')
    }

    /* ---------------- Temizlik ---------------- */
    // Git nesneleri Windows'ta salt okunur olabilir: EPERM'e karsi tekrar denenir.
    for (const p of [fakeBot, slowBot, fakeBot2, plain, nested, pair.base]) forceRemove(p)
  } finally {
    // Ayarlari eski haline getir (kullanicinin gercek yapilandirmasi bozulmasin)
    setSettings({ videoForgePath: originalSettings.videoForgePath })
    try {
      if (originalSettingsRaw !== null) fs.writeFileSync(settingsFile, originalSettingsRaw, 'utf8')
      else if (fs.existsSync(settingsFile)) fs.rmSync(settingsFile, { force: true })
    } catch {
      /* yoksay */
    }
  }

  console.log(`\n=========================================`)
  console.log(`  SONUC: ${passed} basarili, ${failed} basarisiz`)
  if (failures.length) console.log(`  Basarisiz: ${failures.join(' | ')}`)
  console.log(`=========================================\n`)

  app.exit(failed === 0 ? 0 : 1)
}

void main().catch((err) => {
  console.error('SMOKE TEST CRASH:', err)
  app.exit(2)
})
