# /// script
# requires-python = ">=3.10"
# dependencies = ["requests", "markdown"]
# ///
"""litflow: search the literature and download full text (Elsevier, Wiley, Springer, open access).

  check                                   which keys are set and what full text you can actually get
  search "query" [-n 20] [--year-from Y] [--sort relevance|cited|date] [--source auto|scopus|openalex]
  related DOI [--mode similar|citations|references] [-n 20]
  fetch RUN_DIR [--only 1,3,5]            download full text for (some of) a search's results
  fetch --dois DOI [DOI ...]
  ris RUN_DIR                             rebuild library.ris (e.g. after adding PDFs by hand)

Run with:  uv run <this file> <command> ...      Results go to $LITFLOW_HOME (default ~/litflow).

Full text per paper, first hit wins:
  Elsevier  -> full-text XML -> Markdown with figures and tables, plus a PDF printed from it
               (and the accepted-manuscript PDF and supplementary files when Elsevier lists them)
  Wiley     -> TDM API -> publisher PDF
  Springer  -> open-access JATS XML -> Markdown with figures and tables, plus a printed PDF
  any       -> open-access copy found by OpenAlex: PMC PDF, Europe PMC XML, or a repository PDF
Subscription content (Elsevier, Wiley) needs your institution's network/VPN or, for Elsevier,
an institutional token (ELSEVIER_INSTTOKEN).
"""
from __future__ import annotations

import argparse
import base64
import csv
import datetime as dt
import html as html_lib
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import time
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]


# ------------------------------------------------------------------ config
def env(name: str) -> str:
    """Environment variable. On Windows, also the saved user variables (for shells started before
    they were set), unless LITFLOW_NO_REGISTRY=1."""
    v = os.environ.get(name, "")
    if not v and sys.platform == "win32" and not os.environ.get("LITFLOW_NO_REGISTRY"):
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                v = str(winreg.QueryValueEx(k, name)[0])
        except OSError:
            v = ""
    return v


KEYS = {n: env(n) for n in ("ELSEVIER_API_KEY", "ELSEVIER_INSTTOKEN", "WILEY_TDM_TOKEN",
                             "SPRINGER_OA_API_KEY", "OPENALEX_API_KEY")}
EMAIL = env("LITFLOW_EMAIL")  # optional; sent to OpenAlex/Crossref as polite contact
HOME = Path(env("LITFLOW_HOME") or Path.home() / "litflow")
ELSEVIER = ("10.1016/",)
WILEY = ("10.1002/", "10.1111/", "10.1113/", "10.1046/")
SPRINGER = ("10.1007/", "10.1038/", "10.1186/", "10.1140/", "10.1557/")
SCOPUS_FIELD = re.compile(r"\b(TITLE|ABS|KEY|TITLE-ABS-KEY|AUTH|AUTHOR-NAME|SRCTITLE|DOI|PUBYEAR|AFFIL|ALL|"
                          r"AUTHKEY|LANGUAGE|DOCTYPE|SUBJAREA|OPENACCESS|PUBLISHER)\s*\(", re.I)
BROWSER_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36"}
PMC_S3 = "https://pmc-oa-opendata.s3.amazonaws.com/"  # NIH PMC open-access dataset (PDF, XML, images)


def log(msg: str = "") -> None:
    print(msg, flush=True)


def safe_name(doi: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", doi)


def els_headers(accept: str = "application/json") -> dict:
    h = {"X-ELS-APIKey": KEYS["ELSEVIER_API_KEY"], "Accept": accept}
    if KEYS["ELSEVIER_INSTTOKEN"]:
        h["X-ELS-Insttoken"] = KEYS["ELSEVIER_INSTTOKEN"]
    return h


def oa_params(**p) -> dict:
    if KEYS["OPENALEX_API_KEY"]:
        p["api_key"] = KEYS["OPENALEX_API_KEY"]
    if EMAIL:
        p["mailto"] = EMAIL
    return p


def download(url: str, dest: Path, headers: dict | None = None, max_mb: int = 80) -> bool:
    try:
        r = requests.get(url, headers=headers or {}, timeout=180)
        if r.status_code != 200 or not r.content or len(r.content) > max_mb * 2 ** 20:
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(r.content)
        return True
    except requests.RequestException:
        return False


# ------------------------------------------------------------------ search
def row(doi: str = "", title: str = "", author: str = "", journal: str = "", year: Any = "",
        cited: Any = 0, oa: Any = False, abstract: str = "") -> dict:
    return {"doi": doi, "title": title, "first_author": author, "journal": journal, "year": str(year or ""),
            "cited_by": int(cited or 0), "open_access": bool(oa), "abstract": abstract}


def scopus_search(query: str, n: int, year_from: int | None, sort: str) -> list[dict]:
    q = query if SCOPUS_FIELD.search(query) else f"TITLE-ABS-KEY({query})"
    if year_from:
        q += f" AND PUBYEAR > {year_from - 1}"
    sort_by = {"relevance": "relevancy", "cited": "-citedby-count", "date": "-coverDate"}[sort]
    rows: list[dict] = []
    start, total, view = 0, "?", "COMPLETE"  # COMPLETE has abstracts but needs institutional access
    while len(rows) < n:
        r = requests.get("https://api.elsevier.com/content/search/scopus", headers=els_headers(), timeout=60,
                         params={"query": q, "start": start, "count": min(25, n - len(rows)),
                                 "sort": sort_by, "view": view})
        if r.status_code in (401, 403) and view == "COMPLETE":
            view = "STANDARD"
            continue
        r.raise_for_status()
        res = r.json()["search-results"]
        total = res.get("opensearch:totalResults", "?")
        entries = res.get("entry", [])
        if not entries or "error" in entries[0]:
            break
        rows += [row(e.get("prism:doi", ""), e.get("dc:title", ""), e.get("dc:creator", ""),
                     e.get("prism:publicationName", ""), e.get("prism:coverDate", "")[:4], e.get("citedby-count"),
                     e.get("openaccess") in ("1", 1, True), re.sub(r"\s*©.*$", "", e.get("dc:description") or ""))
                 for e in entries]
        start += len(entries)
        if start >= int(total):
            break
    log(f"Scopus: {q}  ->  {total} hits, showing {len(rows)}")
    return rows


def openalex_rows(results: list[dict]) -> list[dict]:
    out = []
    for w in results:
        inv = w.get("abstract_inverted_index") or {}
        abstract = " ".join(x for _, x in sorted((p, word) for word, ps in inv.items() for p in ps))
        out.append(row((w.get("doi") or "").removeprefix("https://doi.org/"), w.get("title") or "",
                       ((w.get("authorships") or [{}])[0].get("author") or {}).get("display_name", ""),
                       (((w.get("primary_location") or {}).get("source")) or {}).get("display_name", ""),
                       w.get("publication_year"), w.get("cited_by_count"),
                       (w.get("open_access") or {}).get("is_oa"), abstract))
    return out


OA_SELECT = ("doi,title,publication_year,cited_by_count,open_access,authorships,primary_location,"
             "abstract_inverted_index")


def openalex_works(n: int, sort: str | None = None, **params) -> list[dict]:
    p = oa_params(per_page=min(n, 200), select=OA_SELECT, **params)
    if sort:
        p["sort"] = sort
    r = requests.get("https://api.openalex.org/works", params=p, timeout=60)
    r.raise_for_status()
    return openalex_rows(r.json().get("results", []))


def openalex_search(query: str, n: int, year_from: int | None, sort: str) -> list[dict]:
    filt = f"from_publication_date:{year_from}-01-01" if year_from else None
    s = {"relevance": None, "cited": "cited_by_count:desc", "date": "publication_date:desc"}[sort]
    rows = openalex_works(n, s, search=query, **({"filter": filt} if filt else {}))
    log(f"OpenAlex: {query}  ->  showing {len(rows)}")
    return rows


def add_abstracts(rows: list[dict]) -> None:
    """Fill missing abstracts: OpenAlex in batches, then Scopus one by one (OpenAlex lacks Elsevier's)."""
    need = [r for r in rows if r["doi"] and not r["abstract"]]
    for i in range(0, len(need), 50):
        chunk = need[i:i + 50]
        try:
            got = {r["doi"].lower(): r["abstract"] for r in
                   openalex_works(50, filter="doi:" + "|".join(x["doi"] for x in chunk))}
            for x in chunk:
                x["abstract"] = got.get(x["doi"].lower(), "")
        except requests.RequestException as e:
            log(f"(OpenAlex abstracts unavailable: {e})")
    if not KEYS["ELSEVIER_API_KEY"]:
        return
    for x in (r for r in need if not r["abstract"]):
        try:
            r = requests.get(f"https://api.elsevier.com/content/abstract/doi/{x['doi']}",
                             params={"field": "description"}, headers=els_headers(), timeout=30)
            if r.ok:
                desc = r.json()["abstracts-retrieval-response"]["coredata"].get("dc:description") or ""
                x["abstract"] = re.sub(r"\s*©.*$", "", desc).strip()
        except (requests.RequestException, KeyError, ValueError):
            pass


def related(doi: str, n: int, mode: str) -> list[dict]:
    """OpenAlex: related works, papers citing this one, or its references."""
    r = requests.get(f"https://api.openalex.org/works/doi:{doi}", params=oa_params(), timeout=30)
    r.raise_for_status()
    w = r.json()
    wid = w["id"].rsplit("/", 1)[-1]
    if mode == "citations":
        return openalex_works(n, "cited_by_count:desc", filter=f"cites:{wid}")
    ids = [u.rsplit("/", 1)[-1] for u in w.get("related_works" if mode == "similar" else "referenced_works", [])]
    rows: list[dict] = []
    for i in range(0, len(ids[:200]), 50):
        rows += openalex_works(50, filter="openalex:" + "|".join(ids[i:i + 50]))
    return sorted(rows, key=lambda x: -x["cited_by"])[:n]


def save_and_show(rows: list[dict], label: str, args) -> None:
    if not args.no_abstracts:
        add_abstracts(rows)
    run_dir = Path(args.out) if args.out else HOME / "runs" / (
        f"{dt.datetime.now():%Y%m%d-%H%M}_" + (re.sub(r"[^A-Za-z0-9]+", "-", label).strip("-")[:40] or "query"))
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "query.txt").write_text(label, encoding="utf-8")
    (run_dir / "results.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    for i, r in enumerate(rows, 1):
        log(f"{i:>3}. [{r['year']}] {'OA' if r['open_access'] else '  '} cit={r['cited_by']:<4} {r['title']}")
        log(f"      {r['first_author']} | {r['journal']} | {r['doi'] or 'no DOI'}")
        if r["abstract"]:
            a = r["abstract"][:300] + ("…" if len(r["abstract"]) > 300 else "")
            log(textwrap.fill(a, 110, initial_indent="      ", subsequent_indent="      "))
        log()
    log(f"run dir: {run_dir}")


def cmd_search(args) -> int:
    use_scopus = args.source == "scopus" or (args.source == "auto" and KEYS["ELSEVIER_API_KEY"])
    if use_scopus and not KEYS["ELSEVIER_API_KEY"]:
        sys.exit("ELSEVIER_API_KEY is not set (see SETUP.md), or use --source openalex")
    fn = scopus_search if use_scopus else openalex_search
    save_and_show(fn(args.query, args.n, args.year_from, args.sort), args.query, args)
    return 0


def cmd_related(args) -> int:
    save_and_show(related(args.doi, args.n, args.mode), f"{args.mode} of {args.doi}", args)
    return 0


# ------------------------------------------------------------------ publishers
_last_wiley = 0.0


def wiley_pdf(doi: str, dest: Path) -> str:
    global _last_wiley
    if not KEYS["WILEY_TDM_TOKEN"]:
        return "no Wiley token"
    time.sleep(max(0.0, 10.5 - (time.time() - _last_wiley)))  # Wiley allows 60 requests / 10 min
    _last_wiley = time.time()
    r = requests.get(f"https://api.wiley.com/onlinelibrary/tdm/v1/articles/{urllib.parse.quote(doi, safe='')}",
                     headers={"Wiley-TDM-Client-Token": KEYS["WILEY_TDM_TOKEN"]}, timeout=120)
    if r.status_code == 200 and r.content[:5] == b"%PDF-":
        dest.write_bytes(r.content)
        return "ok"
    return f"wiley http {r.status_code}"


def elsevier_xml(doi: str, dest: Path) -> str:
    if not KEYS["ELSEVIER_API_KEY"]:
        return "no Elsevier key"
    r = requests.get(f"https://api.elsevier.com/content/article/doi/{doi}", params={"view": "FULL"},
                     headers=els_headers("text/xml"), timeout=120)
    if r.status_code != 200:
        return f"elsevier http {r.status_code}"
    dest.write_bytes(r.content)
    return "ok"


def springer_oa_xml(doi: str, dest: Path) -> str:
    if not KEYS["SPRINGER_OA_API_KEY"]:
        return "no Springer key"
    r = requests.get("https://api.springernature.com/openaccess/jats",
                     params={"q": f"doi:{doi}", "api_key": KEYS["SPRINGER_OA_API_KEY"]}, timeout=120)
    if r.status_code != 200 or b"<body" not in r.content:
        return "not open access at Springer" if r.status_code in (200, 404) else f"springer http {r.status_code}"
    dest.write_bytes(r.content)
    return "ok"


_pmc_cache: dict[str, list[str]] = {}


def pmc_s3_files(pmcid: str) -> list[str]:
    """Object keys of the newest version of a PMC article in the open-access bucket ([] if absent)."""
    if pmcid not in _pmc_cache:
        try:
            r = requests.get(PMC_S3, params={"list-type": "2", "prefix": pmcid + ".", "max-keys": "1000"}, timeout=60)
            keys = re.findall(r"<Key>([^<]+)</Key>", r.text) if r.ok else []
        except requests.RequestException:
            keys = []
        ver = max((k.split("/", 1)[0] for k in keys), key=lambda v: int(v.rsplit(".", 1)[-1]), default="")
        _pmc_cache[pmcid] = [k for k in keys if k.startswith(ver + "/")] if ver else []
    return _pmc_cache[pmcid]


def open_access(doi: str, pdf: Path, xml: Path) -> str:
    """Open-access copy via OpenAlex: 'pdf' (PMC or repository), 'xml' (Europe PMC) or why not."""
    r = requests.get(f"https://api.openalex.org/works/doi:{doi}", params=oa_params(), timeout=30)
    if r.status_code != 200:
        return f"openalex http {r.status_code}"
    w = r.json()
    pmcid = ((w.get("ids") or {}).get("pmcid") or "").rsplit("/", 1)[-1]
    if pmcid:  # PMC's website blocks scripts; its open-access bucket and Europe PMC don't
        pmcid = pmcid if pmcid.upper().startswith("PMC") else "PMC" + pmcid
        key = next((k for k in pmc_s3_files(pmcid) if k.endswith(".pdf")), "")
        if key and download(PMC_S3 + key, pdf) and pdf.read_bytes()[:5] == b"%PDF-":
            return "pdf"
        e = requests.get(f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML", timeout=60)
        if e.status_code == 200 and b"<body" in e.content:
            xml.write_bytes(e.content)
            return "xml"
    locs = [w.get("best_oa_location") or {}] + (w.get("locations") or [])
    urls = list(dict.fromkeys(str(x["pdf_url"]) for x in locs if x and x.get("pdf_url")))
    for u in urls:
        try:
            p = requests.get(u, headers=BROWSER_UA, timeout=60)
            if p.status_code == 200 and p.content[:5] == b"%PDF-":
                pdf.write_bytes(p.content)
                return "pdf"
        except requests.RequestException:
            pass
    if urls or (w.get("open_access") or {}).get("is_oa"):
        return "open access, but the site blocks scripts -> browser"
    return "no open-access copy"


# ------------------------------------------------------------------ XML -> Markdown
XML_TAGS = {"elsevier": ("title", "description", "section", "section-title", "para", "sections"),
            "jats": ("article-title", "abstract", "sec", "title", "p", "body")}
FLOAT_TAGS = {"elsevier": ("figure", "table"), "jats": ("fig", "table-wrap")}
_ln = lambda e: e.tag.rsplit("}", 1)[-1]  # noqa: E731
_text = lambda e: re.sub(r"\s+", " ", "".join(e.itertext())).strip()  # noqa: E731


def _flat(e, skip: tuple[str, ...]) -> str:
    """Text of e without nested figures/tables."""
    def rec(x):
        out = [x.text or ""]
        for c in x:
            if _ln(c) not in skip:
                out.append(rec(c))
            out.append(c.tail or "")
        return "".join(out)
    return re.sub(r"\s+", " ", rec(e)).strip()


def _table(rows: list[list[tuple[str, str, str, str]]]) -> str:
    """rows of (text, colspan, rowspan, tag) -> Markdown, or HTML when cells span."""
    rows = [r for r in rows if r]
    if not rows:
        return ""
    if not any(cs not in ("", "1") or rs not in ("", "1") for r in rows for _, cs, rs, _t in r):
        md = []
        for i, r in enumerate(rows):
            md.append("| " + " | ".join(t.replace("|", "\\|") for t, *_ in r) + " |")
            if i == 0:
                md.append("|" + " --- |" * len(r))
        return "\n".join(md)
    out = ["<table>"]
    for r in rows:
        cells = "".join(f"<{tag}" + (f' colspan="{cs}"' if cs not in ("", "1") else "")
                        + (f' rowspan="{rs}"' if rs not in ("", "1") else "") + f">{html_lib.escape(t)}</{tag}>"
                        for t, cs, rs, tag in r)
        out.append(f"<tr>{cells}</tr>")
    return "\n".join(out + ["</table>"])


def jats_table(tbl) -> str:
    return _table([[(_text(c), c.get("colspan") or "", c.get("rowspan") or "", _ln(c))
                    for c in tr if _ln(c) in ("th", "td")] for tr in tbl.iter() if _ln(tr) == "tr"])


def cals_table(tbl) -> str:
    """Elsevier CALS table."""
    cols = {c.get("colname"): i for i, c in enumerate(e for e in tbl.iter() if _ln(e) == "colspec")}
    rows = []
    for part in ("thead", "tbody"):
        for sec in (e for e in tbl.iter() if _ln(e) == part):
            for r in (e for e in sec if _ln(e) == "row"):
                cells = []
                for c in (x for x in r if _ln(x) == "entry"):
                    a, b = c.get("namest"), c.get("nameend")
                    span = str(cols[b] - cols[a] + 1) if a in cols and b in cols else ""
                    more = int(c.get("morerows", 0) or 0)
                    cells.append((_text(c), span, str(more + 1) if more else "", "th" if part == "thead" else "td"))
                rows.append(cells)
    return _table(rows)


def elsevier_objects(root) -> dict[str, dict[str, str]]:
    """Elsevier <objects>: ref (gr1, mmc1, am, ...) -> {type: url}."""
    out: dict[str, dict[str, str]] = {}
    for o in (e for e in root.iter() if _ln(e) == "object"):
        if o.get("ref") and (o.text or "").strip():
            out.setdefault(o.get("ref"), {})[o.get("type", "")] = o.text.strip()
    return out


def image_source(root, flavor: str, label: str):
    """(locator -> image URL or None, request headers) for the figures of a full-text XML."""
    if flavor == "elsevier":
        objs = elsevier_objects(root)
        return (lambda loc: objs.get(loc, {}).get("IMAGE-HIGH-RES") or objs.get(loc, {}).get("IMAGE-DOWNSAMPLED"),
                els_headers("*/*"))
    ids = {e.get("pub-id-type"): _text(e) for e in root.iter() if _ln(e) == "article-id"}
    if label == "springer" and ids.get("doi"):
        base = f"https://static-content.springer.com/image/art%3A{urllib.parse.quote(ids['doi'], safe='')}/"
        return (lambda href: base + href), {}
    pmcid = ids.get("pmcid") or ("PMC" + ids["pmc"].removeprefix("PMC") if ids.get("pmc") else "")
    if pmcid:
        files = pmc_s3_files(pmcid)

        def pmc(href: str) -> str | None:  # hrefs may lack the extension
            k = next((k for k in files if k.endswith("/" + href) or re.search(re.escape("/" + href) + r"\.\w+$", k)), "")
            return PMC_S3 + k if k else None
        return pmc, {}
    return (lambda _h: None), {}


def xml_to_markdown(xml_path: Path, flavor: str, label: str, folder: Path) -> tuple[str, int, int]:
    """Article XML -> Markdown with figures (downloaded to folder/figs) and tables placed after the
    paragraph that first cites them. Returns (markdown, paragraphs, figures missing)."""
    t_title, t_abs, t_sec, t_sectitle, t_para, t_body = XML_TAGS[flavor]
    t_fig, t_tab = FLOAT_TAGS[flavor]
    root = ET.parse(xml_path).getroot()
    url_of, headers = image_source(root, flavor, label)
    missing = 0

    def image(loc: Any) -> str | None:
        nonlocal missing
        url = url_of(loc)
        name = re.sub(r"[^A-Za-z0-9._-]", "_", Path(loc).stem) + (Path(urllib.parse.urlparse(url or "").path).suffix or ".jpg")
        if url and ((folder / "figs" / name).exists() or download(url, folder / "figs" / name, headers)):
            return f"figs/{name}"
        missing += 1
        return None

    title = next((_text(e) for e in root.iter() if _ln(e) == t_title and _text(e)), "")
    abstract = re.sub(r"^Abstract\s*", "", next((_flat(e, (t_fig,)) for e in root.iter() if _ln(e) == t_abs), ""))
    lines, n = [f"# {title}", "", "## Abstract", "", abstract, ""], 0
    xlink = "{http://www.w3.org/1999/xlink}href"
    floats: dict[str, str] = {}
    for f in (e for e in root.iter() if _ln(e) in (t_fig, t_tab) and e.get("id")):
        lab = next((_text(c) for c in f if _ln(c) == "label"), "").rstrip(".")
        cap = next((_text(c) for c in f if _ln(c) == "caption"), "")
        if not (lab or cap):  # e.g. a graphical abstract
            continue
        block = []
        if _ln(f) == t_fig:
            locs = ([c.get("locator") for c in f if _ln(c) == "link" and c.get("locator")] if flavor == "elsevier"
                    else [g.get(xlink) for g in f.iter() if _ln(g) == "graphic" and g.get(xlink)])
            for loc in locs:
                rel = image(loc)
                block.append(f"![{lab or loc}]({rel})" if rel else f"*[{lab or loc}: image not available]*")
            block.append(f"**{lab}.** {cap}" if lab else cap)
        else:
            block.append(f"**{lab}.** {cap}" if lab else cap)
            tbl = f if flavor == "elsevier" else next((c for c in f if _ln(c) == "table"), None)
            conv = (cals_table(tbl) if flavor == "elsevier" else jats_table(tbl)) if tbl is not None else ""
            block.append(conv or "*[table could not be converted]*")
            block += [f"<sub>{_text(c)}</sub>" for c in f.iter() if _ln(c) in ("table-footnote", "table-wrap-foot")]
        floats[str(f.get("id"))] = "\n\n".join(b for b in block if b)
    placed: set[str] = set()

    def place(ids):
        for rid in ids:
            if rid in floats and rid not in placed:
                placed.add(rid)
                lines.extend([floats[rid], ""])

    def walk(node, depth):
        nonlocal n
        for ch in node:
            t = _ln(ch)
            if t == t_sectitle:
                lines.extend(["#" * min(depth, 6) + " " + _text(ch), ""])
            elif t == t_para:
                lines.extend([_flat(ch, (t_fig, t_tab)), ""])
                n += 1
                if flavor == "elsevier":
                    place(a.get("refid") for a in ch.iter() if _ln(a) == "float-anchor")
                else:
                    place(e.get("id") for e in ch.iter() if _ln(e) in (t_fig, t_tab))
                    place(r for x in ch.iter() if _ln(x) == "xref" and x.get("ref-type") in ("fig", "table")
                          for r in (x.get("rid") or "").split())
            elif t in (t_fig, t_tab):
                place([ch.get("id")])
            elif t == "list":
                lines.extend([f"- {_text(i)}" for i in ch if _ln(i) == "list-item"] + [""])
            elif t == t_sec:
                walk(ch, depth + 1)

    body = next((e for e in root.iter() if _ln(e) == t_body), None)
    if body is not None:
        walk(body, 1)
    rest = [b for k, b in floats.items() if k not in placed]
    if rest:
        lines.extend(["## Figures and tables", ""] + [x for b in rest for x in (b, "")])
    return "\n".join(lines), n, missing


# ------------------------------------------------------------------ Markdown -> PDF
CSS = """@page{margin:18mm 16mm}img,table{break-inside:avoid}body{max-width:52rem;margin:0 auto;
font:16px/1.6 Georgia,serif;color:#222}h1{font-size:1.6rem;line-height:1.3}h2{margin-top:2rem}
img{max-width:100%;display:block;margin:1rem auto}table{border-collapse:collapse;margin:1rem 0;
font:14px/1.4 sans-serif}td,th{border:1px solid #bbb;padding:.3rem .5rem}sub{display:block;font-size:.8rem;color:#555}"""
BROWSERS = ["msedge", "chrome", "google-chrome", "chromium", "chromium-browser",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"]


def find_browser() -> str | None:
    return next((p for b in BROWSERS if (p := shutil.which(b) or (b if Path(b).exists() else None))), None)


def markdown_to_pdf(md: str, folder: Path, pdf: Path) -> bool:
    """Print the Markdown (figures embedded) to PDF with headless Chrome/Edge, in a throwaway profile."""
    import markdown
    exe = find_browser()
    if not exe:
        return False

    def embed(m):
        f = folder / html_lib.unescape(m.group(2))
        if not f.exists():
            return m.group(0)
        mime = {".png": "image/png", ".gif": "image/gif"}.get(f.suffix.lower(), "image/jpeg")
        return f'{m.group(1)}data:{mime};base64,{base64.b64encode(f.read_bytes()).decode()}"'
    body = re.sub(r'(<img[^>]*?src=")(figs/[^"]+)"', embed, markdown.markdown(md, extensions=["tables"]))
    title = html_lib.escape(md.splitlines()[0].lstrip("# ") if md else "")
    page = folder / ".print.html"
    page.write_text(f'<!doctype html><html><head><meta charset="utf-8"><title>{title}</title>'
                    f"<style>{CSS}</style></head><body>{body}</body></html>", encoding="utf-8")
    profile = folder / ".print-profile"
    try:
        subprocess.run([exe, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--no-first-run",
                        "--disable-extensions", f"--user-data-dir={profile}", f"--print-to-pdf={pdf}",
                        page.resolve().as_uri()], capture_output=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return False
    finally:
        shutil.rmtree(profile, ignore_errors=True)
        page.unlink(missing_ok=True)
    return pdf.exists() and pdf.read_bytes()[:5] == b"%PDF-"


# ------------------------------------------------------------------ fetch
def from_xml(xml: Path, flavor: str, label: str, folder: Path, stem: str) -> tuple[bool, str]:
    """Markdown (+ figures) from a full-text XML. Returns (has body text, note)."""
    md, paras, missing = xml_to_markdown(xml, flavor, label, folder)
    if not paras:
        return False, f"{label}: no body text (no access?)"
    (folder / f"{stem}.md").write_text(md, encoding="utf-8")
    return True, f"{missing} figure(s) missing" if missing else ""


def elsevier_extras(xml: Path, folder: Path, stem: str) -> list[str]:
    """Accepted-manuscript PDF and supplementary files listed in Elsevier's XML."""
    got = []
    for ref, types in elsevier_objects(ET.parse(xml).getroot()).items():
        if "AAM-PDF" in types:
            url, dest = types["AAM-PDF"], folder / f"{stem}.accepted.pdf"
        elif ref.startswith("mmc") and types:
            url = next(iter(types.values()))
            dest = folder / "supplementary" / f"{ref}{Path(urllib.parse.urlparse(url).path).suffix}"
        else:
            continue
        if dest.exists() or download(url, dest, els_headers("*/*")):
            got.append("accepted-manuscript" if "AAM-PDF" in types else ref)
    return got


def fetch_one(doi: str, folder: Path) -> dict:
    """Best full text for one DOI into folder. Returns a report row."""
    folder.mkdir(parents=True, exist_ok=True)
    stem, d = safe_name(doi), doi.lower()
    pdf, xml = folder / f"{stem}.pdf", folder / f"{stem}.xml"
    notes, got = [], []
    if pdf.exists():
        return {"doi": doi, "got": "pdf (already there)", "note": ""}
    if d.startswith(ELSEVIER):
        st = elsevier_xml(doi, xml)
        if st == "ok":
            ok, note = from_xml(xml, "elsevier", "Elsevier", folder, stem)
            if ok:
                got += ["text+figures"] + elsevier_extras(xml, folder, stem)
            notes.append(note)
        else:
            notes.append(st)
    elif d.startswith(WILEY):
        st = wiley_pdf(doi, pdf)
        got += ["pdf"] if st == "ok" else []
        notes.append("" if st == "ok" else st)
    elif d.startswith(SPRINGER):
        st = springer_oa_xml(doi, xml)
        if st == "ok":
            ok, note = from_xml(xml, "jats", "springer", folder, stem)
            got += ["text+figures"] if ok else []
            notes.append(note)
        else:
            notes.append(st)
    if "pdf" not in got:  # open-access copy: a PDF for anyone, or text when we have none yet
        oa_xml = folder / f"{stem}.pmc.xml"
        st = open_access(doi, pdf, oa_xml)
        if st == "pdf":
            got.append("pdf")
        elif st == "xml" and "text+figures" not in got:
            ok, note = from_xml(oa_xml, "jats", "pmc", folder, stem)
            got += ["text+figures"] if ok else []
            notes.append(note)
        elif not got:
            notes.append(st)
    md = folder / f"{stem}.md"
    if "pdf" not in got and md.exists():
        if markdown_to_pdf(md.read_text(encoding="utf-8"), folder, folder / f"{stem}.rendered.pdf"):
            got.append("rendered-pdf")
    for raw in (xml, folder / f"{stem}.pmc.xml"):  # converted already; keep the folder tidy
        raw.unlink(missing_ok=True)
    if not any(folder.iterdir()):
        folder.rmdir()
    return {"doi": doi, "got": "+".join(got), "note": "; ".join(n for n in notes if n)}


def best_pdf(folder: Path, stem: str) -> Path | None:
    """The PDF to read: publisher/OA original, else accepted manuscript, else the printed one."""
    return next((p for s in (".pdf", ".accepted.pdf", ".rendered.pdf") if (p := folder / f"{stem}{s}").exists()), None)


def write_ris(run_dir: Path) -> Path:
    """library.ris for Zotero / EndNote / Mendeley: metadata, abstract and the best PDF (L1)."""
    rows = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    out = []
    for r in rows:
        if not r.get("doi"):
            continue
        stem = safe_name(r["doi"])
        folder = run_dir / "papers" / stem
        if not folder.exists():
            continue
        rec = ["TY  - JOUR", f"TI  - {r['title']}", f"AU  - {r['first_author']}", f"JO  - {r['journal']}",
               f"PY  - {r['year']}", f"DO  - {r['doi']}", f"UR  - https://doi.org/{r['doi']}"]
        if r.get("abstract"):
            rec.append(f"AB  - {r['abstract']}")
        if (pdf := best_pdf(folder, stem)):
            rec.append(f"L1  - {pdf.resolve()}")
        out.append("\n".join(rec + ["ER  - ", ""]))
    path = run_dir / "library.ris"
    path.write_text("\n".join(out), encoding="utf-8")
    return path


def cmd_fetch(args) -> int:
    if args.dois:
        run_dir = Path(args.out) if args.out else HOME / "runs" / f"{dt.datetime.now():%Y%m%d-%H%M}_dois"
        run_dir.mkdir(parents=True, exist_ok=True)
        rows = [row(d) for d in args.dois]
        add_abstracts(rows)
        (run_dir / "results.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    else:
        run_dir = Path(args.run_dir)
        rows = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    if args.only:
        picks = {int(x) for x in re.split(r"[,\s]+", args.only.strip()) if x}
        rows = [r for i, r in enumerate(rows, 1) if i in picks]
    rows = [r for r in rows if r.get("doi")]
    log(f"fetching {len(rows)} paper(s) into {run_dir / 'papers'}")
    report = []
    for r in rows:
        x = fetch_one(r["doi"], run_dir / "papers" / safe_name(r["doi"]))
        x["title"] = r.get("title", "")
        report.append(x)
        log(f"  {r['doi']}: {x['got'] or 'nothing'}" + (f"  ({x['note']})" if x["note"] else ""))
    with open(run_dir / "fetch_report.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["doi", "title", "got", "note"])
        w.writeheader()
        w.writerows(report)
    ris = write_ris(run_dir)
    ok = sum(bool(x["got"]) for x in report)
    log(f"\nfull text for {ok}/{len(report)}.  Report: {run_dir / 'fetch_report.csv'}\nImport into a reference manager: {ris}")
    no_pdf = [x for x in report if not re.search(r"(^|\+)pdf", x["got"])]
    if no_pdf:
        log("\nno publisher PDF yet (save one as papers/<doi_with_underscores>/<doi_with_underscores>.pdf, then `ris RUN_DIR`):")
        for x in no_pdf:
            log(f"  https://doi.org/{x['doi']}  [{'have text' if x['got'] else 'nothing'}]")
    return 0


def cmd_ris(args) -> int:
    log(f"written: {write_ris(Path(args.run_dir))}")
    return 0


# ------------------------------------------------------------------ check
def cmd_check(_args) -> int:
    for n, v in KEYS.items():
        log(f"{n:<20}: {'set' if v else '-'}")
    log(f"{'output folder':<20}: {HOME}")
    log(f"{'PDF printing':<20}: {find_browser() or 'no Chrome/Edge found (Markdown only)'}")
    log("")
    try:
        requests.get("https://api.openalex.org/works", params=oa_params(per_page=1), timeout=20).raise_for_status()
        log("OpenAlex search + open-access copies : OK")
    except requests.RequestException as e:
        log(f"OpenAlex                              : FAILED ({e})")
    if KEYS["ELSEVIER_API_KEY"]:
        r = requests.get("https://api.elsevier.com/content/search/scopus", headers=els_headers(), timeout=30,
                         params={"query": "TITLE(catalysis) AND OPENACCESS(0) AND PUBYEAR > 2019", "count": 1})
        if r.status_code != 200:
            log(f"Scopus search                         : FAILED (http {r.status_code}, check the key)")
        else:
            log("Scopus search                         : OK")
            doi = r.json()["search-results"]["entry"][0].get("prism:doi", "")
            full = requests.get("https://api.elsevier.com/content/search/scopus", headers=els_headers(), timeout=30,
                                params={"query": "TITLE(catalysis)", "count": 1, "view": "COMPLETE"}).status_code == 200
            log(f"Scopus abstracts in results           : {'OK' if full else 'no (needs institutional access)'}")
            ent = requests.get(f"https://api.elsevier.com/content/article/doi/{doi}", params={"view": "FULL"},
                               headers=els_headers("text/xml"), timeout=60)
            sub = ent.status_code == 200 and b"<ce:sections" in ent.content
            log(f"Elsevier subscription full text       : {'OK' if sub else 'no (connect to your institution network/VPN, or set ELSEVIER_INSTTOKEN)'}"
                f"   [tested {doi}]")
    else:
        log("Elsevier / Scopus                     : no key (search falls back to OpenAlex)")
    if KEYS["SPRINGER_OA_API_KEY"]:
        r = requests.get("https://api.springernature.com/openaccess/json",
                         params={"q": "keyword:catalysis", "p": 1, "api_key": KEYS["SPRINGER_OA_API_KEY"]}, timeout=30)
        log(f"Springer open access                  : {'OK' if r.status_code == 200 else f'FAILED (http {r.status_code})'}")
    log(f"Wiley TDM                             : {'token set (access is checked per paper)' if KEYS['WILEY_TDM_TOKEN'] else 'no token'}")
    return 0


# ------------------------------------------------------------------ main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="keys and access").set_defaults(fn=cmd_check)

    def listing(p):
        p.add_argument("-n", type=int, default=20)
        p.add_argument("--out", help="run folder (default: $LITFLOW_HOME/runs/<time>_<query>)")
        p.add_argument("--no-abstracts", action="store_true")
    p = sub.add_parser("search", help="search Scopus (with an Elsevier key) or OpenAlex")
    p.add_argument("query")
    listing(p)
    p.add_argument("--year-from", type=int)
    p.add_argument("--sort", choices=["relevance", "cited", "date"], default="relevance")
    p.add_argument("--source", choices=["auto", "scopus", "openalex"], default="auto")
    p.set_defaults(fn=cmd_search)
    p = sub.add_parser("related", help="similar, citing or referenced papers (OpenAlex)")
    p.add_argument("doi")
    listing(p)
    p.add_argument("--mode", choices=["similar", "citations", "references"], default="similar")
    p.set_defaults(fn=cmd_related)
    p = sub.add_parser("fetch", help="download full text")
    p.add_argument("run_dir", nargs="?")
    p.add_argument("--only", help="result numbers, e.g. 1,4,7")
    p.add_argument("--dois", nargs="+")
    p.add_argument("--out")
    p.set_defaults(fn=cmd_fetch)
    p = sub.add_parser("ris", help="rebuild library.ris for a run")
    p.add_argument("run_dir")
    p.set_defaults(fn=cmd_ris)
    args = ap.parse_args()
    if args.cmd == "fetch" and not (args.run_dir or args.dois):
        ap.error("fetch needs RUN_DIR or --dois")
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
