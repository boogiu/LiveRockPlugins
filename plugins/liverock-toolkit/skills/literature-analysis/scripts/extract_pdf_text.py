"""PDF를 쪽 표시가 붙은 텍스트 파일로 한 번만 뽑고, 절 제목이 있는 줄 번호를 색인으로 남긴다.

워커가 PDF를 통째로 대화에 붙이거나 페이지를 이미지로 여는 대신, 이 텍스트 파일에서 필요한 절만
줄 범위로 읽게 하려는 것이다. 대화에 한 번 들어온 내용은 이후 모든 응답에 다시 실려 보내지므로,
원문 전체를 붙이면 토큰이 응답 횟수만큼 곱해진다.

사용:
    python extract_pdf_text.py <PDF 파일 또는 폴더> [...] --out <출력 폴더>

출력:
    <출력 폴더>/<PDF 이름>.txt   "=== page N ===" 줄로 쪽을 나눈 본문
    <출력 폴더>/index.tsv        파일 · 쪽 수 · 글자 수 · 절 제목 줄 번호(예: Abstract:3 Experimental:88)
    <출력 폴더>/digest.md        편마다 초록·결론 앞부분(각 1,200자까지) — 1차 거르기는 이 파일 하나만 읽는다

이미 뽑은 파일은 PDF보다 새것이면 다시 뽑지 않는다. 실패해도 예외로 멈추지 않고 stderr에 남긴다.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SECTION_RE = re.compile(
    r"^\s*(?:\d+(?:\.\d+)*\.?\s*)?"
    r"(abstract|introduction|experimental(?: section| details| procedures?)?|materials and methods|methods?|"
    r"results and discussion|results|discussion|conclusions?|references|acknowledg(?:e)?ments?)\s*$",
    re.IGNORECASE,
)


def _pages_pymupdf(path: Path) -> list[str] | None:
    try:
        import pymupdf  # type: ignore
    except ImportError:
        try:
            import fitz as pymupdf  # type: ignore
        except ImportError:
            return None
    with pymupdf.open(str(path)) as doc:
        return [page.get_text() for page in doc]


def _pages_pypdf(path: Path) -> list[str] | None:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        return None
    return [page.extract_text() or "" for page in PdfReader(str(path)).pages]


def extract(path: Path) -> list[str]:
    for reader in (_pages_pymupdf, _pages_pypdf):
        pages = reader(path)
        if pages is not None:
            return pages
    raise RuntimeError("pymupdf 또는 pypdf가 필요하다 (pip install pymupdf)")


def section_index(text: str) -> str:
    marks = []
    for number, line in enumerate(text.splitlines(), start=1):
        match = SECTION_RE.match(line)
        if match:
            marks.append(f"{match.group(1).split()[0].capitalize()}:{number}")
    return " ".join(marks)


DIGEST_LIMIT = 1200


def section_excerpt(text: str, names: tuple[str, ...]) -> str:
    """names로 시작하는 절의 첫 부분을 DIGEST_LIMIT 글자까지 잘라 돌려준다. 절 제목을 못 찾으면 빈 문자열."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = SECTION_RE.match(line)
        if match and match.group(1).lower().startswith(names):
            body = []
            for following in lines[index + 1 :]:
                if SECTION_RE.match(following):
                    break
                if not following.startswith("=== page "):
                    body.append(following.strip())
                if sum(len(b) for b in body) > DIGEST_LIMIT:
                    break
            return " ".join(b for b in body if b)[:DIGEST_LIMIT]
    return ""


def digest_entry(name: str, text: str) -> str:
    abstract = section_excerpt(text, ("abstract",))
    if not abstract:  # 초록 제목이 없는 PDF는 첫 쪽 앞부분으로 대신한다
        first = text.split("=== page 2 ===")[0].replace("=== page 1 ===", "")
        abstract = " ".join(first.split())[:DIGEST_LIMIT]
    conclusion = section_excerpt(text, ("conclusion",)) or "(결론 절을 찾지 못함 — 필요하면 .txt의 끝부분을 본다)"
    return f"## {name}\n\n초록: {abstract}\n\n결론: {conclusion}\n"


def collect(inputs: list[str], recursive: bool) -> list[Path]:
    pdfs: list[Path] = []
    for item in inputs:
        path = Path(item)
        if path.is_dir():
            found = path.rglob("*") if recursive else path.iterdir()
            pdfs.extend(sorted(p for p in found if p.suffix.lower() == ".pdf"))
        elif path.suffix.lower() == ".pdf" and path.exists():
            pdfs.append(path)
        else:
            print(f"[extract_pdf_text] 건너뜀(PDF 아님 또는 없음): {item}", file=sys.stderr)
    return pdfs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("inputs", nargs="+", help="PDF 파일 또는 PDF가 든 폴더")
    parser.add_argument("--out", required=True, help="텍스트와 index.tsv를 쓸 폴더")
    parser.add_argument("--recursive", action="store_true", help="폴더의 하위 폴더까지 읽는다 (기본은 그 폴더만)")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = ["file\tpages\tchars\tsections"]
    digest = ["# 1차 거르기용 요약 — 편마다 초록·결론 앞부분만 모았다. 판정이 갈리는 편만 .txt를 범위로 읽는다.\n"]
    for pdf in collect(args.inputs, args.recursive):
        target = out / (pdf.stem + ".txt")
        try:
            if target.exists() and target.stat().st_mtime >= pdf.stat().st_mtime:
                text = target.read_text(encoding="utf-8")
                pages = text.count("=== page ")
            else:
                page_texts = extract(pdf)
                pages = len(page_texts)
                text = "".join(f"=== page {i} ===\n{t.strip()}\n" for i, t in enumerate(page_texts, start=1))
                target.write_text(text, encoding="utf-8")
            rows.append(f"{target.name}\t{pages}\t{len(text)}\t{section_index(text)}")
            digest.append(digest_entry(pdf.stem, text))
        except Exception as error:  # 한 편이 깨져도 나머지는 계속 뽑는다
            print(f"[extract_pdf_text] 실패: {pdf.name}: {error}", file=sys.stderr)
            rows.append(f"{target.name}\t0\t0\t추출 실패")
            digest.append(f"## {pdf.stem}\n\n추출 실패\n")
    (out / "index.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    (out / "digest.md").write_text("\n".join(digest), encoding="utf-8")
    print(f"{len(rows) - 1}편 → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
