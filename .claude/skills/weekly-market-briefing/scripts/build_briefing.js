#!/usr/bin/env node
/*
 * 주간 시황브리핑 docx 생성기
 *
 * 사용법:
 *   node build_briefing.js content.json /mnt/user-data/outputs/0728_0804_시황브리핑_발표용.docx
 *
 * content.json 형식:
 * {
 *   "title": "[7/28~8/4 시황 브리핑] 부제",
 *   "sections": [
 *     { "head": "1. 국내 증시: ...", "bullets": ["문장. **강조구절**. 문장."] }
 *   ]
 * }
 *
 * 불릿 문장 안의 **...** 는 볼드 + 노란 음영으로 렌더링된다.
 */

const {
  Document, Packer, Paragraph, TextRun, BorderStyle,
  LevelFormat, AlignmentType, ShadingType, convertInchesToTwip
} = require('docx');
const fs = require('fs');

const FONT = '맑은 고딕';
const NAVY = '0B3D91';
const INK = '1A1A1A';
const MARK = 'FFF0A5';

function title(text) {
  return new Paragraph({
    border: { bottom: { style: BorderStyle.SINGLE, size: 8, space: 4, color: NAVY } },
    spacing: { after: 140 },
    children: [new TextRun({ text, font: FONT, bold: true, size: 30, color: INK })]
  });
}

function head(text) {
  return new Paragraph({
    spacing: { before: 260, after: 120 },
    children: [new TextRun({ text, font: FONT, bold: true, size: 23, color: NAVY })]
  });
}

function bullet(text) {
  const parts = String(text).split('**');
  const children = [];
  parts.forEach((seg, i) => {
    if (seg === '') return;
    const opts = { text: seg, font: FONT, size: 21, color: INK };
    if (i % 2 === 1) {                       // ** 사이 구절 = 강조
      opts.bold = true;
      opts.shading = { type: ShadingType.CLEAR, fill: MARK };
    }
    children.push(new TextRun(opts));
  });
  return new Paragraph({
    numbering: { reference: 'bl', level: 0 },
    spacing: { after: 90, line: 300 },
    children
  });
}

function build(data) {
  const children = [title(data.title)];
  (data.sections || []).forEach(sec => {
    children.push(head(sec.head));
    (sec.bullets || []).forEach(b => children.push(bullet(b)));
  });

  return new Document({
    numbering: {
      config: [{
        reference: 'bl',
        levels: [{
          level: 0, format: LevelFormat.BULLET, text: '•', alignment: AlignmentType.LEFT,
          style: {
            paragraph: {
              indent: {
                left: convertInchesToTwip(0.3),
                hanging: convertInchesToTwip(0.18)
              }
            }
          }
        }]
      }]
    },
    sections: [{
      properties: { page: { margin: { top: 1000, bottom: 1000, left: 1100, right: 1100 } } },
      children
    }]
  });
}

function main() {
  const [, , jsonPath, outPath] = process.argv;
  if (!jsonPath || !outPath) {
    console.error('사용법: node build_briefing.js <content.json> <출력.docx>');
    process.exit(1);
  }
  const data = JSON.parse(fs.readFileSync(jsonPath, 'utf-8'));
  if (!data.title || !Array.isArray(data.sections)) {
    console.error('오류: title 과 sections 가 필요합니다.');
    process.exit(1);
  }
  Packer.toBuffer(build(data)).then(buf => {
    fs.writeFileSync(outPath, buf);
    const n = data.sections.reduce((a, s) => a + (s.bullets || []).length, 0);
    console.log(`생성 완료: ${outPath} (섹션 ${data.sections.length}개 / 불릿 ${n}개)`);
    if (n > 22) console.log('주의: 불릿 22개 초과 — 발표 2분을 넘길 수 있습니다.');
  });
}

main();
