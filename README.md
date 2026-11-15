# literature-review

An agent skill for Claude Code (and other coding agents) that searches the scientific
literature and downloads full text, with figures and tables, from Elsevier, Wiley,
Springer Nature and open-access sources. You get a folder of papers plus a
`library.ris` to import into Zotero, EndNote or Mendeley.

```
you:   find recent papers on TiFe hydrogen storage activation
agent: searches Scopus/OpenAlex, shows a table with abstracts, recommends picks
you:   take 1, 3 and 7
agent: downloads them: text + figures + tables, PDFs, supplementary files
```

## Install: paste this to your agent

> Install the literature-review skill from https://github.com/Hanrong-Huang/literature-review
> and set it up with me. Clone it into my skills folder (Claude Code:
> `~/.claude/skills/literature-review`), then follow its SETUP.md step by step: run the
> check, ask me the setup questions, and walk me through getting any API keys I need.
> Do what you can yourself, and tell me exactly what to click when you can't.

The agent installs the skill, asks two or three questions (institutional access?
which publishers?), opens the sign-up pages for the keys you want, and stores them as
environment variables. In Claude Code the skill then triggers on its own when you ask
for papers.

## What works with what

| | Nothing set up | + free keys | + institutional access (campus network/VPN, or Elsevier insttoken) |
|---|---|---|---|
| Search with abstracts | OpenAlex | Scopus (Elsevier key) | Scopus with full abstracts |
| Open-access papers | PMC / Europe PMC / repository PDFs | + Springer Nature OA with figures (Springer key) | |
| Elsevier subscription papers | | | full text + figures + tables + supplementary files |
| Wiley subscription papers | | | publisher PDF (Wiley TDM token) |

Elsevier and Springer full text arrive as XML. The skill turns it into Markdown, which
is ideal for the agent to read, and prints a PDF from it with headless Chrome/Edge for
you to read. Publisher-typeset PDFs that the APIs don't serve can be fetched in a
browser by the agent (with your OK), and you solve any CAPTCHA yourself.

## Manual install

Needs [uv](https://docs.astral.sh/uv/) and git; Chrome or Edge is optional (for the
printed PDFs).

```bash
git clone https://github.com/Hanrong-Huang/literature-review ~/.claude/skills/literature-review
uv run ~/.claude/skills/literature-review/scripts/litflow.py check
```

Keys are environment variables: `ELSEVIER_API_KEY`, `ELSEVIER_INSTTOKEN`,
`WILEY_TDM_TOKEN`, `SPRINGER_OA_API_KEY`, `OPENALEX_API_KEY`, `LITFLOW_EMAIL`,
`LITFLOW_HOME`. [SETUP.md](SETUP.md) says where to get each one.

## Using the script directly

```bash
litflow="uv run ~/.claude/skills/literature-review/scripts/litflow.py"
$litflow search "solid-state hydrogen storage" -n 20 --year-from 2020 --sort cited
$litflow related 10.1016/j.ijhydene.2018.12.212 --mode citations
$litflow fetch ~/litflow/runs/<run> --only 1,4,7
$litflow fetch --dois 10.1002/er.1284 10.1007/s40820-023-01041-5
```

## Updating

`git -C ~/.claude/skills/literature-review pull`

## Fair use

Bring your own keys and follow each publisher's text-and-data-mining terms. The skill
uses official APIs and open-access sources only. It never bypasses CAPTCHAs or
paywalls; when a site needs a human, it asks you.

## License

MIT
