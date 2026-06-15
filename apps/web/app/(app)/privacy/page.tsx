import {
  Anchor,
  Box,
  Card,
  Divider,
  Group,
  Stack,
  Text,
  ThemeIcon,
  Title
} from '@mantine/core';
import { IconChevronRight } from '@tabler/icons-react';
import type { Metadata } from 'next';
import type { ReactNode } from 'react';

export const metadata: Metadata = {
  title: '개인정보처리방침',
  alternates: { canonical: '/privacy' }
};

const EFFECTIVE_DATE = '2026년 6월 8일';
const PRIVACY_EMAIL = 'privacy@jippin.ai';

/** 절(節) 단위 구성 — 목차와 본문이 같은 배열을 공유한다. */
type Section = { id: string; title: string; body: ReactNode };

const KEEP_ALL = { wordBreak: 'keep-all' as const };

/** 가·나·다 항목 한 줄. */
function Clause({ marker, children }: { marker: string; children: ReactNode }) {
  return (
    <Group gap="xs" align="flex-start" wrap="nowrap">
      <Text size="sm" fw={600} c="dimmed" style={{ flexShrink: 0, minWidth: 16 }}>
        {marker}
      </Text>
      <Text size="sm" c="dimmed" style={KEEP_ALL}>
        {children}
      </Text>
    </Group>
  );
}

/** 1·2·3 세부 항목 — 가·나·다 아래 한 단계 더 들여쓴다. */
function SubClause({ marker, children }: { marker: string; children: ReactNode }) {
  return (
    <Group gap="xs" align="flex-start" wrap="nowrap" pl="lg">
      <Text size="sm" c="dimmed" style={{ flexShrink: 0, minWidth: 14 }}>
        {marker}
      </Text>
      <Text size="sm" c="dimmed" style={KEEP_ALL}>
        {children}
      </Text>
    </Group>
  );
}

/** 항목 없이 흐르는 본문 한 단락. */
function Para({ children }: { children: ReactNode }) {
  return (
    <Text size="sm" c="dimmed" style={KEEP_ALL}>
      {children}
    </Text>
  );
}

/**
 * 위탁·국외이전 표.
 * Mantine 의 `Table.*` compound 컴포넌트는 Turbopack 번들에서 깨지므로
 * `Box component="table"` 기반 네이티브 마크업으로 구성한다.
 */
type EntrustmentRow = {
  trustee: string;
  task: string;
  transfer: string;
  items: string;
  retention: string;
};

const ENTRUSTMENT_ROWS: EntrustmentRow[] = [
  {
    trustee: 'Supabase',
    task: '소셜 로그인 인증 및 회원·상담 데이터베이스 운영',
    transfer: '미국 / 서비스 이용 시점 / 네트워크를 통한 전송',
    items: '소셜 로그인 식별자, 이름, 연락처, 상담 신청 정보',
    retention: '위탁 계약 종료 또는 보유 목적 달성 시까지'
  },
  {
    trustee: 'Cloudflare',
    task: '도면 등 업로드 파일의 저장 및 전송',
    transfer: '미국 / 파일 업로드 시점 / 네트워크를 통한 전송',
    items: '도면 파일(이미지·PDF), 대상 주소 관련 자료',
    retention: '위탁 계약 종료 또는 보유 목적 달성 시까지'
  },
  {
    trustee: 'OpenAI',
    task: '도면 분석을 위한 AI 사전검토 처리',
    transfer: '미국 / 사전검토 요청 시점 / 네트워크를 통한 전송',
    items: '도면 파일 및 분석에 필요한 대상 정보',
    retention: '분석 처리 완료 후 즉시(별도 보관하지 않음)'
  },
  {
    trustee: 'Vercel',
    task: '웹 서비스 호스팅 및 이용 통계·성능 분석(Web Analytics·Speed Insights)',
    transfer: '미국 / 서비스 이용 시점 / 네트워크를 통한 전송',
    items: '접속 로그, 기기·브라우저 정보, 방문 페이지 경로, IP 기반 추정 지역',
    retention: '위탁 계약 종료 또는 보유 목적 달성 시까지'
  },
  {
    trustee: 'CODEF(코드에프)',
    task: '우리집 체크 — 건축물대장(집합건축물 전유부·표제부) 공개정보 조회 대행',
    transfer: '국내 처리(국외 이전 없음) / 우리집 체크 조회 시점 / 네트워크를 통한 전송',
    items: '조회 대상 주소(동·호)',
    retention: '조회 처리 완료 후 즉시(별도 보관하지 않음)'
  }
];

const ENTRUSTMENT_HEADERS = [
  '수탁자',
  '위탁 업무',
  '국외 이전(국가/시점/방법)',
  '이전 항목',
  '보유 기간'
];

const cellStyle = {
  borderBottom: '1px solid var(--mantine-color-default-border)',
  padding: 'var(--mantine-spacing-xs)',
  textAlign: 'left' as const,
  verticalAlign: 'top' as const,
  wordBreak: 'keep-all' as const
};

function EntrustmentTable() {
  return (
    <Box style={{ overflowX: 'auto' }}>
      <Box
        component="table"
        style={{
          width: '100%',
          minWidth: 640,
          borderCollapse: 'collapse'
        }}
      >
        <Box component="thead">
          <Box component="tr">
            {ENTRUSTMENT_HEADERS.map((header) => (
              <Box
                key={header}
                component="th"
                style={{
                  ...cellStyle,
                  whiteSpace: 'nowrap',
                  fontWeight: 600
                }}
              >
                <Text size="sm" fw={600}>
                  {header}
                </Text>
              </Box>
            ))}
          </Box>
        </Box>
        <Box component="tbody">
          {ENTRUSTMENT_ROWS.map((row) => (
            <Box component="tr" key={row.trustee}>
              <Box component="td" style={{ ...cellStyle, whiteSpace: 'nowrap' }}>
                <Text size="sm" fw={600}>
                  {row.trustee}
                </Text>
              </Box>
              <Box component="td" style={cellStyle}>
                <Text size="sm" c="dimmed" style={KEEP_ALL}>
                  {row.task}
                </Text>
              </Box>
              <Box component="td" style={cellStyle}>
                <Text size="sm" c="dimmed" style={KEEP_ALL}>
                  {row.transfer}
                </Text>
              </Box>
              <Box component="td" style={cellStyle}>
                <Text size="sm" c="dimmed" style={KEEP_ALL}>
                  {row.items}
                </Text>
              </Box>
              <Box component="td" style={cellStyle}>
                <Text size="sm" c="dimmed" style={KEEP_ALL}>
                  {row.retention}
                </Text>
              </Box>
            </Box>
          ))}
        </Box>
      </Box>
    </Box>
  );
}

/** 권익침해 구제 안내 기관 한 줄. */
function ReliefRow({ name, contact }: { name: string; contact: string }) {
  return (
    <Group gap="xs" align="flex-start" wrap="nowrap">
      <Text size="sm" c="dimmed" style={{ flexShrink: 0 }}>
        ·
      </Text>
      <Text size="sm" c="dimmed" style={KEEP_ALL}>
        {name} ({contact})
      </Text>
    </Group>
  );
}

const SECTIONS: Section[] = [
  {
    id: 'section-1',
    title: '1. 개인정보의 처리 목적',
    body: (
      <Stack gap="xs">
        <Para>
          집핀(Jippin) 서비스를 운영하는 신한이너텍 주식회사(이하
          &lsquo;회사&rsquo;)는 다음의 목적을 위하여 개인정보를 처리하며, 처리한
          개인정보는 다음의 목적 이외의 용도로는 이용하지 않습니다.
        </Para>
        <Clause marker="가.">
          이용자가 제출한 주소 및 도면을 바탕으로 한 비내력벽 철거 가능성 AI
          사전검토 결과의 제공
        </Clause>
        <Clause marker="나.">
          상담 신청의 접수 및 전문가 상담 연결, 행위허가 후속 절차 안내
        </Clause>
        <Clause marker="다.">
          고객 문의 응대, 본인 확인 및 분쟁 처리 등 이용자 보호 업무의 수행
        </Clause>
        <Clause marker="라.">
          서비스 품질 개선, 신규 기능 개발 및 통계 분석을 통한 서비스 운영
        </Clause>
        <Clause marker="마.">
          우리집 체크 서비스에서 이용자가 입력한 주소의 건축물대장(위반건축물 표시
          등) 공개정보 조회 대행 및 결과 제공
        </Clause>
      </Stack>
    )
  },
  {
    id: 'section-2',
    title: '2. 수집하는 개인정보 항목 및 수집 방법',
    body: (
      <Stack gap="xs">
        <Para>회사는 다음의 개인정보 항목을 수집합니다.</Para>
        <Clause marker="가.">
          상담 신청 시: 이름, 연락처(전화번호 및 이메일), 사전검토 대상 주소,
          도면 파일(이미지 또는 PDF), 상담 메모
        </Clause>
        <Clause marker="나.">
          소셜 로그인(카카오 등 OAuth) 이용 시: 소셜 서비스로부터 제공받는 계정
          식별자 및 프로필 정보
        </Clause>
        <Clause marker="다.">
          서비스 이용 과정에서 자동으로 수집되는 정보: 접속 로그, 쿠키, 기기 및
          브라우저 정보, 익명 세션 식별자
        </Clause>
        <Clause marker="라.">
          우리집 체크 이용 시: 조회 대상 건물의 주소 및 동·호
        </Clause>
        <Para>회사는 다음의 방법으로 개인정보를 수집합니다.</Para>
        <SubClause marker="1.">
          이용자가 서비스 내에서 사전검토 또는 상담을 신청하며 직접 입력하거나
          업로드하는 방법
        </SubClause>
        <SubClause marker="2.">
          소셜 로그인 인증 과정에서 소셜 서비스가 제공하는 정보를 전달받는 방법
        </SubClause>
        <SubClause marker="3.">
          서비스 이용 과정에서 생성 정보 수집 도구를 통해 자동으로 수집되는 방법
        </SubClause>
      </Stack>
    )
  },
  {
    id: 'section-3',
    title: '3. 개인정보의 처리 및 보유기간',
    body: (
      <Stack gap="xs">
        <Clause marker="가.">
          회사는 원칙적으로 개인정보의 처리 목적이 달성된 경우 해당 정보를 지체
          없이 파기합니다.
        </Clause>
        <Clause marker="나.">
          이용자가 동의를 철회하거나 개인정보의 삭제를 요청하는 경우, 관계 법령상
          보존 의무가 없는 정보는 지체 없이 파기합니다.
        </Clause>
        <Clause marker="다.">
          관계 법령에서 일정 기간의 보존을 요구하는 경우에는 해당 법령이 정한
          기간 동안 개인정보를 보관한 후 파기합니다.
        </Clause>
      </Stack>
    )
  },
  {
    id: 'section-4',
    title: '4. 개인정보의 제3자 제공',
    body: (
      <Stack gap="xs">
        <Clause marker="가.">
          회사는 이용자의 개인정보를 본 방침에 명시한 범위를 초과하여 제3자에게
          제공하지 않습니다.
        </Clause>
        <Clause marker="나.">
          다만 이용자가 전문가 상담 연결을 요청하는 경우, 회사는 이용자의 동의를
          받아 상담 진행에 필요한 최소한의 정보를 상담을 담당하는 제휴 전문가 또는
          협력사에 제공할 수 있습니다.
        </Clause>
        <Clause marker="다.">
          회사는 관계 법령에 따라 제공이 요구되는 경우, 법령이 정한 절차와 방법에
          따라 개인정보를 제공할 수 있습니다.
        </Clause>
      </Stack>
    )
  },
  {
    id: 'section-5',
    title: '5. 개인정보 처리의 위탁 및 국외 이전',
    body: (
      <Stack gap="md">
        <Para>
          회사는 원활한 서비스 제공을 위하여 아래와 같이 개인정보 처리 업무를
          외부 전문 업체에 위탁하고 있으며, 일부 업무는 국외에서 처리됩니다. 회사는
          위탁 계약 시 개인정보가 안전하게 관리되도록 필요한 사항을 규정하고
          수탁자를 관리·감독합니다. 위탁 업무의 내용이나 수탁자가 변경되는 경우
          본 방침을 통해 공개하며, 아래 수탁자 및 이전 국가는 서비스 운영 환경에
          따라 변동될 수 있습니다.
        </Para>
        <EntrustmentTable />
        <Para>
          이용자는 개인정보 보호책임자에게 연락하여 개인정보의 국외 이전을 거부할
          수 있으며, 이 경우 해당 처리가 필요한 일부 서비스의 이용이 제한될 수
          있습니다.
        </Para>
      </Stack>
    )
  },
  {
    id: 'section-6',
    title: '6. 정보주체와 법정대리인의 권리·의무 및 행사방법',
    body: (
      <Stack gap="xs">
        <Clause marker="가.">
          이용자는 언제든지 자신의 개인정보에 대한 열람, 정정, 삭제, 처리정지를
          요청할 수 있습니다.
        </Clause>
        <Clause marker="나.">
          권리 행사는 개인정보 보호책임자에게 서면, 이메일 등을 통해 요청할 수
          있으며, 회사는 이에 대해 관계 법령에 따라 지체 없이 필요한 조치를
          취합니다.
        </Clause>
        <Clause marker="다.">
          이용자가 개인정보의 오류에 대한 정정을 요청한 경우, 회사는 정정을
          완료하기 전까지 해당 개인정보를 이용하거나 제3자에게 제공하지 않습니다.
        </Clause>
        <Clause marker="라.">
          만 14세 미만 아동의 경우 법정대리인이 아동의 개인정보에 대한 권리를
          행사할 수 있습니다.
        </Clause>
      </Stack>
    )
  },
  {
    id: 'section-7',
    title: '7. 개인정보의 파기 절차 및 방법',
    body: (
      <Stack gap="xs">
        <Clause marker="가.">
          회사는 개인정보의 보유 기간이 경과하거나 처리 목적이 달성된 경우 해당
          정보를 지체 없이 파기합니다.
        </Clause>
        <Clause marker="나.">
          전자적 파일 형태로 저장된 개인정보는 복구가 불가능한 방법으로 영구
          삭제합니다.
        </Clause>
        <Clause marker="다.">
          종이 문서에 기록된 개인정보는 분쇄하거나 소각하는 방법으로 파기합니다.
        </Clause>
      </Stack>
    )
  },
  {
    id: 'section-8',
    title: '8. 개인정보의 안전성 확보조치',
    body: (
      <Stack gap="xs">
        <Para>
          회사는 개인정보의 안전한 처리를 위하여 다음과 같은 조치를 취하고
          있습니다.
        </Para>
        <Clause marker="가.">
          전송 구간 및 저장 데이터의 암호화 적용
        </Clause>
        <Clause marker="나.">
          개인정보에 대한 접근 권한의 차등 부여 및 접근 통제
        </Clause>
        <Clause marker="다.">
          접속 기록의 보관 및 위·변조 방지를 위한 조치
        </Clause>
        <Clause marker="라.">
          보안 프로그램의 운영 및 보안 취약점의 주기적 점검
        </Clause>
      </Stack>
    )
  },
  {
    id: 'section-9',
    title: '9. 쿠키 등 자동수집 장치의 운영 및 거부',
    body: (
      <Stack gap="xs">
        <Clause marker="가.">
          회사는 로그인 상태 유지 및 서비스 이용 편의 제공을 위하여 쿠키와 세션
          정보를 사용할 수 있습니다.
        </Clause>
        <Clause marker="나.">
          이용자는 웹 브라우저의 설정을 통해 쿠키의 저장을 허용하거나 거부할 수
          있습니다.
        </Clause>
        <Clause marker="다.">
          쿠키 저장을 거부하는 경우 로그인 등 일부 서비스의 이용에 제한이 있을 수
          있습니다.
        </Clause>
      </Stack>
    )
  },
  {
    id: 'section-10',
    title: '10. 개인정보 보호책임자',
    body: (
      <Stack gap="xs">
        <Para>
          회사는 개인정보 처리에 관한 업무를 총괄하여 책임지고, 개인정보 처리와
          관련한 이용자의 문의 및 불만을 처리하기 위하여 아래와 같이 개인정보
          보호책임자를 지정하고 있습니다.
        </Para>
        <Clause marker="·">직책: 개인정보 보호책임자</Clause>
        <Group gap="xs" align="flex-start" wrap="nowrap">
          <Text size="sm" fw={600} c="dimmed" style={{ flexShrink: 0, minWidth: 16 }}>
            ·
          </Text>
          <Text size="sm" c="dimmed" style={KEEP_ALL}>
            이메일:{' '}
            <Anchor href={`mailto:${PRIVACY_EMAIL}`}>{PRIVACY_EMAIL}</Anchor>
          </Text>
        </Group>
        <Para>
          이용자는 서비스를 이용하면서 발생한 모든 개인정보 보호 관련 문의, 불만
          처리, 피해 구제 등에 관한 사항을 개인정보 보호책임자에게 문의할 수
          있으며, 회사는 이에 대해 지체 없이 답변하고 처리합니다.
        </Para>
      </Stack>
    )
  },
  {
    id: 'section-11',
    title: '11. 권익침해 구제방법',
    body: (
      <Stack gap="xs">
        <Para>
          이용자는 개인정보 침해로 인한 구제를 받기 위하여 아래의 기관에 분쟁
          해결이나 상담 등을 신청할 수 있습니다.
        </Para>
        <ReliefRow name="개인정보분쟁조정위원회" contact="1833-6972" />
        <ReliefRow name="개인정보침해신고센터" contact="118" />
        <ReliefRow name="대검찰청 사이버수사과" contact="1301" />
        <ReliefRow name="경찰청 사이버수사국" contact="182" />
      </Stack>
    )
  },
  {
    id: 'section-12',
    title: '12. 개인정보처리방침의 변경',
    body: (
      <Stack gap="xs">
        <Clause marker="가.">
          본 개인정보처리방침은 {EFFECTIVE_DATE}부터 시행합니다.
        </Clause>
        <Clause marker="나.">
          법령, 정책 또는 보안 기술의 변경에 따라 내용의 추가, 삭제 및 수정이 있는
          경우, 변경 사항의 시행 7일 전부터 서비스 내 공지 등을 통해 안내합니다.
        </Clause>
        <Clause marker="다.">
          이용자 권리에 중대한 영향을 미치는 변경의 경우에는 시행 30일 전부터
          안내합니다.
        </Clause>
      </Stack>
    )
  }
];

export default function PrivacyPage() {
  return (
    <Stack gap="xl">
      <Stack gap="xs">
        <Title order={1}>개인정보처리방침</Title>
        <Text c="dimmed" size="sm">
          시행일 {EFFECTIVE_DATE}
        </Text>
        <Text c="dimmed" size="sm" style={KEEP_ALL}>
          집핀(Jippin) 서비스를 운영하는 신한이너텍 주식회사(이하
          &lsquo;회사&rsquo;)는 이용자의 개인정보를 중요하게 생각하며, 「개인정보
          보호법」 등 관계 법령을 준수합니다. 본 개인정보처리방침은 회사가
          제공하는 비내력벽 철거 AI 사전검토 및 전문가
          상담 연결 서비스 이용 과정에서 개인정보가 어떻게 수집·이용·보관·파기되는지를
          안내합니다. 본 방침은 관계 법령의 개정이나 서비스 정책의 변경에 따라
          개정될 수 있으며, 개정 시 시행일과 변경 내용을 사전에 공지합니다.
        </Text>
      </Stack>

      <Card withBorder radius="md" padding="md" component="nav" aria-label="목차">
        <Stack gap="sm">
          <Text fw={600}>목차</Text>
          {SECTIONS.map((section) => (
            <Group key={section.id} gap={6} align="center" wrap="nowrap">
              <ThemeIcon
                variant="transparent"
                color="gray"
                size={16}
                aria-hidden
              >
                <IconChevronRight size={12} stroke={2} />
              </ThemeIcon>
              <Anchor href={`#${section.id}`} c="dimmed" size="sm">
                {section.title}
              </Anchor>
            </Group>
          ))}
        </Stack>
      </Card>

      <Stack gap="xl">
        {SECTIONS.map((section) => (
          <Box key={section.id} id={section.id} component="section">
            <Stack gap="md">
              <Title order={2} size="h4" style={{ scrollMarginTop: 80 }}>
                {section.title}
              </Title>
              <Card withBorder radius="md" padding="md">
                {section.body}
              </Card>
            </Stack>
          </Box>
        ))}
      </Stack>

      <Divider />

      <Text size="sm" c="dimmed" style={KEEP_ALL}>
        서비스 이용 조건에 관한 자세한 사항은{' '}
        <Anchor href="/terms">이용약관</Anchor>을 참고하시기 바랍니다.
      </Text>
    </Stack>
  );
}
