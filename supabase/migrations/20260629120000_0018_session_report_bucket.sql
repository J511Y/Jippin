-- 0018 사전검토 PDF 리포트 보관 버킷 (CMP-DIRECT)
--
-- POST /sessions/{id}/report/pdf 가 발부한 PDF 를 보관하는 비공개 버킷.
-- 백엔드(service role)만 write/read 하고, 사용자에게는 단기 서명 URL 로만 제공한다
-- (클라이언트 직접 접근 없음 → owner-folder 정책 불필요). home-check-docs 와 동일 패턴.
-- 버킷 미생성 시 업로드가 502(REPORT_PDF_STORAGE_FAILED) 로 실패하므로 마이그레이션으로
-- 보장한다 (config.session_report_bucket 기본값과 일치).

insert into storage.buckets (id, name, public)
values ('session-reports', 'session-reports', false)
on conflict (id) do nothing;
