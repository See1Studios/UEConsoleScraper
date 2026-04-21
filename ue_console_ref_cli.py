"""
Unreal Engine Console Variables / Commands Reference 스크래퍼
사용법: python ue_console_ref_cli.py [--target cvars|commands] [--version 5.6] [--lang ko] [--output out.json]
"""

import json
import argparse
import sys
import re
from pathlib import Path


DOCS_BASE = "https://dev.epicgames.com/documentation/unreal-engine"

TARGETS = {
    "cvars":    "unreal-engine-console-variables-reference",
    "commands": "unreal-engine-console-commands-reference",
}

BROWSER_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-web-security",
]

EXTRA_HEADERS = {
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}


def parse_args():
    parser = argparse.ArgumentParser(description="UE Console Reference Scraper")
    parser.add_argument("--target", default="cvars", choices=list(TARGETS.keys()),
                        help="스크래핑 대상: cvars(변수) 또는 commands(명령어) (기본값: cvars)")
    parser.add_argument("--version", default="5.6", help="엔진 버전 (기본값: 5.6)")
    parser.add_argument("--lang", default="ko", help="언어 코드 (기본값: ko)")
    parser.add_argument("--output", default=None, help="출력 파일 경로 (기본값: output_{type}_{version}_{lang}.json)")
    parser.add_argument("--dump-html", action="store_true", help="렌더링된 HTML도 덤프")
    parser.add_argument("--headed", action="store_true", help="브라우저 창 표시 (디버깅용)")
    return parser.parse_args()


def build_url(target: str, version: str, lang: str) -> str:
    slug = TARGETS[target]
    return f"{DOCS_BASE}/{slug}?application_version={version}&lang={lang}"


def scrape_with_playwright(url: str, dump_html: bool = False, headed: bool = False,
                           entry_type: str = "CVar") -> tuple[str, list[dict]]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright가 설치되어 있지 않습니다.")
        print("설치 명령어: pip install playwright && playwright install msedge")
        sys.exit(1)

    print(f"[*] 페이지 로딩 중: {url}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="msedge",
            headless=not headed,
            args=BROWSER_ARGS,
        )

        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
            locale="ko-KR",
        )

        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
        """)

        page = context.new_page()
        page.set_extra_http_headers(EXTRA_HEADERS)

        response = page.goto(url, wait_until="domcontentloaded", timeout=60000)
        print(f"[*] 응답 상태: {response.status if response else 'unknown'}")

        if response and response.status == 403:
            print("[!] 403 차단됨. 잠시 대기 후 재시도...")
            page.wait_for_timeout(3000)
            response = page.reload(wait_until="networkidle", timeout=60000)
            print(f"[*] 재시도 응답 상태: {response.status if response else 'unknown'}")

        try:
            page.wait_for_selector("table, article, main, .content", timeout=20000)
        except Exception:
            print("[!] 콘텐츠 선택자 대기 타임아웃 - 현재 상태로 진행")

        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(2000)

        html = page.content()

        if dump_html:
            html_path = Path("dump.html")
            html_path.write_text(html, encoding="utf-8")
            print(f"[*] HTML 덤프 저장: {html_path} ({len(html):,} bytes)")

        data = extract_cvars(html, entry_type)
        browser.close()

    return html, data


def extract_cvars(html: str, entry_type: str = "CVar") -> list[dict]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")

    title = soup.find("title")
    if title and ("403" in title.get_text() or "Access Denied" in title.get_text()):
        print("[!] 403 Access Denied 페이지가 반환되었습니다.")
        return []

    body_text = soup.get_text(strip=True)
    print(f"[*] 페이지 텍스트 길이: {len(body_text):,}자")
    print(f"[*] 페이지 제목: {title.get_text(strip=True) if title else 'N/A'}")

    for label, fn in [
        ("테이블", _extract_from_tables),
        ("정의 리스트", _extract_from_definition_lists),
        ("헤딩 패턴", _extract_from_headings),
        ("코드 패턴", _extract_from_code_pattern),
    ]:
        result = fn(soup)
        if result:
            print(f"[*] '{label}' 방식으로 {len(result)}개 추출")
            for item in result:
                item["type"] = entry_type
                if entry_type == "CVar" and "default" not in item:
                    item["default"] = ""
            return result

    print("[!] 자동 추출 실패. --dump-html 옵션으로 HTML을 확인하세요.")
    return []


def _extract_from_tables(soup) -> list[dict]:
    results = []
    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
        if not headers:
            continue

        name_idx    = next((i for i, h in enumerate(headers) if any(k in h for k in ["name", "variable", "cvar", "변수", "이름", "名称"])), None)
        desc_idx    = next((i for i, h in enumerate(headers) if any(k in h for k in ["desc", "description", "설명", "描述"])), None)
        type_idx    = next((i for i, h in enumerate(headers) if any(k in h for k in ["type", "타입", "형식", "类型"])), None)
        default_idx = next((i for i, h in enumerate(headers) if any(k in h for k in ["default", "디폴트", "기본값", "默认"])), None)

        col_count = len(headers)
        if name_idx is None:
            name_idx = 0
        if default_idx is None and col_count >= 3:
            default_idx = 1
        if desc_idx is None:
            desc_idx = 2 if col_count >= 3 else (1 if col_count >= 2 else None)

        group = ""
        wrapper = table.parent
        if wrapper:
            h2 = wrapper.find_previous_sibling("h2")
            if h2:
                group = h2.get_text(strip=True)

        for row in table.find_all("tr")[1:]:
            cells = row.find_all(["td", "th"])
            if not cells:
                continue
            entry = {
                "name": cells[name_idx].get_text(strip=True) if name_idx < len(cells) else "",
                "help": cells[desc_idx].get_text(strip=True) if desc_idx is not None and desc_idx < len(cells) else "",
            }
            if group:
                entry["group"] = group
            if type_idx is not None and type_idx < len(cells):
                entry["type"] = cells[type_idx].get_text(strip=True)
            if default_idx is not None and default_idx < len(cells):
                entry["default"] = cells[default_idx].get_text(strip=True)
            if entry["name"]:
                results.append(entry)

    return results


def _extract_from_definition_lists(soup) -> list[dict]:
    results = []
    for dl in soup.find_all("dl"):
        for dt, dd in zip(dl.find_all("dt"), dl.find_all("dd")):
            name = dt.get_text(strip=True)
            if name:
                results.append({"name": name, "help": dd.get_text(strip=True)})
    return results


def _extract_from_headings(soup) -> list[dict]:
    results = []
    cvar_pattern = re.compile(r'^[a-zA-Z][a-zA-Z0-9]*\.[a-zA-Z0-9._\-]+')
    for heading in soup.find_all(["h3", "h4", "h5"]):
        text = heading.get_text(strip=True)
        if cvar_pattern.match(text):
            desc_elem = heading.find_next_sibling(["p", "div", "span"])
            results.append({"name": text, "help": desc_elem.get_text(strip=True) if desc_elem else ""})
    return results


def _extract_from_code_pattern(soup) -> list[dict]:
    results = []
    cvar_pattern = re.compile(r'^[a-zA-Z][a-zA-Z0-9]*\.[a-zA-Z0-9._\-]+$')
    for code in soup.find_all(["code", "tt", "pre"]):
        text = code.get_text(strip=True)
        if cvar_pattern.match(text):
            desc = ""
            if code.parent:
                sib = code.parent.find_next_sibling()
                if sib:
                    desc = sib.get_text(strip=True)
            results.append({"name": text, "help": desc})
    return results


def save_json(data: list[dict], output_path: str):
    path = Path(output_path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[*] JSON 저장 완료: {path} ({len(data)}개 항목)")


def main():
    args = parse_args()
    url = build_url(args.target, args.version, args.lang)
    entry_type = "CVar" if args.target == "cvars" else "CCmds"
    output = args.output or f"output_{entry_type}_{args.version}_{args.lang}.json"

    _, data = scrape_with_playwright(url, dump_html=args.dump_html, headed=args.headed,
                                     entry_type=entry_type)

    if data:
        save_json(data, output)
    else:
        print("[!] 추출된 데이터가 없습니다.")
        print("    --dump-html 옵션으로 HTML을 확인한 후 파싱 전략을 추가하세요.")
        sys.exit(1)


if __name__ == "__main__":
    main()
