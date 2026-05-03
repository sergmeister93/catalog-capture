// Builds Catalog_Capture_Overview.docx — a non-technical, ~5-minute read
// for a small-business boss explaining the Catalog Capture POC.

const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, ImageRun,
  Table, TableRow, TableCell, AlignmentType, HeadingLevel,
  LevelFormat, BorderStyle, WidthType, ShadingType, PageBreak,
} = require("docx");

const OUT_DIR = "C:/Users/serge/OneDrive/Claude Projects/ServicePhoto/UsedItemsListing_App/Handover";
const OUT_PATH = path.join(OUT_DIR, "Catalog_Capture_Overview.docx");
const CHART_PATH = path.join(OUT_DIR, "How It Works.png");

// --- Helpers ----------------------------------------------------------------

const PRIMARY = "1F3A5F";   // deep navy for headings
const ACCENT  = "2E75B6";   // friendly blue for rules
const SOFT_BG = "EEF3F8";   // very pale blue for callouts
const MUTED   = "6B7280";   // muted grey for subtitle

function p(text, opts = {}) {
  return new Paragraph({
    spacing: { after: 120, ...(opts.spacing || {}) },
    alignment: opts.alignment,
    children: [new TextRun({ text, bold: opts.bold, italics: opts.italics, size: opts.size, color: opts.color })],
  });
}

function h1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 320, after: 160 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: ACCENT, space: 4 } },
    children: [new TextRun({ text, bold: true, color: PRIMARY })],
  });
}

function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 240, after: 120 },
    children: [new TextRun({ text, bold: true, color: PRIMARY })],
  });
}

function bullet(text, level = 0) {
  return new Paragraph({
    numbering: { reference: "bullets", level },
    spacing: { after: 80 },
    children: parseRuns(text),
  });
}

// Allow **bold** inside a string for light emphasis.
function parseRuns(text) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g).filter(Boolean);
  return parts.map(part => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return new TextRun({ text: part.slice(2, -2), bold: true });
    }
    return new TextRun({ text: part });
  });
}

function callout(title, body) {
  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [9360],
    rows: [
      new TableRow({
        children: [
          new TableCell({
            width: { size: 9360, type: WidthType.DXA },
            shading: { fill: SOFT_BG, type: ShadingType.CLEAR },
            borders: {
              top:    { style: BorderStyle.SINGLE, size: 4, color: ACCENT },
              bottom: { style: BorderStyle.SINGLE, size: 4, color: ACCENT },
              left:   { style: BorderStyle.SINGLE, size: 24, color: ACCENT },
              right:  { style: BorderStyle.SINGLE, size: 4, color: ACCENT },
            },
            margins: { top: 160, bottom: 160, left: 200, right: 200 },
            children: [
              new Paragraph({
                spacing: { after: 80 },
                children: [new TextRun({ text: title, bold: true, color: PRIMARY })],
              }),
              new Paragraph({ children: parseRuns(body) }),
            ],
          }),
        ],
      }),
    ],
  });
}

// Two-column comparison table (e.g., "AI helps with" vs "Person stays in control of")
function twoColTable(leftHeader, rightHeader, rows) {
  const headerCell = (text) => new TableCell({
    width: { size: 4680, type: WidthType.DXA },
    shading: { fill: PRIMARY, type: ShadingType.CLEAR },
    margins: { top: 100, bottom: 100, left: 140, right: 140 },
    children: [new Paragraph({ children: [new TextRun({ text, bold: true, color: "FFFFFF" })] })],
  });
  const bodyCell = (text) => new TableCell({
    width: { size: 4680, type: WidthType.DXA },
    margins: { top: 100, bottom: 100, left: 140, right: 140 },
    children: [new Paragraph({ children: parseRuns(text) })],
  });
  const border = { style: BorderStyle.SINGLE, size: 4, color: "CCCCCC" };
  const allBorders = { top: border, bottom: border, left: border, right: border };
  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [4680, 4680],
    rows: [
      new TableRow({ tableHeader: true, children: [headerCell(leftHeader), headerCell(rightHeader)] }),
      ...rows.map(([l, r]) => new TableRow({
        children: [
          new TableCell({ ...bodyCell(l), borders: allBorders, width: { size: 4680, type: WidthType.DXA }, margins: { top: 100, bottom: 100, left: 140, right: 140 }, children: [new Paragraph({ children: parseRuns(l) })] }),
          new TableCell({ ...bodyCell(r), borders: allBorders, width: { size: 4680, type: WidthType.DXA }, margins: { top: 100, bottom: 100, left: 140, right: 140 }, children: [new Paragraph({ children: parseRuns(r) })] }),
        ],
      })),
    ],
  });
}

// --- Document content -------------------------------------------------------

const titleBlock = [
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 0, after: 80 },
    children: [new TextRun({ text: "Catalog Capture", bold: true, size: 56, color: PRIMARY })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 80 },
    children: [new TextRun({ text: "From staged photos to a ready-to-publish product listing — in minutes.", italics: true, size: 26, color: MUTED })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 320 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: ACCENT, space: 8 } },
    children: [new TextRun({ text: "A Plain-English Overview", size: 22, color: MUTED })],
  }),
];

const whatItIs = [
  h1("What Catalog Capture Is"),
  p("Catalog Capture is a small internal tool that turns staged product photos into draft online listings. A staff member drops in a few photos of an item; the app uses AI to read the photos and fill in the product details, description, condition, and a fair-price estimate; a person reviews and edits the draft; and the approved listings export as a single spreadsheet, ready to upload to whatever sales channel the business uses."),
  p("The goal is simple: cut the time it takes to list a used item from twenty or thirty minutes of typing down to a couple of minutes of reviewing. The person stays in charge — the AI just does the tedious first draft."),
];

const howItWorks = [
  h1("How It Works"),
  p("The diagram below shows the full journey, from snapping a photo to publishing a listing. The five steps are designed so the staff member spends almost all of their time on Step 4 — reviewing what the AI produced — instead of typing from scratch."),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 160, after: 200 },
    children: [
      new ImageRun({
        type: "png",
        data: fs.readFileSync(CHART_PATH),
        transformation: { width: 600, height: 380 },
        altText: {
          title: "How Catalog Capture Works",
          description: "A five-step flow: take photos, send for AI review, AI analyzes photos, review and approve, publish online.",
          name: "HowItWorks",
        },
      }),
    ],
  }),
];

const stepWalkthrough = [
  h2("Step-by-step, in plain English"),
  bullet("**Take photos.** A staff member stages the item and snaps a few clear photos — front, back, any labels or serial numbers, and any included accessories."),
  bullet("**Send for AI review.** The photos are dropped into the app. One click sends them off to be analyzed."),
  bullet("**AI analyzes the photos.** The AI reads each image and writes a draft listing — the product name, brand, model, a description, the condition, what accessories it can see, and a suggested fair price based on what similar items are selling for online."),
  bullet("**Review and approve.** The staff member reviews each draft. They can edit any field — fix a typo, adjust the price, rewrite the description — and then approve it. Nothing leaves the app until a person says it's ready."),
  bullet("**Publish online.** Once approved, all the listings export as a single spreadsheet that can be uploaded to the business's sales channels."),
];

const aiVsHuman = [
  h1("Where AI Helps, and Where the Person Stays in Control"),
  p("This is the most important point for anyone evaluating the tool. Catalog Capture is built around the idea that the AI is a fast assistant, not a decision-maker. Every listing that ever leaves the app has been seen and approved by a person."),
  twoColTable(
    "What the AI does",
    "What the person stays in control of",
    [
      ["Reads the photos and identifies the product, brand, and model.", "Confirms the AI got the product right and fixes anything wrong."],
      ["Writes a first-draft description and condition note.", "Edits the wording, tone, and any details the photos couldn't show."],
      ["Looks up comparable items online and suggests a fair price.", "Decides the final asking price based on knowledge of the local market."],
      ["Lists the accessories visible in the photos.", "Adds anything the camera missed and removes anything not actually included."],
      ["Flags items it isn't sure about.", "Decides whether to keep, fix, or remove uncertain listings before export."],
    ]
  ),
  new Paragraph({ spacing: { before: 200 } }),
  callout(
    "The simple rule",
    "Nothing is published, exported, or sent anywhere until a person clicks Approve. The AI saves time on the first draft. The person owns the final word."
  ),
];

const scope = [
  h1("What the Tool Does — and What It Doesn't"),
  p("This is a proof of concept. It exists to show that the workflow works end-to-end and to give the business a foundation to build on. To keep it focused, a few things are deliberately left out for now."),
  twoColTable(
    "In scope today",
    "Not in scope yet",
    [
      ["Drag-and-drop photo upload from a laptop.", "Snapping photos directly from a phone into the app."],
      ["AI-generated draft listings with descriptions and pricing.", "Automatic posting to eBay, Facebook Marketplace, or other channels."],
      ["Side-by-side review and editing of every draft.", "Multiple reviewers working through a shared queue."],
      ["One-click bulk export to a CSV spreadsheet.", "Direct integration with inventory or accounting systems."],
      ["A clean, friendly interface designed for non-technical users.", "User accounts, permissions, or audit logs for who approved what."],
    ]
  ),
  new Paragraph({ spacing: { before: 160 } }),
  p("Each of these \"not yet\" items is a normal next step for a tool like this. They were left out on purpose so the proof of concept could be built and tested quickly without getting bogged down in features that aren't needed to prove the idea works."),
];

const costAndSpeed = [
  h1("What It Costs and How Fast It Runs Today"),
  p("Two practical numbers a sponsor usually wants to know up front: how much does each listing cost to generate, and how long does it take? Both are small, and both have room to get even better."),
  h2("Cost per listing"),
  p("Each photo sent to the AI costs roughly two cents. Because one photo produces one listing, the math is simple:"),
  twoColTable(
    "Volume",
    "Approximate AI cost",
    [
      ["1 item", "$0.02"],
      ["10 items", "$0.20"],
      ["100 items", "$2.00"],
      ["1,000 items", "$20.00"],
    ]
  ),
  new Paragraph({ spacing: { before: 160 } }),
  p("That covers the AI portion only — the price the business pays per photo to have the AI read it, write the draft, and look up a fair-market price. There are no per-user fees and no monthly minimums at this stage."),
  h2("Time per listing"),
  p("Today, the AI takes about 36 seconds to fully analyze one photo and produce a draft (including looking up a fair price online). A staff member can be reviewing earlier photos while later ones are still being processed, so a batch of ten items typically lands in a few minutes rather than ten times 36 seconds."),
  p("Compared to listing the same item by hand — typically twenty to thirty minutes of typing per item — the time savings are large even at today's speed."),
  callout(
    "Room to get faster",
    "The 36-second figure is the current state, not the ceiling. Straightforward improvements (processing several photos at once, sending smaller image files, separating the price-lookup step from the description step) could realistically bring the perceived wait down to just a few seconds per item. None of these would change the cost meaningfully."
  ),
];

const businessValue = [
  h1("What This Means for the Business"),
  p("Three things stand out about why this is worth a closer look."),
  bullet("**It saves real time.** Listing a used item by hand typically takes twenty to thirty minutes. With Catalog Capture, the same item takes a couple of minutes of reviewing — most of the typing is gone. Across a day's worth of items, that adds up quickly."),
  bullet("**It keeps the person in charge.** Unlike fully automated tools, nothing is published without human approval. The staff member's judgment about pricing, condition, and presentation is still the final word."),
  bullet("**It's a foundation, not a finished product.** Because the workflow is already proven end-to-end, the next steps — phone uploads, posting straight to a marketplace, multiple reviewers — are real, achievable additions rather than a rebuild from scratch."),
  new Paragraph({ spacing: { before: 200 } }),
  callout(
    "The bottom line",
    "Catalog Capture turns the slowest part of selling used items — writing the listing — into a quick review. The person still decides what gets published. The business gets more listings out the door, faster, with no loss of control."
  ),
];

const closing = [
  new Paragraph({ spacing: { before: 400 } }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    border: { top: { style: BorderStyle.SINGLE, size: 6, color: ACCENT, space: 8 } },
    spacing: { before: 200, after: 80 },
    children: [new TextRun({ text: "Questions or a walk-through? Happy to demo it live.", italics: true, color: MUTED })],
  }),
];

// --- Assemble ---------------------------------------------------------------

const doc = new Document({
  creator: "Sergey",
  title: "Catalog Capture — Overview",
  styles: {
    default: { document: { run: { font: "Calibri", size: 22 } } }, // 11pt body
    paragraphStyles: [
      {
        id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, font: "Calibri", color: PRIMARY },
        paragraph: { spacing: { before: 320, after: 160 }, outlineLevel: 0 },
      },
      {
        id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 26, bold: true, font: "Calibri", color: PRIMARY },
        paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 1 },
      },
    ],
  },
  numbering: {
    config: [{
      reference: "bullets",
      levels: [{
        level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 540, hanging: 280 } } },
      }],
    }],
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 1080, right: 1440, bottom: 1080, left: 1440 },
      },
    },
    children: [
      ...titleBlock,
      ...whatItIs,
      ...howItWorks,
      ...stepWalkthrough,
      ...aiVsHuman,
      ...scope,
      ...costAndSpeed,
      ...businessValue,
      ...closing,
    ],
  }],
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync(OUT_PATH, buf);
  console.log("Wrote:", OUT_PATH);
});
