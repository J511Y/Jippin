#!/usr/bin/env node
/**
 * 관리자 계정 시드 스크립트 (CMP-DIRECT).
 *
 * Supabase GoTrue Admin API 로 이메일/비밀번호 계정을 만들고
 * `app_metadata.role = 'admin'` 클레임을 부여한다. 관리자 사이트(apps/admin)는
 * 이 클레임만으로 접근을 게이트한다 — `user_metadata` 는 사용자가 직접 수정할 수
 * 있으므로 절대 게이트로 쓰지 않는다.
 *
 * 이미 존재하는 이메일은 기본적으로 **실패 처리**한다 — 일반 사용자 이메일 가입이
 * 열려 있는 프로젝트에서 선점(squatting)된 계정에 admin 을 부여하는 사고를 막는다.
 * 기존 계정임을 운영자가 확인한 경우에만 `--promote-existing` 으로 role 부여를
 * 허용한다(비밀번호는 건드리지 않음).
 *
 * 사용법:
 *   SUPABASE_URL=https://<ref>.supabase.co \
 *   SUPABASE_SERVICE_ROLE_KEY=<service_role> \
 *   ADMIN_INITIAL_PASSWORD=<password> \
 *   node tools/admin/create-admin-users.mjs [--promote-existing] admin@example.com ...
 *
 * service_role 키는 서버 전용 시크릿이다. 이 스크립트는 운영자가 로컬에서
 * 일회성으로 실행하며, 키를 파일이나 로그에 남기지 않는다.
 */

const SUPABASE_URL = process.env.SUPABASE_URL;
const SERVICE_ROLE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY;
const PASSWORD = process.env.ADMIN_INITIAL_PASSWORD;
const args = process.argv.slice(2);
const promoteExisting = args.includes('--promote-existing');
const emails = args.filter((arg) => !arg.startsWith('--'));

if (!SUPABASE_URL || !SERVICE_ROLE_KEY) {
  console.error('SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY 환경변수가 필요합니다.');
  process.exit(1);
}
if (emails.length === 0) {
  console.error('생성할 이메일을 인자로 넘겨주세요.');
  process.exit(1);
}
if (!PASSWORD) {
  console.error('ADMIN_INITIAL_PASSWORD 환경변수가 필요합니다.');
  process.exit(1);
}

const headers = {
  apikey: SERVICE_ROLE_KEY,
  Authorization: `Bearer ${SERVICE_ROLE_KEY}`,
  'Content-Type': 'application/json'
};

async function adminFetch(path, init) {
  const res = await fetch(`${SUPABASE_URL}/auth/v1${path}`, { ...init, headers });
  const body = await res.json().catch(() => ({}));
  return { status: res.status, body };
}

async function findUserByEmail(email) {
  // GoTrue admin list 는 이메일 직접 필터가 없어 페이지 순회로 찾는다.
  for (let page = 1; page <= 20; page += 1) {
    const { status, body } = await adminFetch(`/admin/users?page=${page}&per_page=200`);
    if (status !== 200) {
      throw new Error(`사용자 목록 조회 실패 (HTTP ${status}): ${JSON.stringify(body)}`);
    }
    const users = body.users ?? [];
    const hit = users.find((u) => u.email?.toLowerCase() === email.toLowerCase());
    if (hit) return hit;
    if (users.length < 200) return null;
  }
  return null;
}

async function ensureAdmin(email) {
  const { status, body } = await adminFetch('/admin/users', {
    method: 'POST',
    body: JSON.stringify({
      email,
      password: PASSWORD,
      email_confirm: true,
      app_metadata: { role: 'admin' }
    })
  });

  if (status === 200 || status === 201) {
    console.log(`[created] ${email} (id=${body.id})`);
    return;
  }

  const code = body.error_code ?? body.code ?? '';
  const alreadyExists = status === 422 && String(code).includes('email_exists');
  if (!alreadyExists) {
    throw new Error(`${email} 생성 실패 (HTTP ${status}): ${JSON.stringify(body)}`);
  }

  if (!promoteExisting) {
    // fail-closed: 공개 이메일 가입이 가능한 프로젝트에서 선점된 계정을 그대로
    // admin 으로 승격하면 안 된다. 본인 계정임을 확인한 뒤에만 플래그로 허용.
    throw new Error(
      `${email} 은 이미 존재하는 계정입니다. 대시보드에서 해당 계정의 소유자를 확인한 뒤 ` +
        `--promote-existing 플래그로 재실행하세요 (기존 비밀번호는 유지됩니다).`
    );
  }

  const existing = await findUserByEmail(email);
  if (!existing) {
    throw new Error(`${email} 은 이미 존재한다고 응답했지만 목록에서 찾지 못했습니다.`);
  }
  const update = await adminFetch(`/admin/users/${existing.id}`, {
    method: 'PUT',
    body: JSON.stringify({
      app_metadata: { ...existing.app_metadata, role: 'admin' }
    })
  });
  if (update.status !== 200) {
    throw new Error(
      `${email} app_metadata 갱신 실패 (HTTP ${update.status}): ${JSON.stringify(update.body)}`
    );
  }
  console.log(`[updated] ${email} (id=${existing.id}) — 기존 계정에 role=admin 부여, 비밀번호 유지`);
}

for (const email of emails) {
  await ensureAdmin(email);
}
console.log(`완료: ${emails.length}개 계정 처리.`);
