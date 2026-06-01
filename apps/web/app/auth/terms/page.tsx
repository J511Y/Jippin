import { TermsAcceptancePanel } from './terms-acceptance-panel';

export const metadata = {
  title: '약관 동의'
};

type TermsPageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

function pickSingle(value: string | string[] | undefined): string | null {
  if (Array.isArray(value)) {
    return value[0] ?? null;
  }
  return value ?? null;
}

function safeNextPath(value: string | null): string {
  if (!value || !value.startsWith('/') || value.startsWith('//') || value.includes('\\')) {
    return '/';
  }
  return value;
}

export default async function TermsPage({ searchParams }: TermsPageProps) {
  const resolved = (await searchParams) ?? {};
  return <TermsAcceptancePanel nextPath={safeNextPath(pickSingle(resolved.next))} />;
}
