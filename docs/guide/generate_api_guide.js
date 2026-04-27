#!/usr/bin/env node

const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, Header, Footer,
        AlignmentType, BorderStyle, WidthType, ShadingType, VerticalAlign, PageNumber,
        PageBreak, HeadingLevel, TableOfContents, LevelFormat } = require('docx');
const fs = require('fs');
const path = require('path');

// Color definitions
const COLORS = {
  darkBlue: "1A237E",
  metaBlue: "1877F2",
  googleBlue: "4285F4",
  naverGreen: "03C75A",
  kakaoYellow: "FEE500",
  lightGray: "F5F5F5",
  borderGray: "CCCCCC",
  cafe24Blue: "175FC7",
  warningRed: "D32F2F",
  noteYellow: "FFF9C4"
};

// Border styles
const standardBorder = { style: BorderStyle.SINGLE, size: 1, color: COLORS.borderGray };
const standardBorders = { top: standardBorder, bottom: standardBorder, left: standardBorder, right: standardBorder };

const warningBorder = {
  ...standardBorders,
  left: { style: BorderStyle.SINGLE, size: 6, color: COLORS.warningRed }
};

const noteBorder = {
  ...standardBorders,
  left: { style: BorderStyle.SINGLE, size: 6, color: "FFD700" }
};

// Utility: Create centered heading with accent color
function createAccentHeader(text, level, accentColor) {
  return new Paragraph({
    heading: level === 1 ? HeadingLevel.HEADING_1 : HeadingLevel.HEADING_2,
    alignment: AlignmentType.CENTER,
    children: [new TextRun({
      text: text,
      bold: true,
      color: accentColor,
      size: level === 1 ? 32 : 28
    })],
    spacing: { before: 200, after: 200 }
  });
}

// Utility: Create table with consistent styling
function createStyledTable(rows, columnWidths) {
  const totalWidth = 9360; // US Letter content width (1" margins)
  const calculatedWidths = columnWidths || rows[0].map(() => Math.floor(totalWidth / rows[0].length));

  return new Table({
    width: { size: totalWidth, type: WidthType.DXA },
    columnWidths: calculatedWidths,
    rows: rows.map((rowData, rowIndex) =>
      new TableRow({
        children: rowData.map((cellContent, colIndex) => {
          const isHeader = rowIndex === 0;
          return new TableCell({
            borders: standardBorders,
            width: { size: calculatedWidths[colIndex], type: WidthType.DXA },
            shading: {
              fill: isHeader ? COLORS.darkBlue : (rowIndex % 2 === 0 ? "FFFFFF" : COLORS.lightGray),
              type: ShadingType.CLEAR
            },
            margins: { top: 100, bottom: 100, left: 120, right: 120 },
            verticalAlign: VerticalAlign.CENTER,
            children: [new Paragraph({
              children: [new TextRun({
                text: cellContent,
                bold: isHeader,
                color: isHeader ? "FFFFFF" : "000000",
                size: 20
              })],
              alignment: AlignmentType.CENTER
            })]
          });
        })
      })
    )
  });
}

// Utility: Create warning/note box
function createWarningBox(title, content, isWarning = true) {
  const border = isWarning ? warningBorder : noteBorder;
  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [400, 8960],
    rows: [new TableRow({
      children: [
        new TableCell({
          borders: border,
          width: { size: 400, type: WidthType.DXA },
          shading: { fill: isWarning ? COLORS.warningRed : COLORS.noteYellow, type: ShadingType.CLEAR },
          margins: { top: 0, bottom: 0, left: 0, right: 0 },
          children: [new Paragraph("")]
        }),
        new TableCell({
          borders: { ...standardBorders, left: border.left },
          width: { size: 8960, type: WidthType.DXA },
          shading: { fill: isWarning ? "FFEBEE" : COLORS.noteYellow, type: ShadingType.CLEAR },
          margins: { top: 80, bottom: 80, left: 120, right: 120 },
          children: [
            new Paragraph({
              children: [new TextRun({ text: title, bold: true, size: 22 })],
              spacing: { after: 100 }
            }),
            new Paragraph({
              children: [new TextRun({ text: content, size: 20 })],
              spacing: { after: 0 }
            })
          ]
        })
      ]
    })]
  });
}

// Utility: Create step paragraph
function createStep(stepNumber, title, description) {
  return new Paragraph({
    children: [
      new TextRun({
        text: `STEP ${stepNumber}: ${title}`,
        bold: true,
        size: 24,
        color: COLORS.darkBlue
      })
    ],
    spacing: { before: 120, after: 80 }
  });
}

// Utility: Create bullet point
function createBullet(text) {
  return new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    children: [new TextRun(text)],
    spacing: { after: 60 }
  });
}

// Utility: Create numbered list
function createNumberedItem(text) {
  return new Paragraph({
    numbering: { reference: "numbers", level: 0 },
    children: [new TextRun(text)],
    spacing: { after: 60 }
  });
}

// Utility: Create code block
function createCodeBlock(code) {
  return new Paragraph({
    children: [new TextRun({
      text: code,
      font: "Consolas",
      size: 18,
      color: "333333"
    })],
    shading: { fill: "EEEEEE", type: ShadingType.CLEAR },
    border: { left: { style: BorderStyle.SINGLE, size: 3, color: COLORS.darkBlue } },
    indent: { left: 360, right: 360 },
    spacing: { before: 120, after: 120 }
  });
}

function generateDocument() {
  const sections = [];

  // ===== COVER PAGE =====
  sections.push(new Paragraph({ pageBreakBefore: false, children: [new TextRun("")] }));
  sections.push(new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 2000, after: 200 },
    children: [new TextRun({
      text: "광고매체 API 통합 셋업 가이드",
      bold: true,
      size: 48,
      color: COLORS.darkBlue
    })]
  }));

  sections.push(new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 100, after: 600 },
    children: [new TextRun({
      text: "Meta · Google Ads · 네이버 검색광고 · 카카오 광고 · 카페24",
      size: 28,
      color: COLORS.metaBlue
    })]
  }));

  sections.push(new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 600, after: 100 },
    children: [new TextRun({
      text: "브랜드마케팅1팀",
      size: 22
    })]
  }));

  sections.push(new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 50, after: 50 },
    children: [new TextRun({
      text: "2026-04-22",
      size: 22
    })]
  }));

  sections.push(new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 50, after: 1000 },
    children: [new TextRun({
      text: "대행사 운영 기준",
      size: 22,
      italic: true
    })]
  }));

  sections.push(new Paragraph({ children: [new PageBreak()] }));

  // ===== TABLE OF CONTENTS =====
  sections.push(new TableOfContents("목차", { hyperlink: true, headingStyleRange: "1-2" }));
  sections.push(new Paragraph({ children: [new PageBreak()] }));

  // ===== CHAPTER 0: 시작하기 전에 =====
  sections.push(createAccentHeader("Chapter 0: 시작하기 전에", 1, COLORS.darkBlue));

  sections.push(new Paragraph({
    children: [new TextRun({
      text: "이 가이드의 목적",
      bold: true,
      size: 24
    })],
    spacing: { before: 120, after: 80 }
  }));

  sections.push(new Paragraph({
    children: [new TextRun("5개 매체(Meta, Google Ads, 네이버 검색광고, 카카오, 카페24)의 API를 연동하여 광고 및 커머스 데이터를 자동 수집하는 환경을 구축합니다.")],
    spacing: { after: 200 }
  }));

  sections.push(new Paragraph({
    children: [new TextRun({
      text: "대행사 구조 설명",
      bold: true,
      size: 24
    })],
    spacing: { before: 120, after: 80 }
  }));

  sections.push(new Paragraph({
    children: [new TextRun("대행사는 하나의 관리자 계정(MCC/비즈니스 관리자)으로 여러 광고주(고객사) 계정을 관리합니다. API도 동일한 구조로 하나의 토큰/키로 여러 고객사 데이터에 접근할 수 있습니다.")],
    spacing: { after: 200 }
  }));

  sections.push(new Paragraph({
    children: [new TextRun({
      text: "전체 매체 비교",
      bold: true,
      size: 24
    })],
    spacing: { before: 120, after: 120 }
  }));

  sections.push(createStyledTable([
    ["매체", "인증 방식", "토큰 유효기간", "대행사 지원", "발급 난이도"],
    ["Meta", "시스템 유저 토큰", "무기한", "비즈니스 관리자", "★★☆"],
    ["Google Ads", "OAuth 2.0 + Developer Token", "Refresh Token 무기한", "MCC 계정", "★★★"],
    ["네이버 검색광고", "HMAC-SHA256 서명", "무기한 (Secret Key)", "대행사 계정", "★☆☆"],
    ["카카오모먼트", "Business OAuth 2.0", "Refresh Token 무기한", "대행사 계정", "★★☆"],
    ["카페24", "OAuth 2.0", "Refresh Token (2주)", "쇼핑몰 관리자", "★★☆"]
  ], [1872, 1872, 1872, 1872, 1872]));

  sections.push(new Paragraph({ spacing: { after: 200 }, children: [new TextRun("")] }));

  sections.push(new Paragraph({
    children: [new TextRun({
      text: "준비물 체크리스트",
      bold: true,
      size: 24
    })],
    spacing: { before: 120, after: 80 }
  }));

  sections.push(createBullet("각 매체별 관리자 계정 또는 대행사 계정 보유"));
  sections.push(createBullet("JSON 파일 작성 가능한 텍스트 에디터 (메모장, VS Code 등)"));
  sections.push(createBullet("Python 3.8 이상 설치"));
  sections.push(createBullet("API 호출 스크립트 (meta_api_fetcher.py, google_ads_fetcher.py 등)"));

  sections.push(new Paragraph({ children: [new PageBreak()] }));

  // ===== CHAPTER 1: Meta 광고 API =====
  sections.push(createAccentHeader("Chapter 1: Meta 광고 API", 1, COLORS.metaBlue));

  sections.push(new Paragraph({
    children: [new TextRun({
      text: "1.1 개요",
      bold: true,
      size: 26,
      color: COLORS.metaBlue
    })],
    spacing: { before: 120, after: 80 }
  }));

  sections.push(new Paragraph({
    children: [new TextRun("Meta Marketing API를 사용하여 광고 데이터를 수집합니다. 대행사 구조에서는 시스템 유저 토큰 방식을 사용하여 비즈니스 관리자(Business Manager)에서 하나의 토큰으로 모든 광고 계정에 접근합니다.")],
    spacing: { after: 120 }
  }));

  sections.push(new Paragraph({
    children: [new TextRun({
      text: "시스템 유저 토큰의 특징:",
      bold: true,
      size: 20
    })],
    spacing: { after: 80 }
  }));

  sections.push(createBullet("만료 시간이 없음 (무기한)"));
  sections.push(createBullet("비밀번호 변경, 시스템 유저 삭제, 앱 권한 해제 시에만 무효화"));
  sections.push(createBullet("한 번 발급 후 계속 재사용 가능"));

  sections.push(new Paragraph({ spacing: { after: 200 }, children: [new TextRun("")] }));

  sections.push(new Paragraph({
    children: [new TextRun({
      text: "1.2 셋업 절차",
      bold: true,
      size: 26,
      color: COLORS.metaBlue
    })],
    spacing: { before: 120, after: 120 }
  }));

  sections.push(createStep(1, "Meta Business Suite 접속", ""));
  sections.push(new Paragraph({
    children: [new TextRun("business.facebook.com에 접속합니다. (Meta 비즈니스 계정으로 로그인)")],
    spacing: { after: 120 }
  }));

  sections.push(createStep(2, "시스템 사용자 추가", ""));
  sections.push(new Paragraph({
    children: [new TextRun("좌측 메뉴 > 설정(Settings) > 계정(Accounts) > 시스템 사용자(System Users) > 새 시스템 사용자 추가")],
    spacing: { after: 80 }
  }));
  sections.push(createBullet("사용자 이름 입력 (예: API_Automation_User)"));
  sections.push(createBullet("역할: 관리자(Admin) 선택"));
  sections.push(new Paragraph({ spacing: { after: 120 }, children: [new TextRun("")] }));

  sections.push(createStep(3, "앱 만들기 또는 선택", ""));
  sections.push(new Paragraph({
    children: [new TextRun("설정(Settings) > 계정(Accounts) > 앱(Apps) > 앱 추가")],
    spacing: { after: 80 }
  }));
  sections.push(createBullet("앱 유형: 비즈니스(Business) 선택"));
  sections.push(createBullet("앱 이름 입력 (예: Re:NK_광고자동화)"));
  sections.push(new Paragraph({ spacing: { after: 120 }, children: [new TextRun("")] }));

  sections.push(createStep(4, "시스템 사용자에 자산 할당", ""));
  sections.push(new Paragraph({
    children: [new TextRun("설정(Settings) > 시스템 사용자 > 생성한 사용자 선택 > 자산 할당 > 광고 계정(Ad Accounts) 추가")],
    spacing: { after: 80 }
  }));
  sections.push(createBullet("관리 중인 모든 광고 계정 선택"));
  sections.push(createBullet("권한: ads_management, ads_read, read_insights 필수"));
  sections.push(new Paragraph({ spacing: { after: 120 }, children: [new TextRun("")] }));

  sections.push(createStep(5, "토큰 생성", ""));
  sections.push(new Paragraph({
    children: [new TextRun("시스템 사용자 > 토큰 생성(Generate Token) 클릭")],
    spacing: { after: 80 }
  }));
  sections.push(createBullet("앱 선택 (Step 3에서 만든 앱)"));
  sections.push(createBullet("권한 확인 (위 권한들이 체크되어야 함)"));
  sections.push(createBullet("생성된 토큰을 안전한 장소에 복사하여 저장"));
  sections.push(new Paragraph({ spacing: { after: 120 }, children: [new TextRun("")] }));

  sections.push(createStep(6, "인증 파일 작성", ""));
  sections.push(new Paragraph({
    children: [new TextRun("아래 내용으로 JSON 파일을 생성하여 config 폴더에 저장합니다:")],
    spacing: { after: 100 }
  }));

  sections.push(createCodeBlock(`{
  "access_token": "발급받은 시스템 유저 토큰",
  "accounts": {
    "own": "act_901839975672999",
    "smartstore": "act_886230967162493"
  }
}`));

  sections.push(new Paragraph({
    children: [new TextRun({
      text: "파일명: config/renk_meta_credentials.json",
      italic: true,
      size: 20
    })],
    spacing: { after: 200 }
  }));

  sections.push(new Paragraph({
    children: [new TextRun({
      text: "1.3 연결 테스트",
      bold: true,
      size: 26,
      color: COLORS.metaBlue
    })],
    spacing: { before: 120, after: 120 }
  }));

  sections.push(createCodeBlock("python meta_api_fetcher.py --test"));

  sections.push(new Paragraph({
    children: [new TextRun("출력이 성공 메시지이면 연결이 정상입니다.")],
    spacing: { after: 200 }
  }));

  sections.push(new Paragraph({
    children: [new TextRun({
      text: "1.4 트러블슈팅",
      bold: true,
      size: 26,
      color: COLORS.metaBlue
    })],
    spacing: { before: 120, after: 120 }
  }));

  sections.push(createStyledTable([
    ["에러", "원인", "해결책"],
    ["OAuthException (190)", "토큰 만료/무효", "시스템 사용자 > 토큰 재생성"],
    ["Permission error (#10)", "광고 계정 권한 없음", "자산 할당에서 계정 추가 확인"],
    ["Rate limit (#32)", "API 호출 한도 초과", "5분 대기 후 재시도"]
  ], [2340, 2340, 2340]));

  sections.push(new Paragraph({ spacing: { after: 120 }, children: [new TextRun("")] }));

  sections.push(createWarningBox(
    "중요",
    "토큰은 절대 공개하지 마세요. GitHub, 이메일, 공유 문서에 올리면 안 됩니다.",
    true
  ));

  sections.push(new Paragraph({ spacing: { after: 120 }, children: [new TextRun("")] }));

  sections.push(new Paragraph({
    children: [new TextRun({
      text: "1.5 대행사 팁",
      bold: true,
      size: 26,
      color: COLORS.metaBlue
    })],
    spacing: { before: 120, after: 80 }
  }));

  sections.push(createBullet("고객사 추가 시: 비즈니스 관리자에서 광고 계정을 시스템 사용자에 자산 할당만 하면 됨"));
  sections.push(createBullet("토큰 재발급 불필요 — 같은 토큰으로 여러 계정 접근 가능"));
  sections.push(createBullet("자산 할당을 추가/제거할 때마다 토큰은 유지됨"));

  sections.push(new Paragraph({ children: [new PageBreak()] }));

  // ===== CHAPTER 2: Google Ads API =====
  sections.push(createAccentHeader("Chapter 2: Google Ads API", 1, COLORS.googleBlue));

  sections.push(new Paragraph({
    children: [new TextRun({
      text: "2.1 개요",
      bold: true,
      size: 26,
      color: COLORS.googleBlue
    })],
    spacing: { before: 120, after: 80 }
  }));

  sections.push(new Paragraph({
    children: [new TextRun("Google Ads API는 3가지 인증 요소로 구성됩니다: Developer Token + OAuth 2.0 Client + Refresh Token")],
    spacing: { after: 120 }
  }));

  sections.push(new Paragraph({
    children: [new TextRun("대행사 구조에서 MCC(관리자 계정)의 Developer Token 하나로 모든 하위 고객 계정에 접근할 수 있습니다.")],
    spacing: { after: 200 }
  }));

  sections.push(new Paragraph({
    children: [new TextRun({
      text: "2.2 셋업 절차",
      bold: true,
      size: 26,
      color: COLORS.googleBlue
    })],
    spacing: { before: 120, after: 120 }
  }));

  sections.push(createStep(1, "Google Cloud Console 접속", ""));
  sections.push(new Paragraph({
    children: [new TextRun("console.cloud.google.com에 접속합니다.")],
    spacing: { after: 120 }
  }));

  sections.push(createStep(2, "프로젝트 생성", ""));
  sections.push(new Paragraph({
    children: [new TextRun("최상단의 프로젝트 선택 > 새 프로젝트 > 이름 입력 (예: ReNK-Ads-Pipeline) > 만들기")],
    spacing: { after: 120 }
  }));

  sections.push(createStep(3, "Google Ads API 활성화", ""));
  sections.push(new Paragraph({
    children: [new TextRun("프로젝트가 생성되면, 상단 검색창 > \"Google Ads API\" 검색 > 선택 > 사용(Enable) 클릭")],
    spacing: { after: 120 }
  }));

  sections.push(createStep(4, "OAuth 동의 화면 설정", ""));
  sections.push(new Paragraph({
    children: [new TextRun("좌측 메뉴 > API 및 서비스(APIs & Services) > OAuth 동의 화면(OAuth consent screen)")],
    spacing: { after: 80 }
  }));
  sections.push(createBullet("외부(External) 선택"));
  sections.push(createBullet("앱 이름, 사용자 지원 이메일 입력"));
  sections.push(createBullet("아래로 내려가서 테스트 사용자(Test users) 섹션에 Google Ads 관리자 이메일 추가"));
  sections.push(new Paragraph({ spacing: { after: 120 }, children: [new TextRun("")] }));

  sections.push(createStep(5, "OAuth 2.0 Client 생성", ""));
  sections.push(new Paragraph({
    children: [new TextRun("좌측 메뉴 > 사용자 인증 정보(Credentials) > 사용자 인증 정보 만들기(Create Credentials) > OAuth 클라이언트 ID")],
    spacing: { after: 80 }
  }));
  sections.push(createBullet("애플리케이션 유형: 데스크톱 앱(Desktop application) 선택"));
  sections.push(createBullet("생성 후 Client ID와 Client Secret 복사하여 보관"));
  sections.push(new Paragraph({ spacing: { after: 120 }, children: [new TextRun("")] }));

  sections.push(createStep(6, "Developer Token 확인", ""));
  sections.push(new Paragraph({
    children: [new TextRun("Google Ads MCC 계정 > 도구(Tools) > 설정(Settings) > API 센터(API Center)")],
    spacing: { after: 80 }
  }));
  sections.push(createBullet("Developer Token 상태 확인"));
  sections.push(createBullet("상태가 '테스트 계정 액세스'면 '기본 액세스' 신청 필요 (승인: 1-3영업일)"));
  sections.push(new Paragraph({ spacing: { after: 120 }, children: [new TextRun("")] }));

  sections.push(createStep(7, "Refresh Token 생성", ""));
  sections.push(new Paragraph({
    children: [new TextRun("OAuth Playground 사용: https://developers.google.com/oauthplayground")],
    spacing: { after: 80 }
  }));
  sections.push(createBullet("우상단 톱니바퀴 > Use your own OAuth credentials 체크"));
  sections.push(createBullet("Client ID/Secret 입력 (Step 5에서 복사한 값)"));
  sections.push(createBullet("좌측 'Google Ads API v18' scope 선택"));
  sections.push(createBullet("Authorize 클릭 > 권한 동의"));
  sections.push(createBullet("Exchange authorization code for tokens 클릭 > refresh_token 복사"));
  sections.push(new Paragraph({ spacing: { after: 120 }, children: [new TextRun("")] }));

  sections.push(createStep(8, "인증 파일 작성", ""));
  sections.push(new Paragraph({
    children: [new TextRun("아래 내용으로 JSON 파일 생성:")],
    spacing: { after: 100 }
  }));

  sections.push(createCodeBlock(`{
  "developer_token": "xxxxxxxxxxxxxxx",
  "client_id": "123456789-abc.apps.googleusercontent.com",
  "client_secret": "GOCSPX-xxxxxxxxxxxxxxxx",
  "refresh_token": "1//0gxxxxxxxxxxxxxxx",
  "customer_id": "1234567890",
  "login_customer_id": "9876543210"
}`));

  sections.push(new Paragraph({
    children: [new TextRun({
      text: "파일명: config/renk_google_ads_credentials.json",
      italic: true,
      size: 20
    })],
    spacing: { after: 100 }
  }));

  sections.push(new Paragraph({
    children: [new TextRun({
      text: "필드 설명:",
      bold: true,
      size: 20
    })],
    spacing: { after: 60 }
  }));

  sections.push(createBullet("developer_token: MCC API 센터에서 확인"));
  sections.push(createBullet("client_id / client_secret: Google Cloud Console에서 발급"));
  sections.push(createBullet("refresh_token: OAuth Playground에서 발급"));
  sections.push(createBullet("customer_id: 광고 고객 ID (하이픈 없이 숫자만)"));
  sections.push(createBullet("login_customer_id: MCC 계정 ID (대행사 필수)"));

  sections.push(new Paragraph({ spacing: { after: 200 }, children: [new TextRun("")] }));

  sections.push(new Paragraph({
    children: [new TextRun({
      text: "2.3 연결 테스트",
      bold: true,
      size: 26,
      color: COLORS.googleBlue
    })],
    spacing: { before: 120, after: 120 }
  }));

  sections.push(createCodeBlock("python google_ads_fetcher.py --test"));

  sections.push(new Paragraph({
    children: [new TextRun("성공 메시지가 출력되면 연결 완료입니다.")],
    spacing: { after: 200 }
  }));

  sections.push(new Paragraph({
    children: [new TextRun({
      text: "2.4 트러블슈팅",
      bold: true,
      size: 26,
      color: COLORS.googleBlue
    })],
    spacing: { before: 120, after: 120 }
  }));

  sections.push(createStyledTable([
    ["에러", "원인", "해결책"],
    ["DEVELOPER_TOKEN_NOT_APPROVED", "Developer Token이 테스트 상태", "기본 액세스 신청 (MCC > API 센터)"],
    ["OAUTH_TOKEN_INVALID", "Refresh Token 무효", "OAuth Playground에서 새로 발급"],
    ["CUSTOMER_NOT_FOUND", "고객 ID 오류", "Google Ads 대시보드에서 정확한 ID 확인"],
    ["AUTHORIZATION_ERROR", "MCC ID 누락", "login_customer_id 필드 확인"]
  ], [2340, 2340, 2340]));

  sections.push(new Paragraph({ spacing: { after: 120 }, children: [new TextRun("")] }));

  sections.push(createWarningBox(
    "주의",
    "Refresh Token은 발급받은 후 여러 번 사용할 수 있습니다. 한 번만 사용되고 만료되지 않습니다. 절대 공개하지 마세요.",
    false
  ));

  sections.push(new Paragraph({ spacing: { after: 120 }, children: [new TextRun("")] }));

  sections.push(new Paragraph({
    children: [new TextRun({
      text: "2.5 대행사 팁",
      bold: true,
      size: 26,
      color: COLORS.googleBlue
    })],
    spacing: { before: 120, after: 80 }
  }));

  sections.push(createBullet("MCC의 Developer Token 하나로 모든 하위 계정 접근 가능"));
  sections.push(createBullet("고객사 추가 시: login_customer_id(MCC)는 고정, customer_id만 변경"));
  sections.push(createBullet("Developer Token 기본 액세스 승인은 계정당 1회만 필요"));

  sections.push(new Paragraph({ children: [new PageBreak()] }));

  // ===== CHAPTER 3: 네이버 검색광고 API =====
  sections.push(createAccentHeader("Chapter 3: 네이버 검색광고 API", 1, COLORS.naverGreen));

  sections.push(new Paragraph({
    children: [new TextRun({
      text: "3.1 개요",
      bold: true,
      size: 26,
      color: COLORS.naverGreen
    })],
    spacing: { before: 120, after: 80 }
  }));

  sections.push(new Paragraph({
    children: [new TextRun("네이버 검색광고 API는 가장 간단한 인증 방식을 사용합니다. OAuth가 필요 없으며, API Key와 Secret Key만으로 인증합니다.")],
    spacing: { after: 120 }
  }));

  sections.push(new Paragraph({
    children: [new TextRun("대행사 계정으로 API 키를 발급받으면, 관리 중인 모든 광고주 계정의 데이터에 접근할 수 있습니다.")],
    spacing: { after: 200 }
  }));

  sections.push(new Paragraph({
    children: [new TextRun({
      text: "3.2 셋업 절차",
      bold: true,
      size: 26,
      color: COLORS.naverGreen
    })],
    spacing: { before: 120, after: 120 }
  }));

  sections.push(createStep(1, "네이버 검색광고 센터 접속", ""));
  sections.push(new Paragraph({
    children: [new TextRun("searchad.naver.com에 접속하여 대행사 계정으로 로그인합니다.")],
    spacing: { after: 120 }
  }));

  sections.push(createStep(2, "API 키 발급", ""));
  sections.push(new Paragraph({
    children: [new TextRun("상단 메뉴 > 도구(Tools) > API 관리(API Management) > API 라이선스 관리(API License Management)")],
    spacing: { after: 80 }
  }));
  sections.push(createBullet("API Key 발급 버튼 클릭"));
  sections.push(createBullet("3가지 값이 표시됨: 고객번호(Customer ID), API Key, Secret Key"));
  sections.push(createBullet("⚠️ Secret Key는 발급 시 1회만 표시됩니다. 반드시 즉시 복사하여 저장하세요!"));
  sections.push(new Paragraph({ spacing: { after: 120 }, children: [new TextRun("")] }));

  sections.push(createStep(3, "인증 파일 작성", ""));
  sections.push(new Paragraph({
    children: [new TextRun("아래 내용으로 JSON 파일 생성:")],
    spacing: { after: 100 }
  }));

  sections.push(createCodeBlock(`{
  "search_ad": {
    "customer_id": "3445110",
    "api_key": "발급받은_API_Key",
    "secret_key": "발급받은_Secret_Key"
  }
}`));

  sections.push(new Paragraph({
    children: [new TextRun({
      text: "파일명: config/renk_naver_credentials.json",
      italic: true,
      size: 20
    })],
    spacing: { after: 200 }
  }));

  sections.push(createWarningBox(
    "Windows 사용자 필독",
    "메모장으로 JSON을 저장할 때, 파일 형식을 '모든 파일(*.*)'로 반드시 선택하세요. 그렇지 않으면 .json.txt로 저장되어 인식되지 않습니다.",
    true
  ));

  sections.push(new Paragraph({ spacing: { after: 120 }, children: [new TextRun("")] }));

  sections.push(createStep(4, "연결 테스트", ""));
  sections.push(createCodeBlock("python naver_api_fetcher.py --test"));

  sections.push(new Paragraph({
    children: [new TextRun("성공 메시지가 출력되면 연결 완료입니다.")],
    spacing: { after: 200 }
  }));

  sections.push(new Paragraph({
    children: [new TextRun({
      text: "3.3 트러블슈팅",
      bold: true,
      size: 26,
      color: COLORS.naverGreen
    })],
    spacing: { before: 120, after: 120 }
  }));

  sections.push(createStyledTable([
    ["에러", "원인", "해결책"],
    ["HTTP 401", "API Key 또는 Secret Key 오류", "키를 재확인하고 공백/특수문자 제거"],
    ["HTTP 403 (Invalid Signature)", "HMAC 서명 생성 오류", "Secret Key가 정확한지 다시 확인"],
    ["HTTP 403", "고객번호 불일치", "검색광고 센터에서 정확한 고객번호 확인"],
    ["campaignTp [기타]", "캠페인 유형 코드 미정의", "Cowork에 문의하여 코드 업데이트"]
  ], [2340, 2340, 2340]));

  sections.push(new Paragraph({ spacing: { after: 120 }, children: [new TextRun("")] }));

  sections.push(new Paragraph({
    children: [new TextRun({
      text: "3.4 대행사 팁",
      bold: true,
      size: 26,
      color: COLORS.naverGreen
    })],
    spacing: { before: 120, after: 80 }
  }));

  sections.push(createBullet("대행사 계정의 API 키로 관리 중인 모든 광고주 데이터 접근 가능"));
  sections.push(createBullet("고객사별 별도 API 키 발급 불필요"));
  sections.push(createBullet("브랜드검색 캠페인은 월 고정비 모델이므로 API에서 광고비가 0원으로 표시됨 (정상)"));

  sections.push(new Paragraph({ children: [new PageBreak()] }));

  // ===== CHAPTER 4: 카카오 광고 API =====
  sections.push(createAccentHeader("Chapter 4: 카카오 광고 API", 1, COLORS.kakaoYellow));

  sections.push(new Paragraph({
    children: [new TextRun({
      text: "4.1 개요",
      bold: true,
      size: 26,
      color: "000000"
    })],
    spacing: { before: 120, after: 80 }
  }));

  sections.push(new Paragraph({
    children: [new TextRun("카카오 광고 플랫폼은 카카오모먼트와 카카오 키워드광고로 구분됩니다. 두 플랫폼 모두 Business OAuth 2.0 인증을 사용합니다.")],
    spacing: { after: 120 }
  }));

  sections.push(new Paragraph({
    children: [new TextRun("하나의 개발자 앱으로 여러 광고 계정을 관리할 수 있습니다.")],
    spacing: { after: 200 }
  }));

  sections.push(new Paragraph({
    children: [new TextRun({
      text: "4.2 카카오 개발자 앱 등록",
      bold: true,
      size: 26,
      color: "000000"
    })],
    spacing: { before: 120, after: 120 }
  }));

  sections.push(createStep(1, "카카오 개발자 사이트 접속", ""));
  sections.push(new Paragraph({
    children: [new TextRun("developers.kakao.com에 접속하여 카카오 계정으로 로그인합니다.")],
    spacing: { after: 120 }
  }));

  sections.push(createStep(2, "애플리케이션 추가", ""));
  sections.push(new Paragraph({
    children: [new TextRun("상단 '내 애플리케이션(My Applications)' > 애플리케이션 추가하기(Add Application)")],
    spacing: { after: 80 }
  }));
  sections.push(createBullet("앱 이름 입력 (예: 발렌라이프_광고자동화)"));
  sections.push(createBullet("비즈니스 타입 선택하여 계약하기"));
  sections.push(new Paragraph({ spacing: { after: 120 }, children: [new TextRun("")] }));

  sections.push(createStep(3, "앱 키 확인", ""));
  sections.push(new Paragraph({
    children: [new TextRun("생성한 앱 > 앱 설정(App Settings) > 앱 키(App Keys) 탭")],
    spacing: { after: 80 }
  }));
  sections.push(createBullet("REST API 키 복사하여 저장"));
  sections.push(createBullet("플랫폼 설정(Platform) > Web > 사이트 도메인 추가 (예: https://localhost/callback)"));
  sections.push(new Paragraph({ spacing: { after: 200 }, children: [new TextRun("")] }));

  sections.push(new Paragraph({
    children: [new TextRun({
      text: "4.3 카카오모먼트 API 셋업",
      bold: true,
      size: 26,
      color: "000000"
    })],
    spacing: { before: 120, after: 120 }
  }));

  sections.push(createStep(4, "카카오모먼트 API 권한 설정", ""));
  sections.push(new Paragraph({
    children: [new TextRun("앱 설정 > 비즈니스 API(Business APIs) > 카카오모먼트(Kakao Moment) 사용 설정")],
    spacing: { after: 120 }
  }));

  sections.push(createStep(5, "Business Authorization Code 발급", ""));
  sections.push(new Paragraph({
    children: [new TextRun("브라우저에서 아래 URL을 입력합니다 ({REST_API_KEY}와 {REDIRECT_URI}를 실제 값으로 변경):")],
    spacing: { after: 100 }
  }));

  sections.push(createCodeBlock(`https://kauth.kakao.com/oauth/business/authorize?
client_id={REST_API_KEY}&
redirect_uri={REDIRECT_URI}&
response_type=code&
type=moment`));

  sections.push(new Paragraph({
    children: [new TextRun("카카오 로그인 > 권한 동의 > 리다이렉트 URL의 code 파라미터 복사")],
    spacing: { after: 120 }
  }));

  sections.push(createStep(6, "Access Token 및 Refresh Token 발급", ""));
  sections.push(new Paragraph({
    children: [new TextRun("다음 API를 호출합니다:")],
    spacing: { after: 100 }
  }));

  sections.push(createCodeBlock(`POST https://kauth.kakao.com/oauth/token
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&
client_id={REST_API_KEY}&
redirect_uri={REDIRECT_URI}&
code={발급받은_code}`));

  sections.push(new Paragraph({
    children: [new TextRun("응답에서 access_token과 refresh_token을 저장합니다.")],
    spacing: { after: 200 }
  }));

  sections.push(new Paragraph({
    children: [new TextRun({
      text: "4.4 카카오 키워드광고 API 셋업",
      bold: true,
      size: 26,
      color: "000000"
    })],
    spacing: { before: 120, after: 120 }
  }));

  sections.push(createStep(7, "키워드광고 API 권한 설정", ""));
  sections.push(new Paragraph({
    children: [new TextRun("앱 설정 > 비즈니스 API > 카카오 키워드광고(Kakao Keyword Ads) 사용 설정")],
    spacing: { after: 120 }
  }));

  sections.push(createStep(8, "인증 파일 작성", ""));
  sections.push(new Paragraph({
    children: [new TextRun("아래 내용으로 JSON 파일 생성:")],
    spacing: { after: 100 }
  }));

  sections.push(createCodeBlock(`{
  "rest_api_key": "카카오 REST API 키",
  "redirect_uri": "https://localhost/callback",
  "moment": {
    "access_token": "카카오모먼트 Access Token",
    "refresh_token": "카카오모먼트 Refresh Token",
    "ad_account_id": "광고계정 ID"
  },
  "keywordad": {
    "access_token": "키워드광고 Access Token",
    "refresh_token": "키워드광고 Refresh Token",
    "ad_account_id": "키워드광고 계정 ID"
  }
}`));

  sections.push(new Paragraph({
    children: [new TextRun({
      text: "파일명: config/renk_kakao_credentials.json",
      italic: true,
      size: 20
    })],
    spacing: { after: 200 }
  }));

  sections.push(new Paragraph({
    children: [new TextRun({
      text: "4.5 연결 테스트",
      bold: true,
      size: 26,
      color: "000000"
    })],
    spacing: { before: 120, after: 120 }
  }));

  sections.push(createCodeBlock("python kakao_api_fetcher.py --test"));

  sections.push(new Paragraph({
    children: [new TextRun("성공 메시지가 출력되면 연결 완료입니다.")],
    spacing: { after: 200 }
  }));

  sections.push(new Paragraph({
    children: [new TextRun({
      text: "4.6 트러블슈팅",
      bold: true,
      size: 26,
      color: "000000"
    })],
    spacing: { before: 120, after: 120 }
  }));

  sections.push(createStyledTable([
    ["에러", "원인", "해결책"],
    ["KOE101", "REST API 키 오류", "API 키를 다시 확인하고 복사"],
    ["KOE303", "Redirect URI 불일치", "앱 설정의 URI와 코드의 URI가 동일한지 확인"],
    ["KOE010", "비즈니스 인증 미완료", "비즈니스 앱으로 전환 필요"],
    ["401 Unauthorized", "토큰 만료", "Refresh Token으로 새로운 Access Token 발급"]
  ], [2340, 2340, 2340]));

  sections.push(new Paragraph({ spacing: { after: 120 }, children: [new TextRun("")] }));

  sections.push(new Paragraph({
    children: [new TextRun({
      text: "4.7 대행사 팁",
      bold: true,
      size: 26,
      color: "000000"
    })],
    spacing: { before: 120, after: 80 }
  }));

  sections.push(createBullet("하나의 앱(REST API 키)으로 여러 광고 계정 관리 가능"));
  sections.push(createBullet("광고 계정 추가 시 ad_account_id만 변경"));
  sections.push(createBullet("Refresh Token으로 Access Token을 자동 갱신 (자동화 스크립트에서 처리)"));

  sections.push(new Paragraph({ children: [new PageBreak()] }));

  // ===== CHAPTER 5: 카페24 API =====
  sections.push(createAccentHeader("Chapter 5: 카페24 API", 1, COLORS.cafe24Blue));

  sections.push(new Paragraph({
    children: [new TextRun({
      text: "5.1 개요",
      bold: true,
      size: 26,
      color: COLORS.cafe24Blue
    })],
    spacing: { before: 120, after: 80 }
  }));

  sections.push(new Paragraph({
    children: [new TextRun("카페24는 자사몰(독립 쇼핑몰) 플랫폼으로, OAuth 2.0 Authorization Code 방식으로 API에 접근합니다. 쇼핑몰의 주문·매출·방문자 데이터를 자동 수집할 수 있습니다.")],
    spacing: { after: 120 }
  }));

  sections.push(new Paragraph({
    children: [new TextRun({
      text: "카페24 API 특징:",
      bold: true,
      size: 20
    })],
    spacing: { after: 80 }
  }));

  sections.push(createBullet("Access Token 유효기간: 2시간"));
  sections.push(createBullet("Refresh Token 유효기간: 2주 — 만료 전에 반드시 갱신 필요"));
  sections.push(createBullet("자동 갱신 로직이 스크립트에 내장되어 있음 (cafe24_api_fetcher.py)"));
  sections.push(createBullet("쇼핑몰 관리자(Admin) 권한 필요"));

  sections.push(new Paragraph({ spacing: { after: 200 }, children: [new TextRun("")] }));

  sections.push(new Paragraph({
    children: [new TextRun({
      text: "5.2 셋업 절차",
      bold: true,
      size: 26,
      color: COLORS.cafe24Blue
    })],
    spacing: { before: 120, after: 120 }
  }));

  sections.push(createStep(1, "카페24 개발자센터 접속", ""));
  sections.push(new Paragraph({
    children: [new TextRun("developers.cafe24.com에 접속하여 카페24 계정으로 로그인합니다.")],
    spacing: { after: 120 }
  }));

  sections.push(createStep(2, "앱 생성", ""));
  sections.push(new Paragraph({
    children: [new TextRun("개발자센터 > 앱 관리(App Management) > 앱 만들기(Create App)")],
    spacing: { after: 80 }
  }));
  sections.push(createBullet("앱 이름 입력 (예: Re:NK_데이터수집)"));
  sections.push(createBullet("앱 유형: 비공개(Private) 선택"));
  sections.push(createBullet("생성 후 Client ID와 Client Secret 복사하여 저장"));
  sections.push(new Paragraph({ spacing: { after: 120 }, children: [new TextRun("")] }));

  sections.push(createStep(3, "권한(Scope) 설정", ""));
  sections.push(new Paragraph({
    children: [new TextRun("앱 설정에서 아래 권한을 활성화합니다:")],
    spacing: { after: 80 }
  }));
  sections.push(createBullet("mall.read_store — 쇼핑몰 기본 정보"));
  sections.push(createBullet("mall.read_salesreport — 매출 리포트"));
  sections.push(createBullet("mall.read_order — 주문 조회"));
  sections.push(createBullet("mall.read_product — 상품 조회"));
  sections.push(createBullet("mall.read_customer — 방문자/고객 통계"));
  sections.push(new Paragraph({ spacing: { after: 120 }, children: [new TextRun("")] }));

  sections.push(createStep(4, "쇼핑몰에 앱 설치 (Authorization Code 발급)", ""));
  sections.push(new Paragraph({
    children: [new TextRun("브라우저에서 아래 URL을 입력합니다 (값을 실제 값으로 변경):")],
    spacing: { after: 100 }
  }));

  sections.push(createCodeBlock(`https://{MALL_ID}.cafe24api.com/api/v2/oauth/authorize?
response_type=code&
client_id={CLIENT_ID}&
redirect_uri={REDIRECT_URI}&
scope=mall.read_store,mall.read_salesreport,mall.read_order,mall.read_product,mall.read_customer`));

  sections.push(new Paragraph({
    children: [new TextRun("카페24 로그인 > 권한 동의 > 리다이렉트 URL에 포함된 code 파라미터 복사")],
    spacing: { after: 120 }
  }));

  sections.push(createWarningBox(
    "중요: Authorization Code는 1회용입니다",
    "발급 후 즉시 사용해야 합니다. 만료 시 위 URL을 다시 방문하여 재발급하세요.",
    true
  ));

  sections.push(new Paragraph({ spacing: { after: 120 }, children: [new TextRun("")] }));

  sections.push(createStep(5, "Access Token & Refresh Token 발급", ""));
  sections.push(new Paragraph({
    children: [new TextRun("제공된 스크립트를 사용하여 토큰을 교환합니다:")],
    spacing: { after: 100 }
  }));

  sections.push(createCodeBlock(`python cafe24_get_token.py --code {발급받은_Authorization_Code}`));

  sections.push(new Paragraph({
    children: [new TextRun("성공하면 config/renk_cafe24_token.json 파일이 자동 생성됩니다.")],
    spacing: { after: 120 }
  }));

  sections.push(new Paragraph({
    children: [new TextRun("수동 API 호출 방법 (참고용):")],
    spacing: { after: 100 }
  }));

  sections.push(createCodeBlock(`POST https://{MALL_ID}.cafe24api.com/api/v2/oauth/token
Content-Type: application/x-www-form-urlencoded
Authorization: Basic {Base64(CLIENT_ID:CLIENT_SECRET)}

grant_type=authorization_code&
code={발급받은_code}&
redirect_uri={REDIRECT_URI}`));

  sections.push(new Paragraph({ spacing: { after: 120 }, children: [new TextRun("")] }));

  sections.push(createStep(6, "토큰 파일 확인", ""));
  sections.push(new Paragraph({
    children: [new TextRun("자동 생성된 토큰 파일의 구조:")],
    spacing: { after: 100 }
  }));

  sections.push(createCodeBlock(`{
  "access_token": "발급된_Access_Token",
  "refresh_token": "발급된_Refresh_Token",
  "expires_at": 1714000000,
  "refresh_token_expires_at": 1715200000
}`));

  sections.push(new Paragraph({
    children: [new TextRun({
      text: "파일명: config/renk_cafe24_token.json",
      italic: true,
      size: 20
    })],
    spacing: { after: 200 }
  }));

  sections.push(new Paragraph({
    children: [new TextRun({
      text: "5.3 연결 테스트",
      bold: true,
      size: 26,
      color: COLORS.cafe24Blue
    })],
    spacing: { before: 120, after: 120 }
  }));

  sections.push(createCodeBlock("python cafe24_api_fetcher.py --test"));

  sections.push(new Paragraph({
    children: [new TextRun("성공 메시지가 출력되면 연결 완료입니다.")],
    spacing: { after: 200 }
  }));

  sections.push(new Paragraph({
    children: [new TextRun({
      text: "5.4 트러블슈팅",
      bold: true,
      size: 26,
      color: COLORS.cafe24Blue
    })],
    spacing: { before: 120, after: 120 }
  }));

  sections.push(createStyledTable([
    ["에러", "원인", "해결책"],
    ["401 Unauthorized", "Access Token 만료", "자동 갱신 실패 시 cafe24_get_token.py로 재발급"],
    ["403 Forbidden", "Scope(권한) 부족", "앱 설정에서 필요한 권한 추가 후 재인증"],
    ["invalid_grant", "Refresh Token 만료 (2주)", "Authorization Code부터 재발급 (Step 4부터)"],
    ["client_id invalid", "Client ID 오류", "개발자센터 > 앱 관리에서 정확한 ID 확인"]
  ], [2340, 2340, 2340]));

  sections.push(new Paragraph({ spacing: { after: 120 }, children: [new TextRun("")] }));

  sections.push(createWarningBox(
    "Refresh Token 갱신 주의",
    "카페24 Refresh Token은 2주마다 만료됩니다. 매일 run_daily.py를 실행하면 자동 갱신되지만, 2주 이상 실행하지 않으면 토큰이 만료됩니다. 만료 시 Step 4(Authorization Code 발급)부터 다시 시작해야 합니다.",
    true
  ));

  sections.push(new Paragraph({ spacing: { after: 120 }, children: [new TextRun("")] }));

  sections.push(new Paragraph({
    children: [new TextRun({
      text: "5.5 대행사 팁",
      bold: true,
      size: 26,
      color: COLORS.cafe24Blue
    })],
    spacing: { before: 120, after: 80 }
  }));

  sections.push(createBullet("카페24 앱은 쇼핑몰 단위로 설치 — 고객사별 별도 앱 생성 필요"));
  sections.push(createBullet("고객사 쇼핑몰 관리자에게 앱 설치 승인을 요청해야 함"));
  sections.push(createBullet("Refresh Token 만료 관리가 핵심 — 자동 실행 일정을 2주 이내로 유지"));

  sections.push(new Paragraph({ children: [new PageBreak()] }));

  // ===== CHAPTER 6: 인증 파일 총 정리 =====
  sections.push(createAccentHeader("Chapter 6: 인증 파일 총 정리", 1, COLORS.darkBlue));

  sections.push(new Paragraph({
    children: [new TextRun("모든 인증 파일을 한 곳에 정리했습니다. 각 파일을 config 폴더에 저장하세요.")],
    spacing: { after: 120 }
  }));

  sections.push(createStyledTable([
    ["파일명", "매체", "저장 위치"],
    ["renk_meta_credentials.json", "Meta 광고", "config/"],
    ["renk_google_ads_credentials.json", "Google Ads", "config/"],
    ["renk_naver_credentials.json", "네이버 검색광고", "config/"],
    ["renk_kakao_credentials.json", "카카오 광고", "config/"],
    ["renk_cafe24_token.json", "카페24", "config/"]
  ], [2340, 2340, 2340]));

  sections.push(new Paragraph({ spacing: { after: 200 }, children: [new TextRun("")] }));

  sections.push(createWarningBox(
    "Windows 사용자 메모장 JSON 파일 작성 팁",
    "1. 메모장 열기 > JSON 내용 붙여넣기\n2. 파일 > 다른 이름으로 저장\n3. '파일 형식'을 '모든 파일(*.*)'로 변경\n4. 파일명에 .json 확장자 직접 입력\n5. 인코딩: UTF-8 선택\n\n만약 .json.txt로 저장되었다면 파일명에서 .txt를 제거하세요.",
    true
  ));

  sections.push(new Paragraph({ children: [new PageBreak()] }));

  // ===== CHAPTER 7: 전체 테스트 및 일일 자동화 =====
  sections.push(createAccentHeader("Chapter 7: 전체 테스트 및 일일 자동화", 1, COLORS.darkBlue));

  sections.push(new Paragraph({
    children: [new TextRun({
      text: "개별 테스트",
      bold: true,
      size: 26
    })],
    spacing: { before: 120, after: 120 }
  }));

  sections.push(new Paragraph({
    children: [new TextRun("각 매체별 연결을 확인합니다. 모든 명령어가 성공하면 다음 단계로 진행합니다.")],
    spacing: { after: 100 }
  }));

  sections.push(createCodeBlock(`# Meta 테스트
python meta_api_fetcher.py --test

# Google Ads 테스트
python google_ads_fetcher.py --test

# 네이버 검색광고 테스트
python naver_api_fetcher.py --test

# 카카오 광고 테스트
python kakao_api_fetcher.py --test

# 카페24 테스트
python cafe24_api_fetcher.py --test`));

  sections.push(new Paragraph({ spacing: { after: 200 }, children: [new TextRun("")] }));

  sections.push(new Paragraph({
    children: [new TextRun({
      text: "일일 자동 실행",
      bold: true,
      size: 26
    })],
    spacing: { before: 120, after: 120 }
  }));

  sections.push(new Paragraph({
    children: [new TextRun("모든 매체의 데이터를 한 번에 수집합니다.")],
    spacing: { after: 100 }
  }));

  sections.push(createCodeBlock(`# 전체 파이프라인 실행
python run_daily.py

# 또는 Windows 사용자:
실행_윈도우.bat (더블클릭)`));

  sections.push(new Paragraph({ spacing: { after: 200 }, children: [new TextRun("")] }));

  sections.push(new Paragraph({
    children: [new TextRun({
      text: "최종 체크리스트",
      bold: true,
      size: 26
    })],
    spacing: { before: 120, after: 120 }
  }));

  sections.push(createStyledTable([
    ["#", "항목", "상태"],
    ["1", "Meta 시스템 유저 토큰 발급", ""],
    ["2", "Meta 인증 파일 작성 + 테스트 통과", ""],
    ["3", "Google Cloud 프로젝트 + API 활성화", ""],
    ["4", "Google OAuth Client 생성", ""],
    ["5", "Google Developer Token (기본 액세스 신청)", ""],
    ["6", "Google Refresh Token 발급", ""],
    ["7", "Google Ads 인증 파일 작성 + 테스트 통과", ""],
    ["8", "네이버 API Key + Secret Key 발급", ""],
    ["9", "네이버 인증 파일 작성 + 테스트 통과", ""],
    ["10", "카카오 개발자 앱 등록 + 비즈니스 전환", ""],
    ["11", "카카오모먼트 토큰 발급", ""],
    ["12", "카카오 키워드광고 토큰 발급", ""],
    ["13", "카카오 인증 파일 작성 + 테스트 통과", ""],
    ["14", "카페24 개발자센터 앱 생성", ""],
    ["15", "카페24 Authorization Code 발급", ""],
    ["16", "카페24 토큰 교환 (cafe24_get_token.py)", ""],
    ["17", "카페24 연결 테스트 통과", ""],
    ["18", "run_daily.py 통합 실행 성공", ""]
  ], [467, 6533, 2360]));

  sections.push(new Paragraph({ spacing: { after: 200 }, children: [new TextRun("")] }));

  sections.push(createWarningBox(
    "완료 후",
    "모든 테스트가 성공하면 일일 실행 일정을 설정하고, Cowork에 결과 로그를 붙여넣어 데이터 분석을 시작하세요.",
    false
  ));

  // Create document
  const doc = new Document({
    styles: {
      default: {
        document: {
          run: { font: "Arial", size: 22 },
          paragraph: { spacing: { line: 360, lineRule: "auto" } }
        }
      },
      paragraphStyles: [
        {
          id: "Heading1",
          name: "Heading 1",
          basedOn: "Normal",
          next: "Normal",
          quickFormat: true,
          run: { size: 32, bold: true, font: "Arial", color: COLORS.darkBlue },
          paragraph: { spacing: { before: 240, after: 240 }, outlineLevel: 0 }
        },
        {
          id: "Heading2",
          name: "Heading 2",
          basedOn: "Normal",
          next: "Normal",
          quickFormat: true,
          run: { size: 28, bold: true, font: "Arial", color: COLORS.darkBlue },
          paragraph: { spacing: { before: 200, after: 180 }, outlineLevel: 1 }
        }
      ]
    },
    numbering: {
      config: [
        {
          reference: "bullets",
          levels: [
            {
              level: 0,
              format: LevelFormat.BULLET,
              text: "•",
              alignment: AlignmentType.LEFT,
              style: {
                paragraph: { indent: { left: 720, hanging: 360 } }
              }
            }
          ]
        },
        {
          reference: "numbers",
          levels: [
            {
              level: 0,
              format: LevelFormat.DECIMAL,
              text: "%1.",
              alignment: AlignmentType.LEFT,
              style: {
                paragraph: { indent: { left: 720, hanging: 360 } }
              }
            }
          ]
        }
      ]
    },
    sections: [
      {
        properties: {
          page: {
            size: {
              width: 12240,
              height: 15840
            },
            margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 }
          }
        },
        headers: {
          default: new Header({
            children: [
              new Paragraph({
                children: [new TextRun({
                  text: "광고매체 API 통합 셋업 가이드",
                  size: 20,
                  color: COLORS.darkBlue
                })],
                alignment: AlignmentType.CENTER,
                border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: COLORS.darkBlue } },
                spacing: { after: 100 }
              })
            ]
          })
        },
        footers: {
          default: new Footer({
            children: [
              new Paragraph({
                children: [
                  new TextRun({
                    text: "Page ",
                    size: 18
                  }),
                  new TextRun({
                    children: [PageNumber.CURRENT],
                    size: 18
                  }),
                  new TextRun({
                    text: " | 브랜드마케팅1팀",
                    size: 18
                  })
                ],
                alignment: AlignmentType.CENTER,
                spacing: { before: 100 }
              })
            ]
          })
        },
        children: sections
      }
    ]
  });

  // Write document
  return Packer.toBuffer(doc).then(buffer => {
    const outputDir = '/sessions/adoring-bold-einstein/mnt/valen_brandmarketing_Team1_AI.Assistant/docs/guide';
    if (!fs.existsSync(outputDir)) {
      fs.mkdirSync(outputDir, { recursive: true });
    }
    const outputPath = `${outputDir}/광고매체_API_통합_셋업가이드.docx`;
    fs.writeFileSync(outputPath, buffer);
    console.log(`Document created: ${outputPath}`);
    return outputPath;
  });
}

generateDocument().catch(err => {
  console.error('Error:', err);
  process.exit(1);
});
