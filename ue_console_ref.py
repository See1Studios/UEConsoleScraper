"""
UE Console Reference Scraper - GUI
단일 파일 실행: python scraper_gui.py
"""

import sys
from pathlib import Path

# 스크립트 옆 .venv의 site-packages를 sys.path에 추가 (어떤 Python으로 실행해도 동작)
_script_dir = Path(__file__).resolve().parent
_venv_site = _script_dir / ".venv" / "Lib" / "site-packages"
if _venv_site.exists() and str(_venv_site) not in sys.path:
    sys.path.insert(0, str(_venv_site))

import json
import os
import re
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext


DOCS_BASE = "https://dev.epicgames.com/documentation/unreal-engine"

TARGETS = {
    "콘솔 변수 (Console Variables)": "unreal-engine-console-variables-reference",
    "콘솔 명령어 (Console Commands)": "unreal-engine-console-commands-reference",
}

ENGINE_VERSIONS = ["4.27", "5.0", "5.1", "5.2", "5.3", "5.4", "5.5", "5.6", "5.7"]

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

VENV_DIR        = _script_dir / ".venv"
VENV_PYTHON     = VENV_DIR / "Scripts" / "python.exe"
VENV_PIP        = VENV_DIR / "Scripts" / "pip.exe"
VENV_PLAYWRIGHT = VENV_DIR / "Scripts" / "playwright.exe"
REQUIREMENTS    = _script_dir / "requirements.txt"

EDGE_PATHS = [
    Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
    Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe"),
]


# ── 환경 점검 로직 ────────────────────────────────────────────────────────────

def check_env() -> list[dict]:
    """각 구성 요소의 설치 상태를 반환."""
    results = []

    # Python
    results.append({
        "name": "Python",
        "ok": True,
        "detail": f"{sys.version.split()[0]}  ({sys.executable})",
    })

    # 가상환경
    venv_ok = VENV_PYTHON.exists()
    results.append({
        "name": "가상환경 (.venv)",
        "ok": venv_ok,
        "detail": str(VENV_DIR) if venv_ok else "없음 — 설치 필요",
    })

    # Python 패키지
    for pkg, import_name in [
        ("playwright",     "playwright"),
        ("beautifulsoup4", "bs4"),
        ("lxml",           "lxml"),
    ]:
        try:
            mod = __import__(import_name)
            ver = getattr(mod, "__version__", "?")
            results.append({"name": pkg, "ok": True, "detail": f"v{ver}"})
        except ImportError:
            results.append({"name": pkg, "ok": False, "detail": "미설치"})

    # Edge 브라우저
    edge_path = next((p for p in EDGE_PATHS if p.exists()), None)
    results.append({
        "name": "Edge 브라우저",
        "ok": edge_path is not None,
        "detail": str(edge_path) if edge_path else "미설치 (Windows 설정에서 Edge 설치 필요)",
    })

    return results



# ── 스크래핑 로직 ────────────────────────────────────────────────────────────

def build_url(slug: str, version: str, lang: str) -> str:
    return f"{DOCS_BASE}/{slug}?application_version={version}&lang={lang}"


def scrape(url: str, dump_html: bool, headed: bool, log, entry_type: str = "variable") -> list[dict]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log("[오류] playwright가 설치되어 있지 않습니다. 환경 점검 탭에서 설치하세요.")
        return []

    log(f"[*] 페이지 로딩 중...\n    {url}")

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="msedge", headless=not headed, args=BROWSER_ARGS)
        except Exception as e:
            log(f"[오류] Edge 브라우저를 시작할 수 없습니다: {e}")
            log("      시스템에 Edge가 없다면 '환경 점검' 탭에서 전체 설치를 실행하세요.")
            return []

        try:
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
            log(f"[*] 응답 상태: {response.status if response else 'unknown'}")

            if response and response.status == 403:
                log("[!] 403 차단됨. 잠시 대기 후 재시도...")
                page.wait_for_timeout(3000)
                response = page.reload(wait_until="networkidle", timeout=60000)
                log(f"[*] 재시도 응답 상태: {response.status if response else 'unknown'}")

            try:
                page.wait_for_selector("table, article, main, .content", timeout=20000)
            except Exception:
                log("[!] 콘텐츠 선택자 대기 타임아웃 - 현재 상태로 진행")

            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(2000)

            html = page.content()

            if dump_html:
                html_path = _script_dir / "dump.html"
                html_path.write_text(html, encoding="utf-8")
                log(f"[*] HTML 덤프 저장: {html_path} ({len(html):,} bytes)")

            data = extract(html, log, entry_type)
        finally:
            try:
                browser.close()
            except Exception:
                pass

    return data


def extract(html: str, log, entry_type: str = "variable") -> list[dict]:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        log("[오류] beautifulsoup4가 설치되어 있지 않습니다. 환경 점검 탭에서 설치하세요.")
        return []

    soup = BeautifulSoup(html, "lxml")
    title = soup.find("title")
    title_text = title.get_text(strip=True) if title else "N/A"
    body_text = soup.get_text(strip=True)
    log(f"[*] 페이지 제목: {title_text}")
    log(f"[*] 텍스트 길이: {len(body_text):,}자")

    if "403" in title_text or "Access Denied" in title_text:
        log("[!] 403 Access Denied 페이지입니다.")
        return []

    for label, fn in [
        ("테이블", _from_tables),
        ("정의 리스트", _from_definition_lists),
        ("헤딩 패턴", _from_headings),
        ("코드 패턴", _from_code_pattern),
    ]:
        result = fn(soup)
        if result:
            log(f"[*] '{label}' 방식으로 {len(result)}개 추출")
            for item in result:
                item["type"] = entry_type
                if entry_type == "CVar" and "default" not in item:
                    item["default"] = ""
            return result

    log("[!] 자동 추출 실패. 'HTML 덤프' 옵션 후 구조를 확인하세요.")
    return []


def _from_tables(soup) -> list[dict]:
    results = []
    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
        if not headers:
            continue
        name_idx    = next((i for i, h in enumerate(headers) if any(k in h for k in ["name", "variable", "cvar", "이름", "변수", "名称"])), None)
        desc_idx    = next((i for i, h in enumerate(headers) if any(k in h for k in ["desc", "description", "설명", "描述"])), None)
        type_idx    = next((i for i, h in enumerate(headers) if any(k in h for k in ["type", "타입", "형식", "类型"])), None)
        default_idx = next((i for i, h in enumerate(headers) if any(k in h for k in ["default", "디폴트", "기본값", "默认"])), None)

        # 키워드 매칭 실패 시 알려진 컬럼 순서로 폴백: [이름(0), 디폴트 값(1), 설명(2)]
        col_count = len(headers)
        if name_idx is None:
            name_idx = 0
        if default_idx is None and col_count >= 3:
            default_idx = 1
        if desc_idx is None:
            desc_idx = 2 if col_count >= 3 else (1 if col_count >= 2 else None)

        # 그룹 헤더: 테이블 래퍼(div.table-responsive)의 이전 h2 형제
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


def _from_definition_lists(soup) -> list[dict]:
    results = []
    for dl in soup.find_all("dl"):
        for dt, dd in zip(dl.find_all("dt"), dl.find_all("dd")):
            name = dt.get_text(strip=True)
            if name:
                results.append({"name": name, "help": dd.get_text(strip=True)})
    return results


def _from_headings(soup) -> list[dict]:
    results = []
    pattern = re.compile(r'^[a-zA-Z][a-zA-Z0-9]*\.[a-zA-Z0-9._\-]+')
    for tag in soup.find_all(["h3", "h4", "h5"]):
        text = tag.get_text(strip=True)
        if pattern.match(text):
            sib = tag.find_next_sibling(["p", "div", "span"])
            results.append({"name": text, "help": sib.get_text(strip=True) if sib else ""})
    return results


def _from_code_pattern(soup) -> list[dict]:
    results = []
    pattern = re.compile(r'^[a-zA-Z][a-zA-Z0-9]*\.[a-zA-Z0-9._\-]+$')
    for code in soup.find_all(["code", "tt", "pre"]):
        text = code.get_text(strip=True)
        if pattern.match(text):
            desc = ""
            if code.parent:
                sib = code.parent.find_next_sibling()
                if sib:
                    desc = sib.get_text(strip=True)
            results.append({"name": text, "help": desc})
    return results


# ── GUI ──────────────────────────────────────────────────────────────────────

LOG_COLORS = {
    "error": "#f48771",
    "ok":    "#89d185",
    "info":  "#9cdcfe",
    "dim":   "#808080",
}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("UE Console Reference Scraper")
        self.resizable(True, True)
        self.minsize(660, 580)
        self._scrape_running = False
        self._setup_running  = False
        self._build_ui()

    # ── UI 구성 ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self._tab_scrape = ttk.Frame(notebook)
        self._tab_env    = ttk.Frame(notebook)
        notebook.add(self._tab_scrape, text="  스크래핑  ")
        notebook.add(self._tab_env,    text="  환경 점검  ")

        self._build_scrape_tab(self._tab_scrape)
        self._build_env_tab(self._tab_env)

    # ── 스크래핑 탭 ──────────────────────────────────────────────────────────

    def _build_scrape_tab(self, parent):
        pad = {"padx": 8, "pady": 4}

        frame = ttk.LabelFrame(parent, text="설정", padding=10)
        frame.pack(fill="x", padx=8, pady=(10, 4))
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="대상:").grid(row=0, column=0, sticky="w", **pad)
        self.target_var = tk.StringVar(value=list(TARGETS.keys())[0])
        self.target_var.trace_add("write", lambda *_: self._on_target_change())
        ttk.Combobox(frame, textvariable=self.target_var,
                     values=list(TARGETS.keys()), state="readonly", width=40
                     ).grid(row=0, column=1, columnspan=2, sticky="ew", **pad)

        ttk.Label(frame, text="엔진 버전:").grid(row=1, column=0, sticky="w", **pad)
        self.version_var = tk.StringVar(value="5.6")
        self.version_var.trace_add("write", lambda *_: self._on_target_change())
        ttk.Combobox(frame, textvariable=self.version_var,
                     values=ENGINE_VERSIONS, state="readonly", width=10
                     ).grid(row=1, column=1, sticky="w", **pad)

        ttk.Label(frame, text="언어:").grid(row=2, column=0, sticky="w", **pad)
        self.lang_var = tk.StringVar(value="ko")
        self.lang_var.trace_add("write", lambda *_: self._on_target_change())
        lang_frame = ttk.Frame(frame)
        lang_frame.grid(row=2, column=1, columnspan=2, sticky="w", **pad)
        for code, label in [("ko", "한국어"), ("en", "English"), ("zh-CN", "中文")]:
            ttk.Radiobutton(lang_frame, text=label, variable=self.lang_var, value=code
                            ).pack(side="left", padx=4)

        ttk.Label(frame, text="저장 경로:").grid(row=3, column=0, sticky="w", **pad)
        self.output_var = tk.StringVar(value=str(_script_dir / "output_CVar_5.6_ko.json"))
        ttk.Entry(frame, textvariable=self.output_var).grid(row=3, column=1, sticky="ew", **pad)
        ttk.Button(frame, text="찾아보기", command=self._browse_output
                   ).grid(row=3, column=2, **pad)

        opt_frame = ttk.Frame(frame)
        opt_frame.grid(row=4, column=0, columnspan=3, sticky="w", **pad)
        self.dump_html_var = tk.BooleanVar(value=False)
        self.headed_var    = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt_frame, text="HTML 덤프 저장", variable=self.dump_html_var).pack(side="left", padx=4)
        ttk.Checkbutton(opt_frame, text="브라우저 창 표시 (디버깅)", variable=self.headed_var).pack(side="left", padx=4)

        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill="x", padx=8, pady=4)
        self.run_btn = ttk.Button(btn_frame, text="▶  스크래핑 시작", command=self._start_scrape)
        self.run_btn.pack(side="left")
        self.scrape_progress = ttk.Progressbar(btn_frame, mode="indeterminate", length=180)
        self.scrape_progress.pack(side="left", padx=10)
        self.scrape_status = ttk.Label(btn_frame, text="대기 중")
        self.scrape_status.pack(side="left")

        self.scrape_log = self._make_log(parent)

    # ── 환경 점검 탭 ─────────────────────────────────────────────────────────

    def _build_env_tab(self, parent):
        # 상태 테이블
        status_frame = ttk.LabelFrame(parent, text="구성 요소 상태", padding=10)
        status_frame.pack(fill="x", padx=8, pady=(10, 4))

        headers = ["구성 요소", "상태", "버전 / 경로"]
        col_widths = [160, 60, 340]
        for col, (h, w) in enumerate(zip(headers, col_widths)):
            ttk.Label(status_frame, text=h, font=("", 9, "bold"), width=w//8
                      ).grid(row=0, column=col, sticky="w", padx=6, pady=2)
        ttk.Separator(status_frame, orient="horizontal").grid(
            row=1, column=0, columnspan=3, sticky="ew", pady=4)

        COMPONENTS = ["Python", "가상환경 (.venv)", "playwright", "beautifulsoup4", "lxml", "Edge 브라우저"]
        self._env_status_vars  = {}
        self._env_detail_vars  = {}

        for i, name in enumerate(COMPONENTS, start=2):
            ttk.Label(status_frame, text=name).grid(row=i, column=0, sticky="w", padx=6, pady=3)
            sv = tk.StringVar(value="—")
            dv = tk.StringVar(value="")
            self._env_status_vars[name] = sv
            self._env_detail_vars[name] = dv
            ttk.Label(status_frame, textvariable=sv, width=8).grid(row=i, column=1, sticky="w", padx=6)
            ttk.Label(status_frame, textvariable=dv, foreground="#808080").grid(row=i, column=2, sticky="w", padx=6)

        # 버튼
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill="x", padx=8, pady=6)
        ttk.Button(btn_frame, text="🔍  점검 실행", command=self._run_check).pack(side="left", padx=4)
        self.setup_btn = ttk.Button(btn_frame, text="⚙  전체 설치 / 업데이트", command=self._run_setup)
        self.setup_btn.pack(side="left", padx=4)
        self.setup_progress = ttk.Progressbar(btn_frame, mode="indeterminate", length=160)
        self.setup_progress.pack(side="left", padx=10)
        self.setup_status = ttk.Label(btn_frame, text="")
        self.setup_status.pack(side="left")

        self.env_log = self._make_log(parent)

    # ── 공통 위젯 ────────────────────────────────────────────────────────────

    def _make_log(self, parent) -> scrolledtext.ScrolledText:
        frame = ttk.LabelFrame(parent, text="로그", padding=6)
        frame.pack(fill="both", expand=True, padx=8, pady=(4, 10))
        box = scrolledtext.ScrolledText(
            frame, state="disabled", height=10,
            font=("Consolas", 9), bg="#1e1e1e", fg="#d4d4d4",
        )
        box.pack(fill="both", expand=True)
        for tag, color in LOG_COLORS.items():
            box.tag_config(tag, foreground=color)
        return box

    def _log_to(self, box: scrolledtext.ScrolledText, msg: str):
        tag = ("error" if any(k in msg for k in ("[오류]", "[!]")) else
               "ok"    if any(k in msg for k in ("완료", "저장", "✅", "OK")) else
               "dim"   if msg.startswith("  ") else "info")
        box.config(state="normal")
        box.insert("end", msg + "\n", tag)
        box.see("end")
        box.config(state="disabled")

    def _clear_log(self, box: scrolledtext.ScrolledText):
        box.config(state="normal")
        box.delete("1.0", "end")
        box.config(state="disabled")

    # ── 스크래핑 동작 ────────────────────────────────────────────────────────

    def _on_target_change(self):
        entry_type = "CVar" if "Variables" in self.target_var.get() else "CCmds"
        version    = self.version_var.get().strip()
        lang       = self.lang_var.get().strip()
        self.output_var.set(str(_script_dir / f"output_{entry_type}_{version}_{lang}.json"))

    def _browse_output(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON 파일", "*.json"), ("모든 파일", "*.*")],
        )
        if path:
            self.output_var.set(path)

    def _start_scrape(self):
        if self._scrape_running:
            return
        self._scrape_running = True
        self.run_btn.config(state="disabled")
        self.scrape_progress.start(10)
        self.scrape_status.config(text="실행 중...")
        self._clear_log(self.scrape_log)

        target_label = self.target_var.get()
        slug       = TARGETS[target_label]
        entry_type = "CVar" if "Variables" in target_label else "CCmds"
        version    = self.version_var.get().strip()
        lang       = self.lang_var.get().strip()
        output     = self.output_var.get().strip()
        url        = build_url(slug, version, lang)

        def worker():
            try:
                data = scrape(url, self.dump_html_var.get(), self.headed_var.get(),
                              log=lambda m: self.after(0, lambda m=m: self._log_to(self.scrape_log, m)),
                              entry_type=entry_type)
                if data:
                    path = Path(output)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    self.after(0, lambda: self._log_to(self.scrape_log,
                                                       f"[완료] JSON 저장: {path} ({len(data):,}개 항목)"))
                else:
                    self.after(0, lambda: self._log_to(self.scrape_log, "[!] 추출된 데이터가 없습니다."))
            except Exception as e:
                self.after(0, lambda: self._log_to(self.scrape_log, f"[오류] {e}"))
            finally:
                self.after(0, self._done_scrape)

        threading.Thread(target=worker, daemon=True).start()

    def _done_scrape(self):
        self._scrape_running = False
        self.run_btn.config(state="normal")
        self.scrape_progress.stop()
        self.scrape_status.config(text="완료")

    # ── 환경 점검 동작 ───────────────────────────────────────────────────────

    def _run_check(self):
        self._clear_log(self.env_log)
        self._log_to(self.env_log, "[*] 환경 점검 중...")

        def worker():
            results = check_env()
            for r in results:
                icon   = "✅" if r["ok"] else "❌"
                status = "OK" if r["ok"] else "미설치"
                self.after(0, lambda r=r, icon=icon, status=status: (
                    self._env_status_vars[r["name"]].set(f"{icon} {status}"),
                    self._env_detail_vars[r["name"]].set(r["detail"]),
                    self._log_to(self.env_log, f"  {icon} {r['name']:<22} {r['detail']}"),
                ))
            all_ok = all(r["ok"] for r in results)
            msg = "[완료] 모든 구성 요소가 정상입니다." if all_ok else "[!] 일부 구성 요소가 설치되지 않았습니다. '전체 설치'를 실행하세요."
            self.after(0, lambda: self._log_to(self.env_log, msg))

        threading.Thread(target=worker, daemon=True).start()

    def _run_setup(self):
        if self._setup_running:
            return
        self._setup_running = True
        self.setup_btn.config(state="disabled")
        self.setup_progress.start(10)
        self.setup_status.config(text="설치 중...")
        self._clear_log(self.env_log)

        def worker():
            log = lambda m: self.after(0, lambda m=m: self._log_to(self.env_log, m))
            try:
                # 1. venv 생성
                if not VENV_PYTHON.exists():
                    log("[*] 가상환경 생성 중...")
                    self._run_cmd([sys.executable, "-m", "venv", str(VENV_DIR)], log)
                else:
                    log("[*] 가상환경 이미 존재 — 건너뜀")

                # 2. pip install
                log("[*] 패키지 설치 중 (playwright, beautifulsoup4, lxml)...")
                self._run_cmd([str(VENV_PIP), "install", "-r", str(REQUIREMENTS)], log)

                # 3. playwright msedge 드라이버 설치 (시스템 Edge가 있으면 건너뜀)
                edge_path = next((p for p in EDGE_PATHS if p.exists()), None)
                if edge_path:
                    log(f"[*] 시스템 Edge 감지: {edge_path}")
                    log("[*] Playwright Edge 다운로드를 건너뜁니다.")
                else:
                    log("[*] Edge 드라이버 설치 중...")
                    self._run_cmd([str(VENV_PLAYWRIGHT), "install", "msedge"], log)

                log("[완료] 설치가 완료되었습니다. 점검 실행으로 상태를 확인하세요.")
            except Exception as e:
                log(f"[오류] {e}")
            finally:
                self.after(0, self._done_setup)

        threading.Thread(target=worker, daemon=True).start()

    def _run_cmd(self, cmd: list, log):
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            creationflags=creationflags,
        )
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                log(f"  {line}")
        proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(f"명령 실패 (exit code {proc.returncode}): {' '.join(cmd)}")

    def _done_setup(self):
        self._setup_running = False
        self.setup_btn.config(state="normal")
        self.setup_progress.stop()
        self.setup_status.config(text="완료")
        self._run_check()


if __name__ == "__main__":
    app = App()
    app.mainloop()
