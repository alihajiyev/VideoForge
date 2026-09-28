/**
 * VideoForge masaustu surum yayinlama araci.
 *
 *   npm run release              -> patch surumu yukseltir, derler, GitHub surumunu yayinlar
 *   npm run release -- minor     -> minor surum yukseltir (patch | minor | major)
 *   npm run release -- --no-bump -> surumu yukseltmeden mevcut surumu yayinlar (ilk surum icin)
 *   npm run release -- --dry     -> hicbir sey yayinlamaz, sadece derler ve plani yazar
 *   npm run release -- --skip-build [--upload-only]
 *                                -> derlemeyi atlar (dosyalar zaten release/ icindeyse)
 *   npm run release -- --repo alihajiyev/VideoForge
 *
 * Yaptigi isler:
 *  1) package.json surumunu yukseltir
 *  2) uygulamayi derler (vite + electron-builder -> release/*.exe)
 *  3) surum commit'ini ve vX.Y.Z etiketini GitHub'a gonderir
 *  4) kurulum dosyalarini GitHub surumu (release) olarak yukler
 *
 * Ayarlar sayfasindaki "Guncellemeleri kontrol et" butonu tam olarak bu
 * surumleri okur: depodaki en son release > uygulama surumu ise guncelleme gorunur.
 */
import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)))
const pkgPath = path.join(root, 'package.json')
const DEFAULT_REPO = 'alihajiyev/VideoForge'

const argv = process.argv.slice(2)
const dry = argv.includes('--dry')
const noBump = argv.includes('--no-bump')
const skipBuild = argv.includes('--skip-build') || argv.includes('--upload-only')
const uploadOnly = argv.includes('--upload-only')
const repoArgIndex = argv.indexOf('--repo')
const repo = (repoArgIndex >= 0 ? argv[repoArgIndex + 1] : '') || process.env.VF_UPDATE_REPO || DEFAULT_REPO
const BUMPS = ['patch', 'minor', 'major']
const bump = BUMPS.find((b) => argv.includes(b)) ?? 'patch'

/**
 * Komut calistirir. ONEMLI: git/gh icin shell KULLANILMAZ - Windows'ta kabuk,
 * icinde bosluk gecen argumanlari (ornegin commit mesaji) yanlis boler.
 * npm icin ise Windows'ta npm.cmd oldugu icin kabuk gerekir.
 */
function run(command, args, label, shell = false) {
  console.log(`\n> ${label ?? `${command} ${args.join(' ')}`}`)
  execFileSync(command, args, { cwd: root, stdio: 'inherit', shell })
}

function capture(command, args) {
  try {
    return execFileSync(command, args, { cwd: root, encoding: 'utf8' }).trim()
  } catch {
    return ''
  }
}

/** gh komutu basarili oldu mu (cikti dondurmeden). */
function ghOk(args) {
  try {
    execFileSync('gh', args, { cwd: root, stdio: 'ignore' })
    return true
  } catch {
    return false
  }
}

function nextVersion(current, kind) {
  const [major = 0, minor = 0, patch = 0] = String(current)
    .trim()
    .split('-')[0]
    .split('.')
    .map((n) => Number.parseInt(n, 10) || 0)
  if (kind === 'major') return `${major + 1}.0.0`
  if (kind === 'minor') return `${major}.${minor + 1}.0`
  return `${major}.${minor}.${patch + 1}`
}

const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf8'))
const version = noBump ? pkg.version : nextVersion(pkg.version, bump)
const tag = `v${version}`

console.log('=============================================')
console.log(`  VideoForge surum yayinlama`)
console.log(`  mevcut surum : ${pkg.version}`)
console.log(`  yeni surum   : ${version}  (${noBump ? 'yukseltilmedi' : bump})`)
console.log(`  yayin deposu : ${repo}`)
console.log(`  mod          : ${dry ? 'DENEME (yayinlanmaz)' : 'YAYIN'}`)
console.log('=============================================')

if (!dry) {
  if (noBump) {
    console.log(`\n[1/4] Surum degistirilmedi (${version})`)
  } else {
    pkg.version = version
    fs.writeFileSync(pkgPath, `${JSON.stringify(pkg, null, 2)}\n`, 'utf8')
    console.log(`\n[1/4] package.json surumu ${version} olarak guncellendi`)
  }
} else {
  console.log('\n[1/4] DENEME: package.json degistirilmedi')
}

if (skipBuild) {
  console.log('\n[2/4] Derleme atlandi (--skip-build): release/ klasorundeki dosyalar kullanilir')
} else {
  console.log('\n[2/4] Uygulama derleniyor (vite + electron-builder)...')
  run('npm', ['run', 'package'], 'npm run package', true)
}

const releaseDir = path.join(root, 'release')
const assets = fs.existsSync(releaseDir)
  ? fs
      .readdirSync(releaseDir)
      .filter((f) => f.toLowerCase().endsWith('.exe'))
      .map((f) => path.join(releaseDir, f))
  : []

console.log(`\n[2/4] Uretilen dosyalar:`)
for (const a of assets) console.log(`   - ${path.basename(a)} (${(fs.statSync(a).size / 1048576).toFixed(1)} MB)`)
if (!assets.length) {
  console.error('\nHATA: release/ klasorunde .exe bulunamadi - derleme basarisiz olmus olabilir.')
  process.exit(1)
}

if (dry) {
  console.log('\n[3/4] DENEME: git commit/tag/push yapilmadi')
  console.log('[4/4] DENEME: GitHub surumu olusturulmadi')
  console.log('\nYayinlamak icin: npm run release -- ' + bump)
  process.exit(0)
}

if (!capture('gh', ['--version'])) {
  console.error('\nHATA: GitHub CLI (gh) bulunamadi. Kur: winget install GitHub.cli')
  console.error(`Dosyalar release/ klasorunde hazir; elle yukleyebilirsin: https://github.com/${repo}/releases/new`)
  process.exit(1)
}

console.log('\n[3/4] Surum commit + etiket gonderiliyor...')
if (uploadOnly) {
  console.log('   (--upload-only: git islemleri atlandi)')
} else {
if (!noBump) {
  run('git', ['add', 'package.json'], 'git add package.json')
  run('git', ['commit', '-m', `surum ${version}`], `git commit -m "surum ${version}"`)
} else {
  console.log('   (surum yukseltilmedi: package.json commit edilmedi)')
}
const existingTag = capture('git', ['tag', '--list', tag])
if (existingTag) run('git', ['tag', '-d', tag], `git tag -d ${tag} (varsa eski etiket temizlendi)`)
run('git', ['tag', tag], `git tag ${tag}`)
const branch = capture('git', ['rev-parse', '--abbrev-ref', 'HEAD']) || 'main'
run('git', ['push', 'origin', branch], `git push origin ${branch}`)
run('git', ['push', 'origin', tag], `git push origin ${tag}`)
}

console.log('\n[4/4] GitHub surumu hazirlaniyor...')
const notes = capture('git', ['log', '--no-merges', '--pretty=- %s', '-8', 'HEAD~1..HEAD']) || `VideoForge ${version}`
const title = `VideoForge ${version}`
const exists = ghOk(['release', 'view', tag, '--repo', repo])
if (exists) {
  console.log(`   ${tag} surumu zaten var: dosyalar ve notlar guncelleniyor`)
  run('gh', ['release', 'upload', tag, ...assets, '--repo', repo, '--clobber'], `gh release upload ${tag} --clobber`)
  run('gh', ['release', 'edit', tag, '--repo', repo, '--title', title, '--notes', notes], `gh release edit ${tag}`)
} else {
  run(
    'gh',
    ['release', 'create', tag, ...assets, '--repo', repo, '--title', title, '--notes', notes],
    `gh release create ${tag} --repo ${repo}`,
  )
}

console.log('\n=============================================')
console.log(`  TAMAM: ${tag} yayinlandi -> https://github.com/${repo}/releases/tag/${tag}`)
console.log('  Uygulamadaki Ayarlar > Guncellemeleri kontrol et artik bu surumu gorur.')
console.log('=============================================\n')
