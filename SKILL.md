---
name: literature-review
description: Search the scientific literature (Scopus or OpenAlex) and download full text from Elsevier, Wiley, Springer Nature and open-access sources, with figures and tables, into a folder plus a library.ris for Zotero/EndNote/Mendeley. Use whenever the user asks to search for, find, collect or download papers or related work, expand from a key paper (similar / citing / references), or build a reading list or literature review — e.g. "find papers on", "related work", "literature review", 搜文献, 查文献, 找相关文献, 文献调研, 综述.
---

# Literature review

One script does search → pick → download:
`uv run <this skill's folder>/scripts/litflow.py <command>` (`--help` lists every option).
First time here, or `check` shows problems? Follow [SETUP.md](SETUP.md) with the user.

## Workflow

1. **Check**: run `check`. It shows which keys are set and what full text actually
   works from this network. If Elsevier subscription full text says "no" and the user
   has institutional access, suggest their campus network or VPN.
2. **Search**: `search "<query>" -n 20`, adding `--year-from` or `--sort cited|date`
   when useful. It uses Scopus when an Elsevier key is set (plain words become
   `TITLE-ABS-KEY(...)`; full Scopus syntax works) and OpenAlex otherwise. To expand
   from a key paper: `related <DOI> --mode similar|citations|references`.
3. **Pick**: show the numbered results as a compact table (year, journal, citations,
   one-line gist from the abstract) and recommend which to keep. Wait for the user's
   choice unless they already said "all" or gave clear criteria.
4. **Fetch**: `fetch <run_dir> --only 1,4,7`, or `fetch --dois <DOI> ...`.
5. **Report**: how many papers got full text and in what form, the missing ones with
   the reason, and the path of `library.ris` (in Zotero: File → Import, which attaches
   the PDFs). Offer to read or summarise the papers; prefer the `.md` files, whose
   text and tables are cleaner than PDF text.
6. **Browser fallback**, only if the user wants publisher PDFs that the script couldn't
   get, and only if you have a browser tool. Ask once first, listing the papers.
   - Open `https://doi.org/<DOI>`, decline non-essential cookies, and click the page's
     own PDF / Download button. Use no scripted fetches or other tricks.
   - Save or move the file to `papers/<doi_with_underscores>/<doi_with_underscores>.pdf`
     in the run folder. Check that it starts with `%PDF-`, then run `ris <run_dir>`.
   - **On a CAPTCHA or "are you a robot" page, never solve or bypass it.** Ask the user
     to complete it in the browser, then continue. ScienceDirect usually shows one.

## What each source gives

| Source | Needs | You get |
|---|---|---|
| Search | nothing (OpenAlex) or an Elsevier key (Scopus) | results with abstracts |
| Elsevier | API key + institutional network, or an insttoken | full text as Markdown with figures and tables, a PDF printed from it, plus the accepted-manuscript PDF and supplementary files when Elsevier lists them |
| Wiley | TDM token + institutional subscription | publisher PDF |
| Springer Nature | free Open Access API key | open-access articles as Markdown with figures and tables, plus a printed PDF |
| Open access (any publisher) | nothing | PMC PDF, Europe PMC text, or a repository PDF |

Sites that block scripts (MDPI and some others) are reported as `-> browser`. The
printed PDF's pagination is not the journal's, so cite page numbers from the publisher
PDF.

## Output

```
$LITFLOW_HOME/runs/<time>_<query>/     (default ~/litflow)
  results.json          search results (numbered as shown)
  fetch_report.csv      what each paper got, and why not
  library.ris           import into Zotero / EndNote / Mendeley
  papers/<doi>/         <doi>.pdf | .accepted.pdf | .rendered.pdf, <doi>.md, figs/, supplementary/
```
