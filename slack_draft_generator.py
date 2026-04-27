#!/usr/bin/env python3
"""
Re:NK Slack 데일리 코멘트 초안 생성기 v3
==========================================
Meta API 자동 수집 데이터 기반 — 수기 입력 항목 제거
자사몰 + 스마트스토어(협력광고) 계정별 분리 출력
"""

import os
from datetime import datetime

# ============================================================
# KPI 기준값
# ============================================================
KPI = {
    'roas_warning': 100,   # % (1.0x 미만 경고)
    'cpm_warning': 120000,
}

WEEKDAY_KO = ['월', '화', '수', '목', '금', '토', '일']
DIV = '────────────────────────────────'


# ============================================================
# 유틸
# ============================================================

def _d(a, b, default=0.0):
    return a / b if b else default

def won(v):
    return f"{int(round(v)):,}"

def pct(v):
    return f"{v:.2f}"

def roas_x(v):
    return f"{v / 100:.2f}x"

def chg(cur, prev):
    """전일 대비 증감률"""
    if not prev:
        return ""
    diff = (cur - prev) / abs(prev) * 100
    if diff > 0:
        return f"(+{diff:.1f}%▲)"
    elif diff < 0:
        return f"({diff:.1f}%▼)"
    return ""

def metrics(d: dict) -> dict:
    """raw dict → 파생 지표 포함 dict"""
    c   = d.get('cost', 0)
    imp = d.get('impressions', 0)
    clk = d.get('clicks', 0)
    pur = d.get('purchases', 0)
    rev = d.get('revenue', 0)
    cp  = d.get('cpas_purchases', 0)
    cr  = d.get('cpas_revenue', 0)
    return {
        'cost': c, 'impressions': imp, 'clicks': clk,
        'purchases': pur, 'revenue': rev,
        'cpas_purchases': cp, 'cpas_revenue': cr,
        'landing_page_views': d.get('landing_page_views', 0),
        'content_views': d.get('content_views', 0),
        'roas':      _d(rev, c) * 100,
        'ctr':       _d(clk, imp) * 100,
        'cpc':       _d(c, clk),
        'cpm':       _d(c, imp) * 1000,
        'cpa':       _d(c, pur),
        'aov':       _d(rev, pur),
        'cpas_roas': _d(cr, c) * 100,
        'cpas_cpa':  _d(c, cp),
    }


# ============================================================
# 자사몰 섹션
# ============================================================

def _own_section(m, prev, campaigns):
    L = []
    L.append("*[META — 자사몰]*")

    if m['cost'] <= 0:
        L.append("집행 없음")
        return L

    # 전일 파생
    p = prev or {}
    p_roas = _d(p.get('revenue', 0), p.get('cost', 0)) * 100 if p.get('cost') else 0
    p_ctr  = _d(p.get('clicks', 0), p.get('impressions', 0)) * 100 if p.get('impressions') else 0
    p_cpc  = _d(p.get('cost', 0), p.get('clicks', 0)) if p.get('clicks') else 0
    p_cpm  = _d(p.get('cost', 0), p.get('impressions', 0)) * 1000 if p.get('impressions') else 0
    p_cpa  = _d(p.get('cost', 0), p.get('purchases', 0)) if p.get('purchases') else 0

    # 지표 순서: 지출 → 구매전환값 → ROAS → 노출 → 링크클릭 → CTR → CPC → CPM → CPA
    L.append(f"- 지출: {won(m['cost'])}원 {chg(m['cost'], p.get('cost'))}")
    L.append(f"- 구매 전환값: {won(m['revenue'])}원 {chg(m['revenue'], p.get('revenue'))}")
    L.append(f"- ROAS: {roas_x(m['roas'])} {chg(m['roas'], p_roas)}")
    L.append(f"- 노출: {won(m['impressions'])} {chg(m['impressions'], p.get('impressions'))}")
    L.append(f"- 링크 클릭: {won(m['clicks'])} {chg(m['clicks'], p.get('clicks'))}")
    L.append(f"- CTR: {pct(m['ctr'])}% {chg(m['ctr'], p_ctr)}")
    L.append(f"- CPC: {won(m['cpc'])}원 {chg(m['cpc'], p_cpc)}")
    L.append(f"- CPM: {won(m['cpm'])}원 {chg(m['cpm'], p_cpm)}")
    L.append(f"- CPA: {won(m['cpa'])}원 {chg(m['cpa'], p_cpa)}")

    # KPI 경고
    warnings = []
    if m['roas'] < KPI['roas_warning']:
        warnings.append(f"ROAS {roas_x(m['roas'])} 경고선 미달")
    if m['cpm'] > KPI['cpm_warning']:
        warnings.append(f"CPM {won(m['cpm'])}원 경고선 초과")
    if warnings:
        L.append(f"_⚠️ {' / '.join(warnings)}_")

    # 캠페인별 상세
    if campaigns:
        L.append("")
        L.append("*캠페인별:*")
        for c in campaigns:
            cm = metrics(c)
            if cm['cost'] <= 0:
                continue
            name = c.get('campaign_name', '-')

            L.append("")
            L.append(f"> *{name}*")
            # 구매 캠페인
            if cm['purchases'] > 0:
                L.append(f"> 지출 {won(cm['cost'])}원 | 전환값 {won(cm['revenue'])}원 | ROAS {roas_x(cm['roas'])} | 구매 {int(cm['purchases'])}건 | CPA {won(cm['cpa'])}원")
            # 콘텐츠조회 캠페인
            elif cm['content_views'] > 0:
                cpr = won(_d(cm['cost'], cm['content_views']))
                L.append(f"> 지출 {won(cm['cost'])}원 | 콘텐츠조회 {int(cm['content_views'])}건 | 결과당비용 {cpr}원")
            # LP조회 캠페인
            elif cm['landing_page_views'] > 0:
                cpr = won(_d(cm['cost'], cm['landing_page_views']))
                L.append(f"> 지출 {won(cm['cost'])}원 | LP조회 {int(cm['landing_page_views'])}건 | 결과당비용 {cpr}원")
            else:
                L.append(f"> 지출 {won(cm['cost'])}원 | 클릭 {int(cm['clicks'])}")
            L.append(f"> CTR {pct(cm['ctr'])}% | CPC {won(cm['cpc'])}원 | CPM {won(cm['cpm'])}원")

    # 자동 코멘트
    L.append("")
    L.append("*코멘트:*")
    if p.get('cost', 0) > 0:
        diff = m['roas'] - p_roas
        L.append(f"- ROAS {roas_x(m['roas'])} 전일비 {abs(diff):.1f}%p {'상승' if diff > 0 else '하락'}")
    else:
        L.append(f"- ROAS {roas_x(m['roas'])}")

    if campaigns:
        active = [c for c in campaigns if c.get('cost', 0) > 0 and c.get('revenue', 0) > 0]
        if active:
            best  = max(active, key=lambda x: _d(x.get('revenue', 0), x.get('cost', 0)))
            worst = min(active, key=lambda x: _d(x.get('revenue', 0), x.get('cost', 0)))
            br = _d(best['revenue'], best['cost']) * 100
            wr = _d(worst['revenue'], worst['cost']) * 100
            L.append(f"- [{best['campaign_name']}] ROAS {roas_x(br)} 최고 효율 → 예산 확대 검토")
            if best['campaign_name'] != worst['campaign_name']:
                L.append(f"- [{worst['campaign_name']}] ROAS {roas_x(wr)} 최저 → 소재/타겟 재검토")

    return L


# ============================================================
# 스마트스토어 협력광고 섹션
# ============================================================

def _ss_section(m, prev, campaigns):
    L = []
    L.append("*[META — 스마트스토어 · 협력광고]*")

    if m['cost'] <= 0:
        L.append("집행 없음")
        return L

    p = prev or {}
    p_cpas_roas = _d(p.get('cpas_revenue', 0), p.get('cost', 0)) * 100 if p.get('cost') else 0
    p_ctr  = _d(p.get('clicks', 0), p.get('impressions', 0)) * 100 if p.get('impressions') else 0
    p_cpc  = _d(p.get('cost', 0), p.get('clicks', 0)) if p.get('clicks') else 0
    p_cpm  = _d(p.get('cost', 0), p.get('impressions', 0)) * 1000 if p.get('impressions') else 0
    p_cpas_cpa = _d(p.get('cost', 0), p.get('cpas_purchases', 0)) if p.get('cpas_purchases') else 0

    # 지표 순서: 지출 → 구매전환값 → ROAS → 노출 → 링크클릭 → CTR → CPC → CPM → CPA
    L.append(f"- 지출: {won(m['cost'])}원 {chg(m['cost'], p.get('cost'))}")

    if m['cpas_revenue'] > 0 or m['cpas_purchases'] > 0:
        L.append(f"- 구매 전환값: {won(m['cpas_revenue'])}원 {chg(m['cpas_revenue'], p.get('cpas_revenue'))}")
        L.append(f"- ROAS: {roas_x(m['cpas_roas'])} {chg(m['cpas_roas'], p_cpas_roas)}")
    else:
        L.append(f"- 구매 전환값: — _(API 미수신)_")
        L.append(f"- ROAS: — _(API 미수신)_")

    L.append(f"- 노출: {won(m['impressions'])} {chg(m['impressions'], p.get('impressions'))}")
    L.append(f"- 링크 클릭: {won(m['clicks'])} {chg(m['clicks'], p.get('clicks'))}")
    L.append(f"- CTR: {pct(m['ctr'])}% {chg(m['ctr'], p_ctr)}")
    L.append(f"- CPC: {won(m['cpc'])}원 {chg(m['cpc'], p_cpc)}")
    L.append(f"- CPM: {won(m['cpm'])}원 {chg(m['cpm'], p_cpm)}")

    if m['cpas_purchases'] > 0:
        L.append(f"- CPA: {won(m['cpas_cpa'])}원 {chg(m['cpas_cpa'], p_cpas_cpa)}")
    else:
        L.append(f"- CPA: — _(API 미수신)_")

    # KPI 경고
    if m['cpas_revenue'] > 0 and m['cpas_roas'] < KPI['roas_warning']:
        L.append(f"_⚠️ ROAS {roas_x(m['cpas_roas'])} 경고선 미달_")

    # 캠페인별 상세
    if campaigns:
        L.append("")
        L.append("*캠페인별:*")
        for c in campaigns:
            cm = metrics(c)
            if cm['cost'] <= 0:
                continue
            name = c.get('campaign_name', '-')

            L.append("")
            L.append(f"> *{name}*")
            if cm['cpas_purchases'] > 0:
                L.append(f"> 지출 {won(cm['cost'])}원 | 전환값 {won(cm['cpas_revenue'])}원 | ROAS {roas_x(cm['cpas_roas'])} | 구매 {int(cm['cpas_purchases'])}건 | CPA {won(cm['cpas_cpa'])}원")
            else:
                L.append(f"> 지출 {won(cm['cost'])}원 | 클릭 {int(cm['clicks'])}")
            L.append(f"> CTR {pct(cm['ctr'])}% | CPC {won(cm['cpc'])}원 | CPM {won(cm['cpm'])}원")

    return L


# ============================================================
# 메인 생성 함수
# ============================================================

def _cafe24_section(c24, prev_c24):
    """카페24 자사몰 커머스 수치 섹션"""
    L = []
    L.append("*[커머스 — 자사몰 (카페24)]*")

    if not c24 or c24.get('order_count', 0) == 0:
        L.append("주문 없음")
        return L

    p = prev_c24 or {}

    L.append(f"- 순매출: {won(c24['paid_amount'])}원 {chg(c24['paid_amount'], p.get('paid_amount'))}")
    L.append(f"- 주문 건수: {c24['order_count']}건 {chg(c24['order_count'], p.get('order_count'))}")
    L.append(f"- 구매자 수: {c24['unique_customers']}명 {chg(c24['unique_customers'], p.get('unique_customers'))}")
    L.append(f"- 객단가: {won(c24['avg_order_value'])}원 {chg(c24['avg_order_value'], p.get('avg_order_value'))}")

    return L


def generate_draft(
    own_account: dict,
    ss_account: dict,
    date_str: str,
    own_campaigns: list = None,
    ss_campaigns: list = None,
    prev_own: dict = None,
    prev_ss: dict = None,
    cafe24_data: dict = None,
    prev_cafe24: dict = None,
) -> str:
    dt      = datetime.strptime(date_str, '%Y-%m-%d')
    weekday = WEEKDAY_KO[dt.weekday()]
    header  = f"{dt.year}-{dt.month:02d}-{dt.day:02d}({weekday})"

    own_m = metrics(own_account or {})
    ss_m  = metrics(ss_account  or {})

    L = []
    L.append(f"*{header} Re:NK Daily Comments*")
    L.append("")
    L.append(DIV)
    L.append("")

    # 자사몰
    L.extend(_own_section(own_m, prev_own or {}, own_campaigns or []))
    L.append("")
    L.append(DIV)
    L.append("")

    # 스마트스토어
    L.extend(_ss_section(ss_m, prev_ss or {}, ss_campaigns or []))

    # 카페24 커머스 수치 (API 수집 시)
    if cafe24_data and cafe24_data.get('order_count', 0) > 0:
        L.append("")
        L.append(DIV)
        L.append("")
        L.extend(_cafe24_section(cafe24_data, prev_cafe24 or {}))

    return '\n'.join(L)


# ============================================================
# 파일 저장
# ============================================================

def save_draft(content: str, date_str: str, base_dir: str) -> str:
    draft_dir = os.path.join(base_dir, 'slack_draft')
    os.makedirs(draft_dir, exist_ok=True)
    filename  = f"slack_draft_{date_str.replace('-', '')}.txt"
    filepath  = os.path.join(draft_dir, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    return filepath


# ============================================================
# 테스트
# ============================================================

if __name__ == '__main__':
    sample_own = {
        'cost': 840815, 'impressions': 25669, 'clicks': 576,
        'purchases': 9, 'revenue': 712000,
        'landing_page_views': 120, 'content_views': 625,
    }
    prev_own = {
        'cost': 795000, 'impressions': 22100, 'clicks': 510,
        'purchases': 7, 'revenue': 442000,
        'landing_page_views': 105, 'content_views': 580,
    }
    sample_ss = {
        'cost': 142044, 'impressions': 44200, 'clicks': 610,
        'purchases': 0, 'revenue': 0,
        'cpas_purchases': 5, 'cpas_revenue': 389000,
        'landing_page_views': 0, 'content_views': 0,
    }
    prev_ss = {
        'cost': 138000, 'impressions': 41000, 'clicks': 580,
        'purchases': 0, 'revenue': 0,
        'cpas_purchases': 3, 'cpas_revenue': 245000,
        'landing_page_views': 0, 'content_views': 0,
    }
    own_campaigns = [
        {'campaign_name': '커머스_전환수_자사몰_미드샷앨범_상시_260301', 'cost': 325453, 'impressions': 8200, 'clicks': 198, 'purchases': 4, 'revenue': 395000, 'landing_page_views': 0, 'content_views': 0},
        {'campaign_name': '커머스_전환수_자사몰_미드샷앨범_리타겟_260301', 'cost': 394575, 'impressions': 5200, 'clicks': 118, 'purchases': 3, 'revenue': 193000, 'landing_page_views': 0, 'content_views': 0},
        {'campaign_name': '커머스_전환수_자사몰_미드샷앨범_상시2_260301', 'cost': 86241, 'impressions': 3400, 'clicks': 72, 'purchases': 2, 'revenue': 124000, 'landing_page_views': 0, 'content_views': 0},
        {'campaign_name': '커머스_CAPI_퍼널별_컨텐츠조회_자사몰_260301', 'cost': 18028, 'impressions': 6800, 'clicks': 142, 'purchases': 0, 'revenue': 0, 'landing_page_views': 0, 'content_views': 625},
        {'campaign_name': '커머스_전환_자사몰_트래픽_260224', 'cost': 16518, 'impressions': 2069, 'clicks': 46, 'purchases': 0, 'revenue': 0, 'landing_page_views': 120, 'content_views': 0},
    ]
    ss_campaigns = [
        {'campaign_name': '[Valen]SS_트래픽_리타겟', 'cost': 82000, 'impressions': 25000, 'clicks': 350, 'purchases': 0, 'revenue': 0, 'cpas_purchases': 3, 'cpas_revenue': 245000, 'landing_page_views': 0, 'content_views': 0},
        {'campaign_name': '[Valen]SS_신규_전환', 'cost': 60044, 'impressions': 19200, 'clicks': 260, 'purchases': 0, 'revenue': 0, 'cpas_purchases': 2, 'cpas_revenue': 144000, 'landing_page_views': 0, 'content_views': 0},
    ]

    today = datetime.now().strftime('%Y-%m-%d')
    draft = generate_draft(
        own_account=sample_own, ss_account=sample_ss, date_str=today,
        own_campaigns=own_campaigns, ss_campaigns=ss_campaigns,
        prev_own=prev_own, prev_ss=prev_ss,
    )
    print(draft)
    path = save_draft(draft, today, os.path.dirname(os.path.abspath(__file__)))
    print(f"\n→ 저장: {path}")
