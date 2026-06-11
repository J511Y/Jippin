import type { MetadataRoute } from 'next';
import { fetchFaqs } from '@/lib/faq';
import { SITE_URL } from '@/lib/site';

/**
 * 색인 대상은 공개 마케팅/정보 페이지로 한정한다. 검토 세션·상담·인증 등
 * 상호작용/비공개 라우트는 robots.ts 의 disallow 및 각 page 의 noindex 로 제외.
 */
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const lastModified = new Date('2026-06-08');
  // FAQ 상세(`/faq/{faqId}`)도 공개 정보 페이지라 색인한다(API 미연결 시 폴백 id —
  // 시드 identity 와 동일).
  const faqEntries: MetadataRoute.Sitemap = (await fetchFaqs()).map((faq) => ({
    url: `${SITE_URL}/faq/${faq.id}`,
    lastModified,
    changeFrequency: 'monthly',
    priority: 0.5
  }));
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
      // 검토(사전검토 세션) 랜딩 — GEO/SEO 인입 페이지로 색인 허용.
      url: `${SITE_URL}/sessions`,
      lastModified,
      changeFrequency: 'weekly',
      priority: 0.8
    },
    {
      // 자주묻는질문 — FAQ 리치결과/GEO 인입 페이지로 색인 허용.
      url: `${SITE_URL}/faq`,
      lastModified,
      changeFrequency: 'monthly',
      priority: 0.6
    },
    ...faqEntries,
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
