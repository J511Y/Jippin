import { permanentRedirect } from 'next/navigation';

/**
 * `/sessions/new` 는 `/sessions`(통합 채팅 진입)로 영구 이동했다(#sessions-entry-unified).
 * 과거 북마크·외부 링크·구 sitemap 인입이 404 가 되지 않도록 308 리다이렉트만 남긴다.
 */
export default function LegacyNewSessionPage(): never {
  permanentRedirect('/sessions');
}
