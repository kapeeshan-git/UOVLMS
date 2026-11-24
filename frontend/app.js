// University of Vavuniya LMS: single-file SPA. No framework, no build step.
// Every value from the server is escaped with esc() before it goes into HTML.

// ---------- utilities ---------------------------------------------------------------------------
const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1).toLowerCase().replace(/_/g, " ");
const TZ = "Asia/Colombo";
const dtFmt = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, weekday: "short", day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
const dFmt = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, weekday: "short", day: "2-digit", month: "short", year: "numeric" });
const fmtDT = (s) => (s ? dtFmt.format(new Date(s)) : "—");
const fmtD = (s) => (s ? dFmt.format(new Date(s.length === 10 ? s + "T00:00:00+05:30" : s)) : "—");
const money = (v) => (v == null ? "—" : `Rs ${Number(v).toFixed(2)}`);
const formData = (form) => Object.fromEntries(new FormData(form).entries());
const errMsg = (e) => e?.message || "Something went wrong.";

let me = null, demoClock = false, skewMs = 0;
const isStaff = () => me && (me.role === "LIBRARIAN" || me.role === "ADMIN");
const isAdmin = () => me && me.role === "ADMIN";

function uuid() {
  if (crypto.randomUUID) { try { return crypto.randomUUID(); } catch { /* insecure context */ } }
  const b = crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 15) | 64; b[8] = (b[8] & 63) | 128;
  const h = [...b].map((x) => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

function cookie(name) {
  const m = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
  return m ? decodeURIComponent(m[1]) : "";
}

async function api(method, path, body, { idem = false, form = false } = {}) {
  const headers = { Accept: "application/json" };
  if (method !== "GET") headers["X-CSRFToken"] = cookie("csrftoken");
  if (idem) headers["Idempotency-Key"] = uuid(); // fresh key per user action
  let payload;
  if (form) payload = body;
  else if (body !== undefined) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
  const r = await fetch("/api/v1" + path, { method, headers, body: payload, credentials: "same-origin" });
  const data = r.status === 204 ? null : await r.json().catch(() => null);
  if (!r.ok) {
    const e = new Error(data?.error?.message || `Request failed (${r.status})`);
    Object.assign(e, { status: r.status, code: data?.error?.code, fields: data?.error?.fields || {} });
    throw e;
  }
  return data;
}

function toast(msg) {
  const d = document.createElement("div");
  d.textContent = msg;
  $("#toast").appendChild(d);
  setTimeout(() => d.remove(), 4000);
}

const PILL = { AVAILABLE: "ok", ACTIVE: "ok", SENT: "ok", SETTLED: "ok", DONE: "ok", APPLIED: "ok", VALIDATED: "ok", CLEARED: "ok",
  ON_LOAN: "warn", OPEN: "warn", PENDING: "warn", QUEUED: "warn", RUNNING: "warn", SUSPENDED: "warn", IN_REPAIR: "warn",
  LOST: "err", FAILED: "err", WITHDRAWN: "err", INACTIVE: "err", OVERDUE: "err", "NOT CLEARED": "err" };
const pill = (s) => `<span class="pill ${PILL[s] || ""}">${esc(cap(String(s)))}</span>`;

function table(headers, rows, empty = "Nothing to show.") {
  if (!rows.length) return `<p class="muted">${esc(empty)}</p>`;
  return `<div class="table-wrap"><table><thead><tr>${headers.map((h) => `<th scope="col">${esc(h)}</th>`).join("")}</tr></thead>
    <tbody>${rows.map((r) => `<tr>${r.map((c) => `<td>${c ?? ""}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}

function pager(data, href) {
  const pages = Math.max(1, Math.ceil(data.total / data.page_size));
  if (pages <= 1) return `<p class="small muted right">${data.total} result(s)</p>`;
  return `<div class="pager small"><span class="muted">${data.total} result(s), page ${data.page} of ${pages}</span>
    ${data.page > 1 ? `<a href="${href(data.page - 1)}">‹ Prev</a>` : ""} ${data.page < pages ? `<a href="${href(data.page + 1)}">Next ›</a>` : ""}</div>`;
}

const options = (list, selected, blank) =>
  (blank !== undefined ? `<option value="">${esc(blank)}</option>` : "") +
  list.map(([v, t]) => `<option value="${esc(v)}" ${String(v) === String(selected ?? "") ? "selected" : ""}>${esc(t)}</option>`).join("");

const CATEGORIES = ["STUDENT", "ACADEMIC_PERMANENT", "ACADEMIC_TEMPORARY", "NON_ACADEMIC"];
const field = (label, html, cls = "field") => `<div class="${cls}"><label>${esc(label)}${html}</label></div>`;
const input = (name, value = "", attrs = "") => `<input name="${name}" value="${esc(value)}" ${attrs}>`;

// ---------- auth pages ----------------------------------------------------------------------
async function pageLogin(v) {
  v.innerHTML = `<div class="card login"><h1>Library login</h1>
    <form id="f">${field("Username", input("username", "", 'autocomplete="username" required id="u"'))}
    <div style="height:10px"></div>${field("Password", input("password", "", 'type="password" autocomplete="current-password" required'))}
    <div id="msg" class="banner err" role="alert"></div>
    <div class="row" style="margin-top:12px"><button>Log in</button><a href="#/forgot">Forgot password?</a></div></form>
    <p class="small muted">Demo users: admin, librarian1, librarian2, student1, student3, lecturer1, staff1, grad1.</p></div>`;
  $("#u").focus();
  $("#f").onsubmit = async (ev) => {
    ev.preventDefault();
    try { await api("POST", "/auth/login", formData(ev.target)); await loadMe(); location.hash = "#/" + home(); }
    catch (e) { $("#msg").textContent = errMsg(e); }
  };
}

async function pageForgot(v) {
  v.innerHTML = `<div class="card login"><h1>Reset password</h1><form id="f">
    ${field("Your email", input("email", "", 'type="email" required id="e"'))}
    <div id="msg" class="banner info"></div><div class="row" style="margin-top:12px"><button>Send reset link</button><a href="#/login">Back to login</a></div></form></div>`;
  $("#e").focus();
  $("#f").onsubmit = async (ev) => {
    ev.preventDefault();
    try { $("#msg").textContent = (await api("POST", "/auth/password-reset", formData(ev.target))).message; }
    catch (e) { $("#msg").textContent = errMsg(e); }
  };
}

async function pageReset(v, _a, params) {
  v.innerHTML = `<div class="card login"><h1>Choose a new password</h1><form id="f">
    ${field("New password (min 8 characters)", input("new_password", "", 'type="password" minlength="8" required autocomplete="new-password"'))}
    <div id="msg" class="banner info"></div><div class="row" style="margin-top:12px"><button>Save password</button></div></form></div>`;
  $("#f").onsubmit = async (ev) => {
    ev.preventDefault();
    try {
      await api("POST", "/auth/password-reset/confirm", { uid: params.get("uid"), token: params.get("token"), ...formData(ev.target) });
      $("#msg").innerHTML = 'Password changed. <a href="#/login">Log in</a>.';
    } catch (e) { $("#msg").textContent = errMsg(e); }
  };
}

// ---------- catalog / search ----------------------------------------------------------------
async function searchUI(v, params, base, title) {
  const q = params.get("q") || "", cat = params.get("category") || "", avail = params.get("available") === "1", page = +params.get("page") || 1;
  const cats = await api("GET", "/categories");
  const link = (p) => `#/${base}?` + new URLSearchParams({ q, category: cat, available: avail ? "1" : "", page: p });
  const box = document.createElement("div");
  box.innerHTML = `<h1>${esc(title)}</h1><form id="sf" class="card row" role="search">
    ${field("Title, author, ISBN, call number or accession no.", input("q", q, 'id="q" autocomplete="off"'), "field wide")}
    ${field("Category", `<select name="category">${options(cats.results.map((c) => [c.id, c.name]), cat, "All")}</select>`)}
    <label class="row" style="align-items:center"><input type="checkbox" name="available" value="1" ${avail ? "checked" : ""}> Available now</label>
    <button>Search</button></form><div id="res"><p class="muted">Searching…</p></div>`;
  v.appendChild(box);
  $("#sf").onsubmit = (ev) => {
    ev.preventDefault();
    const d = formData(ev.target);
    const next = `#/${base}?` + new URLSearchParams({ q: d.q || "", category: d.category || "", available: d.available ? "1" : "" });
    if (location.hash === next) route(); else location.hash = next;
  };
  $("#q").focus();
  const data = await api("GET", "/books?" + new URLSearchParams({ q, category: cat, available: avail ? "1" : "", page }));
  $("#res").innerHTML = table(["Title", "Authors", "Call no.", "Category", "Available"], data.results.map((b) => [
    `<a href="#/book/${b.id}">${esc(b.title)}</a>${b.title_alt ? `<div class="small muted">${esc(b.title_alt)}</div>` : ""}`,
    esc(b.authors.join(", ")), esc(b.call_number), esc(b.category?.name || ""),
    b.available_count > 0 ? pill("AVAILABLE") + ` ${b.available_count} of ${b.copy_count}` : `<span class="muted">0 of ${b.copy_count}</span>`,
  ]), "No books match your search.") + pager(data, link);
}

const pageSearch = (v, _a, params) => searchUI(v, params, "search", "Search the catalog");

async function pageCatalog(v, _a, params) {
  const cats = await api("GET", "/categories");
  const add = document.createElement("details");
  add.className = "card";
  add.innerHTML = `<summary><b>Add a book</b></summary><form id="bookf" class="grid" style="margin-top:12px">
    ${field("Title *", input("title", "", "required maxlength=500"))}${field("Alternative title (Sinhala/Tamil)", input("title_alt"))}
    ${field("Authors (separate with ;)", input("authors"))}${field("ISBN", input("isbn"))}${field("Call number", input("call_number"))}
    ${field("Publisher", input("publisher"))}${field("Year", input("year", "", 'type="number" min="1000" max="2100"'))}
    ${field("Category", `<select name="category_id">${options(cats.results.map((c) => [c.id, c.name]), "", "—")}</select>`)}
    <div class="row"><button>Create book</button></div></form>`;
  v.appendChild(add);
  $("#bookf").onsubmit = async (ev) => {
    ev.preventDefault();
    try { const b = await api("POST", "/books", formData(ev.target)); toast("Book created. Add copies next."); location.hash = `#/book/${b.id}`; }
    catch (e) { toast(errMsg(e)); }
  };
  await searchUI(v, params, "catalog", "Catalog");
}

const MANUAL = { AVAILABLE: ["IN_REPAIR", "WITHDRAWN"], IN_REPAIR: ["AVAILABLE", "WITHDRAWN"], LOST: ["AVAILABLE"] };

async function pageBook(v, { id }) {
  const b = await api("GET", `/books/${id}`);
  const staff = isStaff();
  const colls = staff ? (await api("GET", "/collections")).results : [];
  v.innerHTML = `<p><a href="javascript:history.back()">← Back</a></p>
    <div class="card"><h1>${esc(b.title)}</h1>${b.title_alt ? `<p class="muted">${esc(b.title_alt)}</p>` : ""}
    <div class="grid small"><div><b>Authors</b><br>${esc(b.authors.join(", ") || "—")}</div><div><b>ISBN</b><br>${esc(b.isbn || "—")}</div>
    <div><b>Call number</b><br>${esc(b.call_number || "—")}</div><div><b>Category</b><br>${esc(b.category?.name || "—")}</div>
    <div><b>Publisher / year</b><br>${esc(b.publisher || "—")} ${esc(b.year || "")}</div>
    <div><b>Availability</b><br>${b.available_count} of ${b.copy_count} copies available</div></div></div>
    <h2>Copies</h2>${table(staff ? ["Accession no.", "Collection", "Shelf", "Status", "Change status"] : ["Accession no.", "Collection", "Shelf", "Status"],
      b.copies.map((c) => {
        const row = [`<code>${esc(c.accession_number)}</code>`, esc(c.collection.name) + (c.borrowable ? "" : ' <span class="pill">In-library use only</span>'),
          esc(c.shelf_location), pill(c.status)];
        if (staff) {
          const opts = MANUAL[c.status] || [];
          row.push(opts.length ? `<div class="row"><select aria-label="New status for ${esc(c.accession_number)}" data-sel="${c.id}">${options(opts.map((s) => [s, cap(s)]))}</select>
            <button class="small secondary" data-copy="${c.id}">Apply</button></div>` : '<span class="muted small">Via circulation</span>');
        }
        return row;
      }), "No copies yet.")}
    ${staff ? `<div class="card" style="margin-top:16px"><h2>Add a copy</h2><form id="cf" class="row">
      ${field("Accession no. *", input("accession_number", "", "required maxlength=50"))}
      ${field("Collection *", `<select name="collection_id" required>${options(colls.map((c) => [c.id, `${c.name}${c.borrowable ? "" : " (in-library)"}`]))}</select>`)}
      ${field("Shelf location", input("shelf_location"))}<button>Add copy</button></form></div>` : ""}`;
  if (!staff) return;
  v.onclick = async (ev) => {
    const btn = ev.target.closest("button[data-copy]");
    if (!btn) return;
    const status = $(`select[data-sel="${btn.dataset.copy}"]`).value;
    const reason = status === "WITHDRAWN" ? prompt("Reason for withdrawal?") || "" : "";
    try { await api("POST", `/copies/${btn.dataset.copy}/status`, { status, reason }); toast("Status updated."); route(); }
    catch (e) { toast(errMsg(e)); }
  };
  $("#cf").onsubmit = async (ev) => {
    ev.preventDefault();
    try { await api("POST", "/copies", { book_id: +id, ...formData(ev.target) }); toast("Copy added."); route(); }
    catch (e) { toast(errMsg(e)); }
  };
}

// ---------- member portal -------------------------------------------------------------------
async function pageMy(v) {
  const [loans, fines] = await Promise.all([api("GET", "/loans/mine?page_size=100"), api("GET", "/fines/mine?page_size=100")]);
  const active = loans.results.filter((l) => l.status === "ACTIVE");
  const past = loans.results.filter((l) => l.status !== "ACTIVE");
  v.innerHTML = `<h1>My loans and fines</h1>
    <div class="card"><h2>On loan (${active.length})</h2>${table(["Title", "Accession", "Due", "Renewals", "Status", ""], active.map((l) => [
      esc(l.title), `<code>${esc(l.copy.accession_number)}</code>`, fmtDT(l.due_at), l.renewal_count,
      l.overdue ? pill("OVERDUE") : pill("ACTIVE"),
      l.overdue ? '<span class="small muted">Please return</span>' : `<button class="small" data-renew="${l.id}">Renew</button>`,
    ]), "You have no books on loan.")}</div>
    <div class="card"><h2>Fines: balance ${money(fines.balance)}</h2>${table(["Title", "Days late", "Amount", "Balance", "Status"], fines.results.map((f) => [
      esc(f.title), f.days_late, money(f.calculated_amount), money(f.balance), pill(f.status)]), "No fines.")}
      <p class="small muted">Pay fines at the circulation desk.</p></div>
    <div class="card"><h2>History</h2>${table(["Title", "Issued", "Returned", "Status"], past.map((l) => [
      esc(l.title), fmtD(l.issued_at), fmtD(l.returned_at), pill(l.status)]), "No past loans.")}</div>`;
  v.onclick = async (ev) => {
    const btn = ev.target.closest("button[data-renew]");
    if (!btn) return;
    btn.disabled = true;
    try { const l = await api("POST", `/loans/${btn.dataset.renew}/renew`, {}, { idem: true }); toast(`Renewed. New due date: ${fmtDT(l.due_at)}`); route(); }
    catch (e) { toast(errMsg(e)); btn.disabled = false; }
  };
}

// ---------- circulation desk (scanner-first) --------------------------------------------------
async function pageDesk(v) {
  let mode = "issue", patron = null;
  const log = [];
  v.innerHTML = `<h1>Circulation desk</h1>
    <div class="tabs" role="group" aria-label="Desk mode">${["issue", "return", "renew"].map((m) =>
      `<button type="button" data-mode="${m}" aria-pressed="${m === mode}">${cap(m)}</button>`).join("")}</div>
    <div class="card scan">
      <form id="pf"><label for="pc">Patron: scan card or type registration no. / username, then Enter</label><input id="pc" autocomplete="off"></form>
      <div id="pbox"></div>
      <form id="bf" style="margin-top:14px"><label for="bc" id="bcl">Book: scan accession no., then Enter</label><input id="bc" autocomplete="off"></form>
      <div id="result" class="banner" role="status" aria-live="assertive"></div>
    </div>
    <div class="card"><h2>Current loans</h2><div id="loans"><p class="muted">Scan a patron to see their loans.</p></div></div>
    <div class="card"><h2>Session log</h2><div id="log" class="log muted">No actions yet. Undo is not allowed; use Return.</div></div>`;

  const result = (ok, msg) => { const r = $("#result"); r.className = "banner " + (ok ? "ok" : "err"); r.textContent = (ok ? "OK: " : "Not done: ") + msg; };
  const addLog = (msg) => {
    log.unshift(`${new Date().toLocaleTimeString("en-GB", { timeZone: TZ })}  ${msg}`);
    $("#log").innerHTML = log.slice(0, 10).map(esc).join("<br>");
  };
  const focusBook = () => { $("#bc").value = ""; $("#bc").focus(); };

  function setMode(m) {
    mode = m;
    v.querySelectorAll("[data-mode]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.mode === m)));
    $("#pf").hidden = m !== "issue";
    $("#pbox").hidden = m !== "issue";
    $("#result").className = "banner"; $("#result").textContent = "";
    if (m === "issue" && !patron) $("#pc").focus(); else focusBook();
  }

  function renderPatron() {
    if (!patron) return;
    const p = patron.patron;
    $("#pbox").innerHTML = `<div class="patron-box"><b>${esc(p.full_name)}</b> <code>${esc(p.reg_number || p.username)}</code> ${pill(p.status)}<br>
      <span class="small">${esc(cap(p.patron_category || "no category"))}${p.academic_year ? `, year ${p.academic_year}` : ""} ·
      ${p.active_loans} active loan(s) · Fines ${money(p.fine_balance)} · <a href="#/patron/${p.id}">Patron page</a></span></div>`;
    $("#loans").innerHTML = table(["Accession", "Title", "Section", "Due", "Status", "Actions"], patron.loans.map((l) => [
      `<code>${esc(l.copy.accession_number)}</code>`, esc(l.title), esc(l.section), fmtDT(l.due_at),
      l.overdue ? pill("OVERDUE") : pill("ACTIVE"),
      `<button class="small secondary" data-renew="${l.id}" data-overdue="${l.overdue}">Renew</button>
       <button class="small secondary" data-lost="${l.id}">Lost</button>`,
    ]), "No active loans.");
  }

  async function lookup(code) {
    try { patron = await api("GET", "/patrons/lookup?code=" + encodeURIComponent(code)); renderPatron(); focusBook(); }
    catch (e) { patron = null; $("#pbox").innerHTML = ""; $("#loans").innerHTML = ""; result(false, errMsg(e)); $("#pc").select(); }
  }
  const refreshPatron = async () => { if (patron) await lookup(patron.patron.reg_number || patron.patron.username); };

  async function renew(loanId, overdue) {
    const body = {};
    if (overdue) {
      const reason = prompt("This loan is overdue. Staff override reason (leave empty to cancel):");
      if (!reason) return;
      body.reason = reason;
    }
    const l = await api("POST", `/loans/${loanId}/renew`, body, { idem: true });
    result(true, `Renewed '${l.title}'. New due date ${fmtDT(l.due_at)}.`);
    addLog(`RENEW  ${l.copy.accession_number}  ${l.title}`);
    await refreshPatron();
  }

  async function onBook(acc) {
    if (!acc) return;
    try {
      if (mode === "issue") {
        if (!patron) { result(false, "Scan a patron first."); $("#pc").focus(); return; }
        const l = await api("POST", "/loans", { patron_id: patron.patron.id, accession_number: acc }, { idem: true });
        result(true, `Issued '${l.title}'. Due ${fmtDT(l.due_at)}.`);
        addLog(`ISSUE  ${acc}  → ${patron.patron.full_name}`);
        await refreshPatron();
      } else if (mode === "return") {
        const r = await api("POST", "/loans/return", { accession_number: acc }, { idem: true });
        result(true, `Returned '${r.loan.title}' (${r.loan.patron.full_name}).` +
          (r.fine ? ` Late by ${r.fine.days_late} open day(s): fine ${money(r.fine.calculated_amount)} due.` : " On time."));
        addLog(`RETURN ${acc}${r.fine ? `  fine ${money(r.fine.calculated_amount)}` : ""}`);
        if (patron && patron.patron.id === r.loan.patron.id) await refreshPatron();
      } else {
        const found = await api("GET", "/loans?" + new URLSearchParams({ accession: acc, status: "ACTIVE" }));
        if (!found.results.length) { result(false, `Copy ${acc} is not on loan.`); return; }
        await renew(found.results[0].id, found.results[0].overdue);
      }
    } catch (e) { result(false, errMsg(e)); }
    finally { focusBook(); }
  }

  v.querySelectorAll("[data-mode]").forEach((b) => (b.onclick = () => setMode(b.dataset.mode)));
  $("#pf").onsubmit = (ev) => { ev.preventDefault(); const c = $("#pc").value.trim(); if (c) lookup(c); };
  $("#bf").onsubmit = (ev) => { ev.preventDefault(); onBook($("#bc").value.trim()); };
  $("#loans").onclick = async (ev) => {
    const rb = ev.target.closest("button[data-renew]"), lb = ev.target.closest("button[data-lost]");
    try {
      if (rb) await renew(rb.dataset.renew, rb.dataset.overdue === "true");
      if (lb) {
        const reason = prompt("Declare this copy lost? Enter a reason:");
        if (!reason) return;
        await api("POST", `/loans/${lb.dataset.lost}/lost`, { reason });
        result(true, "Loan marked lost."); addLog(`LOST   loan #${lb.dataset.lost}`); await refreshPatron();
      }
    } catch (e) { result(false, errMsg(e)); }
    focusBook();
  };
  setMode("issue");
}

// ---------- patrons ----------------------------------------------------------------------------
async function patronForm(p, depts) {
  return `${field("Full name *", input("full_name", p.full_name, "required"))}${field("Email", input("email", p.email, 'type="email"'))}
    ${field("Registration no.", input("reg_number", p.reg_number))}
    ${field("Patron category", `<select name="patron_category">${options(CATEGORIES.map((c) => [c, cap(c)]), p.patron_category, "— (not a borrower)")}</select>`)}
    ${field("Intake year (students)", input("intake_year", p.intake_year, 'type="number" min="1990" max="2100"'))}
    ${field("Department", `<select name="department_id">${options(depts.map((d) => [d.id, d.name]), p.department_id, "—")}</select>`)}
    ${isAdmin() ? field("Role", `<select name="role">${options(["MEMBER", "LIBRARIAN", "ADMIN"].map((r) => [r, cap(r)]), p.role || "MEMBER")}</select>`) : ""}`;
}

async function pagePatrons(v, _a, params) {
  const q = params.get("q") || "", page = +params.get("page") || 1;
  const [data, depts] = await Promise.all([api("GET", "/patrons?" + new URLSearchParams({ q, page })), api("GET", "/departments")]);
  v.innerHTML = `<h1>Patrons</h1><form id="sf" class="card row" role="search">${field("Name, username or registration no.", input("q", q, 'id="q"'), "field wide")}<button>Search</button></form>
    <details class="card"><summary><b>New patron</b></summary><form id="nf" class="grid" style="margin-top:12px">
      ${field("Username *", input("username", "", "required"))}${await patronForm({}, depts.results)}
      ${field("Initial password (optional)", input("password", "", 'type="password" minlength="8" autocomplete="new-password"'))}
      <div class="row"><button>Create patron</button></div></form></details>
    ${table(["Name", "Username", "Reg. no.", "Role", "Category", "Status"], data.results.map((p) => [
      `<a href="#/patron/${p.id}">${esc(p.full_name)}</a>`, esc(p.username), esc(p.reg_number || ""), esc(cap(p.role)),
      esc(p.patron_category ? cap(p.patron_category) : "—") + (p.academic_year ? ` (year ${p.academic_year})` : ""), pill(p.status)]), "No patrons found.")}
    ${pager(data, (p) => "#/patrons?" + new URLSearchParams({ q, page: p }))}`;
  $("#sf").onsubmit = (ev) => { ev.preventDefault(); location.hash = "#/patrons?" + new URLSearchParams({ q: formData(ev.target).q }); };
  $("#nf").onsubmit = async (ev) => {
    ev.preventDefault();
    try { const p = await api("POST", "/patrons", formData(ev.target)); toast("Patron created."); location.hash = `#/patron/${p.id}`; }
    catch (e) { toast(errMsg(e)); }
  };
}

async function pagePatron(v, { id }) {
  const [p, loans, clearance, fines, depts] = await Promise.all([
    api("GET", `/patrons/${id}`), api("GET", `/patrons/${id}/loans?page_size=50`), api("GET", `/patrons/${id}/clearance`),
    api("GET", `/fines?patron=${id}&page_size=50`), api("GET", "/departments")]);
  v.innerHTML = `<p><a href="#/patrons">← Patrons</a></p>
    <div class="card"><h1>${esc(p.full_name)} ${pill(p.status)}</h1>
      <div class="grid small"><div><b>Username</b><br>${esc(p.username)}</div><div><b>Reg. no.</b><br>${esc(p.reg_number || "—")}</div>
      <div><b>Category</b><br>${esc(p.patron_category ? cap(p.patron_category) : "—")}${p.academic_year ? `, year ${p.academic_year}` : ""}</div>
      <div><b>Department</b><br>${esc(p.department || "—")}</div><div><b>Active loans</b><br>${p.active_loans}</div><div><b>Fine balance</b><br>${money(p.fine_balance)}</div></div></div>
    <div class="card"><h2>Graduation clearance: ${pill(clearance.cleared ? "CLEARED" : "NOT CLEARED")}</h2>
      ${clearance.cleared ? '<p class="muted">No outstanding loans or fines.</p>' : `<ul>${clearance.outstanding_loans.map((l) => `<li>Loan: ${esc(l.title)} (${esc(l.accession)}) ${pill(l.status)}</li>`).join("")}
      ${clearance.open_fines.map((f) => `<li>Open fine #${f.id}: ${money(f.balance)}</li>`).join("")}</ul>`}
      <form id="stf" class="row">${field("Change status", `<select name="status">${options(["ACTIVE", "SUSPENDED", "GRADUATED", "INACTIVE"].map((s) => [s, cap(s)]), p.status)}</select>`)}
      ${field("Reason", input("reason"), "field wide")}<button class="secondary">Update status</button></form></div>
    <details class="card"><summary><b>Edit details</b></summary><form id="ef" class="grid" style="margin-top:12px">${await patronForm(p, depts.results)}
      <div class="row"><button>Save</button></div></form></details>
    <div class="card"><h2>Fines</h2>${table(["Title", "Days late", "Amount", "Balance", "Status"], fines.results.map((f) => [
      esc(f.title), f.days_late, money(f.calculated_amount), money(f.balance), pill(f.status)]), "No fines.")}
      <p class="small"><a href="#/fines?patron=${p.id}">Record a payment or waiver</a></p></div>
    <div class="card"><h2>Loan history</h2>${table(["Title", "Accession", "Issued", "Due", "Returned", "Status"], loans.results.map((l) => [
      esc(l.title), `<code>${esc(l.copy.accession_number)}</code>`, fmtD(l.issued_at), fmtDT(l.due_at), fmtD(l.returned_at),
      l.overdue ? pill("OVERDUE") : pill(l.status)]), "No loans.")}</div>`;
  $("#stf").onsubmit = async (ev) => {
    ev.preventDefault();
    try { await api("POST", `/patrons/${id}/status`, formData(ev.target)); toast("Status updated."); route(); } catch (e) { toast(errMsg(e)); }
  };
  $("#ef").onsubmit = async (ev) => {
    ev.preventDefault();
    try { await api("PATCH", `/patrons/${id}`, formData(ev.target)); toast("Saved."); route(); } catch (e) { toast(errMsg(e)); }
  };
}

// ---------- fines ------------------------------------------------------------------------------
async function pageFines(v, _a, params) {
  const status = params.has("status") ? params.get("status") : "OPEN", q = params.get("q") || "", patron = params.get("patron") || "", page = +params.get("page") || 1;
  const data = await api("GET", "/fines?" + new URLSearchParams({ status, q, patron, page }));
  v.innerHTML = `<h1>Fines</h1><form id="sf" class="card row">${field("Patron", input("q", q), "field wide")}
    ${field("Status", `<select name="status">${options([["OPEN", "Open"], ["SETTLED", "Settled"]], status, "All")}</select>`)}<button>Filter</button></form>
    ${table(["Patron", "Title", "Days", "Rate", "Amount", "Balance", "Status", ""], data.results.map((f) => [
      `<a href="#/patron/${f.patron.id}">${esc(f.patron.full_name)}</a><div class="small muted">${esc(f.patron.reg_number || f.patron.username)}</div>`,
      esc(f.title), f.days_late, money(f.rate_applied), money(f.calculated_amount), money(f.balance), pill(f.status),
      `<button class="small secondary" data-fine="${f.id}">Open</button>`]), "No fines.")}
    ${pager(data, (p) => "#/fines?" + new URLSearchParams({ status, q, patron, page: p }))}<div id="detail"></div>`;
  $("#sf").onsubmit = (ev) => { ev.preventDefault(); const d = formData(ev.target); location.hash = "#/fines?" + new URLSearchParams({ q: d.q, status: d.status }); };
  v.onclick = (ev) => { const b = ev.target.closest("button[data-fine]"); if (b) showFine(b.dataset.fine); };

  async function showFine(fid) {
    const f = await api("GET", `/fines/${fid}/transactions`);
    $("#detail").innerHTML = `<div class="card"><h2>Fine #${f.id}: ${esc(f.patron.full_name)}, '${esc(f.title)}'</h2>
      <p>${f.days_late} day(s) × ${money(f.rate_applied)} = ${money(f.calculated_amount)}. Balance <b>${money(f.balance)}</b> ${pill(f.status)}</p>
      ${table(["When", "Type", "Amount", "By", "Reason", "Receipt"], f.transactions.map((t) => [fmtDT(t.created_at), esc(t.type), money(t.amount),
        esc(t.actor), esc(t.reason), esc(t.receipt_ref)]), "No transactions yet.")}
      <form id="tf" class="row" style="margin-top:12px">
        ${field("Type", `<select name="type">${options([["PAYMENT", "Payment"], ["WAIVER", "Waiver"], ...(isAdmin() ? [["ADJUSTMENT", "Adjustment (±)"]] : [])])}</select>`)}
        ${field("Amount (Rs)", input("amount", f.balance, 'type="number" step="0.01" required'))}
        ${field("Reason (required for waiver/adjustment)", input("reason"), "field wide")}${field("Receipt no.", input("receipt_ref"))}
        <button>Record</button></form><p class="small muted">The ledger is append-only. Mistakes are corrected with an adjustment.</p></div>`;
    $("#tf").onsubmit = async (ev) => {
      ev.preventDefault();
      try { await api("POST", `/fines/${fid}/transactions`, formData(ev.target), { idem: true }); toast("Recorded."); await route(); showFine(fid); }
      catch (e) { toast(errMsg(e)); }
    };
    $("#detail").scrollIntoView({ behavior: "smooth" });
  }
}

// ---------- admin ------------------------------------------------------------------------------
const RULE_FIELDS = [["loan_period_days", "Days"], ["max_loans", "Max loans"], ["max_renewals", "Renewals"],
  ["reminder_hours_before", "Reminder h"], ["final_reminder_hours_before", "Final h"]];

async function pageRules(v) {
  const [rules, sections] = await Promise.all([api("GET", "/admin/rules"), api("GET", "/admin/sections")]);
  const secCodes = sections.results.map((s) => s.code);
  const ruleRow = (r) => `<tr>
    <td><select data-f="patron_category">${options(CATEGORIES.map((c) => [c, cap(c)]), r.patron_category)}</select></td>
    <td><input data-f="academic_year" type="number" min="1" max="10" value="${esc(r.academic_year ?? "")}" placeholder="any" style="width:70px"></td>
    <td><select data-f="section_code">${options(secCodes.map((c) => [c, c]), r.section_code)}</select></td>
    <td><input data-f="is_allowed" type="checkbox" ${r.is_allowed ? "checked" : ""} aria-label="Allowed"></td>
    ${RULE_FIELDS.map(([f]) => `<td><input data-f="${f}" type="number" min="0" value="${esc(r[f] ?? 0)}" style="width:75px"></td>`).join("")}
    <td><button type="button" class="small danger" data-del>Remove</button></td></tr>`;
  v.innerHTML = `<h1>Circulation rules</h1>
    <div class="card"><p class="small muted">Year applies to students only (computed from intake year). Leave it empty for other categories.</p>
    <div class="table-wrap"><table id="rt"><thead><tr><th>Category</th><th>Year</th><th>Section</th><th>Allowed</th>${RULE_FIELDS.map(([, t]) => `<th>${t}</th>`).join("")}<th></th></tr></thead>
    <tbody>${rules.results.map(ruleRow).join("")}</tbody></table></div>
    <div class="row" style="margin-top:10px"><button type="button" class="secondary" id="addr">Add rule</button><button type="button" id="saver">Save rules</button></div></div>
    <h1>Sections</h1><div class="card"><div class="table-wrap"><table id="st"><thead><tr><th>Code</th><th>Name</th><th>Issue from</th><th>Issue to</th><th>Return from</th><th>Return to (due time)</th><th>Fine / day</th></tr></thead>
    <tbody>${sections.results.map((s) => `<tr data-code="${esc(s.code)}"><td><b>${esc(s.code)}</b></td><td><input data-f="name" value="${esc(s.name)}"></td>
      ${["issue_start", "issue_end", "return_start", "return_end"].map((f) => `<td><input data-f="${f}" type="time" value="${esc(s[f])}"></td>`).join("")}
      <td><input data-f="fine_per_day" type="number" step="0.01" min="0" value="${esc(s.fine_per_day)}" style="width:90px"></td></tr>`).join("")}</tbody></table></div>
    <div class="row" style="margin-top:10px"><button type="button" id="saves">Save sections</button></div></div>`;
  const tbody = $("#rt tbody");
  $("#addr").onclick = () => tbody.insertAdjacentHTML("beforeend", ruleRow({ patron_category: "STUDENT", section_code: secCodes[0], is_allowed: true, loan_period_days: 7, max_loans: 2, max_renewals: 0, reminder_hours_before: 24, final_reminder_hours_before: 3 }));
  tbody.onclick = (ev) => { if (ev.target.closest("[data-del]")) ev.target.closest("tr").remove(); };
  const rowData = (tr) => Object.fromEntries([...tr.querySelectorAll("[data-f]")].map((el) => [el.dataset.f, el.type === "checkbox" ? el.checked : el.value]));
  $("#saver").onclick = async () => {
    try { await api("PUT", "/admin/rules", { rules: [...tbody.rows].map(rowData) }); toast("Rules saved."); route(); } catch (e) { toast(errMsg(e)); }
  };
  $("#saves").onclick = async () => {
    try { await api("PUT", "/admin/sections", { sections: [...$("#st tbody").rows].map((tr) => ({ code: tr.dataset.code, ...rowData(tr) })) }); toast("Sections saved."); route(); }
    catch (e) { toast(errMsg(e)); }
  };
}

async function pageCalendar(v) {
  const data = await api("GET", "/admin/closed-days");
  const days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
  v.innerHTML = `<h1>Library calendar</h1><div class="card"><p>Weekly closure: <b>${data.weekly_closed.map((d) => days[d]).join(", ") || "none"}</b>
    <span class="small muted">(set in settings)</span>. Due dates roll forward past closed days, and closed days do not count towards fines.</p>
    <form id="cf" class="row">${field("Date", input("day", "", 'type="date" required'))}${field("Reason", input("reason", "", "required"), "field wide")}<button>Add closed day</button></form></div>
    ${table(["Date", "Reason", ""], data.results.map((d) => [fmtD(d.day), esc(d.reason), `<button class="small danger" data-day="${esc(d.day)}">Delete</button>`]), "No closed days.")}`;
  $("#cf").onsubmit = async (ev) => {
    ev.preventDefault();
    try { await api("POST", "/admin/closed-days", formData(ev.target)); toast("Added."); route(); } catch (e) { toast(errMsg(e)); }
  };
  v.onclick = async (ev) => {
    const b = ev.target.closest("button[data-day]");
    if (!b || !confirm(`Remove closed day ${b.dataset.day}?`)) return;
    try { await api("DELETE", `/admin/closed-days/${b.dataset.day}`); toast("Removed."); route(); } catch (e) { toast(errMsg(e)); }
  };
}

async function pageAudit(v, _a, params) {
  const f = { action: params.get("action") || "", resource_type: params.get("resource_type") || "", actor: params.get("actor") || "", page: +params.get("page") || 1 };
  const data = await api("GET", "/admin/audit?" + new URLSearchParams(f));
  v.innerHTML = `<h1>Audit log</h1><form id="af" class="card row">${field("Action starts with", input("action", f.action, 'placeholder="loan."'))}
    ${field("Resource type", input("resource_type", f.resource_type, 'placeholder="loan"'))}${field("Actor username", input("actor", f.actor))}<button>Filter</button></form>
    ${table(["When", "Actor", "Action", "Resource", "Reason", "Details", "Request"], data.results.map((e) => [
      fmtDT(e.timestamp), esc(e.actor || "system"), `<code>${esc(e.action)}</code>`, esc(e.resource_type) + (e.resource_id ? ` #${e.resource_id}` : ""),
      esc(e.reason), `<span class="small">${esc(JSON.stringify(e.metadata))}</span>`, `<span class="small muted">${esc(e.request_id)}</span>`]), "No events.")}
    ${pager(data, (p) => "#/admin/audit?" + new URLSearchParams({ ...f, page: p }))}`;
  $("#af").onsubmit = (ev) => { ev.preventDefault(); location.hash = "#/admin/audit?" + new URLSearchParams(formData(ev.target)); };
}

async function pageJobs(v, _a, params) {
  const status = params.get("status") || "";
  const [jobs, notes] = await Promise.all([api("GET", "/admin/jobs?" + new URLSearchParams({ status })), api("GET", "/admin/notifications?page_size=30")]);
  const hb = jobs.scheduler_heartbeat ? (Date.now() - new Date(jobs.scheduler_heartbeat)) / 1000 : null;
  v.innerHTML = `<h1>Jobs and email</h1>
    <div class="card"><p>Worker heartbeat: ${hb === null ? pill("FAILED") + " never seen. Start it with <code>python manage.py run_worker</code>."
      : hb < 120 ? `${pill("ACTIVE")} last run ${Math.round(hb)}s ago` : `${pill("FAILED")} last run ${fmtDT(jobs.scheduler_heartbeat)}. Is the worker running?`}
      ${jobs.smtp_down ? ` · ${pill("FAILED")} Simulated SMTP outage is ON (Demo tools)` : ""}</p>
      <p class="small">${Object.entries(jobs.counts).map(([k, n]) => `<a href="#/admin/jobs?status=${k}">${esc(cap(k))}: ${n}</a>`).join(" · ")} · <a href="#/admin/jobs">All</a></p></div>
    <h2>Jobs</h2>${table(["#", "Type", "Status", "Attempts", "Run at", "Error", ""], jobs.results.map((j) => [
      j.id, esc(j.type), pill(j.status), j.attempts, fmtDT(j.run_at),
      j.error_category ? `${esc(j.error_category)}<div class="small muted">${esc(j.last_error)}</div>` : "",
      j.status === "FAILED" || (j.status === "PENDING" && j.error_category) ? `<button class="small" data-retry="${j.id}">Retry</button>` : ""]), "No jobs.")}
    ${pager(jobs, (p) => "#/admin/jobs?" + new URLSearchParams({ status, page: p }))}
    <h2>Email outbox (latest 30)</h2>${table(["When", "To", "Subject", "Status"], notes.results.map((n) => [
      fmtDT(n.created_at), esc(n.to || n.user), `<details><summary>${esc(n.subject)}</summary><pre>${esc(n.body)}</pre></details>`,
      pill(n.status) + (n.error_category ? ` <span class="small muted">${esc(n.error_category)}</span>` : "")]), "No emails yet.")}`;
  v.onclick = async (ev) => {
    const b = ev.target.closest("button[data-retry]");
    if (!b) return;
    try { await api("POST", `/admin/jobs/${b.dataset.retry}/retry`); toast("Queued for retry."); route(); } catch (e) { toast(errMsg(e)); }
  };
}

async function pageImport(v) {
  const runs = await api("GET", "/admin/imports?page_size=10");
  v.innerHTML = `<h1>CSV import</h1><div class="card"><form id="if" class="row">
    ${field("Kind", `<select name="kind" id="kind">${options([["BOOKS_COPIES", "Books and copies"], ["PATRONS", "Patrons"]])}</select>`)}
    ${field("CSV file (UTF-8)", '<input type="file" name="file" accept=".csv,text/csv" required>', "field wide")}
    <label class="row" style="align-items:center"><input type="checkbox" name="dry_run" value="true" checked> Dry run (check only, write nothing)</label>
    <button>Upload</button></form><p class="small muted">Columns: <code id="cols"></code></p></div>
    <div id="out"></div><h2>Recent runs</h2>${table(["When", "By", "Kind", "File", "Mode", "Status", "Summary"], runs.results.map((r) => [
      fmtDT(r.created_at), esc(r.created_by), esc(cap(r.kind)), esc(r.file_name), r.dry_run ? "Dry run" : "Apply", pill(r.status), summary(r.summary)]), "No imports yet.")}`;
  const showCols = () => ($("#cols").textContent = runs.columns[$("#kind").value].join(","));
  $("#kind").onchange = showCols; showCols();
  function summary(s) {
    return s.errors?.length ? `${s.error_count || s.errors.length} error(s)` : `${s.rows} rows: ${s.new ?? 0} new, ${s.updated ?? 0} updated, ${s.unchanged ?? 0} unchanged`;
  }
  $("#if").onsubmit = async (ev) => {
    ev.preventDefault();
    const fd = new FormData(ev.target);
    if (!fd.get("dry_run")) fd.set("dry_run", "false");
    try {
      const r = await api("POST", "/admin/imports", fd, { form: true });
      const s = r.summary;
      $("#out").innerHTML = `<div class="card"><h2>${r.dry_run ? "Dry run" : "Import"} result: ${pill(r.status)}</h2><p>${esc(summary(s))}</p>
        ${s.errors?.length ? table(["Row", "Column", "Problem"], s.errors.map((e) => [e.row, esc(e.column), esc(e.message)])) :
          r.dry_run ? "<p>No problems found. Untick <b>Dry run</b> and upload again to apply.</p>" : "<p>Applied.</p>"}</div>`;
    } catch (e) { toast(errMsg(e)); }
  };
}

async function pageDemo(v) {
  const s = await api("GET", "/admin/demo/clock");
  const off = s.offset_minutes, sign = off < 0 ? "-" : "+";
  v.innerHTML = `<h1>Demo tools</h1>
    <div class="card"><h2>Demo clock</h2><p>Demo time: <b>${fmtDT(s.now)}</b><br><span class="muted">Real time: ${fmtDT(s.real_now)} ·
      offset ${sign}${Math.floor(Math.abs(off) / 1440)}d ${Math.floor((Math.abs(off) % 1440) / 60)}h</span></p>
      <div class="row">${[[0, 1, "+1 hour"], [0, 3, "+3 hours"], [1, 0, "+1 day"], [3, 0, "+3 days"], [7, 0, "+7 days"]].map(([d, h, t]) =>
        `<button class="secondary" data-days="${d}" data-hours="${h}">${t}</button>`).join("")}
      <button class="danger" data-reset>Reset to real time</button></div>
      <p class="small muted">The worker scans for reminders every 30 seconds. Watch them arrive in <a href="#/admin/jobs">Jobs and email</a>.</p></div>
    <div class="card"><h2>Simulated SMTP outage</h2><p>Currently ${s.smtp_down ? pill("FAILED") + " <b>down</b>" : pill("ACTIVE") + " up"}.
      While it is down, emails fail and retry with backoff. Turn it back on, then use <b>Retry</b> on the Jobs page.</p>
      <button data-smtp="${!s.smtp_down}">${s.smtp_down ? "Restore SMTP" : "Simulate outage"}</button></div>`;
  v.onclick = async (ev) => {
    const b = ev.target.closest("button");
    if (!b) return;
    try {
      if (b.dataset.smtp) await api("POST", "/admin/demo/smtp", { down: b.dataset.smtp === "true" });
      else if (b.hasAttribute("data-reset")) await api("POST", "/admin/demo/clock", { reset: true });
      else if (b.dataset.days) await api("POST", "/admin/demo/clock", { days: +b.dataset.days, hours: +b.dataset.hours });
      await loadMe(); route();
    } catch (e) { toast(errMsg(e)); }
  };
}

// ---------- router ---------------------------------------------------------------------------
const routes = [
  ["login", pageLogin, null], ["forgot", pageForgot, null], ["reset", pageReset, null],
  ["search", pageSearch, "ANY"], ["book/:id", pageBook, "ANY"], ["my", pageMy, "ANY"],
  ["desk", pageDesk, "STAFF"], ["patrons", pagePatrons, "STAFF"], ["patron/:id", pagePatron, "STAFF"],
  ["catalog", pageCatalog, "STAFF"], ["fines", pageFines, "STAFF"],
  ["admin/rules", pageRules, "ADMIN"], ["admin/calendar", pageCalendar, "ADMIN"], ["admin/audit", pageAudit, "ADMIN"],
  ["admin/jobs", pageJobs, "ADMIN"], ["admin/import", pageImport, "ADMIN"], ["admin/demo", pageDemo, "ADMIN"],
];

const home = () => (!me ? "login" : me.role === "MEMBER" ? "my" : "desk");

function match(path) {
  for (const [pat, fn, role] of routes) {
    const a = pat.split("/"), b = path.split("/"), args = {};
    if (a.length === b.length && a.every((s, i) => (s.startsWith(":") ? ((args[s.slice(1)] = decodeURIComponent(b[i])), true) : s === b[i]))) return { fn, role, args };
  }
  return null;
}

function renderNav(path) {
  $("#topbar").hidden = !me;
  if (!me) return;
  let links = [["my", "My loans"], ["search", "Search"]];
  if (isStaff()) links = [["desk", "Desk"], ["patrons", "Patrons"], ["catalog", "Catalog"], ["fines", "Fines"]];
  if (isAdmin()) links.push(["admin/rules", "Rules"], ["admin/calendar", "Calendar"], ["admin/audit", "Audit"], ["admin/jobs", "Jobs & email"], ["admin/import", "Import"]);
  if (isAdmin() && demoClock) links.push(["admin/demo", "Demo tools"]);
  $("#nav").innerHTML = links.map(([h, t]) => `<a href="#/${h}" class="${path === h || path.startsWith(h + "/") ? "active" : ""}" ${path === h ? 'aria-current="page"' : ""}>${t}</a>`).join("");
  $("#who").textContent = `${me.full_name} (${me.role.toLowerCase()})`;
  const c = $("#clock");
  c.hidden = !(demoClock && Math.abs(skewMs) > 60000);
  if (!c.hidden) c.textContent = "Demo time: " + fmtDT(new Date(Date.now() + skewMs).toISOString());
}

async function route() {
  const raw = location.hash.replace(/^#\/?/, "");
  const [path, qs] = raw.split("?");
  const params = new URLSearchParams(qs || "");
  const m = match(path);
  const go = (p) => { location.hash = "#/" + p; };
  if (!m) return go(home());
  if (m.role && !me) return go("login");
  if ((m.role === "STAFF" && !isStaff()) || (m.role === "ADMIN" && !isAdmin())) return go(home());
  if (!m.role && me && path === "login") return go(home());
  renderNav(path);
  const v = $("#main");
  v.onclick = null;
  v.innerHTML = "";
  try { await m.fn(v, m.args, params); }
  catch (e) {
    if (e.status === 401) { me = null; return go("login"); }
    v.innerHTML = `<div class="banner err" role="alert">${esc(errMsg(e))}</div>`;
  }
}

async function loadMe() {
  try {
    const d = await api("GET", "/auth/me");
    me = d.user; demoClock = d.demo_clock; skewMs = new Date(d.now) - Date.now();
  } catch { me = null; }
}

$("#logout").onclick = async () => { try { await api("POST", "/auth/logout"); } catch { /* already logged out */ } me = null; location.hash = "#/login"; };
window.addEventListener("hashchange", route);
await api("GET", "/auth/csrf").catch(() => {});
await loadMe();
route();
