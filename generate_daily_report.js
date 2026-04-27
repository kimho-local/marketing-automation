#!/usr/bin/env node
/**
 * Re:NK 일간 통합 보고서 생성기 (docx) v2
 * ==========================================
 * JSON 데이터 파일 → 전문 포맷 .docx 보고서 출력
 *
 * 사용법:
 *   node generate_daily_report.js data.json output.docx
 */

const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, HeadingLevel, BorderStyle, WidthType,
  ShadingType, PageNumber, LevelFormat, PageBreak
} = require("docx");

// ── 디자인 시스템 ──
const C = {
  primary:    "1B3A5C",   // 네이비 (제목, 강조)
  accent:     "2B6CB0",   // 블루 (소제목, 링크)
  headerBg:   "1B3A5C",   // 테이블 헤더 배경
  headerText: "FFFFFF",   // 테이블 헤더 텍스트
  altRow:     "F0F4F8",   // 테이블 짝수행
  up:         "1A7F37",   // 상승 (초록)
  down:       "CF222E",   // 하락 (빨강)
  muted:      "8B95A1",   // 보조 텍스트
  border:     "D1D9E0",   // 테이블 테두리
  divider:    "2B6CB0",   // 섹션 구분선
};

// A4, 좌우 1200 여백 → 콘텐츠 폭 9506
const PAGE_W = 11906;
const MARGIN = { top: 1200, right: 1200, bottom: 1200, left: 1200 };
const FULL_W = PAGE_W - MARGIN.left - MARGIN.right; // 9506

const FONT = "Arial";
const SZ = { xs: 16, sm: 18, md: 20, lg: 24, xl: 28, xxl: 36 };

const thinBorder = { style: BorderStyle.SINGLE, size: 1, color: C.border };
const borders = { top: thinBorder, bottom: thinBorder, left: thinBorder, right: thinBorder };
const noBorder = { style: BorderStyle.NONE, size: 0 };
const noBorders = { top: noBorder, bottom: noBorder, left: noBorder, right: noBorder };
const cellPad = { top: 70, bottom: 70, left: 120, right: 120 };
const tightPad = { top: 50, bottom: 50, left: 80, right: 80 };

// ── 네이버 브랜드검색(BS) 일할계산 ──
const BS_MONTHLY_COST = 2530000; // 월 253만원
function bsDailyCost(dateStr) {
  const d = new Date(dateStr + "T00:00:00");
  const year = d.getFullYear(), month = d.getMonth() + 1;
  const daysInMonth = new Date(year, month, 0).getDate();
  return Math.round(BS_MONTHLY_COST / daysInMonth);
}

/** 네이버 데이터에 BS 일할 광고비 보정 (API가 0원 반환하는 경우) */
function applyBsCost(naverObj, dateStr) {
  if (!naverObj || !dateStr) return naverObj || {};
  const obj = JSON.parse(JSON.stringify(naverObj)); // deep copy
  const bt = obj.by_type || {};
  if (!bt['브랜드검색']) {
    bt['브랜드검색'] = { cost: 0, impressions: 0, clicks: 0, conversions: 0, revenue: 0, purchase_count: 0, purchase_revenue: 0 };
  }
  if ((bt['브랜드검색'].cost || 0) === 0) {
    const daily = bsDailyCost(dateStr);
    bt['브랜드검색'].cost = daily;
    obj.by_type = bt;
    // 총광고비에도 반영
    if (obj.sa) obj.sa.cost = (obj.sa.cost || 0) + daily;
  }
  return obj;
}

function getPrevDateStr(dateStr) {
  const d = new Date(dateStr + "T00:00:00");
  d.setDate(d.getDate() - 1);
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${mm}-${dd}`;
}

function shortDate(dateStr) {
  const d = new Date(dateStr + "T00:00:00");
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

// ── 유틸 ──
function won(v) {
  // toLocaleString can insert non-breaking spaces → replace with normal space then trim
  return Math.round(v).toLocaleString("en-US").replace(/\u00A0/g, "").replace(/\s/g, "");
}
function pct(v) { return v.toFixed(2) + "%"; }
function roasP(v) { return v.toFixed(1) + "%"; }
function div(a, b) { return b ? a / b : 0; }

function chg(cur, prev) {
  if (!prev || prev === 0) return null;
  const d = ((cur - prev) / Math.abs(prev)) * 100;
  if (d > 0) return { text: `+${d.toFixed(1)}%`, color: C.up };
  if (d < 0) return { text: `${d.toFixed(1)}%`, color: C.down };
  return { text: "0.0%", color: C.muted };
}

// ── 셀 생성 헬퍼 ──
function cell(text, w, opts = {}) {
  const { bold, fill, color, align, sz, span, pad } = {
    bold: false, fill: "FFFFFF", color: "000000",
    align: AlignmentType.LEFT, sz: SZ.sm, span: 1, pad: cellPad, ...opts
  };
  return new TableCell({
    borders,
    width: { size: w, type: WidthType.DXA },
    shading: { fill, type: ShadingType.CLEAR },
    margins: pad,
    columnSpan: span,
    children: [new Paragraph({
      alignment: align,
      children: [new TextRun({ text: String(text), bold, font: FONT, size: sz, color })],
    })],
  });
}

function chgCell(cur, prev, w, fill) {
  const c = chg(cur, prev);
  const text = c ? `(${c.text})` : "-";
  const color = c ? c.color : C.muted;
  return cell(text, w, { fill, color, align: AlignmentType.CENTER, sz: SZ.xs });
}

// ── 섹션 구분선 ──
function divider() {
  return new Paragraph({
    spacing: { before: 300, after: 300 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 3, color: C.divider, space: 1 } },
    children: [],
  });
}

// ── 섹션 제목 ──
function sectionTitle(text) {
  return new Paragraph({
    spacing: { before: 100, after: 200 },
    children: [new TextRun({ text, bold: true, font: FONT, size: SZ.xl, color: C.primary })],
  });
}

function subTitle(text) {
  return new Paragraph({
    spacing: { before: 200, after: 100 },
    children: [new TextRun({ text, bold: true, font: FONT, size: SZ.md, color: C.accent })],
  });
}

// ── 매체 지표 테이블 (가로형: 행=날짜, 열=지표 + 증감률) ──
function metricTable(m, p, dateStr) {
  const pp = p || {};
  const curLabel = shortDate(dateStr);
  const prevLabel = shortDate(getPrevDateStr(dateStr));

  // 파생 지표 — 당일
  const roas = div(m.revenue, m.cost) * 100;
  const ctr = div(m.clicks, m.impressions) * 100;
  const cpc = div(m.cost, m.clicks);
  const cpm = div(m.cost, m.impressions) * 1000;
  const cpa = div(m.cost, m.purchases);

  // 파생 지표 — 전일
  const pRoas = pp.cost ? div(pp.revenue, pp.cost) * 100 : 0;
  const pCtr = pp.impressions ? div(pp.clicks, pp.impressions) * 100 : 0;
  const pCpc = pp.clicks ? div(pp.cost, pp.clicks) : 0;
  const pCpm = pp.impressions ? div(pp.cost, pp.impressions) * 1000 : 0;
  const pCpa = pp.purchases ? div(pp.cost, pp.purchases) : 0;

  // 11열, 합계 = 9506
  const cw = [900, 900, 800, 750, 700, 1000, 856, 750, 850, 900, 1100];
  const tp = tightPad;
  const XS = SZ.xs;
  const R = AlignmentType.RIGHT;
  const CT = AlignmentType.CENTER;

  const headers = ["날짜", "광고비", "노출", "클릭", "구매", "매출(전환값)", "ROAS(%)", "CTR(%)", "CPC", "CPM", "CPA"];

  const headerRow = new TableRow({
    children: headers.map((h, i) =>
      cell(h, cw[i], { bold: true, fill: C.headerBg, color: C.headerText, sz: XS, align: CT, pad: tp })
    ),
  });

  // 전일 행
  const hasPrev = (pp.cost || 0) > 0 || (pp.impressions || 0) > 0;
  const prevRow = hasPrev ? new TableRow({
    children: [
      cell(prevLabel, cw[0], { bold: true, fill: C.altRow, sz: XS, align: CT, pad: tp }),
      cell(won(pp.cost || 0), cw[1], { fill: C.altRow, sz: XS, align: R, pad: tp }),
      cell(won(pp.impressions || 0), cw[2], { fill: C.altRow, sz: XS, align: R, pad: tp }),
      cell(won(pp.clicks || 0), cw[3], { fill: C.altRow, sz: XS, align: R, pad: tp }),
      cell(String(pp.purchases || 0), cw[4], { fill: C.altRow, sz: XS, align: R, pad: tp }),
      cell(won(pp.revenue || 0), cw[5], { fill: C.altRow, sz: XS, align: R, pad: tp }),
      cell(roasP(pRoas), cw[6], { fill: C.altRow, sz: XS, align: R, pad: tp }),
      cell(pct(pCtr), cw[7], { fill: C.altRow, sz: XS, align: R, pad: tp }),
      cell(won(Math.round(pCpc)), cw[8], { fill: C.altRow, sz: XS, align: R, pad: tp }),
      cell(won(Math.round(pCpm)), cw[9], { fill: C.altRow, sz: XS, align: R, pad: tp }),
      cell(won(Math.round(pCpa)), cw[10], { fill: C.altRow, sz: XS, align: R, pad: tp }),
    ],
  }) : null;

  // 당일 행
  const curRow = new TableRow({
    children: [
      cell(curLabel, cw[0], { bold: true, fill: "FFFFFF", sz: XS, align: CT, pad: tp }),
      cell(won(m.cost), cw[1], { fill: "FFFFFF", sz: XS, align: R, pad: tp }),
      cell(won(m.impressions), cw[2], { fill: "FFFFFF", sz: XS, align: R, pad: tp }),
      cell(won(m.clicks), cw[3], { fill: "FFFFFF", sz: XS, align: R, pad: tp }),
      cell(String(m.purchases || 0), cw[4], { fill: "FFFFFF", sz: XS, align: R, pad: tp }),
      cell(won(m.revenue), cw[5], { fill: "FFFFFF", sz: XS, align: R, pad: tp }),
      cell(roasP(roas), cw[6], { fill: "FFFFFF", sz: XS, align: R, pad: tp }),
      cell(pct(ctr), cw[7], { fill: "FFFFFF", sz: XS, align: R, pad: tp }),
      cell(won(Math.round(cpc)), cw[8], { fill: "FFFFFF", sz: XS, align: R, pad: tp }),
      cell(won(Math.round(cpm)), cw[9], { fill: "FFFFFF", sz: XS, align: R, pad: tp }),
      cell(won(Math.round(cpa)), cw[10], { fill: "FFFFFF", sz: XS, align: R, pad: tp }),
    ],
  });

  // 증감률 행
  const changes = [
    chg(m.cost, pp.cost),
    chg(m.impressions, pp.impressions),
    chg(m.clicks, pp.clicks),
    chg(m.purchases, pp.purchases),
    chg(m.revenue, pp.revenue),
    chg(roas, pRoas),
    chg(ctr, pCtr),
    chg(cpc, pCpc),
    chg(cpm, pCpm),
    chg(cpa, pCpa),
  ];

  const chgRow = hasPrev ? new TableRow({
    children: [
      cell("증감률", cw[0], { bold: true, fill: C.altRow, sz: XS, align: CT, pad: tp }),
      ...changes.map((ch, i) => {
        const text = ch ? ch.text : "-";
        const clr = ch ? ch.color : C.muted;
        return cell(text, cw[i + 1], { fill: C.altRow, color: clr, sz: XS, align: CT, pad: tp });
      }),
    ],
  }) : null;

  const rows = [headerRow];
  if (prevRow) rows.push(prevRow);
  rows.push(curRow);
  if (chgRow) rows.push(chgRow);

  return new Table({
    width: { size: FULL_W, type: WidthType.DXA },
    columnWidths: cw,
    rows,
  });
}

// ── 캠페인 테이블 (5열, 전체 폭) ──
function campaignTable(campaigns, isCpas) {
  if (!campaigns || campaigns.length === 0) return [];
  const active = campaigns.filter(c => c.cost > 0);
  if (active.length === 0) return [];

  const cw = [3506, 1500, 1500, 1500, 1500]; // 합계 = 9506

  const header = new TableRow({
    children: [
      cell("캠페인", cw[0], { bold: true, fill: C.accent, color: C.headerText }),
      cell("지출", cw[1], { bold: true, fill: C.accent, color: C.headerText, align: AlignmentType.RIGHT }),
      cell("전환값", cw[2], { bold: true, fill: C.accent, color: C.headerText, align: AlignmentType.RIGHT }),
      cell("ROAS", cw[3], { bold: true, fill: C.accent, color: C.headerText, align: AlignmentType.CENTER }),
      cell("CPA", cw[4], { bold: true, fill: C.accent, color: C.headerText, align: AlignmentType.RIGHT }),
    ],
  });

  const dataRows = active.map((c, i) => {
    const rev = isCpas ? (c.cpas_revenue || 0) : (c.revenue || 0);
    const pur = isCpas ? (c.cpas_purchases || 0) : (c.purchases || 0);
    const roas = div(rev, c.cost) * 100;
    const cpa = div(c.cost, pur);
    const bg = i % 2 === 0 ? "FFFFFF" : C.altRow;
    const name = (c.campaign_name || "-").substring(0, 35);

    return new TableRow({
      children: [
        cell(name, cw[0], { fill: bg, sz: SZ.xs }),
        cell(won(c.cost) + "원", cw[1], { fill: bg, align: AlignmentType.RIGHT }),
        cell(rev > 0 ? won(rev) + "원" : "-", cw[2], { fill: bg, align: AlignmentType.RIGHT }),
        cell(rev > 0 ? roasP(roas) : "-", cw[3], {
          fill: bg, align: AlignmentType.CENTER,
          color: rev > 0 && roas < 100 ? C.down : "000000",
        }),
        cell(pur > 0 ? won(cpa) + "원" : "-", cw[4], { fill: bg, align: AlignmentType.RIGHT }),
      ],
    });
  });

  return [
    subTitle("캠페인별 상세"),
    new Table({
      width: { size: FULL_W, type: WidthType.DXA },
      columnWidths: cw,
      rows: [header, ...dataRows],
    }),
  ];
}

// ── 간략 지표 테이블 (2열, 전체 폭 — 네이버/구글용) ──
function simpleMetricTable(rows) {
  const cw = [3000, 6506]; // 합계 = 9506

  const header = new TableRow({
    children: [
      cell("지표", cw[0], { bold: true, fill: C.headerBg, color: C.headerText }),
      cell("수치", cw[1], { bold: true, fill: C.headerBg, color: C.headerText, align: AlignmentType.RIGHT }),
    ],
  });

  const dataRows = rows.map((r, i) => {
    const bg = i % 2 === 0 ? C.altRow : "FFFFFF";
    return new TableRow({
      children: [
        cell(r[0], cw[0], { bold: true, fill: bg }),
        cell(r[1], cw[1], { fill: bg, align: AlignmentType.RIGHT }),
      ],
    });
  });

  return new Table({
    width: { size: FULL_W, type: WidthType.DXA },
    columnWidths: cw,
    rows: [header, ...dataRows],
  });
}

// ── 카페24 커머스 테이블 (가로형: 행=날짜, 열=지표 + 증감률) ──
function cafe24Table(c, pc, dateStr) {
  const pp = pc || {};
  const curLabel = shortDate(dateStr);
  const prevLabel = shortDate(getPrevDateStr(dateStr));

  const net = c.paid_amount - c.refund_amount;
  const pNet = (pp.paid_amount || 0) - (pp.refund_amount || 0);

  // 7열, 합계 = 9506
  const cw = [1106, 1500, 1200, 1500, 1200, 1200, 1800];
  const tp = tightPad;
  const XS = SZ.xs;
  const R = AlignmentType.RIGHT;
  const CT = AlignmentType.CENTER;

  const headers = ["날짜", "결제합계", "환불합계", "순매출", "주문건수", "구매자수", "객단가"];

  const headerRow = new TableRow({
    children: headers.map((h, i) =>
      cell(h, cw[i], { bold: true, fill: C.headerBg, color: C.headerText, sz: XS, align: CT, pad: tp })
    ),
  });

  const hasPrev = (pp.paid_amount || 0) > 0 || (pp.order_count || 0) > 0;

  const prevRow = hasPrev ? new TableRow({
    children: [
      cell(prevLabel, cw[0], { bold: true, fill: C.altRow, sz: XS, align: CT, pad: tp }),
      cell(won(pp.paid_amount || 0), cw[1], { fill: C.altRow, sz: XS, align: R, pad: tp }),
      cell(won(pp.refund_amount || 0), cw[2], { fill: C.altRow, sz: XS, align: R, pad: tp }),
      cell(won(pNet), cw[3], { fill: C.altRow, sz: XS, align: R, pad: tp }),
      cell(String(pp.order_count || 0), cw[4], { fill: C.altRow, sz: XS, align: R, pad: tp }),
      cell(String(pp.unique_customers || 0), cw[5], { fill: C.altRow, sz: XS, align: R, pad: tp }),
      cell(won(pp.avg_order_value || 0), cw[6], { fill: C.altRow, sz: XS, align: R, pad: tp }),
    ],
  }) : null;

  const curRow = new TableRow({
    children: [
      cell(curLabel, cw[0], { bold: true, fill: "FFFFFF", sz: XS, align: CT, pad: tp }),
      cell(won(c.paid_amount), cw[1], { fill: "FFFFFF", sz: XS, align: R, pad: tp }),
      cell(won(c.refund_amount), cw[2], { fill: "FFFFFF", sz: XS, align: R, pad: tp }),
      cell(won(net), cw[3], { fill: "FFFFFF", sz: XS, align: R, pad: tp }),
      cell(String(c.order_count), cw[4], { fill: "FFFFFF", sz: XS, align: R, pad: tp }),
      cell(String(c.unique_customers), cw[5], { fill: "FFFFFF", sz: XS, align: R, pad: tp }),
      cell(won(c.avg_order_value), cw[6], { fill: "FFFFFF", sz: XS, align: R, pad: tp }),
    ],
  });

  const changes = [
    chg(c.paid_amount, pp.paid_amount),
    chg(c.refund_amount, pp.refund_amount),
    chg(net, pNet),
    chg(c.order_count, pp.order_count),
    chg(c.unique_customers, pp.unique_customers),
    chg(c.avg_order_value, pp.avg_order_value),
  ];

  const chgRow = hasPrev ? new TableRow({
    children: [
      cell("증감률", cw[0], { bold: true, fill: C.altRow, sz: XS, align: CT, pad: tp }),
      ...changes.map((ch, i) => {
        const text = ch ? ch.text : "-";
        const clr = ch ? ch.color : C.muted;
        return cell(text, cw[i + 1], { fill: C.altRow, color: clr, sz: XS, align: CT, pad: tp });
      }),
    ],
  }) : null;

  const rows = [headerRow];
  if (prevRow) rows.push(prevRow);
  rows.push(curRow);
  if (chgRow) rows.push(chgRow);

  return new Table({
    width: { size: FULL_W, type: WidthType.DXA },
    columnWidths: cw,
    rows,
  });
}

// ── 스마트스토어 커머스 테이블 (가로형: 행=날짜, 열=지표 + 증감률) ──
function smartstoreTable(s, ps, dateStr) {
  const pp = ps || {};
  const curLabel = shortDate(dateStr);
  const prevLabel = shortDate(getPrevDateStr(dateStr));

  const net = (s.paid_amount || 0) - (s.refund_amount || 0);
  const pNet = (pp.paid_amount || 0) - (pp.refund_amount || 0);

  // 7열, 합계 = 9506
  const cw = [1106, 1500, 1200, 1500, 1200, 1200, 1800];
  const tp = tightPad;
  const XS = SZ.xs;
  const R = AlignmentType.RIGHT;
  const CT = AlignmentType.CENTER;

  const headers = ["날짜", "결제합계", "환불합계", "순매출", "주문건수", "결제자수", "객단가"];

  const headerRow = new TableRow({
    children: headers.map((h, i) =>
      cell(h, cw[i], { bold: true, fill: C.headerBg, color: C.headerText, sz: XS, align: CT, pad: tp })
    ),
  });

  const hasPrev = (pp.paid_amount || 0) > 0 || (pp.order_count || 0) > 0;

  const prevRow = hasPrev ? new TableRow({
    children: [
      cell(prevLabel, cw[0], { bold: true, fill: C.altRow, sz: XS, align: CT, pad: tp }),
      cell(won(pp.paid_amount || 0), cw[1], { fill: C.altRow, sz: XS, align: R, pad: tp }),
      cell(won(pp.refund_amount || 0), cw[2], { fill: C.altRow, sz: XS, align: R, pad: tp }),
      cell(won(pNet), cw[3], { fill: C.altRow, sz: XS, align: R, pad: tp }),
      cell(String(pp.order_count || 0), cw[4], { fill: C.altRow, sz: XS, align: R, pad: tp }),
      cell(String(pp.unique_customers || 0), cw[5], { fill: C.altRow, sz: XS, align: R, pad: tp }),
      cell(won(pp.avg_order_value || 0), cw[6], { fill: C.altRow, sz: XS, align: R, pad: tp }),
    ],
  }) : null;

  const avgOV = s.unique_customers > 0 ? Math.round(net / s.unique_customers) : (s.avg_order_value || 0);
  const curRow = new TableRow({
    children: [
      cell(curLabel, cw[0], { bold: true, fill: "FFFFFF", sz: XS, align: CT, pad: tp }),
      cell(won(s.paid_amount || 0), cw[1], { fill: "FFFFFF", sz: XS, align: R, pad: tp }),
      cell(won(s.refund_amount || 0), cw[2], { fill: "FFFFFF", sz: XS, align: R, pad: tp }),
      cell(won(net), cw[3], { fill: "FFFFFF", sz: XS, align: R, pad: tp }),
      cell(String(s.order_count || 0), cw[4], { fill: "FFFFFF", sz: XS, align: R, pad: tp }),
      cell(String(s.unique_customers || 0), cw[5], { fill: "FFFFFF", sz: XS, align: R, pad: tp }),
      cell(won(avgOV), cw[6], { fill: "FFFFFF", sz: XS, align: R, pad: tp }),
    ],
  });

  const pAvgOV = pp.unique_customers > 0 ? Math.round(pNet / pp.unique_customers) : (pp.avg_order_value || 0);
  const changes = [
    chg(s.paid_amount, pp.paid_amount),
    chg(s.refund_amount, pp.refund_amount),
    chg(net, pNet),
    chg(s.order_count, pp.order_count),
    chg(s.unique_customers, pp.unique_customers),
    chg(avgOV, pAvgOV),
  ];

  const chgRow = hasPrev ? new TableRow({
    children: [
      cell("증감률", cw[0], { bold: true, fill: C.altRow, sz: XS, align: CT, pad: tp }),
      ...changes.map((ch, i) => {
        const text = ch ? ch.text : "-";
        const clr = ch ? ch.color : C.muted;
        return cell(text, cw[i + 1], { fill: C.altRow, color: clr, sz: XS, align: CT, pad: tp });
      }),
    ],
  }) : null;

  const rows = [headerRow];
  if (prevRow) rows.push(prevRow);
  rows.push(curRow);
  if (chgRow) rows.push(chgRow);

  return new Table({
    width: { size: FULL_W, type: WidthType.DXA },
    columnWidths: cw,
    rows,
  });
}

// ── 네이버 매체별 상세 테이블 (파워링크/BS/쇼검) ──
function naverTypeTable(byType, title = "매체별 상세") {
  if (!byType || Object.keys(byType).length === 0) return [];

  const entries = Object.entries(byType).filter(([, td]) => td.cost > 0 || td.clicks > 0);
  if (entries.length === 0) return [];

  // 8열, 합계 = 9506
  const cw = [1300, 1100, 900, 800, 1200, 1100, 1006, 2100];
  const tp = tightPad;
  const XS = SZ.xs;
  const R = AlignmentType.RIGHT;
  const CT = AlignmentType.CENTER;

  const headers = ["유형", "광고비", "노출", "클릭", "전환매출", "ROAS(%)", "전환수", "CPC"];

  const headerRow = new TableRow({
    children: headers.map((h, i) =>
      cell(h, cw[i], { bold: true, fill: C.accent, color: C.headerText, sz: XS, align: CT, pad: tp })
    ),
  });

  const dataRows = entries.map(([tp_name, td], i) => {
    const bg = i % 2 === 0 ? "FFFFFF" : C.altRow;
    const rev = td.purchase_revenue || td.revenue || 0;
    const pur = td.purchase_count || td.conversions || 0;
    const roas = div(rev, td.cost) * 100;
    const cpc_val = div(td.cost, td.clicks);

    return new TableRow({
      children: [
        cell(tp_name, cw[0], { bold: true, fill: bg, sz: XS, pad: tp }),
        cell(won(td.cost), cw[1], { fill: bg, sz: XS, align: R, pad: tp }),
        cell(won(td.impressions || 0), cw[2], { fill: bg, sz: XS, align: R, pad: tp }),
        cell(won(td.clicks), cw[3], { fill: bg, sz: XS, align: R, pad: tp }),
        cell(rev > 0 ? won(rev) : "-", cw[4], { fill: bg, sz: XS, align: R, pad: tp }),
        cell(rev > 0 ? roasP(roas) : "-", cw[5], {
          fill: bg, sz: XS, align: CT, pad: tp,
          color: rev > 0 && roas < 100 ? C.down : "000000",
        }),
        cell(pur > 0 ? pur + "건" : "-", cw[6], { fill: bg, sz: XS, align: CT, pad: tp }),
        cell(td.clicks > 0 ? won(Math.round(cpc_val)) : "-", cw[7], { fill: bg, sz: XS, align: R, pad: tp }),
      ],
    });
  });

  return [
    subTitle(title),
    new Table({
      width: { size: FULL_W, type: WidthType.DXA },
      columnWidths: cw,
      rows: [headerRow, ...dataRows],
    }),
  ];
}

// ── 카페24 첫구매/재구매 테이블 ──
function cafe24BuyerTypeTable(c24, pc24, dateStr) {
  const first = c24.first_buyers || 0;
  const repeat = c24.repeat_buyers || 0;
  const total = first + repeat;
  const firstR = total > 0 ? (first / total * 100) : 0;
  const repeatR = total > 0 ? (repeat / total * 100) : 0;

  const pFirst = pc24.first_buyers || 0;
  const pRepeat = pc24.repeat_buyers || 0;
  const pTotal = pFirst + pRepeat;

  if (total === 0 && pTotal === 0) return [];

  const curLabel = shortDate(dateStr);
  const prevLabel = shortDate(getPrevDateStr(dateStr));

  // 6열, 합계 = 9506
  const cw = [1300, 1600, 1600, 1600, 1606, 1800];
  const tp = tightPad;
  const XS = SZ.xs;
  const R = AlignmentType.RIGHT;
  const CT = AlignmentType.CENTER;

  const headerRow = new TableRow({
    children: ["날짜", "첫구매", "재구매", "총 구매자", "첫구매 비율", "재구매 비율"].map((h, i) =>
      cell(h, cw[i], { bold: true, fill: C.accent, color: C.headerText, sz: XS, align: CT, pad: tp })
    ),
  });

  const hasPrev = pTotal > 0;
  const pFirstR = pTotal > 0 ? (pFirst / pTotal * 100) : 0;
  const pRepeatR = pTotal > 0 ? (pRepeat / pTotal * 100) : 0;

  const prevRow = hasPrev ? new TableRow({
    children: [
      cell(prevLabel, cw[0], { bold: true, fill: C.altRow, sz: XS, align: CT, pad: tp }),
      cell(pFirst + "명", cw[1], { fill: C.altRow, sz: XS, align: R, pad: tp }),
      cell(pRepeat + "명", cw[2], { fill: C.altRow, sz: XS, align: R, pad: tp }),
      cell(pTotal + "명", cw[3], { fill: C.altRow, sz: XS, align: R, pad: tp }),
      cell(pFirstR.toFixed(1) + "%", cw[4], { fill: C.altRow, sz: XS, align: CT, pad: tp }),
      cell(pRepeatR.toFixed(1) + "%", cw[5], { fill: C.altRow, sz: XS, align: CT, pad: tp }),
    ],
  }) : null;

  const curRow = new TableRow({
    children: [
      cell(curLabel, cw[0], { bold: true, fill: "FFFFFF", sz: XS, align: CT, pad: tp }),
      cell(first + "명", cw[1], { fill: "FFFFFF", sz: XS, align: R, pad: tp }),
      cell(repeat + "명", cw[2], { fill: "FFFFFF", sz: XS, align: R, pad: tp }),
      cell(total + "명", cw[3], { fill: "FFFFFF", sz: XS, align: R, pad: tp }),
      cell(firstR.toFixed(1) + "%", cw[4], { fill: "FFFFFF", sz: XS, align: CT, pad: tp }),
      cell(repeatR.toFixed(1) + "%", cw[5], { fill: "FFFFFF", sz: XS, align: CT, pad: tp }),
    ],
  });

  const changes = [
    chg(first, pFirst),
    chg(repeat, pRepeat),
    chg(total, pTotal),
    null, // 비율은 증감률 대신 %p
    null,
  ];

  // 비율 변화는 %p로 표시
  const firstRDiff = hasPrev ? firstR - pFirstR : null;
  const repeatRDiff = hasPrev ? repeatR - pRepeatR : null;

  const chgRow = hasPrev ? new TableRow({
    children: [
      cell("증감률", cw[0], { bold: true, fill: C.altRow, sz: XS, align: CT, pad: tp }),
      ...changes.slice(0, 3).map((ch, i) => {
        const text = ch ? ch.text : "-";
        const clr = ch ? ch.color : C.muted;
        return cell(text, cw[i + 1], { fill: C.altRow, color: clr, sz: XS, align: CT, pad: tp });
      }),
      cell(firstRDiff !== null ? `${firstRDiff > 0 ? "+" : ""}${firstRDiff.toFixed(1)}%p` : "-", cw[4], {
        fill: C.altRow, sz: XS, align: CT, pad: tp,
        color: firstRDiff > 0 ? C.up : (firstRDiff < 0 ? C.down : C.muted),
      }),
      cell(repeatRDiff !== null ? `${repeatRDiff > 0 ? "+" : ""}${repeatRDiff.toFixed(1)}%p` : "-", cw[5], {
        fill: C.altRow, sz: XS, align: CT, pad: tp,
        color: repeatRDiff > 0 ? C.up : (repeatRDiff < 0 ? C.down : C.muted),
      }),
    ],
  }) : null;

  const rows = [headerRow];
  if (prevRow) rows.push(prevRow);
  rows.push(curRow);
  if (chgRow) rows.push(chgRow);

  return [
    subTitle("첫구매 / 재구매 분석"),
    new Table({
      width: { size: FULL_W, type: WidthType.DXA },
      columnWidths: cw,
      rows,
    }),
  ];
}

// ── 상품 TOP 3 테이블 ──
function topProductTable(products) {
  if (!products || products.length === 0) return [];

  const cw = [600, 4906, 2200, 1800]; // 합계 = 9506

  const header = new TableRow({
    children: [
      cell("#", cw[0], { bold: true, fill: C.accent, color: C.headerText, align: AlignmentType.CENTER }),
      cell("상품명", cw[1], { bold: true, fill: C.accent, color: C.headerText }),
      cell("실결제금액", cw[2], { bold: true, fill: C.accent, color: C.headerText, align: AlignmentType.RIGHT }),
      cell("판매수량", cw[3], { bold: true, fill: C.accent, color: C.headerText, align: AlignmentType.CENTER }),
    ],
  });

  const dataRows = products.slice(0, 3).map((p, i) => {
    const bg = i % 2 === 0 ? "FFFFFF" : C.altRow;
    const name = (p.product_name || "-").substring(0, 45);
    return new TableRow({
      children: [
        cell(String(i + 1), cw[0], { bold: true, fill: bg, align: AlignmentType.CENTER }),
        cell(name, cw[1], { fill: bg, sz: SZ.xs }),
        cell(won(p.amount) + "원", cw[2], { fill: bg, align: AlignmentType.RIGHT }),
        cell(p.quantity + "개", cw[3], { fill: bg, align: AlignmentType.CENTER }),
      ],
    });
  });

  return [
    subTitle("상품 판매 TOP 3 (실결제금액 기준)"),
    new Table({
      width: { size: FULL_W, type: WidthType.DXA },
      columnWidths: cw,
      rows: [header, ...dataRows],
    }),
  ];
}

// ── GA4 개요 테이블 (가로형: 행=날짜, 열=지표) ──
function ga4OverviewTable(ov, pov, dateStr) {
  const pp = pov || {};
  const curLabel = shortDate(dateStr);
  const prevLabel = shortDate(getPrevDateStr(dateStr));

  // 9열, 합계 = 9506
  const cw = [900, 1000, 1000, 1000, 900, 1200, 1100, 1206, 1200];
  const tp = tightPad;
  const XS = SZ.xs;
  const R = AlignmentType.RIGHT;
  const CT = AlignmentType.CENTER;

  const headers = ["날짜", "세션", "사용자", "신규", "구매", "매출", "참여율(%)", "이탈률(%)", "평균체류(s)"];

  const headerRow = new TableRow({
    children: headers.map((h, i) =>
      cell(h, cw[i], { bold: true, fill: C.headerBg, color: C.headerText, sz: XS, align: CT, pad: tp })
    ),
  });

  const hasPrev = (pp.sessions || 0) > 0;
  const prevRow = hasPrev ? new TableRow({
    children: [
      cell(prevLabel, cw[0], { bold: true, fill: C.altRow, sz: XS, align: CT, pad: tp }),
      cell(won(pp.sessions || 0), cw[1], { fill: C.altRow, sz: XS, align: R, pad: tp }),
      cell(won(pp.users || 0), cw[2], { fill: C.altRow, sz: XS, align: R, pad: tp }),
      cell(won(pp.new_users || 0), cw[3], { fill: C.altRow, sz: XS, align: R, pad: tp }),
      cell(String(pp.purchases || 0), cw[4], { fill: C.altRow, sz: XS, align: R, pad: tp }),
      cell(won(pp.revenue || 0), cw[5], { fill: C.altRow, sz: XS, align: R, pad: tp }),
      cell(pct((pp.engagement_rate || 0) * 100), cw[6], { fill: C.altRow, sz: XS, align: R, pad: tp }),
      cell(pct((pp.bounce_rate || 0) * 100), cw[7], { fill: C.altRow, sz: XS, align: R, pad: tp }),
      cell(String(Math.round(pp.avg_session_duration || 0)), cw[8], { fill: C.altRow, sz: XS, align: R, pad: tp }),
    ],
  }) : null;

  const curRow = new TableRow({
    children: [
      cell(curLabel, cw[0], { bold: true, fill: "FFFFFF", sz: XS, align: CT, pad: tp }),
      cell(won(ov.sessions || 0), cw[1], { fill: "FFFFFF", sz: XS, align: R, pad: tp }),
      cell(won(ov.users || 0), cw[2], { fill: "FFFFFF", sz: XS, align: R, pad: tp }),
      cell(won(ov.new_users || 0), cw[3], { fill: "FFFFFF", sz: XS, align: R, pad: tp }),
      cell(String(ov.purchases || 0), cw[4], { fill: "FFFFFF", sz: XS, align: R, pad: tp }),
      cell(won(ov.revenue || 0), cw[5], { fill: "FFFFFF", sz: XS, align: R, pad: tp }),
      cell(pct((ov.engagement_rate || 0) * 100), cw[6], { fill: "FFFFFF", sz: XS, align: R, pad: tp }),
      cell(pct((ov.bounce_rate || 0) * 100), cw[7], { fill: "FFFFFF", sz: XS, align: R, pad: tp }),
      cell(String(Math.round(ov.avg_session_duration || 0)), cw[8], { fill: "FFFFFF", sz: XS, align: R, pad: tp }),
    ],
  });

  const changes = [
    chg(ov.sessions, pp.sessions),
    chg(ov.users, pp.users),
    chg(ov.new_users, pp.new_users),
    chg(ov.purchases, pp.purchases),
    chg(ov.revenue, pp.revenue),
    chg((ov.engagement_rate || 0) * 100, (pp.engagement_rate || 0) * 100),
    chg((ov.bounce_rate || 0) * 100, (pp.bounce_rate || 0) * 100),
    chg(ov.avg_session_duration, pp.avg_session_duration),
  ];

  const chgRow = hasPrev ? new TableRow({
    children: [
      cell("증감률", cw[0], { bold: true, fill: C.altRow, sz: XS, align: CT, pad: tp }),
      ...changes.map((ch, i) => {
        const text = ch ? ch.text : "-";
        // 이탈률은 하락이 좋음 → 색상 반전 (index 6 = 이탈률)
        let clr = ch ? ch.color : C.muted;
        if (i === 6 && ch) clr = ch.color === C.up ? C.down : (ch.color === C.down ? C.up : C.muted);
        return cell(text, cw[i + 1], { fill: C.altRow, color: clr, sz: XS, align: CT, pad: tp });
      }),
    ],
  }) : null;

  const rows = [headerRow];
  if (prevRow) rows.push(prevRow);
  rows.push(curRow);
  if (chgRow) rows.push(chgRow);

  return new Table({
    width: { size: FULL_W, type: WidthType.DXA },
    columnWidths: cw,
    rows,
  });
}

// ── GA4 채널별 테이블 ──
function ga4ChannelTable(channels) {
  if (!channels || channels.length === 0) return [];

  // 6열, 합계 = 9506
  const cw = [2200, 1400, 1200, 1106, 1800, 1800];
  const tp = tightPad;
  const XS = SZ.xs;
  const R = AlignmentType.RIGHT;
  const CT = AlignmentType.CENTER;

  const headerRow = new TableRow({
    children: ["채널", "세션", "사용자", "구매", "매출", "참여율(%)"].map((h, i) =>
      cell(h, cw[i], { bold: true, fill: C.accent, color: C.headerText, sz: XS, align: CT, pad: tp })
    ),
  });

  const dataRows = channels.map((ch, i) => {
    const bg = i % 2 === 0 ? "FFFFFF" : C.altRow;
    return new TableRow({
      children: [
        cell(ch.channel, cw[0], { bold: true, fill: bg, sz: XS, pad: tp }),
        cell(won(ch.sessions), cw[1], { fill: bg, sz: XS, align: R, pad: tp }),
        cell(won(ch.users), cw[2], { fill: bg, sz: XS, align: R, pad: tp }),
        cell(String(ch.purchases || 0), cw[3], { fill: bg, sz: XS, align: R, pad: tp }),
        cell(ch.revenue > 0 ? won(ch.revenue) : "-", cw[4], { fill: bg, sz: XS, align: R, pad: tp }),
        cell(pct((ch.engagement_rate || 0) * 100), cw[5], { fill: bg, sz: XS, align: R, pad: tp }),
      ],
    });
  });

  return [
    subTitle("채널별 유입"),
    new Table({
      width: { size: FULL_W, type: WidthType.DXA },
      columnWidths: cw,
      rows: [headerRow, ...dataRows],
    }),
  ];
}

// ── GA4 페이지 제목 및 화면 클래스 TOP 5 테이블 ──
function ga4LandingTable(pages) {
  if (!pages || pages.length === 0) return [];

  // 6열, 합계 = 9506
  const cw = [3506, 1200, 1100, 1200, 1200, 1300];
  const tp = tightPad;
  const XS = SZ.xs;
  const R = AlignmentType.RIGHT;
  const CT = AlignmentType.CENTER;

  const headerRow = new TableRow({
    children: ["페이지 제목", "조회수", "사용자", "구매", "매출", "이탈률(%)"].map((h, i) =>
      cell(h, cw[i], { bold: true, fill: C.accent, color: C.headerText, sz: XS, align: CT, pad: tp })
    ),
  });

  const dataRows = pages.slice(0, 5).map((pg, i) => {
    const bg = i % 2 === 0 ? "FFFFFF" : C.altRow;
    const pageTitle = (pg.page || "-").substring(0, 40);
    return new TableRow({
      children: [
        cell(pageTitle, cw[0], { fill: bg, sz: SZ.xs, pad: tp }),
        cell(won(pg.views || pg.sessions || 0), cw[1], { fill: bg, sz: XS, align: R, pad: tp }),
        cell(won(pg.users || 0), cw[2], { fill: bg, sz: XS, align: R, pad: tp }),
        cell(String(pg.purchases || 0), cw[3], { fill: bg, sz: XS, align: R, pad: tp }),
        cell(pg.revenue > 0 ? won(pg.revenue) : "-", cw[4], { fill: bg, sz: XS, align: R, pad: tp }),
        cell(pct((pg.bounce_rate || 0) * 100), cw[5], {
          fill: bg, sz: XS, align: CT, pad: tp,
          color: (pg.bounce_rate || 0) > 0.6 ? C.down : "000000",
        }),
      ],
    });
  });

  return [
    subTitle("페이지 제목 및 화면 클래스 TOP 5"),
    new Table({
      width: { size: FULL_W, type: WidthType.DXA },
      columnWidths: cw,
      rows: [headerRow, ...dataRows],
    }),
  ];
}

// ── GA4 디바이스별 테이블 ──
function ga4DeviceTable(devices) {
  if (!devices || devices.length === 0) return [];

  // 5열, 합계 = 9506
  const cw = [2200, 1800, 1800, 1506, 2200];
  const tp = tightPad;
  const XS = SZ.xs;
  const R = AlignmentType.RIGHT;
  const CT = AlignmentType.CENTER;

  const headerRow = new TableRow({
    children: ["디바이스", "세션", "사용자", "구매", "매출"].map((h, i) =>
      cell(h, cw[i], { bold: true, fill: C.accent, color: C.headerText, sz: XS, align: CT, pad: tp })
    ),
  });

  const dataRows = devices.map((dv, i) => {
    const bg = i % 2 === 0 ? "FFFFFF" : C.altRow;
    return new TableRow({
      children: [
        cell(dv.device, cw[0], { bold: true, fill: bg, sz: XS, pad: tp }),
        cell(won(dv.sessions), cw[1], { fill: bg, sz: XS, align: R, pad: tp }),
        cell(won(dv.users), cw[2], { fill: bg, sz: XS, align: R, pad: tp }),
        cell(String(dv.purchases || 0), cw[3], { fill: bg, sz: XS, align: R, pad: tp }),
        cell(dv.revenue > 0 ? won(dv.revenue) : "-", cw[4], { fill: bg, sz: XS, align: R, pad: tp }),
      ],
    });
  });

  return [
    subTitle("디바이스별"),
    new Table({
      width: { size: FULL_W, type: WidthType.DXA },
      columnWidths: cw,
      rows: [headerRow, ...dataRows],
    }),
  ];
}

// ── 자동 코멘트 ──
function generateInsights(m, prev, campaigns, isCpas) {
  const lines = [];
  const roas = div(isCpas ? m.cpas_revenue : m.revenue, m.cost) * 100;
  const pRoas = prev && prev.cost
    ? div(isCpas ? (prev.cpas_revenue||0) : (prev.revenue||0), prev.cost) * 100 : 0;

  if (pRoas > 0) {
    const d = roas - pRoas;
    lines.push(`ROAS ${roasP(roas)} 전일비 ${Math.abs(d).toFixed(1)}%p ${d > 0 ? "상승" : "하락"}`);
  } else {
    lines.push(`ROAS ${roasP(roas)}`);
  }

  if (campaigns && campaigns.length > 0) {
    const active = campaigns.filter(c => {
      const rev = isCpas ? (c.cpas_revenue||0) : (c.revenue||0);
      return c.cost > 0 && rev > 0;
    });
    if (active.length > 0) {
      const best = active.reduce((a, b) => div(isCpas ? (a.cpas_revenue||0) : a.revenue, a.cost) > div(isCpas ? (b.cpas_revenue||0) : b.revenue, b.cost) ? a : b);
      const worst = active.reduce((a, b) => div(isCpas ? (a.cpas_revenue||0) : a.revenue, a.cost) < div(isCpas ? (b.cpas_revenue||0) : b.revenue, b.cost) ? a : b);
      const br = div(isCpas ? (best.cpas_revenue||0) : best.revenue, best.cost) * 100;
      lines.push(`[${best.campaign_name}] ROAS ${roasP(br)} 최고 효율 — 예산 확대 검토`);
      if (best.campaign_name !== worst.campaign_name) {
        const wr = div(isCpas ? (worst.cpas_revenue||0) : worst.revenue, worst.cost) * 100;
        lines.push(`[${worst.campaign_name}] ROAS ${roasP(wr)} 최저 — 소재/타겟 재검토`);
      }
    }
  }

  if (roas < 100 && roas > 0) lines.push("ROAS 100% 미만 — 긴급 대응 필요");
  return lines;
}

function insightParagraphs(lines) {
  if (lines.length === 0) return [];
  return [
    subTitle("코멘트"),
    ...lines.map(line => new Paragraph({
      numbering: { reference: "bullets", level: 0 },
      spacing: { after: 60 },
      children: [new TextRun({ text: line, font: FONT, size: SZ.sm })],
    })),
  ];
}

// ── GA4 고객구매여정 퍼널 테이블 ──
function ga4FunnelTable(funnel, prevFunnel) {
  if (!funnel || funnel.length === 0) return [];

  const pMap = {};
  if (prevFunnel && prevFunnel.length > 0) {
    prevFunnel.forEach(f => { pMap[f.event_name] = f; });
  }

  // 6열, 합계 = 9506
  const cw = [1500, 1600, 1600, 1606, 1600, 1600];
  const tp = tightPad;
  const XS = SZ.xs;
  const R = AlignmentType.RIGHT;
  const CT = AlignmentType.CENTER;

  const headerRow = new TableRow({
    children: ["단계", "이벤트", "사용자", "전체 전환율", "단계 전환율", "전일비"].map((h, i) =>
      cell(h, cw[i], { bold: true, fill: C.accent, color: C.headerText, sz: XS, align: CT, pad: tp })
    ),
  });

  const dataRows = funnel.map((f, i) => {
    const bg = i % 2 === 0 ? "FFFFFF" : C.altRow;
    const prev = pMap[f.event_name];
    const userChg = prev ? chg(f.users, prev.users) : null;
    const chgText = userChg ? userChg.text : "-";
    const chgColor = userChg ? userChg.color : C.muted;

    return new TableRow({
      children: [
        cell(`${f.step}. ${f.label}`, cw[0], { bold: true, fill: bg, sz: XS, pad: tp }),
        cell(f.event_name, cw[1], { fill: bg, sz: SZ.xs, color: C.muted, pad: tp }),
        cell(won(f.users), cw[2], { fill: bg, sz: XS, align: R, pad: tp }),
        cell(f.overall_rate.toFixed(1) + "%", cw[3], {
          fill: bg, sz: XS, align: CT, pad: tp,
          color: f.step === 1 ? "000000" : (f.overall_rate < 1 ? C.down : "000000"),
        }),
        cell(f.step === 1 ? "100%" : f.step_rate.toFixed(1) + "%", cw[4], {
          fill: bg, sz: XS, align: CT, pad: tp,
          color: f.step === 1 ? "000000" : (f.step_rate < 30 ? C.down : "000000"),
        }),
        cell(chgText, cw[5], { fill: bg, sz: XS, align: CT, pad: tp, color: chgColor }),
      ],
    });
  });

  return [
    subTitle("고객구매여정 퍼널"),
    new Table({
      width: { size: FULL_W, type: WidthType.DXA },
      columnWidths: cw,
      rows: [headerRow, ...dataRows],
    }),
  ];
}

// ── 종합 코멘트 자동 생성 ──
function generateSummaryComment(d) {
  const lines = [];

  // 전체 매체 광고비 합산
  const ownCost = (d.own || {}).cost || 0;
  const ssCost = (d.ss || {}).cost || 0;
  const nvCost = ((d.naver || {}).sa || {}).cost || 0;
  const gglCost = ((d.google || {}).total || {}).cost || 0;
  const totalCost = ownCost + ssCost + nvCost + gglCost;

  // 전체 전환 매출 합산
  const ownRev = (d.own || {}).revenue || 0;
  const ssRev = (d.ss || {}).cpas_revenue || 0;
  const nvRev = ((d.naver || {}).sa || {}).purchase_revenue || ((d.naver || {}).sa || {}).revenue || 0;
  const gglRev = ((d.google || {}).total || {}).revenue || 0;
  const totalRev = ownRev + ssRev + nvRev + gglRev;
  const totalRoas = totalCost > 0 ? (totalRev / totalCost * 100) : 0;

  // 전일 대비
  const pOwnCost = (d.prev_own || {}).cost || 0;
  const pSsCost = (d.prev_ss || {}).cost || 0;
  const pNvCost = ((d.prev_naver || {}).sa || {}).cost || 0;
  const pGglCost = ((d.prev_google || {}).total || {}).cost || 0;
  const pTotalCost = pOwnCost + pSsCost + pNvCost + pGglCost;

  const pOwnRev = (d.prev_own || {}).revenue || 0;
  const pSsRev = (d.prev_ss || {}).cpas_revenue || 0;
  const pNvRev = ((d.prev_naver || {}).sa || {}).purchase_revenue || ((d.prev_naver || {}).sa || {}).revenue || 0;
  const pGglRev = ((d.prev_google || {}).total || {}).revenue || 0;
  const pTotalRev = pOwnRev + pSsRev + pNvRev + pGglRev;
  const pTotalRoas = pTotalCost > 0 ? (pTotalRev / pTotalCost * 100) : 0;

  if (totalCost > 0) {
    let costChg = "";
    if (pTotalCost > 0) {
      const cd = ((totalCost - pTotalCost) / pTotalCost * 100);
      costChg = ` (전일비 ${cd > 0 ? "+" : ""}${cd.toFixed(1)}%)`;
    }
    lines.push(`전체 매체 광고비 ${won(totalCost)}원${costChg}, 전환매출 ${won(totalRev)}원, 통합 ROAS ${roasP(totalRoas)}`);

    if (pTotalRoas > 0) {
      const roasDiff = totalRoas - pTotalRoas;
      lines.push(`통합 ROAS 전일비 ${Math.abs(roasDiff).toFixed(1)}%p ${roasDiff >= 0 ? "상승" : "하락"} (${roasP(pTotalRoas)} → ${roasP(totalRoas)})`);
    }
  }

  // 카페24 커머스 요약
  const c24 = d.cafe24 || {};
  const pc24 = d.prev_cafe24 || {};
  if (c24.paid_amount > 0) {
    const net = c24.paid_amount - (c24.refund_amount || 0);
    let netChg = "";
    if (pc24.paid_amount > 0) {
      const pNet = pc24.paid_amount - (pc24.refund_amount || 0);
      const nd = ((net - pNet) / Math.abs(pNet) * 100);
      netChg = ` (전일비 ${nd > 0 ? "+" : ""}${nd.toFixed(1)}%)`;
    }
    lines.push(`자사몰 순매출 ${won(net)}원${netChg}, 주문 ${c24.order_count}건, 객단가 ${won(c24.avg_order_value || 0)}원`);

    // 첫구매/재구매 인사이트
    const fb = c24.first_buyers || 0;
    const rb = c24.repeat_buyers || 0;
    const bt = fb + rb;
    if (bt > 0) {
      const fr = (fb / bt * 100).toFixed(1);
      const rr = (rb / bt * 100).toFixed(1);
      lines.push(`자사몰 첫구매 ${fb}명(${fr}%) / 재구매 ${rb}명(${rr}%)`);
    }
  }

  // 스마트스토어 커머스 요약
  const ssc_ = d.smartstore_commerce || {};
  const pssc_ = d.prev_smartstore_commerce || {};
  if ((ssc_.paid_amount || 0) > 0) {
    const sNet = (ssc_.paid_amount || 0) - (ssc_.refund_amount || 0);
    let sNetChg = "";
    if ((pssc_.paid_amount || 0) > 0) {
      const pSNet = (pssc_.paid_amount || 0) - (pssc_.refund_amount || 0);
      const snd = ((sNet - pSNet) / Math.abs(pSNet) * 100);
      sNetChg = ` (전일비 ${snd > 0 ? "+" : ""}${snd.toFixed(1)}%)`;
    }
    lines.push(`스마트스토어 순매출 ${won(sNet)}원${sNetChg}, 주문 ${ssc_.order_count || 0}건, 결제자 ${ssc_.unique_customers || 0}명`);
  }

  // GA4 트래픽 요약
  const ga4ov = ((d.ga4 || {}).overview || {});
  const pga4ov = ((d.prev_ga4 || {}).overview || {});
  if (ga4ov.sessions > 0) {
    let sessChg = "";
    if (pga4ov.sessions > 0) {
      const sd = ((ga4ov.sessions - pga4ov.sessions) / pga4ov.sessions * 100);
      sessChg = ` (${sd > 0 ? "+" : ""}${sd.toFixed(1)}%)`;
    }
    const newRatio = ga4ov.users > 0 ? (ga4ov.new_users / ga4ov.users * 100) : 0;
    lines.push(`GA4 세션 ${won(ga4ov.sessions)}${sessChg}, 신규 비율 ${newRatio.toFixed(1)}%, 이탈률 ${pct((ga4ov.bounce_rate || 0) * 100)}`);
  }

  // 채널별 핵심 인사이트
  const channels = (d.ga4 || {}).channels || [];
  if (channels.length > 0) {
    const top = channels[0]; // 세션 기준 1위
    const sessTotal = channels.reduce((s, ch) => s + ch.sessions, 0);
    const topShare = sessTotal > 0 ? (top.sessions / sessTotal * 100) : 0;
    lines.push(`유입 1위 채널: ${top.channel} (세션 ${won(top.sessions)}, 점유율 ${topShare.toFixed(1)}%)`);
  }

  // 매체별 효율 비교 (ROAS 기준)
  const mediaPerf = [];
  if (ownCost > 0) mediaPerf.push({ name: "Meta 자사몰", roas: ownRev / ownCost * 100, cost: ownCost });
  if (ssCost > 0) mediaPerf.push({ name: "Meta SS", roas: ssRev / ssCost * 100, cost: ssCost });
  if (nvCost > 0) mediaPerf.push({ name: "네이버 SA", roas: nvRev / nvCost * 100, cost: nvCost });
  if (gglCost > 0) mediaPerf.push({ name: "Google Ads", roas: gglRev / gglCost * 100, cost: gglCost });

  if (mediaPerf.length >= 2) {
    mediaPerf.sort((a, b) => b.roas - a.roas);
    const best = mediaPerf[0];
    const worst = mediaPerf[mediaPerf.length - 1];
    lines.push(`매체 효율: ${best.name} ROAS ${roasP(best.roas)}(최고) / ${worst.name} ROAS ${roasP(worst.roas)}(최저)`);
  }

  // 퍼널 인사이트
  const funnel = ((d.ga4 || {}).funnel || []);
  if (funnel.length >= 3) {
    const viewItem = funnel.find(f => f.event_name === 'view_item');
    const addToCart = funnel.find(f => f.event_name === 'add_to_cart');
    const purchase = funnel.find(f => f.event_name === 'purchase');
    if (viewItem && addToCart && purchase && viewItem.users > 0) {
      const viewToCart = (addToCart.users / viewItem.users * 100).toFixed(1);
      const cartToPurchase = addToCart.users > 0 ? (purchase.users / addToCart.users * 100).toFixed(1) : "0";
      lines.push(`퍼널: 상품조회→장바구니 ${viewToCart}%, 장바구니→구매 ${cartToPurchase}% (전체 구매전환율 ${purchase.overall_rate.toFixed(1)}%)`);
    }
  }

  // 경고 체크
  if (totalRoas > 0 && totalRoas < 100) {
    lines.push("[경고] 통합 ROAS 100% 미만 — 전체 매체 효율 점검 필요");
  }

  return lines;
}

// ── NEXT 항목 자동 생성 ──
function generateNextItems(d) {
  const items = [];

  // ROAS 저조 매체 확인
  const ownCost = (d.own || {}).cost || 0;
  const ownRev = (d.own || {}).revenue || 0;
  const ownRoas = ownCost > 0 ? (ownRev / ownCost * 100) : 0;
  if (ownCost > 0 && ownRoas < 100) {
    items.push("Meta 자사몰 ROAS 부진 — 소재/타겟 점검 및 예산 재배분 검토");
  }

  const ssCost = (d.ss || {}).cost || 0;
  const ssRev = (d.ss || {}).cpas_revenue || 0;
  const ssRoas = ssCost > 0 ? (ssRev / ssCost * 100) : 0;
  if (ssCost > 0 && ssRoas < 100) {
    items.push("Meta SS(협력광고) ROAS 부진 — CPAS 캠페인 최적화 검토");
  }

  // CTR 저조 경고
  const ownClicks = (d.own || {}).clicks || 0;
  const ownImp = (d.own || {}).impressions || 0;
  const ownCtr = ownImp > 0 ? (ownClicks / ownImp * 100) : 0;
  if (ownImp > 0 && ownCtr < 1.0) {
    items.push("Meta 자사몰 CTR 1% 미만 — 크리에이티브 교체 필요");
  }

  // 이탈률 고수치 체크
  const ga4ov = ((d.ga4 || {}).overview || {});
  if (ga4ov.bounce_rate > 0.6) {
    items.push(`GA4 이탈률 ${pct(ga4ov.bounce_rate * 100)} — 랜딩페이지 UX/콘텐츠 개선 검토`);
  }

  // 랜딩페이지 이탈률 높은 항목 체크
  const landingPages = ((d.ga4 || {}).landing_pages || []);
  const highBouncePage = landingPages.find(p => p.bounce_rate > 0.7 && p.sessions >= 10);
  if (highBouncePage) {
    const pageName = (highBouncePage.page || "").substring(0, 35);
    items.push(`랜딩페이지 "${pageName}" 이탈률 ${pct(highBouncePage.bounce_rate * 100)} — 개선 검토`);
  }

  // CPM 경고 (120,000원 초과)
  if (ownImp > 0) {
    const ownCpm = ownCost / ownImp * 1000;
    if (ownCpm > 120000) {
      items.push(`Meta 자사몰 CPM ${won(Math.round(ownCpm))}원 — 타겟 범위 확장 또는 입찰 전략 조정`);
    }
  }

  // 퍼널 병목 체크
  const funnel = ((d.ga4 || {}).funnel || []);
  if (funnel.length >= 4) {
    const viewItem = funnel.find(f => f.event_name === 'view_item');
    const addToCart = funnel.find(f => f.event_name === 'add_to_cart');
    if (viewItem && addToCart && viewItem.users > 0) {
      const viewToCart = addToCart.users / viewItem.users * 100;
      if (viewToCart < 3) {
        items.push(`퍼널 병목: 상품조회→장바구니 전환율 ${viewToCart.toFixed(1)}% — 상품 상세페이지 CTA/가격/혜택 개선 검토`);
      }
    }
  }

  return items;
}

// ── 미집행 표시 ──
function emptyNotice() {
  return new Paragraph({
    spacing: { before: 100, after: 100 },
    children: [new TextRun({ text: "해당 기간 집행 없음 (0원)", font: FONT, size: SZ.md, color: C.muted, italics: true })],
  });
}

// ══════════════════════════════════════════════
// 메인 생성
// ══════════════════════════════════════════════
async function generateReport(data, outputPath) {
  const d = data;

  // 네이버 BS 일할 광고비 보정 (API cost=0 → 월정액 일할계산)
  const prevDateStr = getPrevDateStr(d.date);
  d.naver = applyBsCost(d.naver || {}, d.date);
  d.prev_naver = applyBsCost(d.prev_naver || {}, prevDateStr);

  const weekdays = ["일", "월", "화", "수", "목", "금", "토"];
  const dt = new Date(d.date + "T00:00:00");
  const wd = weekdays[dt.getDay()];
  const dateLabel = `${d.date}(${wd})`;

  // ── 1. META 자사몰 ──
  const sec1 = [sectionTitle("META — 자사몰")];
  if (d.own && d.own.cost > 0) {
    sec1.push(metricTable(d.own, d.prev_own, d.date));
    sec1.push(...campaignTable(d.own_campaigns, false));
    sec1.push(...insightParagraphs(generateInsights(d.own, d.prev_own, d.own_campaigns, false)));
  } else {
    sec1.push(emptyNotice());
  }

  // ── 2. META 스마트스토어 ──
  const sec2 = [divider(), sectionTitle("META — 스마트스토어 (협력광고)")];
  if (d.ss && d.ss.cost > 0) {
    const ssM = { ...d.ss };
    if (ssM.cpas_revenue) { ssM.revenue = ssM.cpas_revenue; ssM.purchases = ssM.cpas_purchases || 0; }
    const prevSsM = d.prev_ss ? { ...d.prev_ss, revenue: d.prev_ss.cpas_revenue || 0, purchases: d.prev_ss.cpas_purchases || 0 } : {};
    sec2.push(metricTable(ssM, prevSsM, d.date));
    sec2.push(...campaignTable(d.ss_campaigns, true));
    sec2.push(...insightParagraphs(generateInsights(d.ss, d.prev_ss, d.ss_campaigns, true)));
  } else {
    sec2.push(emptyNotice());
  }

  // ── 3. 네이버 검색광고 ──
  const sec3 = [divider(), sectionTitle("네이버 검색광고 (SA/BS/쇼검)")];
  const nv = (d.naver && d.naver.sa) ? d.naver.sa : { cost: 0, impressions: 0, clicks: 0 };
  if (nv.cost > 0 || nv.clicks > 0) {
    // 네이버 SA → metricTable 호환 포맷으로 변환
    const nvNorm = {
      cost: nv.cost, impressions: nv.impressions, clicks: nv.clicks,
      purchases: nv.purchase_count || nv.conversions || 0,
      revenue: nv.purchase_revenue || nv.revenue || 0,
    };
    const pnv = (d.prev_naver && d.prev_naver.sa) ? d.prev_naver.sa : {};
    const pnvNorm = pnv.cost ? {
      cost: pnv.cost, impressions: pnv.impressions, clicks: pnv.clicks,
      purchases: pnv.purchase_count || pnv.conversions || 0,
      revenue: pnv.purchase_revenue || pnv.revenue || 0,
    } : {};
    sec3.push(metricTable(nvNorm, pnvNorm, d.date));
    if (d.naver && d.naver.by_type) {
      sec3.push(...naverTypeTable(d.naver.by_type));
    }
  } else {
    sec3.push(emptyNotice());
  }

  // ── 4. Google Ads ──
  const sec4 = [divider(), sectionTitle("Google Ads")];
  const gt = (d.google && d.google.total) ? d.google.total : { cost: 0, impressions: 0, clicks: 0 };
  if (gt.cost > 0 || gt.clicks > 0) {
    // Google Ads → metricTable 호환 포맷으로 변환
    const gtNorm = {
      cost: gt.cost, impressions: gt.impressions, clicks: gt.clicks,
      purchases: Math.round(gt.conversions || 0),
      revenue: gt.revenue || 0,
    };
    const pgt = (d.prev_google && d.prev_google.total) ? d.prev_google.total : {};
    const pgtNorm = pgt.cost ? {
      cost: pgt.cost, impressions: pgt.impressions, clicks: pgt.clicks,
      purchases: Math.round(pgt.conversions || 0),
      revenue: pgt.revenue || 0,
    } : {};
    sec4.push(metricTable(gtNorm, pgtNorm, d.date));
    if (d.google && d.google.by_type) {
      sec4.push(...naverTypeTable(d.google.by_type, "캠페인 유형별"));
    }
  } else {
    sec4.push(emptyNotice());
  }

  // ── 5. 카페24 커머스 ──
  const sec5 = [divider(), sectionTitle("커머스 — 자사몰 (카페24)")];
  const c24 = d.cafe24 || { paid_amount: 0, refund_amount: 0, order_count: 0, unique_customers: 0, avg_order_value: 0 };
  const pc24 = d.prev_cafe24 || {};
  if (c24.order_count > 0 || c24.paid_amount > 0) {
    sec5.push(cafe24Table(c24, pc24, d.date));
    sec5.push(...cafe24BuyerTypeTable(c24, pc24, d.date));
    sec5.push(...topProductTable(d.top_products));
  } else {
    sec5.push(emptyNotice());
  }

  // ── 5b. 스마트스토어 커머스 ──
  const sec5b = [divider(), sectionTitle("커머스 — 스마트스토어 (네이버)")];
  const ssc = d.smartstore_commerce || { paid_amount: 0, refund_amount: 0, order_count: 0, unique_customers: 0, avg_order_value: 0 };
  const pssc = d.prev_smartstore_commerce || {};
  if ((ssc.order_count || 0) > 0 || (ssc.paid_amount || 0) > 0) {
    sec5b.push(smartstoreTable(ssc, pssc, d.date));
  } else {
    sec5b.push(emptyNotice());
  }

  // ── 6. GA4 웹 트래픽 ──
  const sec6 = [divider(), sectionTitle("GA4 — 웹 트래픽")];
  const ga4 = d.ga4 || {};
  const pga4 = d.prev_ga4 || {};
  const ga4ov = ga4.overview || {};

  if (ga4ov.sessions > 0 || ga4ov.users > 0) {
    sec6.push(ga4OverviewTable(ga4ov, pga4.overview || {}, d.date));
    sec6.push(...ga4ChannelTable(ga4.channels || []));
    sec6.push(...ga4LandingTable(ga4.landing_pages || []));
    sec6.push(...ga4DeviceTable(ga4.devices || []));
    sec6.push(...ga4FunnelTable(ga4.funnel || [], (pga4.funnel || [])));
  } else {
    sec6.push(emptyNotice());
  }

  // ── 7. 종합 코멘트 (자동 생성) ──
  const sec7 = [divider(), sectionTitle("종합 코멘트")];
  const summaryLines = generateSummaryComment(d);
  if (summaryLines.length > 0) {
    sec7.push(...summaryLines.map(line => new Paragraph({
      numbering: { reference: "bullets", level: 0 },
      spacing: { after: 60 },
      children: [new TextRun({ text: line, font: FONT, size: SZ.sm })],
    })));
  } else {
    sec7.push(new Paragraph({
      spacing: { after: 200 },
      children: [new TextRun({ text: "(데이터 부족 — 직접 입력)", font: FONT, size: SZ.md, color: C.muted, italics: true })],
    }));
  }

  // (NEXT 섹션 제거됨)

  // ── 문서 조립 ──
  const doc = new Document({
    styles: {
      default: { document: { run: { font: FONT, size: SZ.md } } },
      paragraphStyles: [
        { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
          run: { size: SZ.xxl, bold: true, font: FONT, color: C.primary },
          paragraph: { spacing: { before: 240, after: 200 }, outlineLevel: 0 } },
        { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
          run: { size: SZ.xl, bold: true, font: FONT, color: C.primary },
          paragraph: { spacing: { before: 200, after: 150 }, outlineLevel: 1 } },
      ],
    },
    numbering: {
      config: [{
        reference: "bullets",
        levels: [{ level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } } }],
      }],
    },
    sections: [{
      properties: {
        page: {
          size: { width: PAGE_W, height: 16838 },
          margin: MARGIN,
        },
      },
      headers: {
        default: new Header({
          children: [new Paragraph({
            alignment: AlignmentType.RIGHT,
            children: [new TextRun({ text: "Re:NK Daily Report  |  Confidential", font: FONT, size: SZ.xs, color: C.muted, italics: true })],
          })],
        }),
      },
      footers: {
        default: new Footer({
          children: [new Paragraph({
            alignment: AlignmentType.CENTER,
            spacing: { before: 100 },
            border: { top: { style: BorderStyle.SINGLE, size: 1, color: C.border, space: 6 } },
            children: [
              new TextRun({ text: "Re:NK  |  valen brandmarketing  —  Page ", font: FONT, size: SZ.xs, color: C.muted }),
              new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: SZ.xs, color: C.muted }),
            ],
          })],
        }),
      },
      children: [
        // 타이틀 블록
        new Paragraph({
          spacing: { after: 60 },
          children: [new TextRun({ text: "Re:NK Daily Report", bold: true, font: FONT, size: SZ.xxl, color: C.primary })],
        }),
        new Paragraph({
          spacing: { after: 80 },
          children: [
            new TextRun({ text: dateLabel, bold: true, font: FONT, size: SZ.lg, color: C.accent }),
            new TextRun({ text: `     생성: ${new Date().toLocaleString("ko-KR")}`, font: FONT, size: SZ.xs, color: C.muted }),
          ],
        }),
        // 구분선
        new Paragraph({
          spacing: { after: 200 },
          border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: C.primary, space: 1 } },
          children: [],
        }),
        // 본문
        ...sec1,
        ...sec2,
        ...sec3,
        ...sec4,
        ...sec5,
        ...sec5b,
        ...sec6,
        ...sec7,
      ],
    }],
  });

  const buffer = await Packer.toBuffer(doc);
  fs.writeFileSync(outputPath, buffer);
  console.log(`Report saved: ${outputPath}`);
}

// ── CLI ──
const args = process.argv.slice(2);
if (args.length < 2) {
  console.error("Usage: node generate_daily_report.js <data.json> <output.docx>");
  process.exit(1);
}

const data = JSON.parse(fs.readFileSync(args[0], "utf-8"));
generateReport(data, args[1]).catch(err => {
  console.error("Error:", err.message);
  process.exit(1);
});
