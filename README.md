# Daily Agricultural Perception Papers

매일 오전 8시(KST), 농업 로봇·인식 분야의 신규 논문을 수집하고 연구 관련도가 높은 2–5편을 두 Slack 채널에 전송합니다.

## 데이터 흐름

1. arXiv와 OpenAlex에서 최근 논문 수집
2. DOI와 정규화된 제목으로 중복 제거
3. 과거 추천 논문 제외
4. 저비용 모델로 전체 후보 평가
5. 상위 후보에서 2–5편을 선정하고 한국어 요약 생성
6. 두 Slack workspace/channel로 전송
7. `state/seen.json`에 추천 이력 저장

관심 분야와 검색식은 [`interests.json`](interests.json)에서 수정할 수 있습니다.

## GitHub Secrets

Repository `Settings → Secrets and variables → Actions`에 아래 Secret을 각각 등록합니다.

| Name | Value |
|---|---|
| `OPENAI_API_KEY` | OpenAI API key |
| `SLACK_TOKEN1` | 첫 번째 Slack bot token |
| `SLACK_SUMMARY_CHANNEL_ID1` | 첫 번째 Slack channel ID |
| `SLACK_TOKEN2` | 두 번째 Slack bot token |
| `SLACK_SUMMARY_CHANNEL_ID2` | 두 번째 Slack channel ID |

Slack bot에는 각 채널의 `chat:write` 권한이 필요하며, bot을 대상 채널에 초대해야 합니다.

## 실행

Actions 탭의 `Daily paper recommendations`에서 `Run workflow`를 누르면 즉시 시험할 수 있습니다. 정기 실행은 매일 `23:00 UTC`, 즉 `08:00 KST`입니다.

로컬 실행:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt pytest
pytest -q
python -m paper_bot.main
```

필수 환경변수가 없거나 외부 API 호출이 실패하면 즉시 오류로 종료합니다.
