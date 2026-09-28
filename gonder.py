"""
VideoForge - GitHub'a gonder (push) yardimcisi.

Kullanim:
    py -3 gonder.py "yaptigim degisiklikler"
    py -3 gonder.py "gemini promptlari guncellendi" --surum      (masaustu surumunu de yayinlar)

Ne yapar:
    1) Degisen dosyalari listeler ve GIZLI anahtar sizintisi kontrolu yapar (.env, API key...)
    2) git add + commit + push ile depoyu gunceller
    3) --surum verilirse desktop/ icindeki release aracini calistirir (kurulum dosyasi yayinlar)

Anahtarlar .env dosyasinda durur ve .gitignore sayesinde depoya hic girmez;
bu betik ek olarak sizinti kontrolu yapip gerekirse gonderimi durdurur.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent

# Depoya asla girmemesi gereken dosya kaliplari
YASAKLI_YOLLAR = [
    ".env",
    "cookies.txt",
    "bot.db",
    "modal_token.txt",
]

# Anahtar benzeri metin arama kaliplari (gercek anahtarlar commit edilmesin)
ANAHTAR_KALIPLARI = [
    re.compile(r"AIza[0-9A-Za-z_\-]{30,}"),          # Google API key
    re.compile(r"AQ\.[0-9A-Za-z_\-]{20,}"),          # Gemini (yeni bicim)
    re.compile(r"sk_[0-9a-zA-Z]{30,}"),              # ElevenLabs / transcript API
    re.compile(r"ghp_[0-9A-Za-z]{30,}"),             # GitHub token
    re.compile(r"eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}"),  # JWT benzeri
]

METIN_UZANTILARI = {".py", ".ts", ".tsx", ".js", ".mjs", ".cjs", ".json", ".md", ".yml", ".yaml", ".bat", ".ps1", ".txt"}


def calistir(*komut: str, kontrol: bool = False) -> int:
    """Komutu calistirir; kontrol=True ise cikti dondurmez, sadece basari durumunu doner."""
    sonuc = subprocess.run(
        komut,
        cwd=KOK,
        shell=(sys.platform == "win32"),
        capture_output=kontrol,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return sonuc.returncode


def git(*args: str) -> str:
    sonuc = subprocess.run(
        ("git", *args),
        cwd=KOK,
        shell=(sys.platform == "win32"),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if sonuc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} basarisiz:\n{sonuc.stderr.strip()}")
    return sonuc.stdout.strip()


def sizinti_taramasi() -> list[str]:
    """Commit edilecek dosyalarda gizli anahtar arar. Bos liste = temiz."""
    bulgular: list[str] = []
    dosyalar = git("diff", "--cached", "--name-only", "--diff-filter=ACMR").splitlines()
    for ad in dosyalar:
        if not ad.strip():
            continue
        yol = KOK / ad
        if any(ad.endswith(y) or yol.name == y for y in YASAKLI_YOLLAR):
            bulgular.append(f"{ad} -> gizli dosya depoya girmemeli (.gitignore'a ekleyin)")
            continue
        if yol.suffix.lower() not in METIN_UZANTILARI or not yol.is_file():
            continue
        try:
            icerik = yol.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        # Ornek/template dosyalarinda bos deger beklenir; yine de tarariz ama
        # sadece gercek anahtar kaliplari eslesirse uyarir.
        for kalip in ANAHTAR_KALIPLARI:
            for eslesme in set(kalip.findall(icerik)):
                bulgular.append(f"{ad} -> {eslesme[:12]}... gibi gizli bir anahtar bulundu")
    return bulgular


def proje_gecerli() -> bool:
    try:
        git("rev-parse", "--is-inside-work-tree")
    except RuntimeError:
        return False
    return True


def uzak_depo_var() -> bool:
    try:
        return bool(git("remote", "get-url", "origin"))
    except RuntimeError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="VideoForge degisikliklerini GitHub'a gonderir.")
    parser.add_argument("mesaj", help="commit mesaji (ornek: 'gemini promptlari guncellendi')")
    parser.add_argument("--surum", action="store_true", help="desktop surumunu de derleyip yayinlar")
    parser.add_argument("--dal", default=None, help="gonderilecek dal (varsayilan: mevcut dal)")
    args = parser.parse_args()

    if not proje_gecerli():
        print("HATA: bu klasor bir git deposu degil.")
        return 1

    if not uzak_depo_var():
        print("HATA: uzak depo tanimli degil. Once 'git remote add origin <adres>' calistirin.")
        return 1

    degisiklikler = git("status", "--porcelain").splitlines()
    if not degisiklikler:
        print("- Gonderilecek degisiklik yok. Depo guncel.")
    else:
        print(f"- {len(degisiklikler)} dosyada degisiklik var:")
        for satir in degisiklikler[:20]:
            print(f"    {satir}")

    print("- Dosyalar hazirlaniyor (git add)...")
    if calistir("git", "add", "-A") != 0:
        print("HATA: git add basarisiz.")
        return 1

    print("- Gizli anahtar kontrolu yapiliyor...")
    bulgular = sizinti_taramasi()
    if bulgular:
        print("\nDURDURULDU - gonderilecek dosyalarda gizli bilgi olabilir:")
        for b in bulgular:
            print(f"    ! {b}")
        print("\nDuzeltmek icin: dosyadan anahtari silip .env icine tasiyin, sonra tekrar deneyin.")
        return 1
    print("    temiz (anahtar bulunamadi)")

    if degisiklikler:
        print(f"- Commit olusturuluyor: {args.mesaj}")
        if calistir("git", "commit", "-m", args.mesaj) != 0:
            print("HATA: commit basarisiz.")
            return 1

    dal = args.dal or git("rev-parse", "--abbrev-ref", "HEAD")
    print(f"- Gonderiliyor: git push origin {dal}")
    if calistir("git", "push", "origin", dal) != 0:
        print("HATA: push basarisiz (internet / yetki / uzak depo adresini kontrol edin).")
        return 1

    print("- Tamam: GitHub'daki dosyalar yenilendi.")
    uzak = git("remote", "get-url", "origin")
    if "github.com" in uzak:
        sayfa = uzak.removesuffix(".git")
        if sayfa.startswith("git@github.com:"):
            sayfa = "https://github.com/" + sayfa.split("git@github.com:", 1)[1]
        print(f"  {sayfa}")
    else:
        print(f"  uzak depo: {uzak}")

    if args.surum:
        print("\n- Masaustu surumu yayinlaniyor (npm run release)...")
        desktop = KOK / "desktop"
        sonuc = subprocess.run(("npm", "run", "release"), cwd=desktop, shell=(sys.platform == "win32"))
        return sonuc.returncode

    return 0


if __name__ == "__main__":
    sys.exit(main())
