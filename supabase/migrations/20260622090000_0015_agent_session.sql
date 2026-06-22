-- 0015 Agent session (우리집 체크 대화형 에이전트) — CMP-DIRECT.
--
-- 두 가지를 한 마이그레이션에 담는다:
--   1) LangGraph Postgres 체크포인터 스키마(`langgraph` 전용 스키마). deepagents
--      런타임의 대화/상태 정본이다. PostgREST(public) 와 분리하고 authenticated/anon
--      에는 어떤 권한도 부여하지 않는다(백엔드 service-role 전용).
--   2) `public.agent_runs` 런 추적 테이블 + 프로젝션 idempotency 백스톱 인덱스
--      (chat_messages / chat_tool_calls 의 lc_* 키 부분 유니크).
--
-- ── 체크포인터 DDL 정합(중요) ──────────────────────────────────────────────
-- 아래 langgraph.* 정의는 langgraph-checkpoint-postgres 2.0.25 의
-- AsyncPostgresSaver.MIGRATIONS(v0..v9, 라이브러리가 .setup() 으로 실행하는 정본
-- SQL)를 그대로 vendoring 한 것이다(설치본에서 introspection 으로 추출). 차이점:
--   (1) langgraph 전용 스키마로 qualify,
--   (2) `CREATE INDEX CONCURRENTLY`(v6~v8)는 트랜잭션 안에서 실행 불가하므로
--       일반 CREATE INDEX 로 둔다(신규 빈 테이블이라 결과 동일),
--   (3) v0..v9 적용 완료를 checkpoint_migrations 에 시드해, 이후 누군가 .setup()
--       을 호출해도 재실행하지 않게 한다.
-- 운영 런타임에서 .setup() DDL 을 실행하지 않는다(부팅 시 verify_schema 는 테이블
-- 존재만 검증). 라이브러리 핀(apps/api/pyproject.toml)을 올릴 때는 새 버전의
-- MIGRATIONS 를 다시 추출해 `00NN_langgraph_checkpointer_upgrade.sql` 로 동반한다.

create schema if not exists langgraph;

-- v0
create table if not exists langgraph.checkpoint_migrations (
  v integer primary key
);

-- v1
create table if not exists langgraph.checkpoints (
  thread_id text not null,
  checkpoint_ns text not null default '',
  checkpoint_id text not null,
  parent_checkpoint_id text,
  type text,
  checkpoint jsonb not null,
  metadata jsonb not null default '{}',
  primary key (thread_id, checkpoint_ns, checkpoint_id)
);

-- v2 + v4(blob nullable)
create table if not exists langgraph.checkpoint_blobs (
  thread_id text not null,
  checkpoint_ns text not null default '',
  channel text not null,
  version text not null,
  type text not null,
  blob bytea,
  primary key (thread_id, checkpoint_ns, channel, version)
);

-- v3 + v9(task_path)
create table if not exists langgraph.checkpoint_writes (
  thread_id text not null,
  checkpoint_ns text not null default '',
  checkpoint_id text not null,
  task_id text not null,
  idx integer not null,
  channel text not null,
  type text,
  blob bytea not null,
  task_path text not null default '',
  primary key (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);

-- v6~v8 (CONCURRENTLY 제거 — 트랜잭션 내 실행)
create index if not exists checkpoints_thread_id_idx
  on langgraph.checkpoints (thread_id);
create index if not exists checkpoint_blobs_thread_id_idx
  on langgraph.checkpoint_blobs (thread_id);
create index if not exists checkpoint_writes_thread_id_idx
  on langgraph.checkpoint_writes (thread_id);

-- 라이브러리 마이그레이션 v0..v9 적용 완료 표시(.setup() 재실행 방지).
insert into langgraph.checkpoint_migrations (v)
  values (0), (1), (2), (3), (4), (5), (6), (7), (8), (9)
  on conflict (v) do nothing;

-- 백엔드 service-role 전용 — PostgREST 노출(authenticated/anon) 차단.
revoke all on schema langgraph from authenticated, anon;
revoke all on all tables in schema langgraph from authenticated, anon;

-- ── public.agent_runs ──────────────────────────────────────────────────────
-- 런 단위 메타/상태 추적. 대화 본문은 langgraph.* (정본) 와 chat_messages
-- (프로젝션) 에 있고, 본 테이블은 런 라이프사이클·LangSmith 링크·에러만 갖는다.
-- home_checks(0014) 와 동일하게 authenticated 에 write 권한을 주지 않는다.
create table public.agent_runs (
  id uuid not null default gen_random_uuid(),
  session_id uuid not null,
  user_id uuid,
  thread_id uuid not null,
  status text not null default 'pending',
  model text not null,
  current_step text,
  langsmith_run_id text,
  langsmith_run_url text,
  error_code text,
  error_message text,
  input_summary jsonb not null default '{}'::jsonb,
  started_at timestamp with time zone,
  finished_at timestamp with time zone,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  constraint pk_agent_runs primary key (id),
  constraint ck_agent_runs_agent_runs_status_allowed check (
    status in (
      'pending',
      'running',
      'awaiting_input',
      'interrupted',
      'succeeded',
      'failed',
      'cancelled'
    )
  ),
  constraint fk_agent_runs_session_id_sessions
    foreign key (session_id)
    references public.sessions (id)
    on delete cascade,
  constraint fk_agent_runs_user_id_users
    foreign key (user_id)
    references auth.users (id)
    on delete set null
);

create index ix_agent_runs_session_id_created_at
  on public.agent_runs (session_id, created_at desc);
create index ix_agent_runs_status_started_at
  on public.agent_runs (status, started_at desc);

-- 세션당 활성 런 1개 — 동시 런 race 를 DB 에서 막는다(409 매핑).
create unique index uq_agent_runs_one_active_per_session
  on public.agent_runs (session_id)
  where status in ('pending', 'running', 'awaiting_input', 'interrupted');

comment on table public.agent_runs is
  'Agent run lifecycle/metadata. Conversation state lives in langgraph.* (SoT) and chat_messages (projection). No authenticated write grant.';
comment on column public.agent_runs.thread_id is
  'LangGraph checkpointer thread_id; equals session_id.';

-- ── 프로젝션 idempotency 백스톱 ─────────────────────────────────────────────
-- 런타임이 astream 이벤트를 chat_messages / chat_tool_calls 로 투영할 때
-- resume/replay 로 같은 LC 메시지·툴콜이 두 번 들어오지 않도록 부분 유니크로
-- 막는다. 서비스 레이어가 먼저 lc_id 로 조회해 insert-if-absent 하고, 동시
-- race 는 본 인덱스의 IntegrityError 로 잡아 "이미 투영됨" 처리한다.
create unique index uq_chat_tool_calls_lc_tool_call_id
  on public.chat_tool_calls (session_id, (metadata ->> 'lc_tool_call_id'))
  where (metadata ->> 'lc_tool_call_id') is not null;

create unique index uq_chat_messages_lc_message_id
  on public.chat_messages (session_id, (metadata ->> 'lc_message_id'))
  where (metadata ->> 'lc_message_id') is not null;

-- ── RLS / grants ────────────────────────────────────────────────────────────
alter table public.agent_runs enable row level security;

-- 소유 세션의 런만 읽기. write 는 백엔드 service-role 전용(grant 없음).
create policy agent_runs_session_owner_read
  on public.agent_runs
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.sessions as s
      where s.id = session_id
        and s.user_id = (select auth.uid())
    )
  );

grant select on public.agent_runs to authenticated;
