import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  CTA_CLICK_EVENT,
  LEAD_CTA_IDS,
  LEAD_CTA_PARAM,
  LEAD_SUBMIT_EVENT,
  leadsNewHref,
  readLeadCtaFromLocation,
  trackLeadCtaClick,
  trackLeadSubmit
} from '@/lib/analytics/lead-cta';

type DataLayerWindow = { dataLayer?: Record<string, unknown>[] };

function dataLayer(): Record<string, unknown>[] {
  return (window as unknown as DataLayerWindow).dataLayer ?? [];
}

beforeEach(() => {
  delete (window as unknown as DataLayerWindow).dataLayer;
  window.history.replaceState(null, '', '/');
});

afterEach(() => {
  window.history.replaceState(null, '', '/');
});

describe('leadsNewHref', () => {
  it('builds /leads/new with the internal cta param (no utm_*)', () => {
    expect(leadsNewHref('home_hero')).toBe('/leads/new?cta=home_hero');
    expect(leadsNewHref('home_hero')).not.toContain('utm_');
  });

  it('keeps the existing fromSession param alongside cta', () => {
    const href = leadsNewHref('report_bottom', { fromSession: 'sess-42' });
    const params = new URLSearchParams(href.split('?')[1]);
    expect(href.startsWith('/leads/new?')).toBe(true);
    expect(params.get(LEAD_CTA_PARAM)).toBe('report_bottom');
    expect(params.get('fromSession')).toBe('sess-42');
  });

  it('omits fromSession when not provided', () => {
    expect(leadsNewHref('prices_consult')).toBe('/leads/new?cta=prices_consult');
  });
});

describe('trackLeadCtaClick', () => {
  it('initializes dataLayer when GTM has not loaded yet', () => {
    trackLeadCtaClick('faq_detail');
    expect(dataLayer()).toEqual([
      { event: CTA_CLICK_EVENT, cta_id: 'faq_detail', cta_destination: '/leads/new' }
    ]);
  });

  it('appends to an existing dataLayer', () => {
    (window as unknown as DataLayerWindow).dataLayer = [{ event: 'gtm.js' }];
    trackLeadCtaClick('mypage_empty');
    expect(dataLayer()).toHaveLength(2);
    expect(dataLayer()[1]).toMatchObject({ cta_id: 'mypage_empty' });
  });
});

describe('readLeadCtaFromLocation', () => {
  it('reads a registered cta id from the current URL', () => {
    window.history.replaceState(null, '', '/leads/new?cta=leads_list');
    expect(readLeadCtaFromLocation()).toBe('leads_list');
  });

  it('rejects unregistered values (tampered or typo links)', () => {
    window.history.replaceState(null, '', '/leads/new?cta=utm_injection');
    expect(readLeadCtaFromLocation()).toBeNull();
  });

  it('returns null when the param is absent', () => {
    window.history.replaceState(null, '', '/leads/new');
    expect(readLeadCtaFromLocation()).toBeNull();
  });
});

describe('trackLeadSubmit', () => {
  it('uses the explicit cta id when given (inline form on home)', () => {
    trackLeadSubmit('main_page', 'home_quick_form');
    expect(dataLayer()).toEqual([
      { event: LEAD_SUBMIT_EVENT, source_form: 'main_page', cta_id: 'home_quick_form' }
    ]);
  });

  it('falls back to the URL cta param for the /leads/new form', () => {
    window.history.replaceState(null, '', '/leads/new?cta=prices_permit&fromSession=s-1');
    trackLeadSubmit('lead_page');
    expect(dataLayer()[0]).toMatchObject({
      event: LEAD_SUBMIT_EVENT,
      source_form: 'lead_page',
      cta_id: 'prices_permit'
    });
  });

  it("reports '(direct)' when no cta context exists", () => {
    window.history.replaceState(null, '', '/leads/new');
    trackLeadSubmit('lead_page');
    expect(dataLayer()[0]).toMatchObject({ cta_id: '(direct)' });
  });
});

describe('LEAD_CTA_IDS naming convention', () => {
  it('keeps ids snake_case and GTM/GA4-safe', () => {
    for (const id of LEAD_CTA_IDS) {
      expect(id).toMatch(/^[a-z][a-z0-9]*(_[a-z0-9]+)*$/);
    }
  });

  it('has no duplicates', () => {
    expect(new Set(LEAD_CTA_IDS).size).toBe(LEAD_CTA_IDS.length);
  });
});
