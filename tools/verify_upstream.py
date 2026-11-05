"""Проверка: встроенные zapret и tg-ws-proxy побайтово совпадают с оригиналами.

    python tools/verify_upstream.py

Скачивает оригинальные репозитории на коммитах из UPSTREAM.json и сравнивает
SHA-256 каждого файла (переводы строк CRLF/LF не учитываются — их меняет git).
"""
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def digest(p: Path) -> str:
    data = p.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def files(base: Path, exclude=()):
    if base.is_file():
        return {"": base}
    out = {}
    for p in base.rglob("*"):
        rel = p.relative_to(base).as_posix()
        if p.is_file() and not any(rel == e or rel.startswith(e + "/") for e in exclude) and "__pycache__" not in rel:
            out[rel] = p
    return out


def clone(repo: str, commit: str, dest: Path) -> None:
    subprocess.run(["git", "-c", "core.autocrlf=false", "init", "-q", str(dest)], check=True)
    subprocess.run(["git", "-C", str(dest), "fetch", "-q", "--depth", "1", repo, commit], check=True)
    subprocess.run(["git", "-C", str(dest), "-c", "core.autocrlf=false", "checkout", "-q", "FETCH_HEAD"], check=True)


def compare(local: Path, up: Path, exclude=()) -> list:
    a, b = files(local, exclude), files(up, exclude)
    problems = []
    for rel in sorted(set(a) | set(b)):
        if rel not in b:
            problems.append(f"  + лишний файл: {local / rel}")
        elif rel not in a:
            problems.append(f"  - нет файла: {local / rel}")
        elif digest(a[rel]) != digest(b[rel]):
            problems.append(f"  ≠ отличается: {local / rel}")
    return problems, len(a)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # консоль Windows по умолчанию не печатает кириллицу
    except Exception:
        pass
    cfg = json.loads((ROOT / "UPSTREAM.json").read_text(encoding="utf-8"))
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        for name, c in cfg.items():
            dest = Path(tmp) / name
            clone(c["repo"], c["commit"], dest)
            pairs = c.get("pairs") or [[c["local"], c.get("upstream", ".")]]
            total, problems = 0, []
            for local, up in pairs:
                pr, n = compare(ROOT / local, dest / up, c.get("exclude", []))
                problems += pr
                total += n
            status = "OK" if not problems else "ОТЛИЧАЕТСЯ"
            print(f"{name} {c['version']} ({c['commit'][:7]}): {total} файлов — {status}")
            for line in problems:
                print(line)
            ok &= not problems
    print("Все встроенные файлы совпадают с оригиналами." if ok else "Найдены отличия!")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
