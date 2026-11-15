# Setup guide (for the agent)

The user starts this by pasting the prompt from the README:

> Install the literature-review skill from https://github.com/Hanrong-Huang/literature-review
> and set it up with me. Clone it into my skills folder (Claude Code:
> `~/.claude/skills/literature-review`), then follow its SETUP.md step by step: run the
> check, ask me the setup questions, and walk me through getting any API keys I need.
> Do what you can yourself, and tell me exactly what to click when you can't.

You are setting up this skill for the user. Do every step you can yourself and tell
the user exactly what to click for the rest. Keep it short: ask one question at a time,
and skip anything they don't need.

## 1. Install

1. Clone the repo into your skills folder, if it isn't there already:
   - Claude Code: `git clone https://github.com/Hanrong-Huang/literature-review ~/.claude/skills/literature-review`
   - Other agents: clone anywhere and use `SKILL.md` as your instructions.
2. Make sure `uv` is installed (`uv --version`). If it isn't:
   - macOS / Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
   - Windows: `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`
3. Run `uv run <skill folder>/scripts/litflow.py check`. It already works with no
   keys: OpenAlex search plus open-access full text.

## 2. Ask the user

1. **"Does your university or company subscribe to Elsevier (ScienceDirect) or Wiley
   journals, and can you use its network or VPN?"**
   - Yes → offer the Elsevier key, and the Wiley token if they read Wiley journals.
   - Off campus with no VPN → Elsevier full text still works if their library gets
     them an *institutional token* (`ELSEVIER_INSTTOKEN`). Offer to draft the email
     to the library, saying the token is for text and data mining via the Elsevier API.
   - No subscription → open-access only. The Springer key is still worth getting.
2. **"Which publishers matter most for your field?"** Only set up those.
3. **"Where should downloads go?"** The default is `~/litflow`. To change it, set
   `LITFLOW_HOME`.

## 3. Getting keys (the user does the sign-up)

Open each page in a browser if you can. Otherwise give the link. The user registers;
you take it from there.

| Variable | Where | Notes |
|---|---|---|
| `ELSEVIER_API_KEY` | https://dev.elsevier.com → *I want an API key* → *Create API Key* | Free. Any website URL is fine. Gives Scopus search; full text needs institutional access |
| `ELSEVIER_INSTTOKEN` | the user's library asks Elsevier | Optional. Lets Elsevier full text work off campus |
| `WILEY_TDM_TOKEN` | https://onlinelibrary.wiley.com/library-info/resources/text-and-datamining | Sign in to Wiley Online Library and accept the TDM terms to see the token. Works for journals the institution subscribes to |
| `SPRINGER_OA_API_KEY` | https://dev.springernature.com → sign up → create an application → copy the *Open Access* key | Free |
| `OPENALEX_API_KEY` | https://openalex.org (sign in → API key) | Optional; raises rate limits |
| `LITFLOW_EMAIL` | the user's email | Optional; sent to OpenAlex as a polite contact |

When the user gives you a key, save it as a **permanent** environment variable.
Never write keys into the repo or any other file.
- Windows (PowerShell): `[Environment]::SetEnvironmentVariable("NAME", "value", "User")`.
  The script also reads these from the registry, so a restart isn't needed.
- macOS / Linux: append `export NAME="value"` to `~/.zshrc` or `~/.bashrc`, then
  `source` it.

If the user would rather not paste keys into chat, give them the command to run
themselves.

## 4. Finish

1. Run `check` again and walk through the results with the user.
2. Do a small test together, e.g. `search "<their topic>" -n 5`, then `fetch` two
   results. Show them the output folder and how to import `library.ris` into Zotero
   (File → Import → choose the file; choose "link to files" if their Zotero cloud
   storage is small).
3. Tell them how to update later: `git -C <skill folder> pull`.
