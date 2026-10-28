"""Fayl menejeri yadrosi: ko'rish, o'qish, yozish, ZIP, savat, nusxa/ko'chirish, yuklash.
Yo'l tokenlari (md5) orqali ishlaydi — brauzer va bot uchun bir xil."""
import hashlib, os, pwd, shutil, time, uuid, zipfile
from pathlib import Path

from config import APPS, TRASH, TMP

PATHS: dict[str, str] = {}
TRASHED: dict[str, tuple[str, str]] = {}
SKIP_ZIP = {".venv", "venv", "node_modules", ".git", "__pycache__"}
SELF = Path(__file__).resolve().parent
DENY = {"/", "/etc", "/usr", "/bin", "/sbin", "/lib", "/lib64", "/boot", "/var", "/home", "/root",
        "/proc", "/sys", "/dev", "/run", "/opt", "/srv", "/tmp", "/mnt", "/media"}
MAX_TEXT = 400_000


def tid(p) -> str:
    s = str(p)
    k = hashlib.md5(s.encode()).hexdigest()[:10]
    PATHS[k] = s
    if len(PATHS) > 4000:
        for old in list(PATHS)[:1000]: PATHS.pop(old, None)
    return k


def P(k: str) -> Path | None:
    s = PATHS.get(k)
    return Path(s) if s else None


def hsize(n: float) -> str:
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or u == "TB":
            return f"{n:.0f}{u}" if u == "B" else f"{n:.1f}{u}"
        n /= 1024


def guard(p: Path) -> str:
    """Xavfli amal bo'lsa sababini qaytaradi, aks holda ''."""
    ap = Path(os.path.abspath(p))
    if str(ap) in DENY or ap in (APPS, TRASH):
        return "Tizim papkasi — bu amal taqiqlangan."
    if ap == SELF or ap in SELF.parents:
        return "Bu panelning o'z papkasi."
    if ap.parent == APPS and not ap.name.startswith("."):
        return "Bu ilova papkasi. «Ilovalar» bo'limidan boshqaring."
    return ""


def unique(p: Path) -> Path:
    if not p.exists() and not p.is_symlink(): return p
    i = 1
    while True:
        c = p.with_name(f"{p.stem}_{i}{p.suffix}")
        if not c.exists(): return c
        i += 1


def app_of(p: Path) -> str | None:
    try: rel = Path(os.path.abspath(p)).relative_to(APPS)
    except ValueError: return None
    return rel.parts[0] if rel.parts and not rel.parts[0].startswith(".") else None


def dir_size(p: Path) -> int:
    tot = 0
    try:
        for dp, _dns, fns in os.walk(p):
            for f in fns:
                try: tot += os.lstat(os.path.join(dp, f)).st_size
                except OSError: pass
    except OSError:
        pass
    return tot


def is_text(p: Path) -> bool:
    try:
        with open(p, "rb") as f:
            return b"\0" not in f.read(4096)
    except OSError:
        return False


ROOTS = [("Ilovalar", "apps", APPS), ("/root", "root", Path("/root")), ("/var/log", "log", Path("/var/log")),
         ("/etc", "etc", Path("/etc")), ("/var/www", "www", Path("/var/www")), ("/", "slash", Path("/")),
         ("Savat", "trash", TRASH)]


def roots() -> list[dict]:
    return [{"key": k, "label": lab, "path": str(p), "token": tid(p), "exists": p.exists()}
            for lab, k, p in ROOTS]


def scan(p: Path):
    dirs, files = [], []
    try:
        with os.scandir(p) as it:
            for e in it:
                try: isd = e.is_dir()
                except OSError: isd = False
                (dirs if isd else files).append(e)
    except (PermissionError, FileNotFoundError, NotADirectoryError):
        return None
    key = lambda e: e.name.lower()
    return sorted(dirs, key=key), sorted(files, key=key)


def listdir(p: Path, page: int = 0, per: int = 200) -> dict:
    parent = str(p.parent) if str(p) != "/" else None
    out = {"path": str(p), "token": tid(p), "parent": tid(p.parent) if parent else None,
           "name": p.name or "/", "items": [], "error": ""}
    try:
        st = p.lstat()
        out.update(mode=oct(st.st_mode & 0o777)[2:], mtime=int(st.st_mtime),
                   owner=(pwd.getpwuid(st.st_uid).pw_name if st.st_uid is not None else ""))
    except OSError as e:
        out["error"] = str(e)
        return out
    sc = scan(p)
    if sc is None:
        out["error"] = "Ochib bo'lmadi (ruxsat yo'q)"
        return out
    dirs, files = sc
    allx = dirs + files
    out["dirs"], out["files"] = len(dirs), len(files)
    total_pages = max(1, -(-len(allx) // per))
    page = min(max(page, 0), total_pages - 1)
    out["page"], out["pages"] = page, total_pages
    for e in allx[page * per:(page + 1) * per]:
        try: isd = e.is_dir()
        except OSError: isd = False
        it = {"name": e.name, "dir": isd, "token": tid(e.path)}
        try:
            st = e.stat()
            it.update(size=st.st_size, size_h=hsize(st.st_size), mtime=int(st.st_mtime),
                      mode=oct(st.st_mode & 0o777)[2:])
        except OSError:
            pass
        out["items"].append(it)
    return out


def stat(p: Path) -> dict:
    st = p.lstat()
    try: owner = pwd.getpwuid(st.st_uid).pw_name
    except KeyError: owner = str(st.st_uid)
    return {"path": str(p), "token": tid(p), "parent": tid(p.parent), "name": p.name or "/",
            "dir": p.is_dir(), "size": st.st_size, "size_h": hsize(st.st_size),
            "mode": oct(st.st_mode & 0o777)[2:], "owner": owner,
            "mtime": int(st.st_mtime), "link": p.is_symlink(), "app": app_of(p) or ""}


def read_text(p: Path, limit: int = 120_000) -> dict:
    sz = p.stat().st_size
    if sz > 5_000_000:
        raise ValueError("Fayl juda katta (5MB dan ortiq) — yuklab oling.")
    if not is_text(p):
        raise ValueError("Bu ikkilik (binary) fayl — matn sifatida ochib bo'lmaydi.")
    txt = p.read_text(errors="replace")
    return {"text": txt[:limit], "size": sz, "truncated": len(txt) > limit}


def write_text(p: Path, text: str):
    if (p.exists() and not p.is_file()) or not p.parent.is_dir():
        raise ValueError("Fayl yo'li yaroqsiz.")
    if p.exists():
        copy_to_trash(p, suffix=".replaced")
    p.write_text(text)


def tail(p: Path, n: int = 6000) -> str:
    with open(p, "rb") as f:
        f.seek(0, 2); size = f.tell(); f.seek(max(0, size - n))
        return f.read().decode(errors="replace")


def to_trash(p: Path) -> Path:
    TRASH.mkdir(parents=True, exist_ok=True)
    dst = TRASH / f"{time.strftime('%Y%m%d-%H%M%S')}-{p.name}"
    shutil.move(str(p), str(dst))
    return dst


def copy_to_trash(p: Path, suffix: str = "") -> Path:
    TRASH.mkdir(parents=True, exist_ok=True)
    dst = TRASH / f"{time.strftime('%Y%m%d-%H%M%S')}-{p.name}{suffix}"
    shutil.copy2(p, dst)
    return dst


def paste(mode: str, src: Path, dstdir: Path) -> Path:
    dst = unique(dstdir / src.name)
    if src.is_dir():
        s, d = src.resolve(), dstdir.resolve()
        if s == d or s in d.parents: raise ValueError("Papkani o'zining ichiga qo'yib bo'lmaydi")
        if mode == "copy": shutil.copytree(src, dst, symlinks=True)
        else: shutil.move(str(src), str(dst))
    else:
        if mode == "copy": shutil.copy2(src, dst)
        else: shutil.move(str(src), str(dst))
    return dst


def zip_dir(src: Path, out: Path):
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        if src.is_file():
            z.write(src, src.name)
            return
        for dp, dns, fns in os.walk(src):
            dns[:] = [d for d in dns if d not in SKIP_ZIP]
            for f in fns:
                fp = Path(dp) / f
                try: z.write(fp, fp.relative_to(src.parent))
                except (OSError, ValueError): pass


def save_upload(dest_dir: Path, filename: str, blob: bytes) -> Path:
    name = os.path.basename((filename or "file").replace("\0", "")) or "file"
    dst = unique(dest_dir / name)
    dst.write_bytes(blob)
    return dst


def purge_trash(days: int = 7):
    now = time.time()
    for x in TRASH.glob("*"):
        try: ts = time.mktime(time.strptime(x.name[:15], "%Y%m%d-%H%M%S"))
        except ValueError: continue
        if now - ts > days * 86400:
            shutil.rmtree(x, ignore_errors=True) if x.is_dir() else x.unlink(missing_ok=True)


def purge_tmp(hours: int = 24):
    now = time.time()
    for x in TMP.glob("*"):
        try:
            if now - x.stat().st_mtime > hours * 3600:
                shutil.rmtree(x, ignore_errors=True) if x.is_dir() else x.unlink(missing_ok=True)
        except OSError:
            pass
