# Daily Agricultural Perception Papers

매일 오전 8시(KST), 최근 30일의 미추천 논문에서 정확히 4편을 골라 두 Slack 채널에 전송합니다.

- 보수적인 Q1/Q2 로봇 친화 저널: 2편
- Phenotyping 저널: 1편
- arXiv 또는 기타 허용 Q1/Q2 저널: 1편

저널 정책은 [`journal_policy.json`](journal_policy.json)에서 관리합니다. 목록에 없는 저널과 MDPI·Frontiers 발행 저널은 추천하지 않습니다.

## 데이터 흐름

1. arXiv와 OpenAlex에서 최근 논문 수집
2. DOI와 정규화된 제목으로 중복 제거
3. 과거 추천 논문 제외
4. 저널 정책과 출판사 차단 정책 적용
5. 저비용 모델로 후보를 평가하고 2+1+1 쿼터로 정확히 4편 선정
6. 네 편의 한국어 요약 생성
7. 두 Slack workspace/channel로 전송
8. `state/seen.json`에 추천 이력 저장 후 저장소에 커밋

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

Slack bot에는 각 채널의 `chat:write` 권한이 필요하며, bot을 대상 채널에 초대해야 합니다. 채팅에 노출된 기존 토큰은 폐기하고 재발급한 토큰을 등록하세요.

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
