# Setup guide (for the agent)

The user starts this by pasting the setup prompt from the README (English or Chinese).
Reply in the user's language.

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
3. **"Do you use Zotero?"** If yes, do section 4. Otherwise papers go to a folder plus
   a `library.ris` that any reference manager can import.
4. **"Where should downloads go?"** The default is `~/litflow`. To change it, set
   `LITFLOW_HOME`. With Zotero, PDFs stay in this folder as linked files, so pick a
   folder that won't move.

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

## 4. Zotero (optional)

This puts papers straight into the user's Zotero library, using
[zotero-cli](https://github.com/54yyyu/zotero-mcp) from the `zotero-mcp-server`
package. It works with the local Zotero app; no Zotero account key is needed.

1. Check that Zotero is version 10 or newer (Help → About Zotero). If it's older,
   ask the user to update, or use the optional web API route in step 6.
2. Ask the user to open Zotero → Settings → Advanced and tick **"Allow other
   applications on this computer to communicate with Zotero"**. Check it with
   `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:23119/api/`, which
   should print `200`.
3. Install the CLI: `uv tool install zotero-mcp-server`. If that fails on a new
   Python, add `--python 3.12`. Check with `zotero-cli --help`.
4. Allow it to write. First save `ZOTERO_LOCAL=true` as a permanent environment
   variable (as in section 3); without it, `authorize-local` refuses to run. Then
   run `zotero-mcp authorize-local` in a shell where `ZOTERO_LOCAL=true` is set.
   Zotero shows a dialog, which may open behind other windows. Ask the user to bring
   Zotero to the front and click **Always Allow** within two minutes.
   `zotero-mcp authorize-local --status` should then say writes go to the local API.
5. Optional but recommended: the *Find PDF* plugin bundled here lets Zotero's own
   *Find Available PDF* run for each new paper. Ask the user to open Zotero →
   Tools → Plugins → gear icon → **Install Plugin From File…** and choose
   `zotero-plugin/find-pdf-endpoint.xpi` from this skill's folder. Show them the full
   path. Then make sure the plugin is enabled in that list.
6. Optional: the web API route works with any Zotero version and while Zotero is
   closed. The user creates a key with write access at
   https://www.zotero.org/settings/keys (their numeric user ID is shown on that
   page). Save the key as `ZOTERO_API_KEY` and the ID as `ZOTERO_LIBRARY_ID`.
   Mention it; don't push it.

Run `check`. The Zotero line should say "running", show how writes go, and say whether
the plugin is OK. Then papers are added with `fetch ... --collection "<name>"`.

Also tell the user about one option: `zotero-mcp install-skill --target claude-user`
adds a companion skill for reading and searching their whole Zotero library.

## 5. Finish

1. Run `check` again and walk through the results with the user.
2. Do a small test together, e.g. `search "<their topic>" -n 5`, then `fetch` two
   results (with `--collection "litflow test"` if Zotero is set up). Show them the
   result in Zotero or in the output folder. Without zotero-cli, show how to import
   `library.ris` (Zotero: File → Import).
3. Tell them how to update later: `git -C <skill folder> pull`, or the plugin update
   if they installed it from the marketplace.
