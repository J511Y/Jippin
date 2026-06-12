import { redirect } from 'next/navigation';

/**
 * 상담 현황은 마이페이지로 이동했다(CMP-DIRECT). 기존 `/contacts` 링크 호환을 위해
 * 마이페이지의 상담 현황 탭으로 리다이렉트한다(기본 탭은 '내 정보').
 */
export default function ContactsPage() {
  redirect('/mypage?tab=consultations');
}
