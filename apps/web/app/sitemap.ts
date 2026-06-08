import type { MetadataRoute } from 'next';
import { SITE_URL } from '@/lib/site';

/**
 * 색인 대상은 공개 마케팅/정보 페이지로 한정한다. 검토 세션·상담·인증 등
 * 상호작용/비공개 라우트는 robots.ts 의 disallow 및 각 page 의 noindex 로 제외.
 */
export default function sitemap(): MetadataRoute.Sitemap {
  const lastModified = new Date('2026-06-08');
  return [
    {
      url: `${SITE_URL}/`,
      lastModified,
      changeFrequency: 'weekly',
      priority: 1
    },
    {
      url: `${SITE_URL}/prices`,
      lastModified,
      changeFrequency: 'monthly',
      priority: 0.8
    },
    {
      url: `${SITE_URL}/terms`,
      lastModified,
      changeFrequency: 'yearly',
      priority: 0.3
    },
    {
      url: `${SITE_URL}/privacy`,
      lastModified,
      changeFrequency: 'yearly',
      priority: 0.3
    }
  ];
}
