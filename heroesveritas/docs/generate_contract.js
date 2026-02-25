// HEROES' VERITAS XR SYSTEMS — API Contract Document Generator
// Phase 1A — Component 6
// Run: node generate_contract.js

const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  HeadingLevel, AlignmentType, BorderStyle, WidthType, ShadingType,
  LevelFormat, PageNumber, PageBreak, Footer, Header, Tab, TabStopType,
  TabStopPosition, ImageRun, ExternalHyperlink
} = require("docx");
const fs = require("fs");
const path = require("path");

// ─── Brand colours ────────────────────────────────────────────────────────────
const C = {
  navy:       "0D1F3C",  // primary dark
  amber:      "C07A00",  // accent
  steel:      "2D4A6B",  // heading blue
  lightBlue:  "D6E4F0",  // table header fill
  paleBlue:   "EEF5FB",  // table alt row
  green:      "1A6630",  // success / POST
  red:        "7B1C1C",  // danger / DELETE
  purple:     "4A1A7B",  // WS messages
  grey:       "595959",  // body secondary
  white:      "FFFFFF",
  borderGrey: "B0C4D8",
  codeBack:   "F2F6FA",
  codeBorder: "C8D8E8",
};

const FONT     = "Arial";
const MONO     = "Courier New";
const PAGE_W   = 12240;  // 8.5 in
const PAGE_H   = 15840;  // 11 in
const MARGIN   = 1080;   // 0.75 in
const CONTENT_W = PAGE_W - MARGIN * 2;  // 10080 DXA

// ─── Helper builders ──────────────────────────────────────────────────────────

const run = (text, opts = {}) => new TextRun({
  text, font: FONT, size: opts.size || 22,
  bold: opts.bold || false,
  italics: opts.italic || false,
  color: opts.color || "000000",
  ...opts,
});

const monoRun = (text, opts = {}) => new TextRun({
  text, font: MONO, size: opts.size || 18,
  color: opts.color || C.navy,
  ...opts,
});

const para = (children, opts = {}) => new Paragraph({
  children: Array.isArray(children) ? children : [children],
  spacing: { before: opts.before || 80, after: opts.after || 80 },
  alignment: opts.align || AlignmentType.LEFT,
  ...opts,
});

const h1 = (text) => new Paragraph({
  heading: HeadingLevel.HEADING_1,
  children: [new TextRun({ text, font: FONT, size: 36, bold: true, color: C.steel })],
  spacing: { before: 400, after: 160 },
  border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: C.steel, space: 4 } },
});

const h2 = (text) => new Paragraph({
  heading: HeadingLevel.HEADING_2,
  children: [new TextRun({ text, font: FONT, size: 26, bold: true, color: C.steel })],
  spacing: { before: 280, after: 100 },
});

const h3 = (text) => new Paragraph({
  heading: HeadingLevel.HEADING_3,
  children: [new TextRun({ text, font: FONT, size: 22, bold: true, color: C.navy })],
  spacing: { before: 200, after: 80 },
});

const h4 = (text) => new Paragraph({
  children: [new TextRun({ text, font: FONT, size: 20, bold: true, color: C.amber })],
  spacing: { before: 160, after: 60 },
});

const body = (text, opts = {}) => para([run(text, { size: 22, color: opts.color || "000000" })], opts);

const note = (text) => new Paragraph({
  children: [
    new TextRun({ text: "NOTE  ", font: FONT, size: 20, bold: true, color: C.amber }),
    new TextRun({ text, font: FONT, size: 20, color: C.grey, italics: true }),
  ],
  spacing: { before: 60, after: 60 },
  indent: { left: 360 },
  border: { left: { style: BorderStyle.SINGLE, size: 12, color: C.amber, space: 8 } },
});

const codeLine = (text) => new Paragraph({
  children: [monoRun(text, { size: 18, color: C.navy })],
  spacing: { before: 20, after: 20 },
  indent: { left: 360, right: 360 },
  shading: { fill: C.codeBack, type: ShadingType.CLEAR },
  border: {
    top:    { style: BorderStyle.SINGLE, size: 2, color: C.codeBorder },
    bottom: { style: BorderStyle.SINGLE, size: 2, color: C.codeBorder },
    left:   { style: BorderStyle.SINGLE, size: 8, color: C.steel },
    right:  { style: BorderStyle.SINGLE, size: 2, color: C.codeBorder },
  },
});

const codeBlock = (lines) => lines.map(l => codeLine(l));

const bullet = (text, opts = {}) => new Paragraph({
  numbering: { reference: "bullets", level: opts.level || 0 },
  children: [run(text, { size: 21, color: opts.color || "000000" })],
  spacing: { before: 40, after: 40 },
});

const numbered = (text, opts = {}) => new Paragraph({
  numbering: { reference: "numbers", level: 0 },
  children: [run(text, { size: 21 })],
  spacing: { before: 40, after: 40 },
});

const spacer = (pts = 120) => new Paragraph({
  children: [new TextRun("")],
  spacing: { before: pts, after: 0 },
});

// ─── Table helpers ────────────────────────────────────────────────────────────

const border = { style: BorderStyle.SINGLE, size: 4, color: C.borderGrey };
const borders = { top: border, bottom: border, left: border, right: border };
const noBorder = { style: BorderStyle.NONE, size: 0, color: C.white };
const noBorders = { top: noBorder, bottom: noBorder, left: noBorder, right: noBorder };

const cell = (content, opts = {}) => {
  const children = typeof content === "string"
    ? [new Paragraph({
        children: [new TextRun({
          text: content,
          font: opts.mono ? MONO : FONT,
          size: opts.size || 20,
          bold: opts.bold || false,
          color: opts.textColor || "000000",
        })],
        spacing: { before: 40, after: 40 },
        alignment: opts.align || AlignmentType.LEFT,
      })]
    : content;
  return new TableCell({
    borders,
    width: { size: opts.w, type: WidthType.DXA },
    shading: { fill: opts.fill || C.white, type: ShadingType.CLEAR },
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    verticalAlign: opts.vAlign,
    children,
  });
};

const headerCell = (text, w) => cell(text, {
  w, fill: C.lightBlue, bold: true, size: 20, textColor: C.navy,
});

// Method badge cell
const methodCell = (method) => {
  const colors = {
    GET:    { fill: "E8F5E9", text: C.green },
    POST:   { fill: "E3F2FD", text: "1565C0" },
    PUT:    { fill: "FFF3E0", text: C.amber },
    DELETE: { fill: "FFEBEE", text: C.red },
    WS:     { fill: "F3E5F5", text: C.purple },
  };
  const c = colors[method] || { fill: "F5F5F5", text: C.grey };
  return cell(method, { w: 800, fill: c.fill, bold: true, size: 18, textColor: c.text, align: AlignmentType.CENTER });
};

const twoColRow = (col1, col2, fills = []) => new TableRow({
  children: [
    cell(col1, { w: 3000, fill: fills[0] || C.white }),
    cell(col2, { w: 7080, fill: fills[1] || C.white }),
  ],
});

// ─── Cover Page ───────────────────────────────────────────────────────────────

const coverPage = [
  spacer(800),
  new Paragraph({
    children: [run("HEROES' VERITAS XR SYSTEMS", { size: 48, bold: true, color: C.navy })],
    alignment: AlignmentType.CENTER,
    spacing: { before: 0, after: 60 },
  }),
  new Paragraph({
    children: [run("Backend API Contract", { size: 36, bold: true, color: C.steel })],
    alignment: AlignmentType.CENTER,
    spacing: { before: 0, after: 40 },
  }),
  new Paragraph({
    border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: C.amber, space: 2 } },
    children: [new TextRun("")],
    spacing: { before: 40, after: 40 },
  }),
  spacer(80),
  new Paragraph({
    children: [run("UE5.5 Integration Reference  ·  Phase 1A", { size: 24, color: C.grey, italic: true })],
    alignment: AlignmentType.CENTER,
    spacing: { before: 0, after: 240 },
  }),

  // Info block
  new Table({
    width: { size: 5760, type: WidthType.DXA },
    columnWidths: [2000, 3760],
    alignment: AlignmentType.CENTER,
    rows: [
      new TableRow({ children: [
        cell("Document Version", { w: 2000, fill: C.lightBlue, bold: true, size: 20 }),
        cell("1.0.0",             { w: 3760, size: 20 }),
      ]}),
      new TableRow({ children: [
        cell("System Version",    { w: 2000, fill: C.lightBlue, bold: true, size: 20 }),
        cell("Phase 1A (MVP)",    { w: 3760, size: 20 }),
      ]}),
      new TableRow({ children: [
        cell("Backend Build",     { w: 2000, fill: C.lightBlue, bold: true, size: 20 }),
        cell("gameplay v1.0.0  ·  economy v1.0.0  ·  config v1.0.0", { w: 3760, size: 20 }),
      ]}),
      new TableRow({ children: [
        cell("Target Client",     { w: 2000, fill: C.lightBlue, bold: true, size: 20 }),
        cell("Unreal Engine 5.5", { w: 3760, size: 20 }),
      ]}),
      new TableRow({ children: [
        cell("Audience",          { w: 2000, fill: C.lightBlue, bold: true, size: 20 }),
        cell("UE5.5 Contractor",  { w: 3760, size: 20 }),
      ]}),
      new TableRow({ children: [
        cell("Status",            { w: 2000, fill: C.lightBlue, bold: true, size: 20 }),
        cell("APPROVED — All 5 backend components validated", { w: 3760, size: 20, textColor: C.green, bold: true }),
      ]}),
    ],
  }),

  spacer(400),
  new Paragraph({
    children: [run("This document is the authoritative integration reference for the UE5.5 client contractor. It defines every network endpoint, message schema, object shape, and data contract the game engine must implement to connect to the Heroes' Veritas backend. No implementation decisions are left to inference.", { size: 20, color: C.grey })],
    alignment: AlignmentType.CENTER,
    spacing: { before: 0, after: 0 },
    indent: { left: 720, right: 720 },
  }),

  new Paragraph({ children: [new PageBreak()], spacing: { before: 0, after: 0 } }),
];

// ─── Section 1 — Overview ─────────────────────────────────────────────────────

const section1 = [
  h1("1.  System Overview"),

  body("The Heroes' Veritas backend is a Python/SQLite server-authoritative system. The UE5.5 client is a thin display layer. All game state lives in the backend. The client renders what it is told; it never makes unilateral state decisions."),
  spacer(80),

  h2("1.1  Network Topology"),
  body("The backend exposes two independent server processes on the same host:"),
  spacer(60),
  new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [1600, 1200, 2400, 3880],
    rows: [
      new TableRow({ children: [
        headerCell("Process",      1600),
        headerCell("Port",         1200),
        headerCell("Protocol",     2400),
        headerCell("Purpose",      3880),
      ]}),
      new TableRow({ children: [
        cell("operator_api.py",    { w: 1600, mono: true }),
        cell("8000",               { w: 1200, mono: true, align: AlignmentType.CENTER }),
        cell("HTTP/1.1 REST",      { w: 2400 }),
        cell("Operator dashboard, analytics, live config tuning", { w: 3880 }),
      ]}),
      new TableRow({ children: [
        cell("websocket_server.py", { w: 1600, mono: true, fill: C.paleBlue }),
        cell("8001",                { w: 1200, mono: true, align: AlignmentType.CENTER, fill: C.paleBlue }),
        cell("WebSocket (RFC 6455)", { w: 2400, fill: C.paleBlue }),
        cell("UE5.5 headsets — real-time game state sync", { w: 3880, fill: C.paleBlue }),
      ]}),
    ],
  }),
  spacer(120),
  note("The UE5.5 client connects ONLY to the WebSocket server (port 8001). The REST API is for the operator dashboard. The client must never call REST endpoints during gameplay."),
  spacer(80),

  h2("1.2  Architecture Principles"),
  bullet("Server-authoritative: All state transitions, XP calculations, flag evaluations, and loot grants happen on the backend. The client reports events; the backend decides consequences."),
  bullet("Config-driven: All tunable values (XP amounts, difficulty multipliers, session duration, hint timings) live in the config_store table. No hardcoded values exist in game logic."),
  bullet("Telemetry-first: Every meaningful action emits a structured telemetry event. The client does not need to log anything separately."),
  bullet("Idempotent flags: The same flag can be set multiple times with no adverse effect. Clients may safely retry flag-setting events."),
  bullet("Zero-dependency transport: The WebSocket server uses Python stdlib only. No broker, no Redis, no Kafka — direct TCP connections, one thread per client."),
  spacer(80),

  h2("1.3  Component Inventory"),
  new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [760, 2800, 2200, 3320],
    rows: [
      new TableRow({ children: [
        headerCell("#",         760),
        headerCell("Component", 2800),
        headerCell("File",      2200),
        headerCell("Status",    3320),
      ]}),
      ...[
        ["1", "Database Schema (17 tables)",          "db/schema.py",                      "✓ Validated"],
        ["2", "Session Orchestration Engine",          "services/orchestration.py",          "✓ Validated · 9-state machine"],
        ["3", "Economy & Progression System",          "services/economy.py",                "✓ Validated · 56/56 checks"],
        ["4", "Operator Control Dashboard + REST API", "operator_api.py + dashboard.html",   "✓ Validated · 44/44 checks"],
        ["5", "WebSocket Real-Time Layer",             "services/websocket_server.py",       "✓ Validated · 44/44 checks"],
        ["6", "API Contract Document",                 "docs/api_contract.docx",             "✓ This document"],
      ].map(([num, comp, file, status], i) => new TableRow({ children: [
        cell(num,    { w: 760,  align: AlignmentType.CENTER, fill: i%2===0?C.white:C.paleBlue }),
        cell(comp,   { w: 2800, fill: i%2===0?C.white:C.paleBlue }),
        cell(file,   { w: 2200, mono: true, size: 18, fill: i%2===0?C.white:C.paleBlue }),
        cell(status, { w: 3320, fill: i%2===0?C.white:C.paleBlue, textColor: C.green, bold: true }),
      ]})),
    ],
  }),

  new Paragraph({ children: [new PageBreak()], spacing: { before: 0, after: 0 } }),
];

// ─── Section 2 — WebSocket Protocol ──────────────────────────────────────────

const section2 = [
  h1("2.  WebSocket Protocol"),

  h2("2.1  Connection Lifecycle"),
  body("The UE5.5 client follows this exact sequence for every session:"),
  spacer(60),

  new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [640, 2560, 6880],
    rows: [
      new TableRow({ children: [
        headerCell("Step", 640),
        headerCell("Action",  2560),
        headerCell("Detail",  6880),
      ]}),
      ...[
        ["1", "TCP + Upgrade",      "Connect to ws://[host]:8001. Standard RFC 6455 HTTP Upgrade handshake."],
        ["2", "Receive connected",  "Server immediately sends a connected message containing the client's assigned client_id."],
        ["3", "Send authenticate",  "Client sends authenticate with session_id, player_id, and client_type='ue5'. This MUST be the first message sent."],
        ["4", "Receive authenticated", "Server confirms authentication and echoes back client_id."],
        ["5", "Receive session_state", "Server immediately pushes the full session object. Client renders initial state from this."],
        ["6", "Game loop",          "Client sends game events. Server pushes state changes. See §2.3 and §2.4."],
        ["7", "Heartbeat",          "Client sends a heartbeat message every 30 seconds. Clients silent for 45 seconds are disconnected."],
        ["8", "Disconnect",         "Client sends a WebSocket close frame (opcode 0x08) when the headset session ends."],
      ].map(([step, action, detail], i) => new TableRow({ children: [
        cell(step,   { w: 640,  align: AlignmentType.CENTER, fill: i%2===0?C.white:C.paleBlue, bold: true }),
        cell(action, { w: 2560, fill: i%2===0?C.white:C.paleBlue, bold: true }),
        cell(detail, { w: 6880, fill: i%2===0?C.white:C.paleBlue }),
      ]})),
    ],
  }),
  spacer(120),

  h2("2.2  Message Envelope"),
  body("Every message in both directions uses the same JSON envelope:"),
  spacer(60),
  ...codeBlock([
    '{',
    '  "type":    "<MESSAGE_TYPE>",',
    '  "payload": { ... }',
    '}',
  ]),
  spacer(80),
  body("Messages are UTF-8 encoded JSON sent as WebSocket text frames (opcode 0x01). Binary frames are not used. Client-to-server frames must be masked per RFC 6455. Server-to-client frames are unmasked."),
  spacer(80),

  h2("2.3  Client → Server Messages"),
  body("The following messages may be sent by the UE5.5 client. All require prior authentication except authenticate itself."),
  spacer(80),

  // authenticate
  h3("authenticate"),
  body("Must be the first message sent after WebSocket connection. All other messages are rejected until this succeeds."),
  spacer(60),
  ...codeBlock([
    '{',
    '  "type": "authenticate",',
    '  "payload": {',
    '    "session_id":  "<uuid>",      // required — from session creation',
    '    "player_id":   "<string>",    // required — registered player ID',
    '    "client_type": "ue5"          // required — always "ue5" for headsets',
    '  }',
    '}',
  ]),
  spacer(80),

  // node_action
  h3("node_action"),
  body("Generic interaction event. Used for any player action within a node that is not a full solve — button presses, item placements, switch toggles, etc. The backend logs this as telemetry and broadcasts it to other clients in the session."),
  spacer(60),
  ...codeBlock([
    '{',
    '  "type": "node_action",',
    '  "payload": {',
    '    "session_id":  "<uuid>",',
    '    "node_id":     "<node_id>",',
    '    "action_type": "<string>",    // e.g. "button_press", "item_placed", "switch_toggled"',
    '    "data":        { ... }        // optional freeform context',
    '  }',
    '}',
  ]),
  spacer(80),

  // puzzle_progress
  h3("puzzle_progress"),
  body("Reports incremental progress within a puzzle. Use for step-by-step puzzles where partial progress should be visible on the operator dashboard. Does not advance the node — only puzzle_solved does that."),
  spacer(60),
  ...codeBlock([
    '{',
    '  "type": "puzzle_progress",',
    '  "payload": {',
    '    "session_id": "<uuid>",',
    '    "node_id":    "<node_id>",',
    '    "step":       <integer>,      // which step was just completed (1-based)',
    '    "value":      "<string>"      // optional — description of what was done',
    '  }',
    '}',
  ]),
  spacer(80),

  // puzzle_solved
  h3("puzzle_solved"),
  body("Reports that a puzzle node has been completed. The backend automatically sets that node's exit flags, which triggers the node transition engine. The session advances to the next eligible node. A session_state broadcast is sent to all session clients."),
  spacer(60),
  ...codeBlock([
    '{',
    '  "type": "puzzle_solved",',
    '  "payload": {',
    '    "session_id": "<uuid>",',
    '    "node_id":    "<node_id>"     // the node that was just solved',
    '  }',
    '}',
  ]),
  spacer(40),
  note("The client must send puzzle_solved only once per node. Sending it again after a node is already completed is a no-op (flags are idempotent) but generates unnecessary telemetry."),
  spacer(80),

  // combat_wave_clear
  h3("combat_wave_clear"),
  body("Reports that one wave of a multi-wave combat node has been cleared. Informational — does not advance the node. Use this to drive visual feedback on the operator dashboard."),
  spacer(60),
  ...codeBlock([
    '{',
    '  "type": "combat_wave_clear",',
    '  "payload": {',
    '    "session_id":  "<uuid>",',
    '    "node_id":     "<node_id>",',
    '    "wave_number": <integer>      // 1-based wave index',
    '  }',
    '}',
  ]),
  spacer(80),

  // combat_complete
  h3("combat_complete"),
  body("Reports that a combat node has been fully completed (all waves cleared, boss defeated, etc.). Equivalent to puzzle_solved for combat nodes — triggers flag-setting and node advancement."),
  spacer(60),
  ...codeBlock([
    '{',
    '  "type": "combat_complete",',
    '  "payload": {',
    '    "session_id": "<uuid>",',
    '    "node_id":    "<node_id>"',
    '  }',
    '}',
  ]),
  spacer(80),

  // player_health
  h3("player_health"),
  body("Reports a player's current health and/or energy. Send this whenever health changes (damage, healing). The backend persists these values and broadcasts them to all clients in the session, including the operator dashboard."),
  spacer(60),
  ...codeBlock([
    '{',
    '  "type": "player_health",',
    '  "payload": {',
    '    "session_id": "<uuid>",',
    '    "player_id":  "<string>",     // which player (may differ from sender)',
    '    "health":     <integer>,      // 0-100',
    '    "energy":     <integer>       // 0-100, optional',
    '  }',
    '}',
  ]),
  spacer(80),

  // request_hint
  h3("request_hint"),
  body("Player manually requests a hint for the current node. The backend delivers a tiered hint (tier 1 → 2 → 3 on successive requests). Hint usage is tracked per node per session and visible on the operator dashboard."),
  spacer(60),
  ...codeBlock([
    '{',
    '  "type": "request_hint",',
    '  "payload": {',
    '    "session_id": "<uuid>",',
    '    "node_id":    "<node_id>",',
    '    "player_id":  "<string>"      // which player is requesting',
    '  }',
    '}',
  ]),
  spacer(80),

  // heartbeat
  h3("heartbeat"),
  body("Keepalive message. Send every 30 seconds. Any client that sends no messages for 45 seconds is disconnected by the server's timeout loop."),
  spacer(60),
  ...codeBlock([
    '{',
    '  "type": "heartbeat",',
    '  "payload": {}',
    '}',
  ]),
  spacer(80),

  h2("2.4  Server → Client Messages"),
  body("The backend pushes the following messages to UE5.5 clients. The client must handle all of them, even if it has no visible effect for some."),
  spacer(80),

  // connected
  h3("connected"),
  body("Sent immediately after the WebSocket handshake completes. Confirms the connection is live."),
  spacer(60),
  ...codeBlock([
    '{',
    '  "type": "connected",',
    '  "payload": {',
    '    "client_id": "<uuid>",        // this connection\'s unique ID',
    '    "server":    "Heroes Veritas WS v1.0",',
    '    "ts":        "<ISO-8601>"',
    '  }',
    '}',
  ]),
  spacer(80),

  // authenticated
  h3("authenticated"),
  body("Sent after a successful authenticate message. Followed immediately by session_state."),
  spacer(60),
  ...codeBlock([
    '{',
    '  "type": "authenticated",',
    '  "payload": {',
    '    "client_id":   "<uuid>",',
    '    "session_id":  "<uuid>",',
    '    "player_id":   "<string>",',
    '    "client_type": "ue5"',
    '  }',
    '}',
  ]),
  spacer(80),

  // session_state
  h3("session_state"),
  body("Full session snapshot. Sent on authentication and after any state-changing event (node advance, flag set, operator action). The client should treat this as the ground truth and fully reconcile its local state against it."),
  spacer(60),
  ...codeBlock([
    '{',
    '  "type": "session_state",',
    '  "payload": {',
    '    "session": { ... }            // full Session Object — see §3.1',
    '  }',
    '}',
  ]),
  spacer(80),

  // hint_delivered
  h3("hint_delivered"),
  body("Sent to all clients in the session when a hint is triggered (by player request or operator action). The UE5.5 client should display this as an in-world notification."),
  spacer(60),
  ...codeBlock([
    '{',
    '  "type": "hint_delivered",',
    '  "payload": {',
    '    "session_id": "<uuid>",',
    '    "node_id":    "<node_id>",',
    '    "tier":       <integer>,      // 1, 2, or 3 (3 = most explicit)',
    '    "type":       "<string>",     // "audio", "visual", "text", "gm_voice"',
    '    "message":    "<string>"      // hint content to display',
    '  }',
    '}',
  ]),
  spacer(80),

  // timer_sync
  h3("timer_sync"),
  body("Sent to all running-session clients every 15 seconds by the server's background loop. Use this to keep the client-side countdown timer accurate without relying solely on local clock drift."),
  spacer(60),
  ...codeBlock([
    '{',
    '  "type": "timer_sync",',
    '  "payload": {',
    '    "session_id":          "<uuid>",',
    '    "elapsed_secs":        <integer>,',
    '    "time_remaining_secs": <integer>',
    '  }',
    '}',
  ]),
  spacer(80),

  // player_update
  h3("player_update"),
  body("Pushed to all session clients when any player's health or energy changes. Use this to update health bars for all players' HUDs."),
  spacer(60),
  ...codeBlock([
    '{',
    '  "type": "player_update",',
    '  "payload": {',
    '    "session_id": "<uuid>",',
    '    "player_id":  "<string>",',
    '    "health":     <integer>,',
    '    "energy":     <integer>',
    '  }',
    '}',
  ]),
  spacer(80),

  // error
  h3("error"),
  body("Sent when the client sends a malformed or invalid message. The client should log these but never crash on receiving an error message."),
  spacer(60),
  ...codeBlock([
    '{',
    '  "type": "error",',
    '  "payload": {',
    '    "code":    "<ERROR_CODE>",    // see §2.5',
    '    "message": "<string>"',
    '  }',
    '}',
  ]),
  spacer(80),

  // pong
  h3("pong"),
  body("Response to a heartbeat message."),
  spacer(60),
  ...codeBlock([
    '{',
    '  "type": "pong",',
    '  "payload": { "ts": "<ISO-8601>" }',
    '}',
  ]),
  spacer(80),

  h2("2.5  Error Codes"),
  spacer(60),
  new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [2800, 7280],
    rows: [
      new TableRow({ children: [
        headerCell("Code",        2800),
        headerCell("Meaning",     7280),
      ]}),
      ...[
        ["NOT_AUTHENTICATED",  "Message received before authenticate was sent. Send authenticate first."],
        ["AUTH_MISSING",       "authenticate payload missing session_id or player_id."],
        ["SESSION_NOT_FOUND",  "The session_id in authenticate does not exist in the database."],
        ["MISSING_FIELDS",     "A required payload field is absent. Check the message schema above."],
        ["NODE_NOT_FOUND",     "The node_id does not exist in node_definitions."],
        ["HINT_ERROR",         "Hint could not be generated (e.g. node has no hints configured)."],
        ["HANDLER_ERROR",      "Unexpected server-side error. Log and report to backend team."],
        ["UNKNOWN_TYPE",       "The message type is not recognised. Check spelling."],
        ["PARSE_ERROR",        "Message body is not valid JSON."],
      ].map(([code, meaning], i) => new TableRow({ children: [
        cell(code,    { w: 2800, mono: true, size: 18, fill: i%2===0?C.white:C.paleBlue }),
        cell(meaning, { w: 7280, fill: i%2===0?C.white:C.paleBlue }),
      ]})),
    ],
  }),

  new Paragraph({ children: [new PageBreak()], spacing: { before: 0, after: 0 } }),
];

// ─── Section 3 — Data Objects ─────────────────────────────────────────────────

const section3 = [
  h1("3.  Data Objects"),

  h2("3.1  Session Object"),
  body("Returned by GET /api/sessions/{id} and in all session_state WebSocket messages."),
  spacer(80),
  new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [2600, 1400, 5080],
    rows: [
      new TableRow({ children: [
        headerCell("Field",       2600),
        headerCell("Type",        1400),
        headerCell("Description", 5080),
      ]}),
      ...[
        ["session_id",          "string",   "UUID. Primary key."],
        ["party_session_id",    "string",   "UUID. Groups all sessions for the same physical party across resets."],
        ["state",               "string",   "Current state machine state. See §3.2."],
        ["difficulty",          "string",   "\"easy\" | \"normal\" | \"hard\""],
        ["current_node_id",     "string?",  "ID of the currently active node. null if not in a node."],
        ["node_index",          "integer",  "0-based index of current node in the sequence."],
        ["timer_started_at",    "string?",  "ISO-8601 timestamp when the timer started. null if not running."],
        ["timer_paused_secs",   "integer",  "Total seconds the timer has been paused in this session."],
        ["total_duration_secs", "integer",  "Total session length in seconds. Default 3600."],
        ["elapsed_secs",        "integer",  "Seconds elapsed (computed). 0 if not started."],
        ["time_remaining_secs", "integer",  "Seconds remaining (computed). Equals total_duration_secs if not started."],
        ["gameplay_version",    "string",   "Backend gameplay build version when session was created."],
        ["content_version",     "string",   "Content asset version."],
        ["config_version",      "string",   "Config snapshot version."],
        ["economy_version",     "string",   "Economy system version."],
        ["room_id",             "string?",  "Physical room identifier. Set at session creation."],
        ["operator_id",         "string?",  "Player ID of the operator who created the session."],
        ["created_at",          "string",   "ISO-8601 creation timestamp."],
        ["completed_at",        "string?",  "ISO-8601 completion timestamp. null if not completed."],
        ["players",             "array",    "Array of Player State objects. See §3.3."],
        ["flags",               "array",    "Array of flag_id strings currently set in this session."],
        ["node_states",         "array",    "Array of Node State objects. See §3.4."],
      ].map(([field, type, desc], i) => new TableRow({ children: [
        cell(field, { w: 2600, mono: true, size: 18, fill: i%2===0?C.white:C.paleBlue }),
        cell(type,  { w: 1400, size: 19, fill: i%2===0?C.white:C.paleBlue, textColor: C.steel }),
        cell(desc,  { w: 5080, fill: i%2===0?C.white:C.paleBlue }),
      ]})),
    ],
  }),
  spacer(80),

  h2("3.2  Session States"),
  body("The session state machine has 9 states. The UE5.5 client must handle transitions between all of them."),
  spacer(60),
  new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [2000, 2400, 5680],
    rows: [
      new TableRow({ children: [
        headerCell("State",       2000),
        headerCell("Transitions To",    2400),
        headerCell("Client Behaviour",  5680),
      ]}),
      ...[
        ["idle",             "lobby",                 "Show lobby/waiting screen."],
        ["lobby",            "running",               "Session created, players joining. Show pre-game lobby."],
        ["running",          "paused, node_transition, completed, failed, error",   "Active gameplay. Timer counting down."],
        ["paused",           "running, idle",         "Gameplay frozen. Show pause indicator. Timer stopped."],
        ["node_transition",  "running",               "Backend is advancing to the next node. Show transition animation. Duration: ~0.01s."],
        ["resetting",        "idle",                  "Hard reset in progress. Show reset screen. SLA: ≤60 seconds."],
        ["completed",        "idle",                  "Session finished successfully. Show post-session summary."],
        ["failed",           "idle",                  "Time expired or force-failed. Show failure screen."],
        ["error",            "idle",                  "Unrecoverable error. Show error screen. Alert operator."],
      ].map(([state, transitions, behaviour], i) => new TableRow({ children: [
        cell(state,       { w: 2000, mono: true, size: 18, bold: true, fill: i%2===0?C.white:C.paleBlue }),
        cell(transitions, { w: 2400, mono: true, size: 16, fill: i%2===0?C.white:C.paleBlue }),
        cell(behaviour,   { w: 5680, fill: i%2===0?C.white:C.paleBlue }),
      ]})),
    ],
  }),
  spacer(80),

  h2("3.3  Player State Object"),
  body("Each object in the session.players array."),
  spacer(60),
  new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [2200, 1200, 5680],
    rows: [
      new TableRow({ children: [
        headerCell("Field",       2200),
        headerCell("Type",        1200),
        headerCell("Description", 5680),
      ]}),
      ...[
        ["player_id",  "string",  "Player identifier. Matches the player_id used in authenticate."],
        ["health",     "integer", "Current health 0–100. Updated via player_health messages."],
        ["energy",     "integer", "Current energy 0–100. Updated via player_health messages."],
        ["is_active",  "boolean", "Whether this player is currently connected and active."],
        ["joined_at",  "string",  "ISO-8601 timestamp when the player joined this session."],
      ].map(([field, type, desc], i) => new TableRow({ children: [
        cell(field, { w: 2200, mono: true, size: 18, fill: i%2===0?C.white:C.paleBlue }),
        cell(type,  { w: 1200, size: 19,   fill: i%2===0?C.white:C.paleBlue, textColor: C.steel }),
        cell(desc,  { w: 5680, fill: i%2===0?C.white:C.paleBlue }),
      ]})),
    ],
  }),
  spacer(80),

  h2("3.4  Node State Object"),
  body("Each object in the session.node_states array. Represents the current gameplay state of one node."),
  spacer(60),
  new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [2200, 1200, 5680],
    rows: [
      new TableRow({ children: [
        headerCell("Field",        2200),
        headerCell("Type",         1200),
        headerCell("Description",  5680),
      ]}),
      ...[
        ["node_id",       "string",  "Unique node identifier. Matches node_definitions.node_id."],
        ["node_type",     "string",  "\"narrative\" | \"puzzle\" | \"combat\" | \"reward\" | \"transition\""],
        ["display_name",  "string",  "Human-readable name for UI display."],
        ["state",         "string",  "\"locked\" | \"available\" | \"in_progress\" | \"completed\" | \"skipped\" | \"failed\""],
        ["attempts",      "integer", "How many times this node has been attempted."],
        ["hints_used",    "integer", "Total hints delivered for this node in this session."],
        ["entered_at",    "string?", "ISO-8601 when the node was first entered."],
        ["completed_at",  "string?", "ISO-8601 when the node was completed."],
        ["time_spent_secs","integer","Seconds spent in this node (running only, excludes pauses)."],
        ["sequence_order","integer", "Position in the linear node graph (0-based)."],
      ].map(([field, type, desc], i) => new TableRow({ children: [
        cell(field, { w: 2200, mono: true, size: 18, fill: i%2===0?C.white:C.paleBlue }),
        cell(type,  { w: 1200, size: 19,   fill: i%2===0?C.white:C.paleBlue, textColor: C.steel }),
        cell(desc,  { w: 5680, fill: i%2===0?C.white:C.paleBlue }),
      ]})),
    ],
  }),

  new Paragraph({ children: [new PageBreak()], spacing: { before: 0, after: 0 } }),
];

// ─── Section 4 — Node Graph ───────────────────────────────────────────────────

const section4 = [
  h1("4.  Node Graph"),

  body("The Phase 1A session consists of 7 nodes in a strict linear sequence. The entry and exit conditions define which flags must be set before a node unlocks, and which flags are set when a node is completed."),
  spacer(80),

  new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [400, 2800, 1400, 2000, 3480],
    rows: [
      new TableRow({ children: [
        headerCell("#",            400),
        headerCell("Node ID",      2800),
        headerCell("Type",         1400),
        headerCell("Entry Flag",   2000),
        headerCell("Sets Flag On Complete", 3480),
      ]}),
      ...[
        ["0", "node_intro_narrative_01", "narrative", "(none — always first)",  "narrative_01_complete"],
        ["1", "node_puzzle_runes_01",    "puzzle",    "narrative_01_complete",  "rune_puzzle_solved"],
        ["2", "node_combat_wave_01",     "combat",    "rune_puzzle_solved",     "combat_01_cleared"],
        ["3", "node_puzzle_spatial_01",  "puzzle",    "combat_01_cleared",      "spatial_puzzle_solved"],
        ["4", "node_puzzle_search_01",   "puzzle",    "spatial_puzzle_solved",  "codex_puzzle_solved"],
        ["5", "node_combat_boss_01",     "combat",    "codex_puzzle_solved",    "boss_defeated"],
        ["6", "node_reward_finale_01",   "reward",    "boss_defeated",          "session_complete"],
      ].map(([seq, nodeId, type, entry, exit_], i) => {
        const typeColors = { narrative: "E8F0FE", puzzle: "FFF8E1", combat: "FFEBEE", reward: "E8F5E9" };
        return new TableRow({ children: [
          cell(seq,     { w: 400,  align: AlignmentType.CENTER, bold: true, fill: i%2===0?C.white:C.paleBlue }),
          cell(nodeId,  { w: 2800, mono: true, size: 17, fill: i%2===0?C.white:C.paleBlue }),
          cell(type,    { w: 1400, fill: typeColors[type] || C.white, bold: true, size: 19, align: AlignmentType.CENTER }),
          cell(entry,   { w: 2000, mono: true, size: 16, fill: i%2===0?C.white:C.paleBlue }),
          cell(exit_,   { w: 3480, mono: true, size: 16, fill: i%2===0?C.white:C.paleBlue }),
        ]});
      }),
    ],
  }),
  spacer(120),

  note("The reward node (node_reward_finale_01) sets the session_complete flag. The backend detects this flag and automatically transitions the session state to 'completed', triggers generate_session_summary(), and pushes a final session_state to all clients."),
  spacer(80),

  h2("4.1  Node Type Behaviour"),
  spacer(60),
  new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [1400, 2000, 6680],
    rows: [
      new TableRow({ children: [
        headerCell("Type",       1400),
        headerCell("Solved By",  2000),
        headerCell("UE5.5 Responsibility", 6680),
      ]}),
      ...[
        ["narrative", "puzzle_solved",   "Play cutscene / narrative sequence. Send puzzle_solved when the narrative beat is complete."],
        ["puzzle",    "puzzle_solved",   "Render puzzle mechanics. Track partial progress via puzzle_progress. Send puzzle_solved when solved."],
        ["combat",    "combat_complete", "Run combat simulation. Send combat_wave_clear per wave. Send combat_complete when all waves done."],
        ["reward",    "puzzle_solved",   "Display reward animations. Send puzzle_solved to trigger session completion."],
      ].map(([type, solved, resp], i) => new TableRow({ children: [
        cell(type,   { w: 1400, bold: true, fill: i%2===0?C.white:C.paleBlue }),
        cell(solved, { w: 2000, mono: true, size: 17, fill: i%2===0?C.white:C.paleBlue }),
        cell(resp,   { w: 6680, fill: i%2===0?C.white:C.paleBlue }),
      ]})),
    ],
  }),

  new Paragraph({ children: [new PageBreak()], spacing: { before: 0, after: 0 } }),
];

// ─── Section 5 — REST API ─────────────────────────────────────────────────────

const section5 = [
  h1("5.  REST API  (Operator Dashboard)"),

  body("These endpoints are for the operator dashboard only. The UE5.5 client does not call them during gameplay. They are documented here for completeness and because the contractor may need to create a test session before running client integration tests."),
  spacer(80),

  h2("5.1  Endpoint Reference"),
  spacer(60),

  new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [800, 3400, 5880],
    rows: [
      new TableRow({ children: [
        headerCell("Method",   800),
        headerCell("Path",     3400),
        headerCell("Purpose",  5880),
      ]}),
      ...[
        ["GET",  "/api/health",                         "Health check. Returns {status:'ok'}."],
        ["GET",  "/api/sessions",                       "List last 50 sessions with state, player count, timer."],
        ["POST", "/api/sessions",                       "Create a new session. Body: {difficulty, room_id, player_ids}."],
        ["GET",  "/api/sessions/{id}",                  "Full session object. Same shape as WS session_state payload."],
        ["POST", "/api/sessions/{id}/action/start",     "Advance session from lobby → running. Starts timer."],
        ["POST", "/api/sessions/{id}/action/pause",     "Pause running session. Freezes timer."],
        ["POST", "/api/sessions/{id}/action/resume",    "Resume paused session. Restarts timer."],
        ["POST", "/api/sessions/{id}/action/bypass_node", "Skip current node. Body: {node_id}."],
        ["POST", "/api/sessions/{id}/action/soft_reset_node", "Reset current node state without clearing session. Body: {node_id}."],
        ["POST", "/api/sessions/{id}/action/hard_reset",  "Full session reset. Clears all flags and node states."],
        ["POST", "/api/sessions/{id}/action/trigger_hint","Deliver operator hint. Body: {node_id}."],
        ["POST", "/api/sessions/{id}/action/set_flag",   "Set a session flag. Body: {flag_id}."],
        ["POST", "/api/sessions/{id}/action/force_fail", "Force session to failed state immediately."],
        ["GET",  "/api/telemetry",                      "Global telemetry stream. Query: ?limit=N&session_id=X."],
        ["GET",  "/api/analytics",                      "Investor KPI metrics: completion rates, avg XP, etc."],
        ["GET",  "/api/config",                         "All live config key-value pairs."],
        ["POST", "/api/config",                         "Update a config value. Body: {config_key, config_value}."],
        ["GET",  "/api/nodes",                          "Node definitions from the database."],
        ["GET",  "/api/operator-log",                   "Recent operator actions with timestamps."],
      ].map(([method, path, purpose], i) => new TableRow({ children: [
        methodCell(method),
        cell(path,    { w: 3400, mono: true, size: 17, fill: i%2===0?C.white:C.paleBlue }),
        cell(purpose, { w: 5880, fill: i%2===0?C.white:C.paleBlue }),
      ]})),
    ],
  }),
  spacer(80),

  h2("5.2  Create Session — Request / Response"),
  body("The contractor will need to create test sessions during integration work."),
  spacer(60),
  h4("Request"),
  ...codeBlock([
    'POST http://[host]:8000/api/sessions',
    'Content-Type: application/json',
    '',
    '{',
    '  "difficulty": "normal",         // "easy" | "normal" | "hard"',
    '  "room_id":    "room-01",        // physical room identifier',
    '  "player_ids": [                 // optional — auto-generates demo players if omitted',
    '    "player-uuid-001",',
    '    "player-uuid-002",',
    '    "player-uuid-003",',
    '    "player-uuid-004"',
    '  ]',
    '}',
  ]),
  spacer(80),
  h4("Response"),
  ...codeBlock([
    '{',
    '  "status": "ok",',
    '  "data": {',
    '    "session_id": "<uuid>",       // use this for WS authenticate',
    '    "state":      "lobby",',
    '    "players":    [ ... ],',
    '    ...                           // full Session Object (§3.1)',
    '  }',
    '}',
  ]),

  new Paragraph({ children: [new PageBreak()], spacing: { before: 0, after: 0 } }),
];

// ─── Section 6 — Economy & Progression ───────────────────────────────────────

const section6 = [
  h1("6.  Economy & Progression"),

  body("All economy processing is server-authoritative. The UE5.5 client receives economy results in the session_complete payload and renders them — it performs no calculations itself."),
  spacer(80),

  h2("6.1  XP Formula"),
  body("XP awarded per player at session completion:"),
  spacer(60),
  ...codeBlock([
    "xp = (base_xp × difficulty_multiplier + time_bonus) × event_multiplier × repeat_decay",
    "",
    "Where:",
    "  base_xp            = sum of base XP for each completed node",
    "                       puzzle node: 150 XP",
    "                       combat node: 200 XP",
    "  difficulty_multiplier:",
    "                       easy:   0.75×",
    "                       normal: 1.00×",
    "                       hard:   1.50×",
    "  time_bonus         = 10 XP × minutes remaining at completion",
    "  event_multiplier   = live event boost (default 1.0, configurable)",
    "  repeat_decay       = 0.5× if same session replayed within 1 hour",
    "  daily_cap          = 2,000 XP max per player per calendar day",
  ]),
  spacer(80),

  h2("6.2  Level Curve"),
  spacer(60),
  new Table({
    width: { size: 5760, type: WidthType.DXA },
    columnWidths: [640, 1440, 1840, 1840],
    rows: [
      new TableRow({ children: [
        headerCell("Level",  640),
        headerCell("XP Required", 1440),
        headerCell("Title Unlocked", 1840),
        headerCell("Loot Unlocked",  1840),
      ]}),
      ...[
        ["1",  "0",     "initiate",                  "—"],
        ["2",  "100",   "rune_bearer",               "emblem_trial_01"],
        ["3",  "300",   "—",                         "avatar_tint_ember"],
        ["4",  "600",   "keeper_of_embers",           "weapon_skin_ember_01"],
        ["5",  "1,000", "—",                         "companion_skin_fox_ember"],
        ["6",  "1,500", "slayer_of_the_first_trial",  "lore_codex_01"],
        ["7",  "2,100", "—",                         "avatar_skin_veritas_01"],
        ["8",  "2,800", "guardian_of_veritas",        "emblem_guardian"],
        ["9",  "3,600", "—",                         "weapon_skin_void_01"],
        ["10", "4,500", "master_of_the_emberlight",   "companion_skin_fox_void"],
      ].map(([level, xp, title, loot], i) => new TableRow({ children: [
        cell(level, { w: 640,  align: AlignmentType.CENTER, bold: true, fill: i%2===0?C.white:C.paleBlue }),
        cell(xp,    { w: 1440, align: AlignmentType.CENTER, fill: i%2===0?C.white:C.paleBlue }),
        cell(title, { w: 1840, mono: true, size: 17, fill: i%2===0?C.white:C.paleBlue }),
        cell(loot,  { w: 1840, mono: true, size: 17, fill: i%2===0?C.white:C.paleBlue }),
      ]})),
    ],
  }),
  spacer(80),

  h2("6.3  Achievements"),
  spacer(60),
  new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [2400, 3200, 4480],
    rows: [
      new TableRow({ children: [
        headerCell("Achievement Key",  2400),
        headerCell("Unlock Condition", 3200),
        headerCell("Reward",           4480),
      ]}),
      ...[
        ["first_completion",   "Complete any session for the first time",         "Title: initiate · Loot: emblem_trial_01"],
        ["perfect_puzzle_run", "Complete session with zero hints used",           "Title: rune_bearer"],
        ["no_down_combat",     "Complete session with no player downed",          "Title: slayer_of_the_first_trial · Loot: emblem_guardian"],
        ["beat_on_hard",       "Complete session on hard difficulty",             "Title: keeper_of_embers · Loot: avatar_skin_veritas_01"],
        ["speed_run",          "Complete session in ≤45 minutes",                "Title: guardian_of_veritas"],
        ["full_codex",         "Own all lore_unlock items (lore_codex_01 + _02)","Title: master_of_the_emberlight · Loot: lore_codex_02"],
      ].map(([key, condition, reward], i) => new TableRow({ children: [
        cell(key,       { w: 2400, mono: true, size: 17, fill: i%2===0?C.white:C.paleBlue }),
        cell(condition, { w: 3200, fill: i%2===0?C.white:C.paleBlue }),
        cell(reward,    { w: 4480, fill: i%2===0?C.white:C.paleBlue }),
      ]})),
    ],
  }),
  spacer(80),

  h2("6.4  Loot Items"),
  spacer(60),
  new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [2800, 1600, 1400, 4280],
    rows: [
      new TableRow({ children: [
        headerCell("Item ID",      2800),
        headerCell("Category",     1600),
        headerCell("Rarity",       1400),
        headerCell("Display Name", 4280),
      ]}),
      ...[
        ["emblem_trial_01",         "emblem",        "common", "Mark of the First Trial"],
        ["lore_codex_01",           "lore_unlock",   "common", "Codex Entry: The Awakening"],
        ["avatar_tint_ember",       "avatar_skin",   "common", "Ember Tint"],
        ["weapon_skin_ember_01",    "weapon_skin",   "rare",   "Emberlight Blade"],
        ["companion_skin_fox_ember","companion_skin","rare",   "Fate Fox — Ember"],
        ["emblem_guardian",         "emblem",        "rare",   "Guardian's Seal"],
        ["lore_codex_02",           "lore_unlock",   "rare",   "Codex Entry: The Keeper"],
        ["avatar_skin_veritas_01",  "avatar_skin",   "rare",   "Veritas Shroud"],
        ["weapon_skin_void_01",     "weapon_skin",   "epic",   "Void Cleaver"],
        ["companion_skin_fox_void", "companion_skin","epic",   "Fate Fox — Void"],
      ].map(([id, cat, rarity, name], i) => {
        const rarityColors = { common: "000000", rare: "1565C0", epic: C.purple };
        return new TableRow({ children: [
          cell(id,     { w: 2800, mono: true, size: 17, fill: i%2===0?C.white:C.paleBlue }),
          cell(cat,    { w: 1600, fill: i%2===0?C.white:C.paleBlue }),
          cell(rarity, { w: 1400, fill: i%2===0?C.white:C.paleBlue, textColor: rarityColors[rarity], bold: true }),
          cell(name,   { w: 4280, fill: i%2===0?C.white:C.paleBlue }),
        ]});
      }),
    ],
  }),

  new Paragraph({ children: [new PageBreak()], spacing: { before: 0, after: 0 } }),
];

// ─── Section 7 — Live Config ──────────────────────────────────────────────────

const section7 = [
  h1("7.  Live Configuration"),

  body("All tuning values live in the config_store table. Operators can update any value via POST /api/config without a code deploy. This table documents every key the UE5.5 client may be affected by."),
  spacer(80),

  new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [2800, 1400, 5880],
    rows: [
      new TableRow({ children: [
        headerCell("Config Key",    2800),
        headerCell("Default",       1400),
        headerCell("Description",   5880),
      ]}),
      ...[
        ["session.duration_secs",         "3600",   "Session length in seconds. Changes take effect on next session creation."],
        ["session.max_players",           "6",      "Maximum players per session."],
        ["session.min_players",           "2",      "Minimum players required to start a session."],
        ["session.reset_sla_secs",        "60",     "Maximum seconds allowed for a hard reset operation."],
        ["hints.auto_trigger_secs",       "[180,360,540]", "Seconds a party can be stuck before automatic hint tiers 1, 2, 3 are triggered."],
        ["hints.player_request_enabled",  "true",   "Whether players can manually request hints."],
        ["xp.base_node_puzzle",           "150",    "Base XP awarded for completing a puzzle node."],
        ["xp.base_node_combat",           "200",    "Base XP awarded for completing a combat node."],
        ["xp.time_bonus_per_min",         "10",     "XP per minute remaining at session end."],
        ["xp.daily_cap",                  "2000",   "Maximum XP a player can earn per calendar day."],
        ["xp.difficulty_multiplier",      "{easy:0.75,...}", "XP multiplier by difficulty tier."],
        ["xp.repeat_decay_factor",        "0.5",    "XP multiplier applied when replaying within 1 hour."],
        ["economy.xp_event_multiplier",   "1.0",    "Live event XP multiplier. Set >1.0 for bonus XP events."],
        ["economy.reward_boost_active",   "false",  "When true, adds +1 loot roll per player at session end."],
        ["version.gameplay",              "1.0.0",  "Gameplay build version tag. Stamped on all sessions."],
        ["version.content",               "1.0.0",  "Content asset version tag."],
        ["version.economy",               "1.0.0",  "Economy system version tag."],
        ["version.config",                "1.0.0",  "Config snapshot version tag."],
      ].map(([key, def, desc], i) => new TableRow({ children: [
        cell(key, { w: 2800, mono: true, size: 17, fill: i%2===0?C.white:C.paleBlue }),
        cell(def, { w: 1400, mono: true, size: 17, align: AlignmentType.CENTER, fill: i%2===0?C.white:C.paleBlue }),
        cell(desc,{ w: 5880, fill: i%2===0?C.white:C.paleBlue }),
      ]})),
    ],
  }),

  new Paragraph({ children: [new PageBreak()], spacing: { before: 0, after: 0 } }),
];

// ─── Section 8 — Integration Checklist ───────────────────────────────────────

const section8 = [
  h1("8.  UE5.5 Integration Checklist"),

  body("Use this checklist to verify integration before handoff. Every item must pass before the client build is considered complete."),
  spacer(80),

  h2("8.1  Connection & Authentication"),
  numbered("Connect to ws://[host]:8001 and receive a connected message containing client_id."),
  numbered("Send authenticate with a valid session_id (created via POST /api/sessions) and receive authenticated followed by session_state."),
  numbered("Verify that sending any message before authenticate returns NOT_AUTHENTICATED error."),
  numbered("Verify that sending authenticate with a nonexistent session_id returns SESSION_NOT_FOUND error."),
  spacer(60),

  h2("8.2  Game Loop"),
  numbered("Receive session_state and correctly render all 7 nodes with their initial states (locked/available)."),
  numbered("On session start (operator clicks Start), receive session_state with state='running'."),
  numbered("Send puzzle_solved for node_intro_narrative_01 and receive puzzle_solved_ack with flags_set=['narrative_01_complete']."),
  numbered("Receive session_state broadcast showing node_puzzle_runes_01 now 'available'."),
  numbered("Progress through all 7 nodes using the appropriate completion messages."),
  numbered("On node_reward_finale_01 completion, receive session_state with state='completed'."),
  spacer(60),

  h2("8.3  Timer"),
  numbered("Receive timer_sync every 15 seconds while session is running."),
  numbered("Verify elapsed_secs and time_remaining_secs are consistent with total_duration_secs."),
  numbered("When session is paused, confirm timer_sync messages stop and resume on un-pause."),
  spacer(60),

  h2("8.4  Hints"),
  numbered("Send request_hint for the current node and receive hint_delivered with tier=1."),
  numbered("Send request_hint again and receive hint_delivered with tier=2."),
  numbered("Verify hint content is displayed in-world and hint_used count increments in session_state."),
  spacer(60),

  h2("8.5  Multi-Player"),
  numbered("Connect 4 simultaneous clients to the same session_id (4 different player_ids)."),
  numbered("Client 1 sends puzzle_solved. Verify all 4 clients receive the session_state broadcast."),
  numbered("Client 1 sends player_health with health=50. Verify all 4 clients receive player_update."),
  spacer(60),

  h2("8.6  Operator Actions"),
  numbered("Operator triggers hint from dashboard. Verify all in-session clients receive hint_delivered."),
  numbered("Operator pauses session. Verify all clients receive session_state with state='paused'."),
  numbered("Operator bypasses a node. Verify session advances and all clients receive updated session_state."),
  numbered("Operator hard resets. Verify all clients receive session_state with state='idle' and all node states reset to 'locked' or 'available'."),
  spacer(60),

  h2("8.7  Economy"),
  numbered("Complete a full session and verify generate_session_summary() is called."),
  numbered("Verify each player in the session receives correct XP based on nodes completed and time remaining."),
  numbered("Verify level-up rewards are present in the summary when XP thresholds are crossed."),
  spacer(80),

  h2("8.8  Error Handling"),
  bullet("Client must not crash on receiving an error message."),
  bullet("Client must reconnect automatically if the WebSocket connection drops."),
  bullet("Client must re-send authenticate after reconnecting."),
  bullet("Client must handle session_state messages at any point in the game loop (they may arrive unexpectedly after operator actions)."),

  new Paragraph({ children: [new PageBreak()], spacing: { before: 0, after: 0 } }),
];

// ─── Section 9 — Telemetry ────────────────────────────────────────────────────

const section9 = [
  h1("9.  Telemetry Reference"),

  body("All telemetry is handled server-side. The UE5.5 client does not need to emit telemetry directly — every meaningful server action emits a structured event automatically. This section documents the events for visibility."),
  spacer(80),

  new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [3200, 6880],
    rows: [
      new TableRow({ children: [
        headerCell("Event Type",  3200),
        headerCell("Triggered When", 6880),
      ]}),
      ...[
        ["session_created",           "New session created via REST API."],
        ["session_started",           "Session transitions lobby → running."],
        ["session_paused",            "Session paused by operator."],
        ["session_resumed",           "Session resumed."],
        ["session_completed",         "Session reaches completed state."],
        ["session_failed",            "Session reaches failed state."],
        ["session_hard_reset",        "Hard reset performed."],
        ["node_entered",              "A node transitions to in_progress state."],
        ["node_completed",            "A node transitions to completed state."],
        ["flag_set",                  "A session flag is set."],
        ["hint_used",                 "A hint is delivered to players."],
        ["node_bypassed",             "Operator bypasses a node."],
        ["xp_granted",                "XP calculated and granted to a player."],
        ["loot_granted",              "A loot item is granted to a player."],
        ["achievement_unlocked",      "An achievement is unlocked for a player."],
        ["level_up",                  "A player advances to a new level."],
        ["session_summary_generated", "Post-session summary computed for all players."],
        ["ws:client_authenticated",   "A WebSocket client successfully authenticates."],
        ["ws:client_disconnected",    "A WebSocket client disconnects."],
        ["ws:puzzle_solved",          "Client sends puzzle_solved over WebSocket."],
        ["ws:combat_complete",        "Client sends combat_complete over WebSocket."],
        ["ws:player_health_update",   "Client reports health/energy update."],
        ["ws:hint_requested",         "Player manually requests a hint."],
      ].map(([event, trigger], i) => new TableRow({ children: [
        cell(event,   { w: 3200, mono: true, size: 17, fill: i%2===0?C.white:C.paleBlue }),
        cell(trigger, { w: 6880, fill: i%2===0?C.white:C.paleBlue }),
      ]})),
    ],
  }),
  spacer(80),

  h2("9.1  Telemetry Event Schema"),
  body("All events share this structure in the telemetry_events table:"),
  spacer(60),
  ...codeBlock([
    "{",
    "  event_id:         UUID,",
    "  session_id:       UUID | null,",
    "  player_id:        string | null,",
    "  event_type:       string,",
    "  context_json:     JSON string with event-specific data,",
    "  gameplay_version: string,",
    "  config_version:   string,",
    "  ts:               ISO-8601 timestamp",
    "}",
  ]),
];

// ─── Section 10 — Quick Reference ─────────────────────────────────────────────

const section10 = [
  new Paragraph({ children: [new PageBreak()], spacing: { before: 0, after: 0 } }),
  h1("10.  Quick Reference Card"),

  body("Tear-out reference for the UE5.5 contractor."),
  spacer(60),

  // Two side-by-side tables via a wrapper table
  new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [4920, 120, 5040],
    rows: [
      new TableRow({ children: [

        // Left: WS messages client sends
        new TableCell({
          borders: noBorders,
          width: { size: 4920, type: WidthType.DXA },
          children: [
            new Paragraph({
              children: [new TextRun({ text: "Client → Server (UE5.5 sends)", font: FONT, size: 22, bold: true, color: C.steel })],
              spacing: { before: 0, after: 80 },
            }),
            new Table({
              width: { size: 4920, type: WidthType.DXA },
              columnWidths: [2200, 2720],
              rows: [
                new TableRow({ children: [
                  headerCell("Message Type", 2200),
                  headerCell("When to Send",  2720),
                ]}),
                ...[
                  ["authenticate",       "First — before anything else"],
                  ["puzzle_solved",      "Puzzle / narrative complete"],
                  ["combat_complete",    "Combat node fully cleared"],
                  ["puzzle_progress",    "Step completed within puzzle"],
                  ["combat_wave_clear",  "One wave cleared"],
                  ["node_action",        "Any player interaction"],
                  ["player_health",      "Health / energy changes"],
                  ["request_hint",       "Player asks for hint"],
                  ["heartbeat",          "Every 30 seconds"],
                ].map(([msg, when], i) => new TableRow({ children: [
                  cell(msg,  { w: 2200, mono: true, size: 17, fill: i%2===0?C.white:C.paleBlue }),
                  cell(when, { w: 2720, size: 19, fill: i%2===0?C.white:C.paleBlue }),
                ]})),
              ],
            }),
          ],
          margins: { top: 0, bottom: 0, left: 0, right: 0 },
        }),

        // Spacer column
        new TableCell({
          borders: noBorders,
          width: { size: 120, type: WidthType.DXA },
          children: [new Paragraph({ children: [new TextRun("")] })],
          margins: { top: 0, bottom: 0, left: 0, right: 0 },
        }),

        // Right: WS messages server sends
        new TableCell({
          borders: noBorders,
          width: { size: 5040, type: WidthType.DXA },
          children: [
            new Paragraph({
              children: [new TextRun({ text: "Server → Client (UE5.5 receives)", font: FONT, size: 22, bold: true, color: C.steel })],
              spacing: { before: 0, after: 80 },
            }),
            new Table({
              width: { size: 5040, type: WidthType.DXA },
              columnWidths: [2200, 2840],
              rows: [
                new TableRow({ children: [
                  headerCell("Message Type",  2200),
                  headerCell("What It Means", 2840),
                ]}),
                ...[
                  ["connected",      "Connection confirmed"],
                  ["authenticated",  "Auth accepted"],
                  ["session_state",  "Full state — reconcile now"],
                  ["hint_delivered", "Show hint in-world"],
                  ["timer_sync",     "Sync countdown timer"],
                  ["player_update",  "Update player health bar"],
                  ["pong",           "Heartbeat acknowledged"],
                  ["error",          "Log; never crash"],
                ].map(([msg, meaning], i) => new TableRow({ children: [
                  cell(msg,     { w: 2200, mono: true, size: 17, fill: i%2===0?C.white:C.paleBlue }),
                  cell(meaning, { w: 2840, size: 19, fill: i%2===0?C.white:C.paleBlue }),
                ]})),
              ],
            }),
          ],
          margins: { top: 0, bottom: 0, left: 0, right: 0 },
        }),

      ]}),
    ],
  }),

  spacer(120),
  h2("Session Startup Sequence (copy-paste)"),
  spacer(60),
  ...codeBlock([
    "// 1. Create session (REST)",
    "POST http://[host]:8000/api/sessions",
    '    body: { "difficulty": "normal", "room_id": "room-01" }',
    "    → save session_id from response",
    "",
    "// 2. Start session (REST)",
    "POST http://[host]:8000/api/sessions/{session_id}/action/start",
    "",
    "// 3. Connect each headset (WebSocket)",
    "ws://[host]:8001",
    "",
    "// 4. Authenticate each headset",
    '    { "type": "authenticate",',
    '      "payload": { "session_id": "...", "player_id": "...", "client_type": "ue5" } }',
    "",
    "// 5. Receive session_state → render initial scene",
    "",
    "// 6. Game loop: send events, receive session_state broadcasts",
    "",
    "// 7. puzzle_solved / combat_complete → triggers auto-advance",
  ]),
];

// ─── Assemble document ────────────────────────────────────────────────────────

const doc = new Document({
  numbering: {
    config: [
      {
        reference: "bullets",
        levels: [{
          level: 0, format: LevelFormat.BULLET, text: "•",
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } },
        }],
      },
      {
        reference: "numbers",
        levels: [{
          level: 0, format: LevelFormat.DECIMAL, text: "%1.",
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } },
        }],
      },
    ],
  },
  styles: {
    default: {
      document: { run: { font: FONT, size: 22 } },
    },
    paragraphStyles: [
      {
        id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run:       { size: 36, bold: true, font: FONT, color: C.steel },
        paragraph: { spacing: { before: 400, after: 160 }, outlineLevel: 0 },
      },
      {
        id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run:       { size: 26, bold: true, font: FONT, color: C.steel },
        paragraph: { spacing: { before: 280, after: 100 }, outlineLevel: 1 },
      },
      {
        id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run:       { size: 22, bold: true, font: FONT, color: C.navy },
        paragraph: { spacing: { before: 200, after: 80 }, outlineLevel: 2 },
      },
    ],
  },
  sections: [
    {
      properties: {
        page: {
          size: { width: PAGE_W, height: PAGE_H },
          margin: { top: MARGIN, right: MARGIN, bottom: MARGIN, left: MARGIN },
        },
      },
      headers: {
        default: new Header({
          children: [
            new Paragraph({
              children: [
                new TextRun({ text: "HEROES' VERITAS XR — Backend API Contract  v1.0.0", font: FONT, size: 18, color: C.grey }),
                new TextRun({ children: [new Tab()], font: FONT }),
                new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 18, color: C.grey }),
                new TextRun({ text: " / ", font: FONT, size: 18, color: C.grey }),
                new TextRun({ children: [PageNumber.TOTAL_PAGES], font: FONT, size: 18, color: C.grey }),
              ],
              tabStops: [{ type: TabStopType.RIGHT, position: CONTENT_W }],
              border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: C.borderGrey, space: 4 } },
              spacing: { before: 0, after: 80 },
            }),
          ],
        }),
      },
      children: [
        ...coverPage,
        ...section1,
        ...section2,
        ...section3,
        ...section4,
        ...section5,
        ...section6,
        ...section7,
        ...section8,
        ...section9,
        ...section10,
      ],
    },
  ],
});

Packer.toBuffer(doc).then(buffer => {
  const outPath = path.join(__dirname, "api_contract.docx");
  fs.writeFileSync(outPath, buffer);
  console.log(`\n  ✓ Generated: ${outPath}`);
  console.log(`  Size: ${(buffer.length / 1024).toFixed(1)} KB\n`);
}).catch(err => {
  console.error("Error generating document:", err);
  process.exit(1);
});
