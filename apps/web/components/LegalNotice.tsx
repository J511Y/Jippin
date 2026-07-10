import { Anchor, Box, Container, Group, Stack, Text } from '@mantine/core';

/**
 * AGENTS.md §4.6 — 모든 리포트 화면·다운로드 산출물에 노출되어야 하는 법적 고지.
 * 본 컴포넌트는 base layout 에서 항상 렌더되며, 리포트/공유 산출물에서 재사용한다.
 *
 * - `inline` (결과 카드 등 본문 컨텍스트): caption(13/20). 면책은 실제로 읽혀야 하므로
 *   result-card 안에서는 한 단계 크게 노출한다.
 * - `footer` (페이지 푸터): 네이버식 컴팩트 푸터(약관·개인정보 링크 + 운영사 사업자 표기 +
 *   법적 고지 1줄 + 카피라이트).
 * - `compact` (모바일 상시 푸터): 사업자 표기 핵심 2~3줄 + 링크 + 법적 고지 1줄.
 *   root layout 이 모바일(<sm)에서 상시 노출한다(사업자 표기는 표시 의무라 화면에서
 *   전부 숨기면 컴플라이언스 리스크). 주소 포함 풀 표기는 데스크톱 푸터·모바일
 *   Drawer(메뉴) 안의 `footer` variant 가 계속 담당한다.
 */
export const LEGAL_NOTICE_TEXT =
  '본 서비스는 AI 기반 사전 검토 시스템입니다. 최종 행위허가 여부는 관할 행정기관 판단에 따라 달라질 수 있습니다.';

/**
 * 운영사 사업자 표기 — 정보통신망법·전자상거래법상 표기 의무이자, 카카오 비즈니스
 * 채널 심사(사업자–채널 연관성)의 핵심 증빙이므로 footer variant 에서 항상 노출한다.
 */
export const BUSINESS_INFO = {
  company: '신한이너텍 주식회사',
  representative: '윤찬웅',
  businessRegistrationNumber: '106-86-55414',
  phone: '010-3657-9841',
  email: 'titiroll@hanmail.net',
  address: '서울특별시 강서구 양천로 400-12, 더리브골드타워 416호',
  homepage: 'https://www.sh-innertech.com'
} as const;

type LegalNoticeProps = {
  className?: string;
  variant?: 'inline' | 'footer' | 'compact';
};

/* 사업자 표기·법고지 공용 마이크로 타이포 — 크기는 legal 토큰(12px) 단일
   (TYPOGRAPHY.md — 임의 px 발명 금지, 11px 하드코딩 폐지). */
const FINE_PRINT_PROPS = {
  fz: 'var(--jippin-fz-legal)',
  lh: '1.15rem',
  style: { wordBreak: 'keep-all', overflowWrap: 'break-word' }
} as const;

/** 약관·개인정보·FAQ 링크 줄 — footer/compact 가 공유한다. */
function FooterLinks() {
  return (
    <Group gap="xs" align="center" wrap="wrap">
      <Anchor
        href="/terms"
        size="xs"
        fw={600}
        c="var(--jippin-brand-copy)"
        underline="never"
      >
        이용약관
      </Anchor>
      <Text size="xs" c="dimmed">
        ·
      </Text>
      <Anchor
        href="/privacy"
        size="xs"
        fw={600}
        c="var(--jippin-brand-copy)"
        underline="never"
      >
        개인정보처리방침
      </Anchor>
      <Text size="xs" c="dimmed">
        ·
      </Text>
      <Anchor
        href="/faq"
        size="xs"
        fw={600}
        c="var(--jippin-brand-copy)"
        underline="never"
      >
        자주묻는질문
      </Anchor>
    </Group>
  );
}

export function LegalNotice({ className, variant = 'footer' }: LegalNoticeProps) {
  if (variant === 'inline') {
    return (
      <Box
        component="aside"
        role="note"
        aria-label="법적 고지"
        data-testid="legal-notice"
        className={className}
        px="sm"
        py="xs"
        style={{
          // 흰 캔버스/흰 카드 위 구획 — 회색(gray-0)이 아니라 브랜드 surface 틴트로
          // 격자 캔버스와 톤을 맞춘다.
          background: 'var(--jippin-brand-surface)',
          borderRadius: 'var(--mantine-radius-md)',
          wordBreak: 'keep-all',
          overflowWrap: 'break-word'
        }}
      >
        <Text c="var(--jippin-notice-legal)" fz="13px" lh="1.25rem">
          {LEGAL_NOTICE_TEXT}
        </Text>
      </Box>
    );
  }

  if (variant === 'compact') {
    return (
      <Box
        component="footer"
        data-testid="legal-notice"
        className={className}
        style={{
          borderTop: '1px solid var(--jippin-brand-border)',
          background: 'var(--jippin-brand-surface)',
          // iOS 홈 인디케이터가 마지막 줄을 가리지 않게 safe-area 하단 여백만 둔다.
          paddingBottom: 'env(safe-area-inset-bottom, 0px)'
        }}
      >
        <Container size="lg" py="md">
          <Stack gap={6}>
            <Group justify="space-between" align="center" wrap="wrap" gap="xs">
              <FooterLinks />
              <Text size="xs" c="dimmed">
                © 2026 {BUSINESS_INFO.company}
              </Text>
            </Group>
            <Stack gap={2}>
              <Text c="dimmed" {...FINE_PRINT_PROPS}>
                상호: {BUSINESS_INFO.company} · 대표자:{' '}
                {BUSINESS_INFO.representative} · 사업자등록번호:{' '}
                {BUSINESS_INFO.businessRegistrationNumber}
              </Text>
              <Text c="dimmed" {...FINE_PRINT_PROPS}>
                전화: {BUSINESS_INFO.phone} · 이메일: {BUSINESS_INFO.email}
              </Text>
            </Stack>
            <Text c="var(--jippin-notice-legal)" {...FINE_PRINT_PROPS}>
              {LEGAL_NOTICE_TEXT}
            </Text>
          </Stack>
        </Container>
      </Box>
    );
  }

  return (
    <Box
      component="footer"
      data-testid="legal-notice"
      className={className}
      style={{
        borderTop: '1px solid var(--jippin-brand-border)',
        // 흰 캔버스 위 푸터 구획 — 흰색(surface-alt) 대신 브랜드 surface 틴트로
        // 본문과의 경계를 만든다(상단 브랜드 보더와 한 쌍).
        background: 'var(--jippin-brand-surface)'
      }}
    >
      <Container size="lg" py="md">
        <Stack gap={6}>
          <Group justify="space-between" align="center" wrap="wrap" gap="xs">
            <FooterLinks />
            <Text size="xs" c="dimmed">
              © 2026 {BUSINESS_INFO.company}
            </Text>
          </Group>
          <Stack gap={2}>
            <Text c="dimmed" {...FINE_PRINT_PROPS}>
              집핀(Jippin)은{' '}
              <Anchor
                href={BUSINESS_INFO.homepage}
                target="_blank"
                rel="noopener noreferrer"
                fz="var(--jippin-fz-legal)"
                c="dimmed"
                underline="always"
              >
                {BUSINESS_INFO.company}
              </Anchor>
              가 운영하는 서비스입니다.
            </Text>
            <Text c="dimmed" {...FINE_PRINT_PROPS}>
              상호: {BUSINESS_INFO.company} · 대표자:{' '}
              {BUSINESS_INFO.representative} · 사업자등록번호:{' '}
              {BUSINESS_INFO.businessRegistrationNumber}
            </Text>
            <Text c="dimmed" {...FINE_PRINT_PROPS}>
              전화: {BUSINESS_INFO.phone} · 이메일: {BUSINESS_INFO.email}
            </Text>
            <Text c="dimmed" {...FINE_PRINT_PROPS}>
              주소: {BUSINESS_INFO.address}
            </Text>
          </Stack>
          <Text c="var(--jippin-notice-legal)" {...FINE_PRINT_PROPS}>
            {LEGAL_NOTICE_TEXT}
          </Text>
        </Stack>
      </Container>
    </Box>
  );
}
