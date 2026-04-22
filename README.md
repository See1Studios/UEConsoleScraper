# UEConsoleScraper

Unreal Engine 공식 문서에서 콘솔 변수(Console Variables)와 콘솔 명령어(Console Commands) 레퍼런스를 JSON으로 수집하는 도구입니다.

- 엔진 버전: 4.27 ~ 5.7
- 지원 언어: 한국어(`ko`) / English(`en`) / 中文(`zh-CN`)

## 출력 형식

### 콘솔 변수 (`output_CVar_*.json`)
```json
{
  "name": "a.AnimNode.AimOffsetLookAt.Enable",
  "help": "LookAt AimOffset을 활성화/비활성화합니다.",
  "group": "애니메이션",
  "default": "1",
  "type": "CVar"
}
```

### 콘솔 명령어 (`output_CCmds_*.json`)
```json
{
  "name": "abtest",
  "help": "단순 변수 두 값을 비교하거나 AB 테스트 시스템을 제어합니다.",
  "group": "AB 테스트",
  "type": "CCmds"
}
```

## 요구사항

- Python 3.10+
- Microsoft Edge (Windows에 기본 설치)

## 설치

```bash
# 저장소 클론
git clone https://github.com/your-username/UEConsoleScraper.git
cd UEConsoleScraper

# 가상환경 생성 및 패키지 설치
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\playwright install msedge
```

또는 `setup.bat`을 더블클릭하면 위 과정을 자동으로 실행합니다.

## 사용법

### GUI (`run_scraper.vbs` 더블클릭)

콘솔 창 없이 GUI가 바로 실행됩니다.

```
run_scraper.vbs
```

| 탭 | 기능 |
|----|------|
| 스크래핑 | 대상·버전·언어 선택 후 JSON 저장 |
| 환경 점검 | 패키지 설치 상태 확인 및 자동 설치 |

### CLI

```bash
.venv\Scripts\activate

# 콘솔 변수 수집 (UE 5.6, 한국어) → output_CVar_5.6_ko.json
python ue_console_ref_cli.py --target cvars --version 5.6 --lang ko

# 콘솔 명령어 수집 (영어) → output_CCmds_5.6_en.json
python ue_console_ref_cli.py --target commands --lang en

# 옵션
python ue_console_ref_cli.py --help
```

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--target` | `cvars` | `cvars` 또는 `commands` |
| `--version` | `5.6` | `4.27` ~ `5.7` |
| `--lang` | `ko` | `ko` / `en` / `zh-CN` |
| `--output` | 자동 생성 | 출력 파일 경로 |
| `--dump-html` | — | 렌더링된 HTML 덤프 저장 |
| `--headed` | — | 브라우저 창 표시 (디버깅) |
