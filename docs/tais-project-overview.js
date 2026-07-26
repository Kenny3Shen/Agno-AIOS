// T.A.I.S — Project Overview Deck
// Visual language adapted from local_ai_consulting_pitch_deck (dark, technical, minimal)

const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const path = require("path");
const {
  FaComments, FaProjectDiagram, FaUserCheck, FaDatabase, FaShieldAlt,
  FaCogs, FaSearch, FaBug, FaRobot, FaLayerGroup, FaBolt, FaLock,
} = require("react-icons/fa");

function renderIconSvg(IconComponent, color = "#ECE8E1", size = 256) {
  return ReactDOMServer.renderToStaticMarkup(
    React.createElement(IconComponent, { color, size: String(size) })
  );
}
async function iconToBase64Png(IconComponent, color, size = 256) {
  const svg = renderIconSvg(IconComponent, color, size);
  const pngBuffer = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + pngBuffer.toString("base64");
}

const C = {
  bg: "0A0A0A", panel: "141412", card: "1A1A18",
  ink: "ECE8E1", muted: "A8A49B", dim: "6B6760",
  faint: "2A2A28", fainter: "1D1D1B",
  accent: "C5DD97", accent2: "7EB8DA", warn: "E8B86D",
};
const FONT = "Arial";
const SW = 13.333, SH = 7.5, ML = 0.55, MR = 0.55, CW = SW - ML - MR;

const pres = new pptxgen();
pres.defineLayout({ name: "TAIS_16x9", width: SW, height: SH });
pres.layout = "TAIS_16x9";
pres.author = "T.A.I.S";
pres.title = "T.A.I.S — Trinity AI Security 项目介绍";
pres.company = "T.A.I.S";

function cs(spc) { return spc / 100; }

function addHeader(slide, sectionLabel) {
  slide.addText("T.A.I.S", {
    x: ML, y: 0.28, w: 2.2, h: 0.32,
    fontFace: FONT, fontSize: 12, color: C.ink, bold: true,
    charSpacing: cs(200), margin: 0,
  });
  slide.addText(sectionLabel, {
    x: SW - MR - 5.5, y: 0.28, w: 5.5, h: 0.32,
    fontFace: FONT, fontSize: 11, color: C.muted, align: "right",
    charSpacing: cs(120), margin: 0,
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: ML, y: 0.68, w: CW, h: 0.01,
    fill: { color: C.faint }, line: { type: "none" },
  });
}

function addFooter(slide, page, total) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x: ML, y: SH - 0.48, w: CW, h: 0.01,
    fill: { color: C.faint }, line: { type: "none" },
  });
  slide.addText("Trinity AI Security", {
    x: ML, y: SH - 0.4, w: 4, h: 0.28,
    fontFace: FONT, fontSize: 10, color: C.dim, margin: 0,
  });
  slide.addText(`${String(page).padStart(2, "0")} / ${String(total).padStart(2, "0")}`, {
    x: SW - MR - 1.4, y: SH - 0.4, w: 1.4, h: 0.28,
    fontFace: FONT, fontSize: 10, color: C.dim, align: "right", margin: 0,
  });
}

function card(slide, x, y, w, h) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x, y, w, h,
    fill: { color: C.card }, line: { color: C.faint, width: 1 }, rectRadius: 0.08,
  });
}

async function main() {
  const total = 10;
  const icons = {
    chat: await iconToBase64Png(FaComments, "#C5DD97"),
    flow: await iconToBase64Png(FaProjectDiagram, "#7EB8DA"),
    hitl: await iconToBase64Png(FaUserCheck, "#E8B86D"),
    kb: await iconToBase64Png(FaDatabase, "#C5DD97"),
    shield: await iconToBase64Png(FaShieldAlt, "#7EB8DA"),
    cogs: await iconToBase64Png(FaCogs, "#A8A49B"),
    search: await iconToBase64Png(FaSearch, "#C5DD97"),
    bug: await iconToBase64Png(FaBug, "#E8B86D"),
    robot: await iconToBase64Png(FaRobot, "#C5DD97"),
    layers: await iconToBase64Png(FaLayerGroup, "#7EB8DA"),
    bolt: await iconToBase64Png(FaBolt, "#E8B86D"),
    lock: await iconToBase64Png(FaLock, "#C5DD97"),
  };
  const archPath = path.join(__dirname, "assets", "tais-architecture.png");

  // 1 Cover
  {
    const s = pres.addSlide();
    s.background = { color: C.bg };
    s.addText("T.A.I.S", {
      x: ML, y: 0.4, w: 4, h: 0.35,
      fontFace: FONT, fontSize: 14, color: C.accent, bold: true,
      charSpacing: cs(280), margin: 0,
    });
    s.addText("PROJECT OVERVIEW", {
      x: SW - MR - 4, y: 0.4, w: 4, h: 0.35,
      fontFace: FONT, fontSize: 12, color: C.muted, align: "right",
      charSpacing: cs(160), margin: 0,
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x: ML, y: 0.9, w: CW, h: 0.01,
      fill: { color: C.faint }, line: { type: "none" },
    });
    s.addText("Trinity AI Security", {
      x: ML, y: 2.1, w: CW, h: 0.9,
      fontFace: FONT, fontSize: 42, color: C.ink, bold: true, margin: 0,
    });
    s.addText("面向安全运营的 AI 工作台", {
      x: ML, y: 3.05, w: CW, h: 0.5,
      fontFace: FONT, fontSize: 22, color: C.accent, margin: 0,
    });
    s.addText("将 Agent 对话、工作流编排、HITL 审批、知识库检索、威胁情报与可观测性\n收敛到统一认证的控制面 — 基于 Agno 运行时构建。", {
      x: ML, y: 3.75, w: 11, h: 0.9,
      fontFace: FONT, fontSize: 15, color: C.muted, margin: 0,
    });
    s.addText("React · FastAPI · Agno · FastMCP · PostgreSQL + pgvector", {
      x: ML, y: SH - 0.9, w: CW, h: 0.3,
      fontFace: FONT, fontSize: 12, color: C.dim, margin: 0,
    });
  }

  // 2 Agenda
  {
    const s = pres.addSlide();
    s.background = { color: C.bg };
    addHeader(s, "AGENDA");
    addFooter(s, 2, total);
    s.addText("目录", {
      x: ML, y: 0.95, w: CW, h: 0.5,
      fontFace: FONT, fontSize: 28, color: C.ink, bold: true, margin: 0,
    });
    const items = [
      ["01", "问题与定位", "为什么需要安全运营 AI 工作台"],
      ["02", "系统架构", "浏览器工作台 · API · Agno 运行时"],
      ["03", "内置能力", "Agents · Team · Skills · MCP"],
      ["04", "工作流与 HITL", "Studio · 审批 · 触发器"],
      ["05", "知识与情报", "Knowledge · CVE · Collect"],
      ["06", "治理与运维", "RBAC · 护栏 · Jobs · 可观测"],
      ["07", "技术栈与路线", "工具链与交付方式"],
    ];
    items.forEach((row, i) => {
      const y = 1.65 + i * 0.68;
      s.addText(row[0], {
        x: ML, y, w: 0.7, h: 0.45,
        fontFace: FONT, fontSize: 18, color: C.accent, bold: true, margin: 0,
      });
      s.addText(row[1], {
        x: ML + 0.9, y, w: 3.2, h: 0.45,
        fontFace: FONT, fontSize: 18, color: C.ink, margin: 0,
      });
      s.addText(row[2], {
        x: ML + 4.3, y, w: 7.5, h: 0.45,
        fontFace: FONT, fontSize: 15, color: C.muted, margin: 0,
      });
      if (i < items.length - 1) {
        s.addShape(pres.shapes.RECTANGLE, {
          x: ML + 0.9, y: y + 0.52, w: CW - 0.9, h: 0.008,
          fill: { color: C.fainter }, line: { type: "none" },
        });
      }
    });
  }

  // 3 Positioning
  {
    const s = pres.addSlide();
    s.background = { color: C.bg };
    addHeader(s, "01  ·  POSITIONING");
    addFooter(s, 3, total);
    s.addText("安全运营需要可治理的 AI 工作台", {
      x: ML, y: 0.95, w: CW, h: 0.5,
      fontFace: FONT, fontSize: 26, color: C.ink, bold: true, margin: 0,
    });
    const pains = [
      { t: "工具碎片化", d: "对话、工作流、情报、审批散落在多套系统，上下文断裂。" },
      { t: "能力难治理", d: "模型与工具调用缺少统一的权限、审计与护栏策略。" },
      { t: "人机协同不足", d: "高风险操作需要 HITL，但缺少可恢复、可追踪的审批闭环。" },
      { t: "可观测薄弱", d: "Run / Trace / 失败原因难以回放，运营与研发协作成本高。" },
    ];
    pains.forEach((p, i) => {
      const col = i % 2, row = Math.floor(i / 2);
      const x = ML + col * 6.2, y = 1.7 + row * 2.15;
      card(s, x, y, 5.9, 1.95);
      s.addShape(pres.shapes.RECTANGLE, {
        x, y, w: 0.08, h: 1.95,
        fill: { color: C.accent }, line: { type: "none" },
      });
      s.addText(p.t, {
        x: x + 0.35, y: y + 0.35, w: 5.2, h: 0.4,
        fontFace: FONT, fontSize: 18, color: C.ink, bold: true, margin: 0,
      });
      s.addText(p.d, {
        x: x + 0.35, y: y + 0.9, w: 5.2, h: 0.7,
        fontFace: FONT, fontSize: 14, color: C.muted, margin: 0,
      });
    });
  }

  // 4 Architecture
  {
    const s = pres.addSlide();
    s.background = { color: C.bg };
    addHeader(s, "02  ·  ARCHITECTURE");
    addFooter(s, 4, total);
    s.addText("三层结构：工作台 · API · Agno 运行时", {
      x: ML, y: 0.9, w: CW, h: 0.4,
      fontFace: FONT, fontSize: 24, color: C.ink, bold: true, margin: 0,
    });
    const imgW = 8.0, imgH = 4.5;
    s.addImage({ path: archPath, x: ML, y: 1.5, w: imgW, h: imgH });
    const notes = [
      { t: "浏览器", d: "React 19 · Ant Design X · JWT" },
      { t: "控制面", d: "FastAPI · RBAC · Alembic" },
      { t: "运行时", d: "Agno Agent / Team / Workflow" },
      { t: "数据", d: "Postgres · pgvector · Jobs" },
    ];
    notes.forEach((n, i) => {
      const y = 1.55 + i * 1.1;
      card(s, 8.9, y, 3.85, 0.95);
      s.addText(n.t, {
        x: 9.1, y: y + 0.15, w: 3.5, h: 0.3,
        fontFace: FONT, fontSize: 14, color: C.accent, bold: true, margin: 0,
      });
      s.addText(n.d, {
        x: 9.1, y: y + 0.48, w: 3.5, h: 0.35,
        fontFace: FONT, fontSize: 12, color: C.muted, margin: 0,
      });
    });
  }

  // 5 Agents
  {
    const s = pres.addSlide();
    s.background = { color: C.bg };
    addHeader(s, "03  ·  CAPABILITIES");
    addFooter(s, 5, total);
    s.addText("内置 Agents 与协作模式", {
      x: ML, y: 0.9, w: CW, h: 0.4,
      fontFace: FONT, fontSize: 24, color: C.ink, bold: true, margin: 0,
    });
    const agents = [
      { id: "security-operations", name: "安全运营助手", cap: "MCP · Skills · HITL · Knowledge", use: "告警研判、隔离确认、工作流编排" },
      { id: "data-analysis", name: "数据分析助手", cap: "File/CSV · SQL · Calculator", use: "指标解读、异常定位、可复现计算" },
      { id: "deep-research", name: "深度研究助手", cap: "Website · Web Search · Reasoning", use: "多源检索、交叉验证、研究报告" },
      { id: "Team beta", name: "研究分析团队", cap: "coordinate / route / tasks", use: "多 Agent 协作与任务板" },
    ];
    agents.forEach((a, i) => {
      const x = ML + i * 3.1;
      card(s, x, 1.55, 2.95, 4.55);
      s.addShape(pres.shapes.RECTANGLE, {
        x, y: 1.55, w: 2.95, h: 0.08,
        fill: { color: i === 3 ? C.accent2 : C.accent }, line: { type: "none" },
      });
      s.addText(a.id, {
        x: x + 0.2, y: 1.85, w: 2.55, h: 0.55,
        fontFace: FONT, fontSize: 11, color: C.dim, margin: 0,
      });
      s.addText(a.name, {
        x: x + 0.2, y: 2.45, w: 2.55, h: 0.7,
        fontFace: FONT, fontSize: 18, color: C.ink, bold: true, margin: 0,
      });
      s.addText("能力", {
        x: x + 0.2, y: 3.35, w: 2.55, h: 0.28,
        fontFace: FONT, fontSize: 11, color: C.accent, margin: 0,
      });
      s.addText(a.cap, {
        x: x + 0.2, y: 3.7, w: 2.55, h: 0.85,
        fontFace: FONT, fontSize: 13, color: C.muted, margin: 0,
      });
      s.addText("场景", {
        x: x + 0.2, y: 4.7, w: 2.55, h: 0.28,
        fontFace: FONT, fontSize: 11, color: C.accent, margin: 0,
      });
      s.addText(a.use, {
        x: x + 0.2, y: 5.05, w: 2.55, h: 0.75,
        fontFace: FONT, fontSize: 13, color: C.muted, margin: 0,
      });
    });
  }

  // 6 Workflow + HITL
  {
    const s = pres.addSlide();
    s.background = { color: C.bg };
    addHeader(s, "04  ·  WORKFLOW & HITL");
    addFooter(s, 6, total);
    s.addText("工作流 Studio 与人机审批闭环", {
      x: ML, y: 0.9, w: CW, h: 0.4,
      fontFace: FONT, fontSize: 24, color: C.ink, bold: true, margin: 0,
    });
    card(s, ML, 1.55, 6.0, 4.75);
    s.addImage({ data: icons.flow, x: ML + 0.35, y: 1.8, w: 0.4, h: 0.4 });
    s.addText("Workflow Studio", {
      x: ML + 0.9, y: 1.85, w: 4.5, h: 0.35,
      fontFace: FONT, fontSize: 18, color: C.ink, bold: true, margin: 0,
    });
    const wf = [
      "可视化编排：Step / 条件 / 并行 / 循环 / 路由",
      "DSL 校验、版本发布、草稿与已发布隔离",
      "SSE 流式运行；Esc / 停止 → cancel_run",
      "Cron / Webhook 触发；审计与通知",
      "步骤可绑定内置 Agent 与 Skills",
    ];
    s.addText(wf.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < wf.length - 1 } })), {
      x: ML + 0.4, y: 2.55, w: 5.3, h: 3.3,
      fontFace: FONT, fontSize: 14, color: C.muted, paraSpacing: 10, margin: 0,
    });
    card(s, ML + 6.25, 1.55, 6.0, 4.75);
    s.addImage({ data: icons.hitl, x: ML + 6.6, y: 1.8, w: 0.4, h: 0.4 });
    s.addText("HITL 审批中心", {
      x: ML + 7.15, y: 1.85, w: 4.5, h: 0.35,
      fontFace: FONT, fontSize: 18, color: C.ink, bold: true, margin: 0,
    });
    const hitl = [
      "工具调用可强制审批（Agno RunRequirement）",
      "暂停 → 管理员解析 → acontinue_run 恢复",
      "拒绝理由写入 resolution_data.note",
      "Skill / MCP 上传入库审批",
      "飞书 Webhook 通知 + 深链回会话 / Trace",
    ];
    s.addText(hitl.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < hitl.length - 1 } })), {
      x: ML + 6.65, y: 2.55, w: 5.3, h: 3.3,
      fontFace: FONT, fontSize: 14, color: C.muted, paraSpacing: 10, margin: 0,
    });
  }

  // 7 Knowledge
  {
    const s = pres.addSlide();
    s.background = { color: C.bg };
    addHeader(s, "05  ·  KNOWLEDGE & INTEL");
    addFooter(s, 7, total);
    s.addText("知识库与安全情报", {
      x: ML, y: 0.9, w: CW, h: 0.4,
      fontFace: FONT, fontSize: 24, color: C.ink, bold: true, margin: 0,
    });
    const tiles = [
      { icon: icons.kb, t: "Knowledge", d: "Docling 入库 · hybrid 检索 · Rerank · 相似度阈值 · Settings 可调" },
      { icon: icons.bug, t: "CVE 情报", d: "多源同步 · 标签检索 · 流式更新 · 与 Chat Skill 联动" },
      { icon: icons.search, t: "安全情报采集", d: "源站规则采集 · 文章入库 · 失败重采 · 与 CVE 交叉引用" },
      { icon: icons.shield, t: "IP 黑名单", d: "FireHOL 等威胁源 · 检索 API · Skill 意图挂载" },
    ];
    tiles.forEach((tile, i) => {
      const col = i % 2, row = Math.floor(i / 2);
      const x = ML + col * 6.2, y = 1.55 + row * 2.35;
      card(s, x, y, 5.95, 2.15);
      s.addImage({ data: tile.icon, x: x + 0.35, y: y + 0.4, w: 0.42, h: 0.42 });
      s.addText(tile.t, {
        x: x + 0.95, y: y + 0.45, w: 4.5, h: 0.35,
        fontFace: FONT, fontSize: 18, color: C.ink, bold: true, margin: 0,
      });
      s.addText(tile.d, {
        x: x + 0.35, y: y + 1.1, w: 5.3, h: 0.7,
        fontFace: FONT, fontSize: 14, color: C.muted, margin: 0,
      });
    });
  }

  // 8 Governance
  {
    const s = pres.addSlide();
    s.background = { color: C.bg };
    addHeader(s, "06  ·  GOVERNANCE");
    addFooter(s, 8, total);
    s.addText("权限、护栏、Jobs 与可观测", {
      x: ML, y: 0.9, w: CW, h: 0.4,
      fontFace: FONT, fontSize: 24, color: C.ink, bold: true, margin: 0,
    });
    const gov = [
      { icon: icons.lock, t: "RBAC", d: "admin / user；JWT scopes 驱动导航与写操作。" },
      { icon: icons.shield, t: "模型护栏", d: "Agno PII + Prompt Injection pre_hooks；Settings 可热更新；不含 OpenAI Moderation。" },
      { icon: icons.bolt, t: "Durable Jobs", d: "Knowledge 入库、HITL resume、Workflow cron dispatch；SKIP LOCKED 租约与幂等键。" },
      { icon: icons.layers, t: "Trace & Audit", d: "Agno 风格 traces / sessions；审计日志；Dashboard 失败与延迟口径。" },
      { icon: icons.cogs, t: "Chat 运行参数", d: "num_history_runs、session summaries、tool history cap、agentic memory 等可配置。" },
      { icon: icons.robot, t: "Cron 调度", d: "对齐 SchedulePoller：poll interval、catch-up、表达式校验、scheduled_at 推进。" },
    ];
    gov.forEach((g, i) => {
      const col = i % 3, row = Math.floor(i / 3);
      const x = ML + col * 4.15, y = 1.55 + row * 2.45;
      card(s, x, y, 3.95, 2.25);
      s.addImage({ data: g.icon, x: x + 0.3, y: y + 0.3, w: 0.36, h: 0.36 });
      s.addText(g.t, {
        x: x + 0.8, y: y + 0.35, w: 2.9, h: 0.32,
        fontFace: FONT, fontSize: 16, color: C.ink, bold: true, margin: 0,
      });
      s.addText(g.d, {
        x: x + 0.3, y: y + 0.95, w: 3.35, h: 1.0,
        fontFace: FONT, fontSize: 13, color: C.muted, margin: 0,
      });
    });
  }

  // 9 Stack
  {
    const s = pres.addSlide();
    s.background = { color: C.bg };
    addHeader(s, "07  ·  STACK");
    addFooter(s, 9, total);
    s.addText("技术栈与交付", {
      x: ML, y: 0.9, w: CW, h: 0.4,
      fontFace: FONT, fontSize: 24, color: C.ink, bold: true, margin: 0,
    });
    const cols = [
      { t: "前端", items: ["React 19 · TypeScript", "Vite · TanStack Router/Query", "Ant Design · Ant Design X", "UnoCSS · Bun · Playwright"] },
      { t: "后端", items: ["FastAPI · FastAPI Users", "Agno Agent/Team/Workflow", "FastMCP", "SQLAlchemy Async · Alembic"] },
      { t: "数据与工具", items: ["PostgreSQL + pgvector", "Durable Jobs Worker", "uv · ruff · ty", "Docling · 本地 GPU cu124"] },
    ];
    cols.forEach((col, i) => {
      const x = ML + i * 4.15;
      card(s, x, 1.55, 3.95, 4.55);
      s.addShape(pres.shapes.RECTANGLE, {
        x, y: 1.55, w: 3.95, h: 0.7,
        fill: { color: C.panel }, line: { type: "none" },
      });
      s.addText(col.t, {
        x: x + 0.3, y: 1.7, w: 3.35, h: 0.4,
        fontFace: FONT, fontSize: 18, color: C.accent, bold: true, margin: 0,
      });
      s.addText(col.items.map((t, j) => ({ text: t, options: { bullet: true, breakLine: j < col.items.length - 1 } })), {
        x: x + 0.3, y: 2.55, w: 3.35, h: 3.1,
        fontFace: FONT, fontSize: 15, color: C.muted, paraSpacing: 12, margin: 0,
      });
    });
  }

  // 10 Closing
  {
    const s = pres.addSlide();
    s.background = { color: C.bg };
    s.addText("T.A.I.S", {
      x: ML, y: 0.4, w: 3, h: 0.35,
      fontFace: FONT, fontSize: 14, color: C.accent, bold: true,
      charSpacing: cs(280), margin: 0,
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x: ML, y: 0.9, w: CW, h: 0.01,
      fill: { color: C.faint }, line: { type: "none" },
    });
    s.addText("统一、可治理、可观测的\n安全运营 AI 工作台", {
      x: ML, y: 2.0, w: CW, h: 1.4,
      fontFace: FONT, fontSize: 32, color: C.ink, bold: true, margin: 0,
    });
    s.addText("Agent 对话 · Workflow · HITL · Knowledge · 情报 · Trace — 一套认证与审计边界内闭环交付。", {
      x: ML, y: 3.7, w: 11, h: 0.6,
      fontFace: FONT, fontSize: 16, color: C.muted, margin: 0,
    });
    s.addText("文档：docs/  ·  计划：TODOs.md  ·  入口：README.md", {
      x: ML, y: 5.0, w: CW, h: 0.35,
      fontFace: FONT, fontSize: 14, color: C.dim, margin: 0,
    });
    s.addText("Trinity AI Security", {
      x: ML, y: SH - 0.7, w: CW, h: 0.3,
      fontFace: FONT, fontSize: 12, color: C.dim, margin: 0,
    });
  }

  const out = path.join(__dirname, "T.A.I.S-项目介绍.pptx");
  await pres.writeFile({ fileName: out });
  console.log("Wrote", out);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
