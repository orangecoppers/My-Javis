# My Javis

API 키 없이 로컬에서 실행하는 개인용 저빈도 픽시 리셀 조사 음성 도구입니다.

마이크 입력은 로컬 Whisper가 전사하고, `자비스` 호출어와 제한된 한국어 명령을 규칙 기반으로
해석합니다. 공개 매물은 화면에 보이는 Chromium에서 Playwright adapter가 직접 탐색합니다.
결과 음성은 macOS `say` 명령으로 출력합니다.

## 지원 명령

```text
자비스 리더 픽시 매물 찾아줘
자비스 2번 후보 문의 초안 만들어줘
응 입력해
취소
```

자유 대화형 AI가 아니라 안전하게 범위를 제한한 오프라인 명령형 자비스입니다. 외부 API를
사용하지 않으므로 자연어 표현은 `찾아`, `검색`, `분석`, `문의`, `초안`, `승인`, `입력해`,
`취소` 키워드 중심으로 인식합니다.

## 안전 경계

- 공개 탐색 브라우저와 번개장터 로그인 브라우저를 분리합니다.
- 문의 초안은 사용자의 명시적 승인 후 입력칸까지만 채웁니다.
- 전송, 결제, 구매, 계정 변경, 외부 사이트 리다이렉트는 차단합니다.
- SQLite 가격은 체결가가 아니라 공개된 판매 희망가 관측치입니다.
- 예약 수집기는 제공하지 않습니다. 사용자가 명령했을 때만 최대 100개를 직렬 탐색합니다.

사이트 구조와 이용 정책은 바뀔 수 있습니다. 실제 사용 전 각 마켓의 최신 정책을 직접 확인하고,
adapter selector가 깨진 경우 코드를 갱신하기 전까지 자동화를 중단하세요.

## 설치

Python 3.11과 macOS Intel 기준입니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
playwright install chromium
cp .env.example .env
python -m jarvis download-model
```

`download-model`은 `.env`의 `JARVIS_WHISPER_MODEL=small` 모델을 `.local/models/`에 한 번
저장합니다. 이후 `run`은 로컬 모델 파일만 읽습니다. 정확도가 더 필요하면 모델 다운로드 전에
더 큰 모델로 바꿀 수 있지만 Intel Mac에서는 느려집니다.

macOS의 `System Settings > Privacy & Security > Microphone`에서 터미널 앱의 마이크 권한을
허용하세요.

## 실행

```bash
python -m jarvis doctor
python -m jarvis audio-check
python -m jarvis speech-check
python -m jarvis login bunjang
python -m jarvis run
```

개발 중에는 호출어 없이 공개 탐색과 분석만 단발 실행할 수 있습니다.

```bash
python -m jarvis analyze 픽시
```

수집 배분, 지연, 점수 가중치, 문의 질문은 `config/rules.yaml`에서 조정합니다. 주변 소음 때문에
호출이 잘못 감지되면 `.env`의 `JARVIS_VOICE_ENERGY_THRESHOLD` 값을 올리세요. 호출을 놓치면
`audio-check` 결과의 `max_rms`보다 충분히 낮은 값으로 내리세요. 여러 입력 장치가 있으면
`.env`의 `JARVIS_AUDIO_DEVICE_INDEX`에 `audio-check`가 표시한 장치 번호를 넣으세요.
`speech-check` 결과가 이상하면 `afplay .local/last-speech-check.wav`로 실제 녹음을 확인하세요.

## 테스트

```bash
pytest
ruff check .
```

자동 테스트는 API 없이 분석, 저장, 개인정보 제거, 브라우저 격리, URL 차단, 로컬 명령 파싱을
검증합니다. 실제 마이크와 실제 마켓 DOM은 수동으로 확인해야 합니다.
