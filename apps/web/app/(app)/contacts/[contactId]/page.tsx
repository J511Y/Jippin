import { redirect } from 'next/navigation';

/**
 * 상담 현황은 마이페이지로 이동했다(CMP-DIRECT). 기존 상세 링크는 마이페이지의
 * 상담 현황 탭으로 보낸다(기본 탭은 '내 정보').
 */
export default function ContactDetailPage() {
  redirect('/mypage?tab=consultations');
}
