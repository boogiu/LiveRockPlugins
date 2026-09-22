#!/usr/bin/env python3
"""OpenAlex API로 논문 후보를 탐색한다. 브라우저 대신 코드로 검색한다."""
import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

API_URL = "https://api.openalex.org/works"


def reconstruct_abstract(inverted_index):
    if not inverted_index:
        return ""
    positions = {}
    for word, idxs in inverted_index.items():
        for i in idxs:
            positions[i] = word
    return " ".join(positions[i] for i in sorted(positions))


def load_trusted_list(path):
    entries = []
    if not path:
        return entries
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            name = parts[0].lstrip("-* ").strip()
            domain = parts[1].strip() if len(parts) > 1 else ""
            if name:
                entries.append((name.lower(), domain.lower()))
    return entries


def is_trusted(venue, url, trusted_entries):
    venue_l = (venue or "").lower()
    url_l = (url or "").lower()
    for name, domain in trusted_entries:
        if name and name in venue_l:
            return True
        if domain and domain in url_l:
            return True
    return False


def search(query, per_page, year_from, year_to, mailto):
    params = {"search": query, "per_page": str(per_page)}
    filters = []
    if year_from:
        filters.append(f"from_publication_date:{year_from}-01-01")
    if year_to:
        filters.append(f"to_publication_date:{year_to}-12-31")
    if filters:
        params["filter"] = ",".join(filters)
    if mailto:
        params["mailto"] = mailto
    url = API_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "liverock-toolkit/literature-analysis"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("results", [])


def extract_row(work, trusted_entries):
    title = work.get("display_name") or ""
    year = work.get("publication_year") or ""
    doi = work.get("doi") or ""
    primary = work.get("primary_location") or {}
    source = primary.get("source") or {}
    venue = source.get("display_name") or ""
    landing_url = primary.get("landing_page_url") or ""
    oa = work.get("open_access") or {}
    oa_url = oa.get("oa_url") or ""
    abstract = reconstruct_abstract(work.get("abstract_inverted_index"))
    trusted = is_trusted(venue, landing_url or oa_url, trusted_entries)
    return {
        "title": title,
        "year": year,
        "venue": venue,
        "doi": doi,
        "url": landing_url,
        "oa_url": oa_url,
        "trusted": trusted,
        "abstract": abstract,
    }


def print_markdown(rows):
    print("| 신뢰 | 연도 | 제목 | 저널 | DOI | OA 링크 |")
    print("| --- | --- | --- | --- | --- | --- |")
    for r in rows:
        trust_mark = "O" if r["trusted"] else ""
        print(f"| {trust_mark} | {r['year']} | {r['title']} | {r['venue']} | {r['doi']} | {r['oa_url']} |")


def main():
    parser = argparse.ArgumentParser(description="OpenAlex 논문 탐색")
    parser.add_argument("--query", required=True)
    parser.add_argument("--per-page", type=int, default=10)
    parser.add_argument("--year-from", type=int, default=None)
    parser.add_argument("--year-to", type=int, default=None)
    parser.add_argument("--trusted-file", default=None)
    parser.add_argument("--trusted-only", action="store_true")
    parser.add_argument("--mailto", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    # Windows에서 Python은 stdout에 로캘 인코딩(한국어 환경이면 CP949)을 쓴다. 표 머리글과
    # --json 결과가 CP949 바이트로 나가면 UTF-8을 기대하는 쪽 — 에이전트 화면, 로그, 다음
    # 단계의 파싱 — 에서 전부 깨진다. 출력 자체를 UTF-8로 고정한다.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # 구버전 스트림이면 그대로 쓴다
            pass

    trusted_entries = load_trusted_list(args.trusted_file)

    try:
        works = search(args.query, args.per_page, args.year_from, args.year_to, args.mailto)
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        print(f"검색 실패: {e}", file=sys.stderr)
        sys.exit(1)

    rows = [extract_row(w, trusted_entries) for w in works]
    if args.trusted_only:
        rows = [r for r in rows if r["trusted"]]

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        print_markdown(rows)


if __name__ == "__main__":
    main()
