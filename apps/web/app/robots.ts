import type { MetadataRoute } from 'next';
import { SITE_URL } from '@/lib/site';

/**
 * 모든 크롤러(검색 + GPTBot/ClaudeBot/PerplexityBot 등 AI)를 허용한다.
 * GEO 핵심 전제 = AI 크롤러를 robots 에서 막지 않을 것. 비공개 앱 라우트만 차단.
 */

// 비공개/개인 라우트 — 검색·AI 모두 크롤 제외(색인 가치 0 + 개인정보 노출 방지).
const DISALLOW = [
  '/contacts',
  '/leads',
  '/login',
  '/auth',
  '/api',
  '/healthz',
  '/mypage' // 회원 개인 페이지(page metadata 에서도 noindex). 크롤 예산 낭비 차단.
];

// 생성형 AI 크롤러를 명시적으로 allow 해 GEO 의도를 코드에 고정한다(누군가 와일드카드
// 규칙을 손대도 AI 인입이 한꺼번에 죽지 않도록). 비공개 라우트는 동일하게 제외.
const AI_BOTS = [
  'GPTBot',
  'OAI-SearchBot',
  'ChatGPT-User',
  'ClaudeBot',
  'Claude-Web',
  'anthropic-ai',
  'PerplexityBot',
  'Google-Extended',
  'Applebot-Extended'
];

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: AI_BOTS,
        allow: '/',
        disallow: DISALLOW
      },
      {
        userAgent: '*',
        allow: '/',
        disallow: DISALLOW
      }
    ],
    sitemap: `${SITE_URL}/sitemap.xml`,
    host: SITE_URL
  };
}
