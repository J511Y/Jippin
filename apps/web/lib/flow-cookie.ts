import { createHmac, randomBytes, timingSafeEqual } from 'node:crypto';

const FLOW_COOKIE_SECRET_ENV = 'SUPABASE_FLOW_COOKIE_SECRET';
const SIGNATURE_ALG = 'sha256';

type FlowCookieEnvelope = {
  payload: Record<string, string>;
  exp: number;
};

type VerifyFailureReason = 'malformed' | 'expired' | 'bad_signature' | 'nonce_replay';

function flowCookieSecret(): string {
  const secret = process.env[FLOW_COOKIE_SECRET_ENV];
  if (!secret) {
    throw new Error(`[flow-cookie] missing required env var: ${FLOW_COOKIE_SECRET_ENV}`);
  }
  return secret;
}

function base64UrlEncode(value: string | Buffer): string {
  return Buffer.from(value).toString('base64url');
}

function base64UrlDecode(value: string): string {
  return Buffer.from(value, 'base64url').toString('utf8');
}

function hmac(value: string): string {
  return createHmac(SIGNATURE_ALG, flowCookieSecret()).update(value).digest('base64url');
}

function safeEqual(left: string, right: string): boolean {
  const leftBuffer = Buffer.from(left);
  const rightBuffer = Buffer.from(right);
  return leftBuffer.length === rightBuffer.length && timingSafeEqual(leftBuffer, rightBuffer);
}

function isStringRecord(value: unknown): value is Record<string, string> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return false;
  }
  return Object.values(value).every((item) => typeof item === 'string');
}

export function signFlowCookie(payload: Record<string, string>, ttlSeconds: number): string {
  if (!Number.isInteger(ttlSeconds) || ttlSeconds <= 0) {
    throw new Error('[flow-cookie] ttlSeconds must be a positive integer');
  }

  const issuedAt = Math.floor(Date.now() / 1000);
  const envelope: FlowCookieEnvelope = {
    payload: {
      ...payload,
      iat: String(issuedAt),
      nonce: randomBytes(16).toString('hex'),
    },
    exp: issuedAt + ttlSeconds,
  };
  const body = base64UrlEncode(JSON.stringify(envelope));
  return `${body}.${hmac(body)}`;
}

export function verifyFlowCookie(
  raw: string,
): { ok: true; payload: Record<string, string> } | { ok: false; reason: VerifyFailureReason } {
  const [body, signature, ...extra] = raw.split('.');
  if (!body || !signature || extra.length > 0) {
    return { ok: false, reason: 'malformed' };
  }

  if (!safeEqual(hmac(body), signature)) {
    return { ok: false, reason: 'bad_signature' };
  }

  let envelope: Partial<FlowCookieEnvelope>;
  try {
    envelope = JSON.parse(base64UrlDecode(body)) as Partial<FlowCookieEnvelope>;
  } catch {
    return { ok: false, reason: 'malformed' };
  }

  if (!isStringRecord(envelope.payload) || typeof envelope.exp !== 'number') {
    return { ok: false, reason: 'malformed' };
  }

  if (Math.floor(Date.now() / 1000) > envelope.exp) {
    return { ok: false, reason: 'expired' };
  }

  return { ok: true, payload: envelope.payload };
}
