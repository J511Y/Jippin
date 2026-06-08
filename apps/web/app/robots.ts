import type { MetadataRoute } from 'next';
import { SITE_URL } from '@/lib/site';

/**
 * 모든 크롤러(검색 + GPTBot/ClaudeBot/PerplexityBot 등 AI)를 허용한다.
 * GEO 핵심 전제 = AI 크롤러를 robots 에서 막지 않을 것. 비공개 앱 라우트만 차단.
 */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: '*',
        allow: '/',
        disallow: [
          '/sessions',
          '/contacts',
          '/leads',
          '/login',
          '/auth',
          '/api',
          '/healthz'
        ]
      }
    ],
    sitemap: `${SITE_URL}/sitemap.xml`,
    host: SITE_URL
  };
}
