import { PageColumn } from '@/components/ui';

import { FindEmailForm } from './find-email-form';

export const metadata = {
  title: '아이디 찾기'
};

export default function FindEmailPage() {
  return (
    // 수직 센터링 대신 상단 고정(pt 48) — 인증 4페이지 공통 패턴(login/page.tsx 참조).
    <PageColumn width="form" pt={48}>
      <FindEmailForm />
    </PageColumn>
  );
}
