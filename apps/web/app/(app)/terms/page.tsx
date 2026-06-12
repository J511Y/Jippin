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
  title: '이용약관',
  alternates: { canonical: '/terms' }
};

const EFFECTIVE_DATE = '2026년 6월 8일';

/** 장(章) 단위 구성 — 목차와 본문이 같은 배열을 공유한다. */
type Article = { id: string; title: string; body: ReactNode };
type Chapter = { id: string; title: string; articles: Article[] };

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

const CHAPTERS: Chapter[] = [
  {
    id: 'chapter-1',
    title: '제1장 총칙',
    articles: [
      {
        id: 'article-1',
        title: '제1조 [목적]',
        body: (
          <Para>
            본 약관은 신한이너텍 주식회사(이하 &lsquo;회사&rsquo;)가
            집핀(Jippin) 브랜드로 제공하는 비내력벽 철거 사전검토 AI 서비스 및
            전문가 상담 연결 서비스(이하
            &lsquo;서비스&rsquo;)의 이용과 관련하여 회사와 이용자 간의 권리,
            의무 및 책임사항, 서비스 이용 절차에 관한 사항을 규정함을 목적으로
            합니다.
          </Para>
        )
      },
      {
        id: 'article-2',
        title: '제2조 [용어의 정의]',
        body: (
          <Stack gap="xs">
            <Para>이 약관에서 사용하는 용어의 정의는 다음과 같습니다.</Para>
            <Clause marker="가.">
              &lsquo;서비스&rsquo;란 이용자가 제출한 주소 및 도면 등을 기반으로
              비내력벽 철거 가능성을 인공지능(AI)이 사전 검토하고, 그 결과를
              바탕으로 전문가 상담 및 행위허가 절차를 안내·연결하는 일체의
              서비스를 말합니다.
            </Clause>
            <Clause marker="나.">
              &lsquo;이용자&rsquo;란 본 약관에 동의하고 회사가 제공하는 서비스를
              이용하는 자로서, 회원과 비회원을 모두 포함합니다.
            </Clause>
            <Clause marker="다.">
              &lsquo;회원&rsquo;이란 소셜 로그인을 통해 인증하고 회사가 제공하는
              서비스에 지속적으로 접근할 수 있는 이용자를 말하며,
              &lsquo;비회원&rsquo;이란 로그인 없이 상담 신청 등 일부 기능을
              이용하는 자를 말합니다.
            </Clause>
            <Clause marker="라.">
              &lsquo;사전검토 결과&rsquo;란 이용자가 제출한 정보를 토대로 AI가
              산출한 참고용 분석 결과를 말합니다.
            </Clause>
            <Clause marker="마.">
              &lsquo;제출물&rsquo;이란 이용자가 서비스 이용 과정에서 업로드하거나
              입력한 도면, 주소, 연락처, 상담 메모 등 일체의 자료를 말합니다.
            </Clause>
          </Stack>
        )
      },
      {
        id: 'article-3',
        title: '제3조 [약관의 효력과 변경]',
        body: (
          <Stack gap="xs">
            <Clause marker="가.">
              본 약관은 서비스 화면에 게시하거나 기타의 방법으로 이용자에게
              공지함으로써 효력이 발생합니다.
            </Clause>
            <Clause marker="나.">
              회사는 관계 법령을 위배하지 않는 범위에서 본 약관을 개정할 수
              있으며, 약관을 개정하는 경우 적용 일자 및 변경 사유를 명시하여 다음과
              같이 안내합니다.
            </Clause>
            <SubClause marker="1.">
              일반적인 변경의 경우 적용 일자 7일 전부터 서비스 내 공지를 통해
              안내합니다.
            </SubClause>
            <SubClause marker="2.">
              이용자에게 불리하거나 중대한 변경의 경우 적용 일자 30일 전부터
              안내합니다.
            </SubClause>
            <Clause marker="다.">
              이용자가 개정 약관의 적용 일자 이후에도 서비스를 계속 이용하는
              경우, 개정 약관에 동의한 것으로 봅니다.
            </Clause>
          </Stack>
        )
      },
      {
        id: 'article-4',
        title: '제4조 [약관 외 준칙]',
        body: (
          <Para>
            본 약관에 명시되지 아니한 사항은 「전자상거래 등에서의 소비자보호에
            관한 법률」, 「약관의 규제에 관한 법률」, 「개인정보 보호법」 등 관계
            법령 및 회사가 정한 개별 서비스의 이용 안내에 따릅니다.
          </Para>
        )
      }
    ]
  },
  {
    id: 'chapter-2',
    title: '제2장 서비스 이용계약',
    articles: [
      {
        id: 'article-5',
        title: '제5조 [이용계약의 성립]',
        body: (
          <Stack gap="xs">
            <Clause marker="가.">
              이용계약은 이용자가 본 약관의 내용에 동의하고 회사가 정한 절차에
              따라 서비스 이용을 신청한 후, 회사가 이를 승낙함으로써 성립합니다.
            </Clause>
            <Clause marker="나.">
              회원의 경우 소셜 로그인을 통한 인증을 완료한 시점에, 비회원의 경우
              회사가 정한 양식에 따라 상담 신청을 제출한 시점에 본 약관에 동의한
              것으로 봅니다.
            </Clause>
          </Stack>
        )
      },
      {
        id: 'article-6',
        title: '제6조 [소셜 로그인 및 회원가입]',
        body: (
          <Stack gap="xs">
            <Clause marker="가.">
              서비스의 로그인은 카카오(Kakao) 등 회사가 지정한 소셜 로그인(OAuth)을
              통해서만 제공되며, 회사는 별도의 아이디·비밀번호 가입 절차를 운영하지
              않습니다.
            </Clause>
            <Clause marker="나.">
              회사는 이용자가 소셜 로그인을 통해 제공한 인증 정보를 서비스 제공
              목적의 범위 내에서만 이용합니다.
            </Clause>
            <Clause marker="다.">
              이용자는 본인의 소셜 로그인 계정을 직접 관리할 책임이 있으며, 계정의
              도용이나 부정 사용을 인지한 경우 즉시 회사에 통지하여야 합니다.
            </Clause>
          </Stack>
        )
      },
      {
        id: 'article-7',
        title: '제7조 [비회원의 상담 신청]',
        body: (
          <Stack gap="xs">
            <Clause marker="가.">
              상담 신청은 회원가입이나 로그인 없이 비회원도 할 수 있습니다.
            </Clause>
            <Clause marker="나.">
              다만 신청한 상담의 진행 현황 조회, 상담 내역 및 사전검토 이력의
              관리 등 지속적인 접근이 필요한 기능은 소셜 로그인을 통한 회원
              인증을 거쳐 이용할 수 있습니다.
            </Clause>
            <Clause marker="다.">
              비회원이 상담 신청 시 제공한 연락처 등 정보의 수집 및 이용에 관한
              사항은{' '}
              <Anchor href="/privacy">개인정보처리방침</Anchor>에 따릅니다.
            </Clause>
          </Stack>
        )
      },
      {
        id: 'article-8',
        title: '제8조 [이용신청의 제한]',
        body: (
          <Stack gap="xs">
            <Para>
              회사는 다음 각 호에 해당하는 경우 서비스 이용신청을 승낙하지
              아니하거나 사후에 이용계약을 해지할 수 있습니다.
            </Para>
            <Clause marker="가.">
              타인의 명의나 연락처를 도용하는 등 신청 내용에 허위 사실을 기재한
              경우
            </Clause>
            <Clause marker="나.">
              정당한 권한 없이 타인 소유의 주소 또는 도면에 대한 검토를 신청한
              경우
            </Clause>
            <Clause marker="다.">
              관계 법령을 위반하거나 회사의 정상적인 서비스 운영을 방해할 목적으로
              신청한 경우
            </Clause>
          </Stack>
        )
      }
    ]
  },
  {
    id: 'chapter-3',
    title: '제3장 서비스의 제공 및 이용',
    articles: [
      {
        id: 'article-9',
        title: '제9조 [서비스의 내용]',
        body: (
          <Stack gap="xs">
            <Clause marker="가.">
              회사는 이용자가 제출한 주소와 도면을 바탕으로 비내력벽 철거
              가능성에 대한 AI 사전검토 결과를 제공합니다.
            </Clause>
            <Clause marker="나.">
              회사는 사전검토 결과를 바탕으로 전문가 상담 및 행위허가 지원
              절차로의 연결 서비스를 제공할 수 있습니다.
            </Clause>
            <Clause marker="다.">
              회사는 서비스의 품질 향상을 위해 서비스의 내용을 변경하거나 일부
              기능을 추가·중단할 수 있으며, 중요한 변경 사항은 사전에 공지합니다.
            </Clause>
          </Stack>
        )
      },
      {
        id: 'article-10',
        title: '제10조 [AI 사전검토 결과의 성격]',
        body: (
          <Stack gap="xs">
            <Clause marker="가.">
              사전검토 결과는 이용자의 의사결정을 돕기 위한 참고 자료이며, 법적
              효력을 갖는 확정적 판단이 아닙니다.
            </Clause>
            <Clause marker="나.">
              비내력벽 철거에 대한 실제 가능 여부 및 행위허가는 관할 행정기관의
              판단에 따르며, 회사는 이에 대한 결정 권한을 갖지 않습니다.
            </Clause>
            <Clause marker="다.">
              회사는 사전검토 결과가 관할 행정기관의 최종 판단과 일치할 것을
              보증하지 않으며, 이용자는 실제 공사 진행 전 관할 행정기관 및 전문가의
              확인을 거쳐야 합니다.
            </Clause>
          </Stack>
        )
      },
      {
        id: 'article-11',
        title: '제11조 [서비스 이용시간]',
        body: (
          <Stack gap="xs">
            <Clause marker="가.">
              서비스의 이용은 회사의 업무상 또는 기술상 특별한 지장이 없는 한
              연중무휴 1일 24시간을 원칙으로 합니다.
            </Clause>
            <Clause marker="나.">
              회사는 시스템 정기점검, 증설 및 교체 등 운영상 필요한 경우 서비스의
              전부 또는 일부의 제공을 일시적으로 중단할 수 있으며, 이 경우 사전에
              그 내용을 공지합니다.
            </Clause>
          </Stack>
        )
      },
      {
        id: 'article-12',
        title: '제12조 [서비스의 변경 및 중지]',
        body: (
          <Stack gap="xs">
            <Para>
              회사는 다음 각 호에 해당하는 경우 서비스의 전부 또는 일부를 변경하거나
              제공을 중지할 수 있습니다.
            </Para>
            <Clause marker="가.">
              설비의 보수 등 공사로 인한 부득이한 경우
            </Clause>
            <Clause marker="나.">
              정전, 통신 두절 등 천재지변 또는 이에 준하는 불가항력이 발생한 경우
            </Clause>
            <Clause marker="다.">
              서비스 제공을 위해 연동하는 외부 서비스(소셜 로그인, 데이터 저장 등)에
              장애가 발생한 경우
            </Clause>
            <Clause marker="라.">
              이 외에 회사의 경영상 또는 기술상의 사유로 서비스를 유지하기 어려운
              경우
            </Clause>
          </Stack>
        )
      },
      {
        id: 'article-13',
        title: '제13조 [정보의 제공 및 공지]',
        body: (
          <Stack gap="xs">
            <Clause marker="가.">
              회사는 서비스 운영과 관련된 각종 정보를 서비스 화면 공지, 이메일 등의
              방법으로 이용자에게 제공할 수 있습니다.
            </Clause>
            <Clause marker="나.">
              회사는 광고성 정보를 전송하는 경우 관계 법령에 따라 이용자의 사전
              동의를 받으며, 이용자는 언제든지 수신을 거부할 수 있습니다.
            </Clause>
          </Stack>
        )
      }
    ]
  },
  {
    id: 'chapter-4',
    title: '제4장 의무 및 책임',
    articles: [
      {
        id: 'article-14',
        title: '제14조 [회사의 의무]',
        body: (
          <Stack gap="xs">
            <Clause marker="가.">
              회사는 관계 법령과 본 약관을 준수하며, 안정적이고 지속적으로 서비스를
              제공하기 위하여 노력합니다.
            </Clause>
            <Clause marker="나.">
              회사는 이용자의 개인정보를 보호하기 위하여 관계 법령이 정하는 바에
              따라 안전성 확보에 필요한 기술적·관리적 조치를 시행합니다.
            </Clause>
            <Clause marker="다.">
              회사는 이용자가 제기하는 의견이나 불만이 정당하다고 인정되는 경우 이를
              지체 없이 처리하며, 처리에 시일이 소요되는 경우 그 사유와 일정을
              안내합니다.
            </Clause>
          </Stack>
        )
      },
      {
        id: 'article-15',
        title: '제15조 [이용자의 의무]',
        body: (
          <Stack gap="xs">
            <Para>이용자는 서비스 이용과 관련하여 다음의 의무를 부담합니다.</Para>
            <Clause marker="가.">
              서비스 이용 시 정확하고 진실한 정보를 제공하여야 하며, 타인의 권리를
              침해하거나 허위 정보를 제출하여서는 안 됩니다.
            </Clause>
            <Clause marker="나.">
              본인이 정당한 권한을 가진 대상 주소 및 도면에 한하여 서비스를
              이용하여야 합니다.
            </Clause>
            <Clause marker="다.">
              관계 법령, 본 약관 및 회사가 공지하는 이용 안내를 준수하여야 하며,
              회사의 업무를 방해하는 행위를 하여서는 안 됩니다.
            </Clause>
            <Clause marker="라.">
              사전검토 결과를 실제 공사 가능 여부에 대한 확정적 판단으로 오인하여
              임의로 공사를 진행하여서는 안 되며, 관할 행정기관의 행위허가 및
              전문가의 확인을 거쳐야 합니다.
            </Clause>
          </Stack>
        )
      },
      {
        id: 'article-16',
        title: '제16조 [개인정보의 보호 및 사용]',
        body: (
          <Stack gap="xs">
            <Clause marker="가.">
              회사는 서비스 제공을 위해 필요한 최소한의 범위에서 이용자의 개인정보를
              수집하며, 수집한 개인정보는 서비스 제공 목적의 범위 내에서만
              이용합니다.
            </Clause>
            <Clause marker="나.">
              이용자가 전문가 상담 연결을 요청하는 경우, 회사는 상담 진행에 필요한
              범위에서 이용자의 동의를 받아 해당 전문가에게 관련 정보를 제공할 수
              있습니다.
            </Clause>
            <Clause marker="다.">
              개인정보의 수집 항목, 이용 목적, 보유 기간 등 구체적인 사항은{' '}
              <Anchor href="/privacy">개인정보처리방침</Anchor>에 따릅니다.
            </Clause>
          </Stack>
        )
      },
      {
        id: 'article-17',
        title: '제17조 [제출물의 권리]',
        body: (
          <Stack gap="xs">
            <Clause marker="가.">
              이용자가 제출한 도면 등 제출물의 저작권 및 기타 권리는 해당 권리자에게
              귀속됩니다.
            </Clause>
            <Clause marker="나.">
              이용자는 제출물을 회사가 사전검토 및 상담 연결 목적으로 이용하는 것에
              동의하며, 회사는 해당 목적의 범위를 넘어 제출물을 이용하지 않습니다.
            </Clause>
            <Clause marker="다.">
              제출물의 내용이 부정확하거나 불완전한 경우, 그로 인해 발생하는
              사전검토 결과의 오류에 대한 책임은 이용자에게 있습니다.
            </Clause>
          </Stack>
        )
      },
      {
        id: 'article-18',
        title: '제18조 [저작권의 귀속]',
        body: (
          <Stack gap="xs">
            <Clause marker="가.">
              회사가 작성한 사전검토 결과 및 서비스 화면, 디자인, 소프트웨어 등
              서비스를 구성하는 일체의 저작물에 대한 저작권은 회사에 귀속됩니다.
            </Clause>
            <Clause marker="나.">
              이용자는 회사가 제공하는 사전검토 결과를 본인의 의사결정 목적으로
              이용할 수 있으며, 회사의 사전 동의 없이 이를 영리 목적으로 복제·배포
              또는 제3자에게 제공하여서는 안 됩니다.
            </Clause>
          </Stack>
        )
      },
      {
        id: 'article-19',
        title: '제19조 [면책]',
        body: (
          <Stack gap="xs">
            <Clause marker="가.">
              사전검토 결과는 참고용 정보이며, 회사는 해당 결과가 관할 행정기관의
              최종 판단과 일치할 것을 보증하지 않습니다.
            </Clause>
            <Clause marker="나.">
              이용자가 사전검토 결과만을 신뢰하여 관할 행정기관의 행위허가 없이 실제
              공사를 진행함으로써 발생한 손해에 대하여, 회사는 관계 법령이 허용하는
              범위에서 책임을 지지 않습니다.
            </Clause>
            <Clause marker="다.">
              회사는 천재지변, 불가항력, 이용자의 귀책사유 또는 연동된 외부 서비스의
              장애로 인하여 서비스를 제공할 수 없는 경우 그에 대한 책임을 지지
              않습니다.
            </Clause>
            <Clause marker="라.">
              전문가 상담은 회사가 연결을 지원하는 것으로서, 상담 과정에서 전문가가
              제공하는 의견 및 그에 따른 결과에 대하여 회사는 관계 법령이 허용하는
              범위에서 책임을 지지 않습니다.
            </Clause>
            <Clause marker="마.">
              가목부터 라목까지의 면책은 회사의 고의 또는 중대한 과실로 인한 손해에
              대하여는 적용되지 아니합니다.
            </Clause>
          </Stack>
        )
      },
      {
        id: 'article-20',
        title: '제20조 [손해배상]',
        body: (
          <Stack gap="xs">
            <Clause marker="가.">
              회사 또는 이용자가 본 약관을 위반하여 상대방에게 손해를 입힌 경우,
              귀책사유 있는 당사자는 그 손해를 배상할 책임이 있습니다.
            </Clause>
            <Clause marker="나.">
              이용자가 서비스를 이용하는 과정에서 관계 법령 또는 본 약관을 위반하여
              회사 또는 제3자에게 손해를 발생시킨 경우, 이용자는 그 손해를 배상하여야
              합니다.
            </Clause>
          </Stack>
        )
      }
    ]
  },
  {
    id: 'chapter-5',
    title: '제5장 기타',
    articles: [
      {
        id: 'article-21',
        title: '제21조 [분쟁의 해결]',
        body: (
          <Stack gap="xs">
            <Clause marker="가.">
              회사와 이용자는 서비스 이용과 관련하여 분쟁이 발생한 경우 원만한
              해결을 위해 필요한 협의를 성실히 진행합니다.
            </Clause>
            <Clause marker="나.">
              협의로 해결되지 않는 분쟁에 대하여는 관계 법령 및 회사가 안내하는
              분쟁 처리 절차에 따라 해결합니다.
            </Clause>
          </Stack>
        )
      },
      {
        id: 'article-22',
        title: '제22조 [준거법 및 관할법원]',
        body: (
          <Stack gap="xs">
            <Clause marker="가.">
              본 약관 및 서비스 이용과 관련하여 회사와 이용자 간에 발생한 분쟁에
              대하여는 대한민국 법령을 준거법으로 합니다.
            </Clause>
            <Clause marker="나.">
              서비스 이용과 관련하여 회사와 이용자 간에 발생한 소송은 관계 법령이
              정한 절차에 따른 관할 법원에 제기합니다.
            </Clause>
          </Stack>
        )
      }
    ]
  }
];

export default function TermsPage() {
  return (
    <Stack gap="xl">
      <Stack gap="xs">
        <Title order={1}>이용약관</Title>
        <Text c="dimmed" size="sm">
          시행일 {EFFECTIVE_DATE}
        </Text>
        <Text c="dimmed" size="sm" style={KEEP_ALL}>
          본 약관은 신한이너텍 주식회사가 집핀(Jippin) 브랜드로 제공하는
          비내력벽 철거 사전검토 AI 서비스 및 전문가 상담 연결 서비스의 이용에
          관한 조건과 절차를 정합니다. 약관은
          서비스 개선 및 관계 법령의 변경에 따라 개정될 수 있으며, 개정 시
          시행일과 변경 내용을 사전에 공지합니다.
        </Text>
      </Stack>

      <Card withBorder radius="md" padding="md" component="nav" aria-label="목차">
        <Stack gap="sm">
          <Text fw={600}>목차</Text>
          {CHAPTERS.map((chapter) => (
            <Stack key={chapter.id} gap={4}>
              <Anchor href={`#${chapter.id}`} fw={600} size="sm">
                {chapter.title}
              </Anchor>
              <Stack gap={2} pl="sm">
                {chapter.articles.map((article) => (
                  <Group key={article.id} gap={6} align="center" wrap="nowrap">
                    <ThemeIcon
                      variant="transparent"
                      color="gray"
                      size={16}
                      aria-hidden
                    >
                      <IconChevronRight size={12} stroke={2} />
                    </ThemeIcon>
                    <Anchor href={`#${article.id}`} c="dimmed" size="sm">
                      {article.title}
                    </Anchor>
                  </Group>
                ))}
              </Stack>
            </Stack>
          ))}
          <Anchor href="#addendum" c="dimmed" size="sm" fw={600}>
            부칙
          </Anchor>
        </Stack>
      </Card>

      <Stack gap="xl">
        {CHAPTERS.map((chapter) => (
          <Box key={chapter.id} id={chapter.id} component="section">
            <Stack gap="md">
              <Title order={2} size="h4" style={{ scrollMarginTop: 80 }}>
                {chapter.title}
              </Title>
              <Card withBorder radius="md" padding="md">
                <Stack gap="md">
                  {chapter.articles.map((article, index) => (
                    <Box key={article.id} id={article.id} component="article">
                      {index > 0 && <Divider mb="md" />}
                      <Stack gap="xs">
                        <Text fw={600} style={{ scrollMarginTop: 80 }}>
                          {article.title}
                        </Text>
                        {article.body}
                      </Stack>
                    </Box>
                  ))}
                </Stack>
              </Card>
            </Stack>
          </Box>
        ))}

        <Box id="addendum" component="section">
          <Stack gap="md">
            <Title order={2} size="h4" style={{ scrollMarginTop: 80 }}>
              부칙
            </Title>
            <Card withBorder radius="md" padding="md">
              <Stack gap="xs">
                <Para>본 약관은 {EFFECTIVE_DATE}부터 시행합니다.</Para>
              </Stack>
            </Card>
          </Stack>
        </Box>
      </Stack>

      <Divider />

      <Text size="sm" c="dimmed" style={KEEP_ALL}>
        개인정보의 수집 및 이용에 관한 자세한 사항은{' '}
        <Anchor href="/privacy">개인정보처리방침</Anchor>을 참고하시기 바랍니다.
      </Text>
    </Stack>
  );
}
