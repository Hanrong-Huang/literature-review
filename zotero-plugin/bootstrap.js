var PATH = "/claude/find-pdf";

function log(m) { Zotero.debug("[find-pdf-endpoint] " + m); }

async function collectItems(data) {
  let libraryID = Zotero.Libraries.userLibraryID;
  let out = new Map();
  for (let key of data.keys || []) {
    let it = Zotero.Items.getByLibraryAndKey(libraryID, key);
    if (it) out.set(it.id, it);
  }
  let conds = [];
  for (let t of data.tags || (data.tag ? [data.tag] : [])) conds.push(["tag", "is", t]);
  for (let d of data.dois || []) conds.push(["DOI", "is", d]);
  for (let c of conds) {
    let s = new Zotero.Search();
    s.libraryID = libraryID;
    s.addCondition(c[0], c[1], c[2]);
    let ids = await s.search();
    for (let it of await Zotero.Items.getAsync(ids)) out.set(it.id, it);
  }
  return [...out.values()].filter(i => i.isRegularItem());
}

async function hasFile(item) {
  for (let id of item.getAttachments()) {
    let a = Zotero.Items.get(id);
    if (a && a.isFileAttachment() && await a.fileExists()) return a.attachmentContentType || true;
  }
  return false;
}

async function findOne(item) {
  let A = Zotero.Attachments;
  if (A.addAvailableFile) return A.addAvailableFile(item);
  return A.addAvailablePDF(item);
}

function Endpoint() {}
Endpoint.prototype = {
  supportedMethods: ["GET", "POST"],
  supportedDataTypes: ["application/json"],
  permitBookmarklet: false,
  init: async function (req) {
    // Custom header forces a CORS preflight, so web pages cannot call this.
    let h = req.headers || {};
    let ok = typeof h.get === "function" ? h.get("X-Find-PDF") : (h["X-Find-PDF"] || h["x-find-pdf"]);
    if (!ok) return [403, "text/plain", "missing X-Find-PDF header"];
    if (req.method === "GET") return [200, "application/json", JSON.stringify({ ok: true, version: "1.0.0" })];
    let data = req.data || {};
    if (typeof data === "string") data = JSON.parse(data);
    let items = await collectItems(data);
    let results = [];
    for (let item of items) {
      let r = { key: item.key, doi: item.getField("DOI"), title: item.getField("title").slice(0, 80) };
      try {
        let had = await hasFile(item);
        if (had && !data.force) { r.status = "already_has_file"; r.type = had; }
        else {
          let att = await findOne(item);
          if (att) { r.status = "found"; r.attachment = att.key; r.type = att.attachmentContentType; }
          else r.status = "not_found";
        }
      } catch (e) { r.status = "error"; r.error = String(e); }
      results.push(r);
    }
    return [200, "application/json", JSON.stringify({ count: results.length, results })];
  }
};

function install() {}
function uninstall() {}
async function startup() {
  await Zotero.initializationPromise;
  Zotero.Server.Endpoints[PATH] = Endpoint;
  log("registered " + PATH);
}
function shutdown() { delete Zotero.Server.Endpoints[PATH]; }
