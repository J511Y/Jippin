# 에이전트 Responses 체크포인트 복구

## 적용 범위

OpenAI Responses API를 `store=false`로 호출하는 LangGraph 세션이
`invalid_encrypted_content`로 반복 실패할 때만 사용한다. HF 세그멘테이션 실패,
일반 OpenAI 4xx, 도구 비즈니스 오류에는 사용하지 않는다.

원인은 먼저 Fly 로그의 `agent_run_failed.error_code`가
`AGENT_CHECKPOINT_INVALID`인지 확인한다. 사용자 발화·주소·도면·암호화 데이터 원문을
로그나 PR 본문에 복사하지 않는다.

## 예방 설정

에이전트 `ChatOpenAI`는 다음 계약을 유지한다.

- `use_responses_api=True`
- `output_version="responses/v1"`
- `include=["reasoning.encrypted_content"]`
- LangGraph가 대화 상태 정본이므로 `use_previous_response_id`는 사용하지 않는다.

`responses/v1`은 reasoning, assistant text, function call을 순서 있는 content block으로
보존한다. legacy v0 형식의 단일 `additional_kwargs.reasoning` 필드로 되돌리지 않는다.

## 운영 복구 절차

복구 전 해당 세션의 활성 agent run이 없고 마지막 run이 terminal 상태인지 확인한다.
먼저 dry-run으로 제거 대상 개수만 확인한다.

```bash
fly ssh console -a jippin -C "python -m src.agent.checkpoint_repair <session-uuid>"
```

진단에서 확인한 개수와 일치할 때만 적용한다. `--expected-items` 불일치 시 아무것도
쓰지 않고 실패한다.

```bash
fly ssh console -a jippin -C "python -m src.agent.checkpoint_repair <session-uuid> --apply --expected-items 1"
```

도구는 최신 체크포인트의 암호화된 legacy reasoning 필드만 제거한다. 사용자/assistant
본문, function call, tool output은 보존한다. 기존 DB row를 수정하지 않고 원본을 부모로
하는 새 체크포인트를 추가하므로 원본 이력이 남는다.

적용 후 세션에서 다음 사용자 턴을 전송하고, Fly 로그에서 다음을 확인한다.

- `agent_run_failed` 재발 없음
- OpenAI Responses 요청 2xx
- tool call과 assistant 메시지 정상 투영
- 세션이 `collecting_info` 이후 단계로 진행

복구 결과가 예상과 다르면 새 입력을 보내지 말고 출력된 `source_checkpoint_id`를 기준으로
조사한다. 체크포인트 테이블을 직접 UPDATE/DELETE하지 않는다.
