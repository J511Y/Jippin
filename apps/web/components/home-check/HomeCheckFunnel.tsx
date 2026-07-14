'use client';

import { ActionIcon, Button, Loader, Progress, Text, TextInput } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import {
  IconArrowLeft,
  IconArrowsMaximize,
  IconChevronRight,
  IconHelpCircle,
  IconHome,
  IconMapPin,
  IconPencil,
  IconSearch,
  IconShieldCheck
} from '@tabler/icons-react';
import { useRouter } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';

import { parseApiError } from '@/lib/api/error';
import {
  createHomeCheck,
  type CreateHomeCheckPayload,
  warmHomeCheckWorker
} from '@/lib/home-check/api';
import {
  searchAddress as searchAddressApi,
  type AddressItem,
  type AddressSearchResult
} from '@/lib/leads/api';
import { ensureAnonymousSession } from '@/lib/leads/ensure-anonymous-session';
import { openJusoAddressPopup } from '@/lib/leads/juso-popup';

/**
 * 우리집 체크 입력 퍼널 (CMP-DIRECT, ADR-0008 — 토스/삼쩜삼식 재설계).
 *
 * 기존 밀집형 단일 폼(HomeCheckNewForm)을 "한 화면에 한 질문" 퍼널로 바꿔 이탈을 줄인다.
 * 스텝: 주소 → 동 → 호 → 확장 여부(큰 카드) → (있으면) 부위 선택 → 제출.
 * 제출 페이로드(CreateHomeCheckPayload)는 기존 폼과 100% 동일하게 유지한다.
 *
 * 주소는 **퍼널 안 인앱 검색**(백엔드 프록시 `GET /leads/address/search`)으로 받는다.
 * juso 공식 팝업은 주소 선택 후 "상세주소 입력" 화면을 강제하는데(useDetailAddr 은
 * 그 화면의 입력 방식만 바꿀 뿐 화면 자체를 끄지 못함 — 실측 확인), 동·호를 전용
 * 스텝으로 받는 본 퍼널에서는 중복 입력 혼동만 남긴다. 검색 프록시가 실패하면
 * (승인키 미설정 등) juso 팝업 폴백 버튼을 노출해 흐름이 끊기지 않게 한다.
 *
 * 미리보기(백엔드 없음)에서 재사용할 수 있도록 주소 검색과 제출을 주입 가능하게 뒀다.
 * override 가 없으면 실제 검색 API + `POST /home-check` + 결과 페이지 이동으로 동작한다.
 */

/** 주소 선택 결과(퍼널이 쓰는 최소 형태). 검색 API·팝업 폴백 결과를 이 형태로 좁혀서 받는다. */
export interface PickedAddress {
  /** 세움터 조회용 도로명 part1(건물명 괄호 제외). API 로 보내는 값. */
  roadAddrPart1: string;
  /** 화면 표시용 전체주소(건물명 포함). */
  roadFullAddr: string;
}

export interface HomeCheckFunnelProps {
  /**
   * 미리보기용: 실제 주소 검색 API 대신 mock 결과를 돌려준다.
   * 없으면 백엔드 프록시(`GET /leads/address/search`)를 호출한다.
   */
  searchAddressOverride?: (keyword: string) => Promise<AddressSearchResult>;
  /**
   * 미리보기용: 실제 제출/이동 대신 페이로드만 받는다. resolve 되면 '완료' 화면을 보여 준다.
   * 없으면 익명 세션 보장 후 `POST /home-check` → 결과 상세로 이동한다.
   */
  onSubmitOverride?: (payload: CreateHomeCheckPayload) => Promise<void>;
}

// 인트로 스텝은 없다 — 랜딩(`/home-check`)이 유일한 인트로이고, 여기 진입 시 곧장
// 첫 질문(address)부터 시작한다(시작 버튼 두 번 누르던 중복 제거).
type StepKey =
  | 'address'
  | 'dong'
  | 'ho'
  | 'extension'
  | 'areas'
  | 'submitting'
  | 'done';

/** 확장 신고 선택. yes=있음, no=없음, unsure=모름(대조 생략). */
type ExtensionChoice = 'yes' | 'no' | 'unsure';

/** 확장 부위 다중 선택지. key 는 내부 식별용, label 은 표시·extended_areas 조립용. */
// '발코니/베란다' 단독 항목은 두지 않는다 — 통용상 "거실"이 곧 거실 발코니 확장을 뜻한다.
const AREA_OPTIONS: ReadonlyArray<{ key: string; label: string }> = [
  { key: 'living', label: '거실' },
  { key: 'bedroom', label: '침실' },
  { key: 'kitchen', label: '주방' },
  { key: 'etc', label: '직접 입력할게요' }
];

/** 확장 선택 → 페이로드(reported_extension/extended_areas) 매핑. HomeCheckNewForm 과 동일 규칙. */
function extensionPayload(
  choice: ExtensionChoice,
  areasText: string
): Pick<CreateHomeCheckPayload, 'reported_extension' | 'extended_areas'> {
  if (choice === 'yes') {
    return { reported_extension: true, extended_areas: areasText.trim() || null };
  }
  if (choice === 'no') {
    return { reported_extension: false };
  }
  // unsure → 대조 생략(reported_extension 을 아예 싣지 않는다).
  return {};
}

export function HomeCheckFunnel({ searchAddressOverride, onSubmitOverride }: HomeCheckFunnelProps) {
  const router = useRouter();

  // 스텝 상태 + 뒤로가기 스택. 확장 분기(있어요→부위) 때문에 index 대신 명시 스택을 쓴다.
  // 첫 질문(address)부터 시작한다 — 인트로는 랜딩(`/home-check`)이 담당한다.
  // step 과 스택은 반드시 한 상태로 묶어 원자적으로 갱신한다 — 따로 두면 뒤로가기
  // 더블클릭(같은 프레임 2회) 때 스택만 두 번 pop 되고 step 은 한 번만 움직여 꼬인다.
  const [nav, setNav] = useState<{ step: StepKey; stack: StepKey[] }>({
    step: 'address',
    stack: []
  });
  const step = nav.step;

  // 입력값.
  const [roadAddr, setRoadAddr] = useState(''); // API 로 보내는 part1
  const [displayAddr, setDisplayAddr] = useState(''); // 표시용 전체주소
  const [dong, setDong] = useState('');
  const [ho, setHo] = useState('');
  const [extension, setExtension] = useState<ExtensionChoice | null>(null);
  const [areaKeys, setAreaKeys] = useState<string[]>([]);
  const [etcText, setEtcText] = useState('');

  // 호 스텝 인라인 검증 노출 여부(사용자가 '다음'을 눌렀을 때만 에러를 보여 준다).
  const [hoTouched, setHoTouched] = useState(false);

  const bodyRef = useRef<HTMLDivElement>(null);

  // 이 화면에 진입한 동안 세움터 worker를 best-effort로 깨운다. scale-to-zero 비용은
  // 유지하면서 사용자가 주소·동·호를 입력하는 시간에 Chromium cold-start를 숨긴다.
  // warm-up은 익명 세션을 만들지 않는 공개·cooldown API라, 제출 전 불필요한 anonymous user를
  // 생성하지 않는다. 미리보기는 백엔드를 쓰지 않으므로 실제 호출을 건너뛴다.
  useEffect(() => {
    if (onSubmitOverride) return;
    let cancelled = false;

    void (async () => {
      try {
        if (!cancelled) await warmHomeCheckWorker();
      } catch {
        // warm-up은 UX 최적화다. 실패해도 제출 시 서버의 ready 가드가 다시 준비를 시도한다.
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [onSubmitOverride]);

  // 스텝 전환 시 새 스텝의 포커스 대상으로 포커스를 옮긴다. 입력 스텝(주소 검색·동·호)은
  // 입력칸에 곧장 포커스해 키보드 조작(엔터 진행)이 끊기지 않게 하고, 그 외 스텝은 질문
  // 헤딩에 포커스한다(스크린리더 맥락 전달). input 이 있으면 input 이 우선한다.
  useEffect(() => {
    const root = bodyRef.current;
    const target =
      root?.querySelector<HTMLElement>('input[data-step-focus]') ??
      root?.querySelector<HTMLElement>('[data-step-focus]');
    target?.focus();
  }, [step]);

  // 진행바 계산 — 확장을 '있어요'로 고르면 부위 스텝이 늘어난다.
  const questionOrder: StepKey[] =
    extension === 'yes'
      ? ['address', 'dong', 'ho', 'extension', 'areas']
      : ['address', 'dong', 'ho', 'extension'];
  const orderIndex = questionOrder.indexOf(step);
  const progressCurrent = orderIndex >= 0 ? orderIndex + 1 : 0;
  const progressTotal = questionOrder.length;
  const progressPct =
    step === 'submitting' || step === 'done'
      ? 100
      : (progressCurrent / progressTotal) * 100;

  const showTopBar = step !== 'submitting' && step !== 'done';

  function go(next: StepKey) {
    setNav((n) => ({ step: next, stack: [...n.stack, n.step] }));
  }

  function back() {
    // 첫 질문(address)에서 뒤로 = 랜딩으로 (인트로 스텝이 없으므로).
    if (nav.stack.length === 0) {
      router.push('/home-check');
      return;
    }
    setNav((n) => {
      const prev = n.stack[n.stack.length - 1];
      return prev === undefined ? n : { step: prev, stack: n.stack.slice(0, -1) };
    });
  }

  /** 주소 확정 공통 처리 — 인앱 검색 선택·팝업 폴백 양쪽이 이 경로로 합류한다. */
  function applyPicked(picked: PickedAddress) {
    // 주소가 바뀌면 이후 단계(동/호/확장) 값을 초기화한다 — 뒤로 가서 다른 주소를 골라도 이전
    // 동·호·확장 답이 남아 새 주소에 옛 호수로 조회되는 것을 막는다.
    if (picked.roadAddrPart1 !== roadAddr) {
      setDong('');
      setHo('');
      setHoTouched(false);
      setExtension(null);
      setAreaKeys([]);
      setEtcText('');
    }
    setRoadAddr(picked.roadAddrPart1);
    setDisplayAddr(picked.roadFullAddr);
    // 주소를 골랐으면 곧장 동 입력으로 — 선택 카드에서 '다음'을 한 번 더 누르게 하지 않는다.
    go('dong');
  }

  /** 검색 프록시 실패 시 폴백 — juso 공식 팝업(상세주소 화면은 juso 강제라 못 없앰). */
  async function pickAddressViaPopup() {
    const result = await openJusoAddressPopup({ useDetailAddr: false });
    // CODEF/세움터는 "동·호 전 도로명" 만 받는다 → 건물명 괄호(part2) 제외, part1 만 전송.
    applyPicked({
      roadAddrPart1: result.roadAddrPart1.trim(),
      roadFullAddr: result.roadFullAddr.trim() || result.roadAddrPart1.trim()
    });
  }

  function toggleArea(key: string) {
    setAreaKeys((keys) =>
      keys.includes(key) ? keys.filter((k) => k !== key) : [...keys, key]
    );
  }

  /** 선택 부위 → extended_areas 문자열. 직접 입력은 자유입력 텍스트로, 비어 있으면 '기타'로.
   *  버튼 라벨("직접 입력할게요")은 UI 카피일 뿐 부위명이 아니므로 페이로드에 싣지 않는다. */
  function buildAreasText(): string {
    return AREA_OPTIONS.filter((o) => areaKeys.includes(o.key))
      .map((o) => (o.key === 'etc' ? etcText.trim() || '기타' : o.label))
      .join(', ');
  }

  async function runSubmit(choice: ExtensionChoice) {
    const areasText = choice === 'yes' ? buildAreasText() : '';
    const payload: CreateHomeCheckPayload = {
      road_addr: roadAddr.trim(),
      jibun_addr: null,
      dong: dong.trim(),
      ho: ho.trim(),
      ...extensionPayload(choice, areasText)
    };

    go('submitting');
    try {
      if (onSubmitOverride) {
        await onSubmitOverride(payload);
        setNav((n) => ({ ...n, step: 'done' }));
        return;
      }
      // 세션 보장: apiClient 가 Bearer 를 부착한다(익명 세션 허용).
      await ensureAnonymousSession();
      const job = await createHomeCheck(payload);
      router.push(`/home-check/${job.id}`);
    } catch (error) {
      notifications.show({
        color: 'danger',
        title: '조회 요청에 실패했어요',
        message: parseApiError(error).message
      });
      back();
    }
  }

  /** 확장 여부 카드 선택 — 있어요는 부위 스텝으로, 나머지는 곧장 제출. */
  function chooseExtension(choice: ExtensionChoice) {
    setExtension(choice);
    if (choice === 'yes') {
      go('areas');
    } else {
      void runSubmit(choice);
    }
  }

  const areasValid = areaKeys.length > 0;
  const hoValid = ho.trim().length > 0;

  return (
    <div className="hc-funnel">
      {showTopBar ? (
        <div className="hc-funnel__top">
          {/* 모바일 터치 타깃 ≥44px — ActionIcon lg 는 34px 라 xl(44px)을 쓴다. */}
          <ActionIcon
            variant="subtle"
            color="gray"
            size="xl"
            radius="md"
            aria-label="이전 단계로"
            onClick={back}
          >
            <IconArrowLeft size={20} />
          </ActionIcon>
          {/* 진행바 — 치수선 모티프로 가볍게: 채움은 브랜드 틸, 트랙은 Mantine 기본
              gray 대신 브랜드 보더 토큰. */}
          <Progress
            value={progressPct}
            color="jippin"
            size="sm"
            radius="xl"
            bg="var(--jippin-brand-border)"
            style={{ flex: 1 }}
            aria-hidden
          />
        </div>
      ) : null}

      {/* 스크린리더용 진행 안내(시각적으로 숨김). */}
      <p className="sr-only" aria-live="polite">
        {showTopBar ? `${progressCurrent}단계 / 총 ${progressTotal}단계` : ''}
      </p>

      <div className="hc-body" ref={bodyRef}>
        <div className="hc-step" key={step}>
          {step === 'address' ? (
            <AddressStep
              displayAddr={displayAddr}
              onSearch={searchAddressOverride ?? ((keyword) => searchAddressApi(keyword))}
              onSelect={(item) =>
                applyPicked({
                  roadAddrPart1: item.road_addr_part1.trim(),
                  roadFullAddr: item.road_addr.trim() || item.road_addr_part1.trim()
                })
              }
              onPopupFallback={() => void pickAddressViaPopup()}
              onNext={() => go('dong')}
            />
          ) : step === 'dong' ? (
            <DongStep
              value={dong}
              onChange={setDong}
              onNext={() => go('ho')}
            />
          ) : step === 'ho' ? (
            <HoStep
              value={ho}
              valid={hoValid}
              showError={hoTouched && !hoValid}
              onChange={(v) => {
                setHo(v);
                if (hoTouched) setHoTouched(false);
              }}
              onNext={() => {
                if (!hoValid) {
                  setHoTouched(true);
                  return;
                }
                go('extension');
              }}
            />
          ) : step === 'extension' ? (
            <ExtensionStep selected={extension} onChoose={chooseExtension} />
          ) : step === 'areas' ? (
            <AreasStep
              areaKeys={areaKeys}
              etcText={etcText}
              onToggle={toggleArea}
              onEtcChange={setEtcText}
              valid={areasValid}
              onSubmit={() => void runSubmit('yes')}
            />
          ) : step === 'submitting' ? (
            <SubmittingStep />
          ) : (
            <DoneStep />
          )}
        </div>
      </div>
    </div>
  );
}

/* --------------------------------------------------------------------------
   스텝 컴포넌트 — 각자 하나의 질문/입력. 1차 액션 버튼은 .hc-dock 안에 sticky 로 둔다.
   -------------------------------------------------------------------------- */

function StepHeading({ id, children }: { id?: string; children: React.ReactNode }) {
  return (
    <h2 className="hc-heading" id={id} tabIndex={-1} data-step-focus>
      {children}
    </h2>
  );
}

function StepSub({ children }: { children: React.ReactNode }) {
  return <p className="hc-sub">{children}</p>;
}

/** 하단 고정 "다음/확인" 버튼 — 제품 기능 진행 = 1차 액션(버튼 위계 §2: jippin
 *  filled). coral 은 상담·견적 등 전환 CTA 전용이라 퍼널 진행 버튼엔 쓰지 않는다. */
function DockButton({
  label,
  disabled,
  loading,
  onClick
}: {
  label: string;
  disabled?: boolean;
  loading?: boolean;
  onClick: () => void;
}) {
  return (
    <div className="hc-dock">
      <Button
        color="jippin"
        size="lg"
        fullWidth
        disabled={disabled}
        loading={loading}
        onClick={onClick}
      >
        {label}
      </Button>
    </div>
  );
}

function AddressStep({
  displayAddr,
  onSearch,
  onSelect,
  onPopupFallback,
  onNext
}: {
  displayAddr: string;
  onSearch: (keyword: string) => Promise<AddressSearchResult>;
  onSelect: (item: AddressItem) => void;
  onPopupFallback: () => void;
  onNext: () => void;
}) {
  const hasAddr = displayAddr.trim().length > 0;
  // 뒤로 이동으로 재진입해 이미 고른 주소가 있으면 선택 카드부터, 없으면 검색부터 시작.
  const [searching, setSearching] = useState(!hasAddr);
  const [keyword, setKeyword] = useState('');
  const [result, setResult] = useState<AddressSearchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // '다른 주소로 다시 검색' 토글은 스텝 전환이 아니라 부모의 스텝 포커스 효과가 안 돈다 —
  // 검색 UI 가 마운트되면 직접 검색어 입력칸에 포커스한다(초기 마운트에도 무해).
  useEffect(() => {
    if (searching) inputRef.current?.focus();
  }, [searching]);

  async function runSearch() {
    const trimmed = keyword.trim();
    if (!trimmed || loading) return;
    setLoading(true);
    setFailed(false);
    try {
      setResult(await onSearch(trimmed));
    } catch {
      // 검색 프록시 실패(승인키 미설정·네트워크 등) — 팝업 폴백 버튼을 노출한다.
      setResult(null);
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }

  if (hasAddr && !searching) {
    return (
      <>
        <StepHeading>어느 집을 확인해 드릴까요?</StepHeading>
        <StepSub>이 주소가 맞는지 확인해 주세요. 동·호는 다음 단계에서 입력해요.</StepSub>

        <div style={{ marginTop: 28 }}>
          <div className="hc-address-picked">
            <span className="hc-address-picked__icon" aria-hidden>
              <IconMapPin size={20} />
            </span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <Text
                size="sm"
                fw={600}
                c="var(--jippin-brand-ink)"
                style={{ wordBreak: 'keep-all', lineHeight: 1.45 }}
              >
                {displayAddr}
              </Text>
              <Button
                variant="subtle"
                color="jippin"
                size="compact-sm"
                px={0}
                mt={4}
                leftSection={<IconSearch size={14} aria-hidden />}
                onClick={() => setSearching(true)}
              >
                다른 주소로 다시 검색
              </Button>
            </div>
          </div>
        </div>

        <DockButton label="다음" onClick={onNext} />
      </>
    );
  }

  return (
    <>
      <StepHeading>어느 집을 확인해 드릴까요?</StepHeading>
      <StepSub>건물 도로명주소로 검색해 주세요. 동·호는 다음 단계에서 입력해요.</StepSub>

      <TextInput
        ref={inputRef}
        data-step-focus
        mt={28}
        size="lg"
        radius="lg"
        placeholder="예: 여의대방로43나길 25"
        value={keyword}
        onChange={(e) => setKeyword(e.currentTarget.value)}
        onKeyDown={(e) => {
          // 한글 IME 조합 중 엔터(isComposing)는 조합 확정일 뿐 — 검색을 실행하지 않는다.
          if (e.key === 'Enter' && !e.nativeEvent.isComposing) void runSearch();
        }}
        rightSectionWidth={56}
        rightSection={
          <ActionIcon
            variant="subtle"
            color="jippin"
            size="lg"
            radius="md"
            aria-label="주소 검색"
            loading={loading}
            onClick={() => void runSearch()}
          >
            <IconSearch size={20} />
          </ActionIcon>
        }
        aria-label="도로명주소 검색어"
      />

      {failed ? (
        <div style={{ marginTop: 16 }}>
          <Text size="sm" c="var(--mantine-color-danger-7)">
            주소 검색 서비스에 연결하지 못했어요. 잠시 후 다시 시도하거나, 주소 검색
            팝업으로 찾아 주세요.
          </Text>
          <Button
            mt={10}
            variant="light"
            color="jippin"
            fullWidth
            leftSection={<IconSearch size={16} aria-hidden />}
            onClick={onPopupFallback}
          >
            주소 검색 팝업으로 찾기
          </Button>
        </div>
      ) : null}

      {result ? (
        result.items.length > 0 ? (
          <div
            role="group"
            aria-label="주소 검색 결과"
            style={{ marginTop: 20, display: 'flex', flexDirection: 'column', gap: 10 }}
          >
            {result.items.map((item) => (
              <button
                key={`${item.road_addr}-${item.zip_no ?? ''}`}
                type="button"
                className="hc-choice"
                onClick={() => onSelect(item)}
              >
                <span className="hc-choice__icon" aria-hidden>
                  <IconMapPin size={22} />
                </span>
                <span className="hc-choice__body">
                  <span className="hc-choice__label">{item.road_addr}</span>
                  {item.jibun_addr ? (
                    <span className="hc-choice__desc">지번 {item.jibun_addr}</span>
                  ) : null}
                </span>
                <IconChevronRight size={18} className="hc-choice__chev" aria-hidden />
              </button>
            ))}
            {result.total_count > result.items.length ? (
              <Text size="xs" c="dimmed">
                총 {result.total_count}건 중 {result.items.length}건이에요. 건물번호까지
                입력하면 더 정확하게 찾을 수 있어요.
              </Text>
            ) : null}
          </div>
        ) : (
          <Text mt={20} size="sm" c="dimmed">
            검색 결과가 없어요. 도로명과 건물번호(예: 여의대방로43나길 25)로 다시 검색해
            보세요.
          </Text>
        )
      ) : null}
    </>
  );
}

function DongStep({
  value,
  onChange,
  onNext
}: {
  value: string;
  onChange: (v: string) => void;
  onNext: () => void;
}) {
  return (
    <>
      <StepHeading>동이 어떻게 되나요?</StepHeading>
      <StepSub>아파트라면 동 번호를 적어 주세요. 동이 없는 집이면 비워두고 넘어가도 돼요.</StepSub>

      <TextInput
        data-step-focus
        mt={28}
        size="lg"
        radius="lg"
        inputMode="numeric"
        placeholder="예: 101"
        value={value}
        onChange={(e) => onChange(e.currentTarget.value)}
        onKeyDown={(e) => {
          // IME 조합 확정 엔터로 다음 스텝이 튀지 않게 가드('가'동 같은 한글 동 대비).
          if (e.key === 'Enter' && !e.nativeEvent.isComposing) onNext();
        }}
        aria-label="동"
      />

      <DockButton label={value.trim() ? '다음' : '동 없이 넘어가기'} onClick={onNext} />
    </>
  );
}

function HoStep({
  value,
  valid,
  showError,
  onChange,
  onNext
}: {
  value: string;
  valid: boolean;
  showError: boolean;
  onChange: (v: string) => void;
  onNext: () => void;
}) {
  return (
    <>
      <StepHeading>우리 집은 몇 호인가요?</StepHeading>
      <StepSub>세대를 정확히 찾기 위해 호수가 필요해요.</StepSub>

      <TextInput
        data-step-focus
        mt={28}
        size="lg"
        radius="lg"
        inputMode="numeric"
        placeholder="예: 1502"
        value={value}
        error={showError ? '호를 입력해 주세요' : undefined}
        onChange={(e) => onChange(e.currentTarget.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.nativeEvent.isComposing) onNext();
        }}
        aria-label="호"
      />

      <DockButton label="다음" disabled={!valid} onClick={onNext} />
    </>
  );
}

function ExtensionStep({
  selected,
  onChoose
}: {
  selected: ExtensionChoice | null;
  onChoose: (choice: ExtensionChoice) => void;
}) {
  const options: ReadonlyArray<{
    value: ExtensionChoice;
    label: string;
    desc: string;
    Icon: typeof IconArrowsMaximize;
  }> = [
    {
      value: 'yes',
      label: '있어요',
      desc: '발코니 확장처럼 바꾼 곳이 있어요',
      Icon: IconArrowsMaximize
    },
    { value: 'no', label: '없어요', desc: '분양받은 그대로예요', Icon: IconHome },
    {
      value: 'unsure',
      label: '잘 모르겠어요',
      desc: '확장 여부를 잘 모르겠어요',
      Icon: IconHelpCircle
    }
  ];

  return (
    <>
      <StepHeading>확장하거나 구조를 바꾼 곳이 있나요?</StepHeading>
      <StepSub>발코니 확장·벽 철거처럼 원래 도면과 달라진 곳이 있는지 알려주세요.</StepSub>

      <div
        role="group"
        aria-label="확장·구조 변경 여부"
        style={{ marginTop: 28, display: 'flex', flexDirection: 'column', gap: 12 }}
      >
        {options.map(({ value, label, desc, Icon }) => (
          <button
            key={value}
            type="button"
            className="hc-choice"
            data-selected={selected === value ? 'true' : undefined}
            onClick={() => onChoose(value)}
          >
            <span className="hc-choice__icon" aria-hidden>
              <Icon size={24} />
            </span>
            <span className="hc-choice__body">
              <span className="hc-choice__label">{label}</span>
              <span className="hc-choice__desc">{desc}</span>
            </span>
            <IconChevronRight size={18} className="hc-choice__chev" aria-hidden />
          </button>
        ))}
      </div>
    </>
  );
}

function AreasStep({
  areaKeys,
  etcText,
  onToggle,
  onEtcChange,
  valid,
  onSubmit
}: {
  areaKeys: string[];
  etcText: string;
  onToggle: (key: string) => void;
  onEtcChange: (v: string) => void;
  valid: boolean;
  onSubmit: () => void;
}) {
  const etcSelected = areaKeys.includes('etc');
  return (
    <>
      <StepHeading>어디를 바꾸셨어요?</StepHeading>
      <StepSub>해당하는 곳을 모두 선택해 주세요. 여러 곳을 골라도 괜찮아요.</StepSub>

      <div
        role="group"
        aria-label="확장·변경한 부위"
        style={{ marginTop: 28, display: 'flex', flexWrap: 'wrap', gap: 10 }}
      >
        {AREA_OPTIONS.map(({ key, label }) => {
          const isSelected = areaKeys.includes(key);
          return (
            <button
              key={key}
              type="button"
              className="hc-chip"
              data-selected={isSelected ? 'true' : undefined}
              aria-pressed={isSelected}
              onClick={() => onToggle(key)}
            >
              {label}
            </button>
          );
        })}
      </div>

      {etcSelected ? (
        <TextInput
          mt="md"
          size="md"
          radius="lg"
          placeholder="어디를 바꾸셨는지 적어 주세요 (예: 다용도실 확장)"
          value={etcText}
          onChange={(e) => onEtcChange(e.currentTarget.value)}
          aria-label="기타 확장·변경 부위"
        />
      ) : null}

      <DockButton label="우리 집 확인하기" disabled={!valid} onClick={onSubmit} />
    </>
  );
}

function SubmittingStep() {
  // 조회는 수십 초 걸릴 수 있어, 기다리는 동안 안심 카피를 번갈아 보여 준다.
  const MESSAGES = [
    '건축물대장을 확인하고 있어요…',
    '전유부와 표제부를 조회하고 있어요…',
    '확장 등재 여부를 대조하고 있어요…'
  ];
  const [idx, setIdx] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => {
      setIdx((i) => (i + 1) % MESSAGES.length);
    }, 2600);
    return () => clearInterval(timer);
    // MESSAGES 는 상수라 의존성 불필요.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div
      style={{
        minHeight: 'min(520px, calc(100dvh - 220px))',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        textAlign: 'center',
        gap: 20
      }}
    >
      <Loader color="jippin" size="lg" />
      <div>
        {/* 크기는 .hc-heading 의 display 토큰을 그대로 쓴다 — 인라인 축소 금지. */}
        <p className="hc-heading" data-step-focus tabIndex={-1} aria-live="polite">
          {MESSAGES[idx]}
        </p>
        <StepSub>
          외부 시스템 조회라 최대 1분 정도 걸릴 수 있어요. 화면을 닫지 말고 잠시만 기다려
          주세요.
        </StepSub>
      </div>
    </div>
  );
}

function DoneStep() {
  return (
    <div
      style={{
        minHeight: 'min(520px, calc(100dvh - 220px))',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        textAlign: 'center',
        gap: 16
      }}
    >
      <span
        aria-hidden
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: 56,
          height: 56,
          borderRadius: 18,
          color: 'var(--mantine-color-success-7)',
          background: 'var(--mantine-color-success-0)'
        }}
      >
        <IconShieldCheck size={30} />
      </span>
      <div>
        {/* 크기는 .hc-heading 의 display 토큰을 그대로 쓴다 — 인라인 축소 금지. */}
        <p className="hc-heading" data-step-focus tabIndex={-1}>
          미리보기: 제출이 완료됐어요
        </p>
        <StepSub>
          실제 화면에서는 이 시점에 건축물대장을 조회하는 결과 페이지로 이동해요.
        </StepSub>
      </div>
      <Button
        variant="light"
        color="jippin"
        leftSection={<IconPencil size={16} aria-hidden />}
        onClick={() => window.location.reload()}
      >
        처음부터 다시 보기
      </Button>
    </div>
  );
}
