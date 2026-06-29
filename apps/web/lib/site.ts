/**
 * 사이트 전역 SEO/GEO 메타데이터 SSOT.
 *
 * - 모든 절대 URL·canonical·sitemap·robots·JSON-LD 가 본 모듈을 단일 소스로 사용한다.
 * - 운영 도메인은 `https://jippin.ai` (ADR-0006: Vercel Pro, apex + www). 프리뷰 등
 *   다른 origin 에서 빌드할 때만 `NEXT_PUBLIC_SITE_URL` 로 덮어쓴다.
 */

/** canonical origin (no trailing slash). */
export const SITE_URL = (
  process.env.NEXT_PUBLIC_SITE_URL ?? 'https://jippin.ai'
).replace(/\/$/, '');

export const SITE_NAME = '집핀';
export const SITE_NAME_FULL = '집핀 (Jippin)';

/**
 * Google Tag Manager 컨테이너 ID. 브라우저로 그대로 노출되는 공개 클라이언트
 * 식별자라 코드에 둔다. GA4 등 실제 태그는 GTM 컨테이너 안에서 관리한다.
 * 프리뷰/스테이징 컨테이너 분리 시에만 `NEXT_PUBLIC_GTM_ID` 로 덮어쓴다.
 */
export const GTM_CONTAINER_ID =
  process.env.NEXT_PUBLIC_GTM_ID ?? 'GTM-TQN3DM5W';

/**
 * 검색·LLM 인입 키워드. 사용자 지정 핵심 키워드 + 동의어/롱테일.
 * (베란다 확장 / 인테리어 / 아파트 확장 / 화단철거 / 가벽철거 / 사전검토)
 */
export const SITE_KEYWORDS = [
  '베란다 확장',
  '발코니 확장',
  '아파트 확장',
  '인테리어',
  '화단철거',
  '가벽철거',
  '사전검토',
  '확장 가능여부',
  '내력벽 철거',
  '비내력벽',
  '벽 철거',
  '행위허가',
  '입주민 동의서',
  '방화판 시공'
];

/** 홈/기본 메타 설명. 핵심 키워드를 자연스러운 문장에 녹였다. */
export const SITE_DESCRIPTION =
  '베란다(발코니) 확장·아파트 확장, 화단철거·가벽철거가 우리 집에서 가능한지 도면과 주소만으로 1분 만에 AI 사전검토. 내력벽·비내력벽을 판별하고 행위허가 필요 여부까지 진단하며, 입주민 동의서·행위허가 대행과 인테리어 시공까지 연결합니다.';

/** OG/트위터 카드 기본 이미지(루트 public). */
export const SITE_OG_IMAGE = '/logo.png';

/** 절대 URL 헬퍼. */
export function absoluteUrl(path = '/'): string {
  return `${SITE_URL}${path.startsWith('/') ? path : `/${path}`}`;
}

/**
 * JSON-LD 를 ``<script type="application/ld+json">`` 에 인라인하기 위한 직렬화.
 *
 * ``JSON.stringify`` 는 ``<`` 를 이스케이프하지 않아 콘텐츠에 ``</script>`` 가
 * 들어오면(관리자 편집·DB 직접 수정 경로) 스크립트가 조기 종료되어 뒤따르는
 * 마크업이 실행될 수 있다. ``<`` 를 유니코드 이스케이프(backslash-u003c)로 치환해
 * 차단한다(JSON 파싱 결과는 동일).
 */
export function safeJsonLd(data: unknown): string {
  return JSON.stringify(data).replace(/</g, '\\u003c');
}

/**
 * 홈 화면에 주입하는 JSON-LD 그래프.
 * Organization + WebSite + Service(제공 서비스) + FAQPage 를 한 @graph 로 묶어
 * 검색 리치 결과와 LLM 의 사실 추출(GEO) 정확도를 동시에 높인다.
 *
 * 수치·문구는 홈/가격 화면 카피와 일치시킨다(2007년~, 누적 25,000+건).
 */
export const SITE_FAQ: { question: string; answer: string }[] = [
  {
    question: '베란다(발코니) 확장은 합법인가요? 행위허가가 필요한가요?',
    answer:
      '발코니 확장 자체는 건축법상 허용되지만, 대부분 관할 지자체의 행위허가(또는 신고)와 입주민 동의가 필요합니다. 집핀은 도면과 주소만으로 행위허가 필요 여부를 1분 만에 사전검토하고, 동의서·허가 신청 대행까지 진행합니다.'
  },
  {
    question: '어떤 벽을 철거할 수 있나요? 내력벽도 철거가 되나요?',
    answer:
      '하중을 받지 않는 비내력벽(가벽)은 일반적으로 철거·이동이 가능하지만, 건물 하중을 지지하는 내력벽은 원칙적으로 철거할 수 없습니다. 집핀 AI 는 평면도에서 벽체·개구부·치수를 인식해 내력벽과 비내력벽을 판별하고 위험 구간을 진단합니다.'
  },
  {
    question: '사전검토는 시간이 얼마나 걸리나요?',
    answer:
      '평면도 한 장과 주소만 입력하면 로그인 없이 약 1분 만에 철거·확장 가능성, 주의 구간, 행위허가 필요 여부를 신호등 리포트로 확인할 수 있습니다.'
  },
  {
    question: '화단철거·가벽철거나 거실 확장 같은 인테리어 공사도 가능한가요?',
    answer:
      '네. 발코니 화단철거, 가벽(비내력벽) 철거, 거실·방 확장 등 인테리어 공사를 사전검토 → 행위허가 대행 → 방화판·방화유리 시공 → 사용검사·건축물대장 등재까지 전 과정으로 진행합니다.'
  },
  {
    question: '발코니 확장 시 방화판·방화유리가 꼭 필요한가요?',
    answer:
      '발코니를 확장하면 인접 세대로의 화재 확산을 막기 위해 90cm 이상의 방화판 또는 방화유리 설치가 의무입니다. 집핀은 건축법 및 KS F 2845 기준에 맞춰 시공합니다.'
  }
];

export function buildHomeJsonLd() {
  const orgId = `${SITE_URL}/#organization`;
  return {
    '@context': 'https://schema.org',
    '@graph': [
      {
        '@type': 'Organization',
        '@id': orgId,
        name: SITE_NAME_FULL,
        alternateName: ['집핀', 'Jippin'],
        url: SITE_URL,
        logo: absoluteUrl(SITE_OG_IMAGE),
        description: SITE_DESCRIPTION,
        foundingDate: '2007',
        areaServed: { '@type': 'Country', name: '대한민국' },
        knowsAbout: SITE_KEYWORDS
      },
      {
        '@type': 'WebSite',
        '@id': `${SITE_URL}/#website`,
        url: SITE_URL,
        name: SITE_NAME_FULL,
        inLanguage: 'ko-KR',
        description: SITE_DESCRIPTION,
        publisher: { '@id': orgId }
      },
      {
        '@type': 'Service',
        '@id': `${SITE_URL}/#service`,
        name: '베란다 확장·벽 철거 AI 사전검토 및 행위허가 대행',
        serviceType: '발코니 확장 / 인테리어 행위허가 사전검토',
        provider: { '@id': orgId },
        areaServed: { '@type': 'Country', name: '대한민국' },
        description:
          '도면과 주소만으로 베란다(발코니) 확장·아파트 확장, 화단철거·가벽철거 가능 여부를 AI 로 사전검토하고, 입주민 동의서·행위허가 신청과 방화판 시공·사용검사까지 대행합니다.',
        offers: {
          '@type': 'Offer',
          price: '0',
          priceCurrency: 'KRW',
          description: 'AI 사전검토 무료 — 로그인 없이 1분'
        }
      },
      {
        '@type': 'FAQPage',
        '@id': `${SITE_URL}/#faq`,
        mainEntity: SITE_FAQ.map((f) => ({
          '@type': 'Question',
          name: f.question,
          acceptedAnswer: { '@type': 'Answer', text: f.answer }
        }))
      }
    ]
  };
}

/**
 * `/home-check`(우리집 체크) 랜딩 JSON-LD.
 *
 * 운영에 새로 열린 기능이라 홈 `@graph` 에는 없는 별도 서비스(위반건축물 셀프 진단)다.
 * WebPage + Service + BreadcrumbList 로 LLM(GEO)·검색이 "우리집 체크"를 집핀의 독립
 * 서비스로 인식하게 한다. 지원/미지원 대상(집합건물 vs 단독·다가구)을 description 에
 * 명시해 "오피스텔도 되나요?" 같은 질의에 정확히 답하도록 한다.
 */
export function buildHomeCheckJsonLd() {
  const orgId = `${SITE_URL}/#organization`;
  const pageUrl = absoluteUrl('/home-check');
  return {
    '@context': 'https://schema.org',
    '@graph': [
      {
        '@type': 'WebPage',
        '@id': `${pageUrl}#webpage`,
        url: pageUrl,
        name: '우리집 체크 — 위반건축물 셀프 진단',
        inLanguage: 'ko-KR',
        isPartOf: { '@id': `${SITE_URL}/#website` },
        about: { '@id': `${pageUrl}#service` }
      },
      {
        '@type': 'Service',
        '@id': `${pageUrl}#service`,
        name: '우리집 체크 (건축물대장 위반건축물 셀프 진단)',
        serviceType: '건축물대장 전유부·표제부 조회 기반 위반건축물 확인',
        provider: { '@id': orgId },
        areaServed: { '@type': 'Country', name: '대한민국' },
        description:
          '아파트·연립·다세대(빌라)·오피스텔·도시형 생활주택 등 집합건물 세대의 건축물대장(전유부·표제부)을 조회해 위반건축물(노란딱지) 표시 여부와 확장·변경 등재 여부를 로그인 없이 셀프로 확인합니다. 단독주택·다가구주택·상가 단독건물은 일반건축물대장 소관이라 현재 미지원입니다.',
        offers: {
          '@type': 'Offer',
          price: '0',
          priceCurrency: 'KRW',
          description: '우리집 체크 무료 — 로그인 없이 건축물대장 셀프 조회'
        }
      },
      {
        '@type': 'BreadcrumbList',
        itemListElement: [
          { '@type': 'ListItem', position: 1, name: '홈', item: SITE_URL },
          { '@type': 'ListItem', position: 2, name: '우리집 체크', item: pageUrl }
        ]
      }
    ]
  };
}

/**
 * `/prices`(가격) JSON-LD. 가격은 전형적 LLM 질의("베란다 확장 비용", "사전검토
 * 무료냐")라 OfferCatalog 로 단계별 제공물을 구조화한다. 정가가 없는 "문의" 단계는
 * 허위 가격 schema 를 넣지 않고 description 으로만 표기한다(price 미기재).
 */
export function buildPricesJsonLd() {
  const orgId = `${SITE_URL}/#organization`;
  return {
    '@context': 'https://schema.org',
    '@type': 'Service',
    '@id': `${absoluteUrl('/prices')}#pricing`,
    name: '집핀 서비스 — AI 사전검토·행위허가 대행 가격',
    provider: { '@id': orgId },
    areaServed: { '@type': 'Country', name: '대한민국' },
    hasOfferCatalog: {
      '@type': 'OfferCatalog',
      name: '집핀 서비스 가격',
      itemListElement: [
        {
          '@type': 'Offer',
          name: 'AI 사전검토',
          price: '0',
          priceCurrency: 'KRW',
          description: '도면과 주소만으로 받는 무료 AI 행위허가 가능성 사전검토. 로그인 없이 즉시 시작.'
        },
        {
          '@type': 'Offer',
          name: '전문가 단건 상담',
          priceCurrency: 'KRW',
          description: '담당 전문가가 진행하는 1:1 맞춤 도면 검토·현장 리스크 피드백(가격 문의).'
        },
        {
          '@type': 'Offer',
          name: '행위허가 대행',
          priceCurrency: 'KRW',
          description: '입주민 동의서 징구부터 행위허가 신청·승인까지 전 과정 대행(가격 문의).'
        }
      ]
    }
  };
}

/**
 * 사전검토 4단계(도면 업로드 → 인식 → 판별 → 리포트). 랜딩의 HowTo JSON-LD 와 화면
 * 카피를 한 소스로 유지하기 위한 SSOT(홈 `STEPS` 와 문구 일치).
 */
export const PRECHECK_STEPS: { name: string; text: string }[] = [
  {
    name: '도면·주소 업로드',
    text: '평면도 한 장과 주소만 입력하면 끝. 로그인 없이 약 1분이면 됩니다.'
  },
  {
    name: '도면 자동 인식',
    text: 'AI 가 평면도에서 벽체·개구부·치수를 인식해 구조를 읽어냅니다.'
  },
  {
    name: '구조 판별 · 위험 진단',
    text: '내력벽·비내력벽을 판별하고, 행위허가 필요 여부와 주의 구간을 진단합니다.'
  },
  {
    name: '사전검토 리포트',
    text: '철거·확장 가능성을 신호등 리포트로 즉시 확인하고, 바로 상담으로 이어갈 수 있습니다.'
  }
];

/**
 * `/sessions/landing`(사전검토 안내) JSON-LD.
 *
 * 인터랙티브 세션(`/sessions/*`)은 noindex 라 GEO 가치가 없으므로, 색인 가능한 서버렌더
 * 랜딩이 사전검토의 사실(무료·1분·로그인 불필요·내력/비내력 판별·행위허가)을 LLM·검색에
 * 노출하는 단일 인입면이 된다. WebPage + Service + HowTo + FAQPage + BreadcrumbList.
 */
export function buildSessionsLandingJsonLd() {
  const orgId = `${SITE_URL}/#organization`;
  const pageUrl = absoluteUrl('/sessions/landing');
  return {
    '@context': 'https://schema.org',
    '@graph': [
      {
        '@type': 'WebPage',
        '@id': `${pageUrl}#webpage`,
        url: pageUrl,
        name: 'AI 사전검토 — 벽 철거·베란다 확장 가능 여부 1분 진단',
        inLanguage: 'ko-KR',
        isPartOf: { '@id': `${SITE_URL}/#website` },
        about: { '@id': `${SITE_URL}/#service` }
      },
      {
        '@type': 'Service',
        '@id': `${pageUrl}#service`,
        name: 'AI 사전검토 (벽 철거·확장 가능 여부 진단)',
        serviceType: '평면도·주소 기반 행위허가 가능성 AI 사전검토',
        provider: { '@id': orgId },
        areaServed: { '@type': 'Country', name: '대한민국' },
        description:
          '평면도 한 장과 주소만으로 벽 철거·베란다(발코니) 확장 가능 여부, 내력벽·비내력벽 판별, 행위허가 필요 여부, 주의 구간을 약 1분 만에 진단합니다. 로그인 불필요, 무료.',
        offers: {
          '@type': 'Offer',
          price: '0',
          priceCurrency: 'KRW',
          description: 'AI 사전검토 무료 — 로그인 없이 약 1분'
        }
      },
      {
        '@type': 'HowTo',
        '@id': `${pageUrl}#howto`,
        name: '도면 한 장으로 1분 AI 사전검토 받는 법',
        totalTime: 'PT1M',
        step: PRECHECK_STEPS.map((s, i) => ({
          '@type': 'HowToStep',
          position: i + 1,
          name: s.name,
          text: s.text
        }))
      },
      {
        '@type': 'FAQPage',
        '@id': `${pageUrl}#faq`,
        mainEntity: SITE_FAQ.map((f) => ({
          '@type': 'Question',
          name: f.question,
          acceptedAnswer: { '@type': 'Answer', text: f.answer }
        }))
      },
      {
        '@type': 'BreadcrumbList',
        itemListElement: [
          { '@type': 'ListItem', position: 1, name: '홈', item: SITE_URL },
          { '@type': 'ListItem', position: 2, name: 'AI 사전검토', item: pageUrl }
        ]
      }
    ]
  };
}
