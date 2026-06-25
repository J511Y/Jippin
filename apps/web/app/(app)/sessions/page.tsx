import { redirect } from 'next/navigation';

/**
 * `/sessions` 진입은 곧장 새 검토 시작(`/sessions/new`)으로 보낸다.
 *
 * 사전검토는 사용자가 평생 한두 번 하는 일이라 '세션 목록'을 일차 화면으로 두는 것은
 * B2C 에 맞지 않는다(제목이 다 같고 내부 상태 뱃지는 의미가 없었다). 과거 검토 다시 보기는
 * 마이페이지(회원)에서 리포트로 제공하는 방향이 맞다. 북마크·직접 진입도 새 검토로 흡수한다.
 */
export default function SessionsPage(): never {
  redirect('/sessions/new');
}
