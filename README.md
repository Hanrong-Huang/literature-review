# literature-review

An agent skill for Claude Code (and other coding agents) that searches the scientific
literature and downloads full text, with figures and tables, from Elsevier, Wiley,
Springer Nature and open-access sources. Papers go straight into your local Zotero,
or into a folder plus a `library.ris` for Zotero, EndNote or Mendeley.

```
you:   find recent papers on TiFe hydrogen storage activation
agent: searches Scopus/OpenAlex, shows a table with abstracts, recommends picks
you:   take 1, 3 and 7
agent: downloads them: text + figures + tables, PDFs, supplementary files
```

## Install: copy this prompt into Claude Code (or any coding agent)

```text
Install the literature-review skill from https://github.com/Hanrong-Huang/literature-review and set it up with me.
1. Clone it into my skills folder (Claude Code: ~/.claude/skills/literature-review; other agents: wherever you keep skills or instructions).
2. Read its SETUP.md and follow it step by step: run the check, then ask me the setup questions one at a time.
3. Walk me through the API keys I need and my Zotero setup, if I use Zotero. Open the sign-up pages for me, save keys as permanent environment variables, and never write them into files.
4. Do everything you can yourself, and tell me exactly what to click when you can't.
5. Finish by running its selftest to check the whole workflow, fix anything that fails, then do a small search on my research topic and show me the result.
```

中文版：

```text
请从 https://github.com/Hanrong-Huang/literature-review 安装 literature-review skill，并带我完成设置：
1. 克隆到我的 skills 文件夹（Claude Code 是 ~/.claude/skills/literature-review；其他 agent 放到你存放 skill 或指令的位置）。
2. 阅读其中的 SETUP.md，按步骤进行：先运行 check，再一次问我一个设置问题。
3. 带我获取需要的 API key；如果我用 Zotero，也帮我连好本机 Zotero。注册页面由你打开，key 存成永久环境变量，不要写进任何文件。
4. 你能做的都自己做，做不了的告诉我具体点哪里。
5. 最后运行 selftest 测试整个流程，有失败的就修好，再用我的研究方向做一次小检索，给我看结果。
```

The agent installs the skill and asks a few questions: institutional access? which
publishers? Zotero? It opens the sign-up pages for the keys you want, stores them as
environment variables, and connects your local Zotero if you use it. In Claude Code
the skill then triggers on its own when you ask for papers.

### Or as a Claude Code plugin

```
/plugin install literature-review --marketplace Hanrong-Huang/literature-review
```

Then paste:

```text
Set up the literature-review skill with me: follow its SETUP.md step by step, run the check, and ask me the setup questions one at a time.
```

On older Claude Code versions, run
`/plugin marketplace add Hanrong-Huang/literature-review` and then
`/plugin install literature-review@literature-review-tools`. Plugin updates are
manual unless you turn on auto-update for this marketplace in `/plugin`.

## What works with what

| | Nothing set up | + free keys | + institutional access (campus network/VPN, or Elsevier insttoken) |
|---|---|---|---|
| Search with abstracts | OpenAlex | Scopus (Elsevier key) | Scopus with full abstracts |
| Open-access papers | PMC / Europe PMC / repository PDFs | + Springer Nature OA with figures (Springer key) | |
| Elsevier subscription papers | | | full text + figures + tables + supplementary files |
| Wiley subscription papers | | | publisher PDF (Wiley TDM token) |

**Zotero (optional).** With Zotero 10+ running and
[zotero-cli](https://github.com/54yyyu/zotero-mcp) installed, papers are added to a
collection you name, with the PDF and the text attached as linked files (they don't
use your Zotero cloud storage). The bundled `zotero-plugin/` also lets Zotero's own
*Find Available PDF* run for each new paper. No Zotero account key is needed; a web
API key is an optional alternative for older Zotero versions.

Elsevier and Springer full text arrive as XML. The skill turns it into Markdown, which
is ideal for the agent to read, and prints a PDF from it with headless Chrome/Edge for
you to read. Publisher-typeset PDFs that the APIs don't serve can be fetched in a
browser by the agent (with your OK), and you solve any CAPTCHA yourself. In your own
browser (e.g. Claude in Chrome) your institutional sign-in works off campus too, with
no VPN.

## Manual install

Needs [uv](https://docs.astral.sh/uv/) and git; Chrome or Edge is optional (for the
printed PDFs).

```bash
git clone https://github.com/Hanrong-Huang/literature-review ~/.claude/skills/literature-review
uv run ~/.claude/skills/literature-review/scripts/litflow.py check      # keys and access
uv run ~/.claude/skills/literature-review/scripts/litflow.py selftest   # whole workflow, PASS/FAIL per step
```

Keys are environment variables: `ELSEVIER_API_KEY`, `ELSEVIER_INSTTOKEN`,
`WILEY_TDM_TOKEN`, `SPRINGER_OA_API_KEY`, `OPENALEX_API_KEY`, `LITFLOW_EMAIL`,
`LITFLOW_HOME`. [SETUP.md](SETUP.md) says where to get each one.

## Using the script directly

```bash
litflow="uv run ~/.claude/skills/literature-review/scripts/litflow.py"
$litflow search "solid-state hydrogen storage" -n 20 --year-from 2020 --sort cited
$litflow related 10.1016/j.ijhydene.2018.12.212 --mode citations
$litflow fetch ~/litflow/runs/<run> --only 1,4,7 --collection "Hydrogen/TiFe"   # into Zotero
$litflow fetch --dois 10.1002/er.1284 10.1007/s40820-023-01041-5
```

## Updating

Clone install: `git -C ~/.claude/skills/literature-review pull`. Plugin install:
`/plugin`, then *Update now*.

## Layout

```
SKILL.md                 what the agent does (workflow, sources, output)
SETUP.md                 guided first-time setup, run by the agent
scripts/litflow.py       the whole tool, one file (uv installs its two dependencies)
zotero-plugin/           optional Zotero plugin: Find Available PDF over a local endpoint
.claude-plugin/          marketplace entry for /plugin install
```

## Fair use

Bring your own keys and follow each publisher's text-and-data-mining terms. The skill
uses official APIs and open-access sources only. It never bypasses CAPTCHAs or
paywalls; when a site needs a human, it asks you.

## License

MIT
