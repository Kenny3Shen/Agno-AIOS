一文读懂：openClaw 分析与教程（Moltbot、Clawdbot）
AI产品经理大群
AI产品经理大群​
计算机技术与软件专业技术资格证持证人
​关注
收录于 · 产品与科技前沿
190 人赞同了该文章
​
目录
收起
openClaw 是何方神圣？
系统架构深度解析
整体架构概览
Gateway 组件：中央控制平面
Agent：推理引擎
agent的四个核心阶段
多 LLM 提供商支持
Skills 系统：能力扩展机制
Channels 系统：多平台消息集成
Nodes 系统：移动/桌面扩展
Memory 系统：持久化记忆
工作流与实现细节
消息处理完整流程
Heartbeat 心跳机制
Cron 定时任务（插件）
Docker 沙箱隔离
openClaw部署与配置指南
系统要求
一键快速安装
引导向导
配置启动
关键环境变量
Docker Compose 部署
核心功能详解
长期记忆系统
技能系统（Skills）与 ClawdHub
主动提醒能力（Cron 任务）
语音支持（ElevenLabs）
总结与展望
附录：
openClaw（原名Clawdbot、Moltbot，改了好几次）在短短 2周内突破 150,000+ stars，成为 GitHub 历史上增长最快的开源项目之一（langchain、dify也就130k左右stars）。

这款由 PSPDFKit 创始人 Peter Steinberger （亿万富翁）通过AI编程打造的本地、自托管 AI 个人智能助手，通过将消息平台与 LLM 、智能体深度整合，实现了从会议摘要生成到电商购买谈判的全场景自动化。

我们今天就来拆解这个项目。

如果你只想看安装部署教程，就直接点本文的目录：openClaw部署与配置指南
开源地址：<https://github.com/openclaw/openclaw>

使用文档：<https://docs.openclaw.ai/concepts/models>

openClaw 是何方神圣？
openClaw 的走红，并不是一次偶然的“刷屏”，而是多股技术与情绪叠加后的结果。

在 2024–2025 年，开发者社区其实已经对「只会聊天的 AI」产生了明显疲劳。ChatGPT、Claude、deepseek 很聪明，但它们停留在web端页面里：不能真正替你完成电脑的实际任务，只能告诉你“应该怎么做”。与此同时，AutoGPT、BabyAGI 这类“自治智能体”项目又显得过于学术化、工程负担重、成功率不稳定。Manus和openmanus有有点不够用。

openClaw刚好卡位在中间那条断层上：

真简单：一条命令即可本地启动，不需要先搭一整套复杂的向量数据库和调度系统。
真能用：不是演示，而是能真的发消息、跑脚本、读写文件。
真惊喜：它第一次让大量普通用户意识到——“哇，原来 LLM 真的可以替我操作电脑”。

真正点燃社区热情的，是大量“第一天就能复现”的体验分享，吸引力一众技术和非技术用户：

“我让AI监控一个新闻网页，一有新 信息 就自动总结。”
“我只是连上 whatsapp，它就变成了我的私人助理。”

这种即时反馈 + 可控性，是 openClaw 爆火的第一推动力。

对比其他的智能体：

系统架构深度解析
整体架构概览
ClawdBot 用一套相对完整的智能体架构设计，并验证了可行性：

Gateway 统一多渠道接入
Tools + Skills 定义能力边界
Memory 实现持久化记忆
多层防护保证设备安全

从架构上来看，你可以把 openClaw 想象成一间智能平台，有五个重要功能区：

Gateway（大门）：管理会话、路由请求、做鉴权。它通常在本地运行，默认将控制面板绑定到 loopback（只允许本机访问），并支持通过 Tailscale 等私有网络扩展远程访问。
Agent（大脑）：有专门的人设，负责理解上下文意图、制定分步计划、决定要调用哪些工具或技能。
Skills（工具箱）：一组插件/技能（以 Markdown 与脚本描述），让 Agent 可以“开门、倒咖啡、发邮件、跑脚本”。
Channels（通道）：连接 各种app，如WhatsApp、Telegram、Discord、Slack、SMS 等，让 AI 与用户的日常通信无缝对接。
Nodes（传感器/终端）：运行在用户端设备（手机、笔记本、Raspberry Pi，台式机）的小智能体，可以提供摄像头、地理位置或系统通知等本地能力。

组件名称 功能定位 技术细节
Gateway (网关) 中央控制平面 运行在本地或 VPS 上的 Node.js 守护进程，负责会话管理、权限验证与路由 1。
Pi Agent (智能体) 推理大脑 负责处理自然语言、制定任务计划并选择合适的工具。支持 Claude、GPT-4 及 Ollama 本地模型 1。
Skills (技能) 执行能力集 模块化的插件系统，通过 SKILL.md 定义功能，支持文件操作、浏览器控制、API 调用等 1。
Channels (通道) 通信接口 连接用户现有的即时通讯软件（WhatsApp, Telegram, Discord, Slack 等） 1。
Nodes (节点) 设备端扩展 运行在 iOS/Android 或 macOS 上的轻量级智能体，允许 AI 访问相机、地理位置或发送系统通知 1。
这样的分层设计让 openClaw既能快速扩展社区技能skill和mcp等，也能够在不同设备间弹性部署和执行任务。

Gateway 组件：中央控制平面
Gateway 是系统的核心枢纽——一个长期运行的守护进程，负责管理所有消息通道并作为 WebSocket 控制平面。ClawdBot 支持多 Agent 架构。一个 Gateway 可以托管多个独立的 Agent。

Gateway 主要做三件事：

接收消息：从各个渠道收集用户指令
路由分发：决定这条消息应该交给哪个 Agent 处理
回复投递：把 Agent 的回复发送回对应的渠道

默认配置：

WebSocket 端点：ws://127.0.0.1:18789
Canvas 服务器：HTTP 端口 18793，路径 /__openClaw__/canvas/
每台主机建议运行单个 Gateway（独占 WhatsApp Web 会话）

WebSocket 协议详解
传输协议方式如下：

传输层：WebSocket 文本，JSON 格式
首帧必须为 connect
请求格式：{type:"req", id, method, params} → 响应：{type:"res", id, ok, payload|error}
事件格式：{type:"event", event, payload, seq?, stateVersion?}
支持事件类型：agent、chat、presence、health、heartbeat、cron、tick、shutdown

Agent：推理引擎
Agent在接收到消息与任务后，动用自己的脑袋（LLM/大模型）、手脚（Tools）、专业知识（Skills），尽可能的完成任务，其中可能会访问Web、运行命令、读写文件、编写代码，调用其他Nodes能力（比如摄像头）。

ClawdBot 的核心运行的核心是Agent Loop

Agent Loop 的核心是一个 “思考-行动”循环：

提问 → 思考 → 规划 → 行动 → 观察 → 思考 → 行动 → 等待 → 检查  → 纠错  ... → 完成
LLM 负责”思考”（决定做什么），Tools 负责”行动”（执行操作），执行结果作为”观察”反馈给 LLM，然后继续下一轮循环。

这就是 Agent 和 Chatbot 的本质区别：Chatbot 只会说，Agent 会做。

agent的四个核心阶段
阶段 1：上下文组装（Context Assembly）

Agent 需要告诉 LLM “你是谁、你能做什么、你有什么工具，用户说了什么”。这包括：

系统提示：Agent 的身份、规则、工具列表
会话历史：之前的对话记录
Bootstrap 文件：AGENTS.md、SOUL.md、TOOLS.md 等工作区文件
ClawdBot 会把这些内容拼接成一个完整的 Prompt，发送给 LLM。

阶段 2：模型推理（Model Inference）

LLM 收到 Prompt 后，决定下一步行动。它可能：

直接回复用户
调用一个工具（Tool Call）
请求更多信息
阶段 3：工具执行（Tool Execution）

如果 LLM 决定调用工具，Agent 会：

解析 Tool Call 参数
执行对应的工具（exec、read、write、browser…）
把执行结果返回给 LLM
阶段 4：回复分发（Reply Dispatch）

当 LLM 生成最终回复后，Agent 会：

格式化回复内容
通过 Gateway 发送回对应的消息渠道
支持流式输出（边生成边发送）
Clawdbot支持多Agent模式，可以互不干扰，或者相互协作。每个Agent有自己的工作区，放置专属配置与记忆。

其内核Pi Agent 是一个精简高效的编程智能体，核心特点包括：

Agent Loop（智能体循环）：处理用户消息、执行工具调用、将结果反馈给 LLM，循环直到模型生成无工具调用的响应
事件驱动架构：循环过程发射生命周期事件，支持响应式 UI
消息队列：支持两种模式（逐条处理或批量处理）
工具流式传输：支持块流式传输和增量流式传输，实现实时输出
核心工具仅用如下 4 个，即可实现有效智能体：

bash - 执行 shell 命令
read - 读取文件内容
write - 写入文件内容
edit - 编辑文本文件
系统提示词也极为精简，仅约 1000 tokens（包含工具定义），大模型可以理解编程智能体上下文。

多 LLM 提供商支持
openClaw 内置 pi-ai 目录，支持多种提供商：

// Anthropic Claude
{
  "agent": { "model": "anthropic/claude-opus-4-5" }
}

// GLM zai
{
  "agent": { "model": "zai/GLM-4.7" }
}

// Ollama 本地模型
{
  "models": {
    "providers": {
      "ollama": { "baseUrl": "<http://127.0.0.1:11434/v1>" }
    }
  }
}

// LM Studio 本地
{
  "models": {
    "providers": {
      "lmstudio": {
        "baseUrl": "<http://localhost:1234/v1>",
        "apiKey": "LMSTUDIO_KEY",
        "api": "openai-completions",
        "models": [{
          "id": "minimax-m2.1-gs32",
          "name": "MiniMax M2.1",
          "contextWindow": 200000
        }]
      }
    }
  }
}
模型选择使用 provider/model 格式（如 zai/GLM系列），并支持模型故障转移。

Skills 系统：能力扩展机制
Skills 是 智能体执行任务或者使用工具的指引，openClaw 的核心扩展机制，遵循 AgentSkills 规范——这是 Anthropic 开发的开放标准，已被 Claude Code、Cursor、VS Code、OpenAI Codex、Gemini CLI、GitHub Copilot 等广泛采用。

SKILL.md 格式规范：

---

name: nano-banana-pro
description: 通过 Gemini 3 Pro 生成或编辑图像
homepage: <https://example.com>
user-invocable: true
disable-model-invocation: false
command-dispatch: tool
command-tool: image-gen
command-arg-mode: raw
metadata: {"openClawt":{"requires":{"bins":["uv"],"env":["GEMINI_API_KEY"],"config":["browser.enabled"]},"primaryEnv":"GEMINI_API_KEY"}}
---

Skills元数据字段详解（metadata.openClaw 下）：

字段 说明
always: true 始终加载（跳过条件检查）
emoji 可选表情符号（macOS Skills UI 显示）
homepage 网站链接
os 支持平台：["darwin", "linux", "win32"]
requires.bins 必需的 PATH 二进制文件列表
requires.env 必需的环境变量
requires.config 必需的配置路径
primaryEnv 主要环境变量（对应 skills.entries.&lt;name&gt;.apiKey）
install 安装器规范（brew/node/go/uv/download）
Skill 加载优先级（从高到低）：

工作区 skills：&lt;workspace&gt;/skills
托管/本地 skills：~/.clawdbot/skills
内置 skills：随安装包分发
内置 Skills（49+ 个）涵盖：

Apple 生态：Notes、Reminders、Things 3、Bear Notes
Google Workspace：Gmail、Calendar、Drive、Docs、Sheets（通过 gog CLI）
通信工具：Slack、iMessage、Twitter/X、Discord
智能家居：Philips Hue、Sonos、Eight Sleep
开发工具：GitHub CLI、Claude Code 子进程、Whisper 转录
Channels 系统：多平台消息集成
Channels 负责连接各消息平台到中央 Gateway。根据配置与不同的渠道（比如飞书）建立安全链接，完成消息收发（通常是WebSocket 协议）以及格式转换 — 即翻译成 Clawdbot 能听懂的格式。

Channel 协议/库 特性
WhatsApp Baileys（WhatsApp Web 协议） QR 登录、媒体支持、群组提及网关
Telegram grammY（Bot API） 流式传输、Webhook 支持
Discord discord.js 原生命令、DM 策略
Slack Bolt DM 配对策略、频道白名单
Signal signal-cli 需本地安装 signal-cli
iMessage imsg CLI 仅 macOS
Google Chat Chat API 扩展渠道
Matrix、Teams 扩展插件 社区支持
WhatsApp 配置示例：

{
  "channels": {
    "whatsapp": {
      "allowFrom": ["+15555550123"],
      "groups": { "*": { "requireMention": true } }
    }
  },
  "messages": {
    "groupChat": { "mentionPatterns": ["@clawd"] }
  }
}
由于微信没有开放API，现在还没有微信的支持。未来可能会有飞书或者钉钉的支持。

Nodes 系统：移动/桌面扩展
Nodes 就是在主机之外的其他“能力”节点，连接到 Gateway 的子设备（iOS、Android、macOS），提供设备本地功能：

旧手机、闲置电脑都可以作为 Node 加入网络，以提供更多的能力，比如摄像头、屏幕录制、系统控制、屏幕共享、显示可交互式的UI界面等。Nodes 需要在远程设备上运行相应的Node 客户端 App。

Node 支持的类型：

平台 功能
iOS Node Canvas、语音唤醒、摄像头拍照/录像、屏幕录制、语音触发
Android Node Canvas、语音交互、摄像头、屏幕截图、短信集成（可选）
macOS Node system.run（执行命令）、system.notify（通知）、Canvas/摄像头
Node 通信协议：

传输：Gateway WebSocket（LAN/Tailscale/SSH 隧道）
发现：node.list / node.describe 枚举能力
执行：node.invoke 运行设备本地操作
命令：camera.snap/camera.clip（拍照/录像）、screen.record、location.get、notifications
这实现了"远程大脑，本地双手"的架构——Gateway 可运行在远程 Linux 实例，而 Nodes 通过 Tailscale 连接，执行操作运行在设备本地。

场景：Gateway 跑在 Linux 服务器上，但你想用 Mac 的摄像头拍照。

// 列出已连接的节点
{ "tool": "nodes", "action": "status" }

// 在 Mac 节点上执行命令
{ "tool": "nodes", "action": "run", "node": "office-mac", "command": ["echo", "Hello"] }

// 拍照
{ "tool": "nodes", "action": "camera_snap", "node": "iphone-1" }

// 屏幕录制
{ "tool": "nodes", "action": "screen_record", "node": "office-mac", "duration": "10s" }

// 获取位置
{ "tool": "nodes", "action": "location_get", "node": "iphone-1" }
Memory 系统：持久化记忆
openClaw 的记忆系统非常简单明了，直接基于纯 Markdown 文件——文件是真实来源，模型只"记住"写入磁盘的内容。

记忆文件结构：

~/clawd/
├── AGENTS.md          # 智能体的描述和提示词
├── BOOTSTRAP.md       # 初始系统设置
├── HEARTBEAT.md       # 系统健康检查清单
├── IDENTITY.md        # openClaw智能体 身份/人设
├── SOUL.md            # 性格特征
├── TOOLS.md           # 可用工具参考
├── USER.md            # 用户偏好/上下文
├── MEMORY.md          # 长期策划记忆（可选）
├── canvas/            # 可视化工作区
├── memory/            # 持久化记忆目录
│   ├── 2026-01-28.md  # 每日笔记
│   └── 2026-01-29.md
└── skills/            # 已安装 skills
向量记忆搜索：

默认启用
索引文件：MEMORY.md + memory/**/*.md
分块策略：约 400 token 目标，80 token 重叠
存储：sqlite-vec 加速向量搜索
嵌入提供商（自动选择顺序）：local → openai → gemini
混合搜索（BM25 + 向量结合）配置：

{
  "agents": {
    "defaults": {
      "memorySearch": {
        "query": {
          "hybrid": {
            "enabled": true,
            "vectorWeight": 0.7,
            "textWeight": 0.3,
            "candidateMultiplier": 4
          }
        }
      }
    }
  }
}
自动记忆刷新机制：当会话接近自动压缩时，触发静默智能体回合，提示模型将持久记忆写入磁盘。

工作流与实现细节
消息处理完整流程
用户消息 (WhatsApp/Telegram/Discord/等)
        ↓
    Channel Adapter（标准化为内部格式）
        ↓
    Gateway (WebSocket API - ws://127.0.0.1:18789)
        ↓
    Agent Runtime (Pi agent via RPC)
        ↓
    LLM Provider (Claude/GPT/本地模型)
        ↓
    Tool Execution（按需执行）
        ↓
    Response → Gateway → Channel Adapter → 用户
以“自动整理会议纪要并发 WhatsApp 提醒”为例：

感知：Slack 的 webhook 或文件上传触发消息到 Gateway。
计划：Agent 从短期对话与长期记忆（本地的 MEMORY.md 等持久文件）中抓取上下文，生成一个 multi-step plan。
执行：按计划调用 Skill（可能在 Docker 沙箱中执行浏览器脚本或 shell 命令）。
反哺：结果写回本地记忆并发送给用户，同时将关键操作记录供将来检索。
这套闭环让 openClaw看起来像一个“会思考的执行器”，而不是只会说话的聊天机器人。

Heartbeat 心跳机制
Heartbeat 实现定时任务的自动行为——openClaw 可在无用户提示时主动联系用户。

配置示例：

{
  "agent": {
    "heartbeat": {
      "every": "30m",
      "activeHours": { "start": "08:00", "end": "22:00" }
    }
  }
}
工作原理： 在 ~/clawd/HEARTBEAT.md 创建检查清单：

心跳检查清单

检查邮件中的紧急消息
查看未来 2 小时的日历事件
如果空闲超过 8 小时，发送简短问候
Cron 定时任务（插件）
一次性提醒：

openClaw cron add \
  --name "发送提醒" \
  --at "2026-01-12T18:00:00Z" \
  --session main \
  --system-event "提醒：提交费用报告。" \
  --wake now \
  --delete-after-run
周期性任务：

openClaw cron add \
  --name "早间状态" \
  --cron "0 7 ** *" \
  --tz "Asia/Shanghai" \
  --session isolated \
  --message "总结今天的收件箱和日历。" \
  --deliver \
  --channel whatsapp \
  --to "+8613800138000"
Docker 沙箱隔离
沙箱配置：

{
  "agents": {
    "defaults": {
      "sandbox": {
        "mode": "non-main",
        "scope": "agent",
        "workspaceAccess": "none"
      }
    }
  }
}

沙箱模式：

"none"：无沙箱（工具在主机运行）
"non-main"：仅非主会话沙箱化
"all"：所有会话沙箱化
隔离范围：

"agent"（默认）：每智能体一个容器
"session"：更严格的每会话隔离
"shared"：单容器共享（安全性较低）
工作区访问级别：

"none"（默认）：智能体工作区不可访问
"ro"：智能体工作区只读挂载到 /agent
"rw"：智能体工作区读写挂载到 /workspace
安全容器运行示例：

docker run \
  --name openClaw-secure \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=64M \
  --security-opt=no-new-privileges \
  --cap-drop=ALL \
  --cap-add=NET_BIND_SERVICE \
  --cpus="1.0" \
  --memory="2g" \
  -u 1000:1000 \
  openClaw/agent:latest

openClaw部署与配置指南

系统要求
组件 要求
Node.js——需要提前安装 版本 22+
RAM 最低 2GB（浏览器自动化建议 4GB+）
CPU 最低双核
存储 Docker 部署 20GB
操作系统 macOS、Linux、Windows（WSL2）、树莓派也可以
网络 API 访问需互联网
端口（默认） 18789（Gateway）、18790（Bridge）

一键快速安装
macOS/Linux：

curl -fsSL <https://openClaw.bot/install.sh> | bash
Windows (PowerShell)：

iwr -useb <https://molt.bot/install.ps1> | iex
npm 安装：

npm install -g openClaw@latest

# 或

pnpm add -g openClawt@latest
从源码构建：

git clone <https://github.com/openClaw/openClaw.git>
cd openClaw
pnpm install
pnpm ui:build
pnpm build
openClaw onboard --install-daemon
引导向导
运行 openClaw onboard --install-daemon 配置：

本地 vs 远程 Gateway 选择
认证：OAuth（OpenAI Code/Codex）、API 密钥或 claude setup-token
Channel：WhatsApp QR 登录、Telegram/Discord bot tokens
守护进程：后台安装（launchd/systemd）
Gateway token：自动生成并存储
工作区引导 + skills 配置
配置启动
4.3 初始配置（Onboarding 向导详解）

运行以下命令启动配置向导：

clawdbot onboard
向导会显示一个有趣的 ASCII 龙虾 Logo：

░████░█░░░░░█████░█░░░█░███░░████░░████░░▀█▀
█░░░░░█░░░░░█░░░█░█░█░█░█░░█░█░░░█░█░░░█░░█░
█░░░░░█░░░░░█████░█░█░█░█░░█░████░░█░░░█░░█░
█░░░░░█░░░░░█░░░█░█░█░█░█░░█░█░░█░░█░░░█░░█░
░████░█████░█░░░█░░█░█░░███░░████░░░███░░░█░
              🦞 FRESH DAILY 🦞
步骤 1：安全确认

◇  Security ───────────────────────────────────────────────────────╮
│  Clawdbot agents can run commands, read/write files, and act     │
│  through any tools you enable.                                   │
│  Please read: <https://docs.clawd.bot/security>                    │
├──────────────────────────────────────────────────────────────────╯

◇  I understand this is powerful and inherently risky. Continue?
│  Yes
步骤 2：选择 AI 后端和认证方式

◇  Model/auth provider
│  Anthropic

◆  Anthropic auth method
│  ● Anthropic token (paste setup-token) ← 推荐 Claude Max 用户
│  ○ Anthropic token (Claude Code CLI)
│  ○ Anthropic API key
◆ token
│  XXXX-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx...
然后输入key即可

步骤 3：配置消息平台（以 Telegram 为例）

◇  Channel status ────────────────────────────╮
│  Telegram: not configured                   │
│  WhatsApp: not configured                   │
│  Discord: not configured                    │
│  ...共支持 12+ 平台                          │
├─────────────────────────────────────────────╯

◇  Select channel (QuickStart)
│  Telegram (Bot API)
配置对应app的 Token请执行检索或者问AI

步骤 4：安装配置 Gateway 服务

◇  Gateway service runtime ────────────────────────────────────────────╮
│  QuickStart uses Node for the Gateway service (stable + supported).  │
├──────────────────────────────────────────────────────────────────────╯

◒  Installing Gateway service…
Installed LaunchAgent: /Users/your-username/Library/LaunchAgents/com.clawdbot.gateway.plist
Logs: /Users/your-username/.clawdbot/logs/gateway.log
◇  Gateway service installed

步骤 5：完成配置

◇
Telegram: ok (@YourBotName) (1416ms)  ← 你的 Bot 已连接
Agents: main (default)
Heartbeat interval: 1h (main)
Session store (main): /Users/your-username/.clawdbot/agents/main/sessions/sessions.json

◇  Control UI ─────────────────────────────────────────────────────────╮
│  Web UI: <http://127.0.0.1:18789/>                                     │
│  Web UI (with token): <http://127.0.0.1:18789/?token=your-token>...    │
│  Gateway WS: ws://127.0.0.1:18789                                    │
├──────────────────────────────────────────────────────────────────────╯

└  Onboarding complete.
Gateway 服务管理（重要）

步骤 6： 首次对话与配对验证

去 Telegram 给你的 Bot 发消息，你会收到一个配对码：

Clawdbot: access not configured.

Your Telegram user id: 1234567890

Pairing code: ABC12345

Ask the bot owner to approve with:
clawdbot pairing approve telegram &lt;code&gt;
关键环境变量

变量 说明
ANTHROPIC_API_KEY Anthropic Claude API 密钥
OPENAI_API_KEY OpenAI API 密钥
CLAWDBOT_GATEWAY_TOKEN Gateway 认证令牌
CLAWDBOT_CONFIG_DIR 配置目录（默认：~/.clawdbot）
CLAWDBOT_WORKSPACE_DIR 工作区目录（默认：~/clawd）
CLAWDBOT_GATEWAY_PORT Gateway 端口（默认：18789）
CLAWDBOT_GATEWAY_BIND 绑定地址（loopback/lan/tailnet）
Docker Compose 部署
快速启动：

./docker-setup.sh
docker-compose.yml 配置：

services:
  openClaw-gateway:
    image: ${CLAWDBOT_IMAGE:-openClaw:local}
    environment:
      HOME: /home/node
      CLAWDBOT_GATEWAY_TOKEN: ${CLAWDBOT_GATEWAY_TOKEN}
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
    volumes:
      - ${CLAWDBOT_CONFIG_DIR}:/home/node/.clawdbot
      - ${CLAWDBOT_WORKSPACE_DIR}:/home/node/clawd
    ports:
      - "${CLAWDBOT_GATEWAY_PORT:-18789}:18789"
      - "${CLAWDBOT_BRIDGE_PORT:-18790}:18790"
    init: true
    restart: unless-stopped
    command:
      - "node"
      - "dist/index.js"
      - "gateway"
      - "--bind"
      - "${CLAWDBOT_GATEWAY_BIND:-lan}"
智能体沙箱配置：

{
  "agents": {
    "defaults": {
      "sandbox": {
        "docker": {
          "image": "openClaw-sandbox:bookworm-slim",
          "workdir": "/workspace",
          "readOnlyRoot": true,
          "network": "none",
          "memory": "1g",
          "cpus": 1,
          "pidsLimit": 256
        }
      }
    }
  }
}
构建沙箱镜像：scripts/sandbox-setup.sh

核心功能详解
长期记忆系统
记忆是 Clawdbot 最核心的差异化能力。

普通聊天机器人：用完就忘 VS Clawdbot：记住你的一切

记忆架构：

混合检索：

当你问"我上周说的那个投资想法"时，Clawdbot 会：

向量检索（70% 权重）：找到语义相近的内容
BM25 全文检索（30% 权重）：找到关键词匹配的内容
融合排序：返回最相关的记忆
实际效果：

你（3 个月前）：我打算学习 Rust，主要是想写高性能的系统工具

你（今天）：我之前想学什么编程语言来着？

Clawdbot：你 3 个月前提到想学习 Rust，主要目的是写高性能的系统工具。
技能系统（Skills）与 ClawdHub
Clawdbot 通过"技能"来扩展能力，就像手机的 App Store。

技能包括什么？

一个 Markdown 文件（SKILL.md）+ 可选的脚本
定义了特定场景下 AI 应该如何行动
可以调用外部工具和 API
三层加载机制：

优先级从高到低：

1. Workspace Skills   &lt;当前目录&gt;/.claude/skills/
   └── 项目级别，只在该项目生效

2. User Skills        ~/.clawdbot/skills/
   └── 用户级别，所有项目共享

3. Bundled Skills     内置技能
   └── Clawdbot 自带的基础技能
安装技能：

# 从 ClawdHub 安装

clawdhub install weather-forecast

# 或手动创建

mkdir -p ~/.clawdbot/skills/my-skill
cat &gt; ~/.clawdbot/skills/my-skill/SKILL.md &lt;&lt; 'EOF'
---

name: my-skill
description: 我的自定义技能
triggers:

- "帮我做XXX"

---

当用户请求 XXX 时，按以下步骤执行：

1. ...
2. ...
EOF
ClawdHub 社区的技能市场：<https://clawdhub.com>

主动提醒能力（Cron 任务）
这是普通聊天机器人做不到的——Clawdbot 可以主动找你。

设置提醒：

你：每天早上 8 点提醒我看晨报
Clawdbot：好的，已设置每日 8:00 的提醒

→ 第二天早上 8:00，Clawdbot 发消息：
  "早上好！该看晨报了。"
技术实现：

Clawdbot 内置了 Cron 工具，支持：

一次性提醒
周期性提醒（每天/每周/每月）
条件触发（当某事发生时）
配置示例（高级用户）：

// ~/.clawdbot/clawdbot.json
{
  "cron": {
    "tasks": [
      {
        "name": "morning-brief",
        "schedule": "0 8 ** *",
        "action": "send_message",
        "prompt": "生成今日简报，包括天气、日程、未读消息摘要"
      }
    ]
  }
}
语音支持（ElevenLabs）
Clawdbot 可以和你语音对话，就像真正的助手一样。

语音模式：

开启语音模式后：

你说话 → 语音转文字 → AI 处理 → 文字转语音 → 播放回复

配置方式：

// ~/.clawdbot/clawdbot.json
{
  "nodes": {
    "talk": {
      "voiceId": "XB0fDUnXU5LcNxj5cHcI",  // ElevenLabs 语音 ID
      "modelId": "eleven_v3",
      "apiKey": "your-elevenlabs-api-key"
    }
  }
}

支持的场景：

macOS App（原生支持）
iOS/Android App（通过节点）
需要 ElevenLabs API Key
5.5 浏览器控制

Clawdbot 可以帮你操作浏览器，执行复杂的网页任务。

示例：

输入：帮我在京东搜索"机械键盘"，找一个 500 元以下评价最好的

Clawdbot：

1. 打开京东
2. 搜索"机械键盘"
3. 筛选价格 &lt; 500
4. 按评价排序
5. 返回前 3 个结果的截图和链接

技术实现：

使用 Chrome DevTools Protocol (CDP)
支持截图、点击、输入、滚动等操作
可以处理登录态（需要手动授权一次）
总结与展望
openClaw 代表了个人 AI 助手领域的重要突破：通过本地优先、自托管的架构，将 LLM 能力与真实世界的执行能力深度整合。

从技术架构角度，其分层设计（Gateway → Agent → Skills → Channels/Nodes）实现了清晰的关注点分离；

AgentSkills 开放标准确保了与 Claude Code、Cursor 等工具的生态兼容；

精简的系统提示词（约 1000 tokens）证明了前沿模型无需冗长指令即可理解智能体的上下文。

openClaw 是一次用开源实验回答未来个人计算问题的大胆尝试。它把“记忆”“主动性”“执行力”这三件事结合起来，展示了个人 AI 助手能如何真正融入工作流。但任何一项超能力都伴随着代价：配置的疏忽、默认设置的危险、以及社区生态的信任问题。

唯一的不足就是对中文生态支持还不算深入。任务的执行深度和交互性还是需要加强一点。

如果把 openClaw看作是一只脱壳中的龙虾——它的新壳既漂亮也脆弱——但他在飞速的成长，每一个AI开发者都不应该错过它。

一文读懂： Clawdbot分析与教程（Moltbot、openClaw）
190 赞同 · 16 评论 文章

读懂AI Agent：基于大模型的人工智能代理
923 赞同 · 31 评论 文章
附录：
从 Clawdbot 到 Moltbot到openClaw：项目时间线：

时间节点 里程碑事件
2024 年 4 月 开始构思"生活助手"项目，但因认为大公司会开发此类产品而搁置
2024 年 11 月 在 Twitter 发布"We are so back 🚀"，宣告回归
2025 年末 作为业余项目开发 Clawdbot
2026 年 1 月 26 日 正式发布 Clawdbot
首日 获得 9,000 GitHub stars
数日内 突破 100,000+ stars
2026 年 1 月 27 日 收到 Anthropic 商标通知，同日宣布更名
2026 年 1 月 28 日 正发布 Moltbot 更名公告
2026 年 1 月 30 日 正式发布 openClaw 更名公告，并宣告商业化目标
