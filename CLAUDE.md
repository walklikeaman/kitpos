# KIT POS — Project Schema

This file is read automatically by Claude Code from any subfolder of this repo (root + walked-up parents). Sub-agents in `agents/*` inherit this context — their own `AGENT_CONTEXT.md` adds local detail, this file gives the shared picture.

## Behavioral guidelines

Apply the [`andrej-karpathy-skills:karpathy-guidelines`](https://github.com/forrestchang/andrej-karpathy-skills) skill on every non-trivial task: think before coding, surface assumptions, surgical changes, define verifiable success.

## Repo layout

```
kitpos/
├── agents/                          # Sub-agents (each is its own package)
│   ├── maverick-terminal-agent/     # PAX Store provisioning (headless browser)
│   ├── kit-dashboard-merchant-data/ # KIT API VAR data lookup + logo
│   ├── kit-dashboard-agent/         # Merchant onboarding (OCR/MICR + form fill)
│   └── amazon-purchase-agent/
├── Context/                         # RAW SOURCES (immutable). PDFs, IDs, checks, VAR sheets, correspondence.
├── Research/                        # Workspace for ad-hoc research output
├── docs/                            # Architecture / setup / API guides (human-authored)
├── scripts/                         # Cross-agent helpers (ingest, supabase, eml batch)
└── wiki/                            # LLM-maintained knowledge base. See wiki/CLAUDE.md (this section).
```

## Wiki layer (LLM-owned)

Pattern from Karpathy's "LLM Wiki" idea: `Context/` is raw (you read, never modify); `wiki/` is the persistent compounding artifact (you write and maintain).

- `wiki/index.md` — catalog of every wiki page. Read this FIRST before answering questions about the project's accumulated knowledge.
- `wiki/log.md` — append-only chronological record. Format: `## [YYYY-MM-DD] {ingest|query|lint} | {title}`.
- `wiki/overview.md` — project-level synthesis (what KIT POS is, who's involved, current state).
- `wiki/sources/` — one page per ingested source (PDF, email thread, doc). Filename = sanitized source name.
- `wiki/entities/` — merchants, people (colleague Maverick, etc.), agents, vendors (PAX, TSYS, KIT).
- `wiki/concepts/` — KIT API, VAR sheets, MID, BroadPOS, Push Template, ACH change request, etc.

## Operations

**Ingest** (user drops a source into `Context/` and asks to process it):
1. Read the source.
2. Briefly discuss key takeaways with the user before writing.
3. Create `wiki/sources/<slug>.md` with summary + extracted facts + links to related pages.
4. Update affected `entities/` and `concepts/` pages (create if missing). Cross-link with `[[wiki-link]]` style or relative markdown links.
5. Append `## [YYYY-MM-DD] ingest | <title>` to `wiki/log.md`.
6. Update `wiki/index.md` with new pages.

**Query** (user asks a question):
1. Read `wiki/index.md` first.
2. Drill into relevant pages.
3. Answer with citations (link to wiki pages and to raw `Context/` files when relevant).
4. If the answer is non-trivial and reusable, file it back as a new `wiki/` page and update `index.md`.

**Lint** (on request):
- Contradictions between pages, stale claims, orphan pages, missing concept pages, missing cross-references, data gaps worth a web search.

## Page conventions

- YAML frontmatter on every wiki page: `type` (source|entity|concept), `created`, `updated`, `sources` (list of source slugs that contributed).
- Use today's date — current date is provided in the session context. Convert relative dates ("на той неделе") to absolute when filing.
- Keep summaries shorter than the source. No 30+ word displacive quotes — paraphrase.
- Russian or English content is fine; match the source language for direct quotes.

## UI / tooling

The repo doubles as an Obsidian vault (`.obsidian/` at root). Open `kitpos/` directly in Obsidian — `wiki/`, `Context/`, `docs/`, agent READMEs all show up. Graph view, backlinks, and frontmatter properties work out of the box.

- **Attachment folder**: `Context/clipped/` (set in `.obsidian/app.json`). Web Clipper drops new web sources here. Existing PDFs in `Context/` stay where they are.
- **Web Clipper** (browser extension at `obsidian.md/clipper`): use to ingest vendor docs (PAX / Sunmi / Otter / Instacart pages) into `Context/clipped/`. Treat as raw — Claude reads, then writes a wiki source page summarising it.
- **Hotkey suggestion**: bind "Download attachments for current file" so images in clipped articles are pulled local (otherwise URLs rot).

## Memory compiler (separate, complementary)

`.claude-memory-compiler/` (gitignored, personal) auto-captures every Claude Code session in `daily/YYYY-MM-DD.md` via SessionEnd / PreCompact hooks, then compiles into `knowledge/` articles. That is for *cross-session AI-interaction* knowledge (decisions, gotchas). The `wiki/` here is for *project-domain* knowledge (merchants, APIs, workflows). They don't overlap.

## What NOT to do

- Never modify files in `Context/` (raw layer is immutable). Web-clipped pages in `Context/clipped/` are also raw — don't edit, summarise into `wiki/sources/<slug>.md` instead.
- Don't pre-create empty entity/concept pages — they're created on first ingest that mentions them.
- Don't duplicate content across pages; link instead.
- Don't put ephemeral conversation state in `wiki/` — that's what `~/.claude/projects/.../memory/` (auto-memory) is for. The wiki is for accumulating project knowledge across sessions.
