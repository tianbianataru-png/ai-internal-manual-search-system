// 画面の動作。ユーザー由来の文字列は必ず textContent で入れる(XSS対策)。
const $ = (id) => document.getElementById(id);

function showMessage(text, isError = false) {
  const m = $("message");
  m.textContent = text;
  m.className = "message" + (isError ? " error" : "");
  m.hidden = false;
}
function clearMessage() { $("message").hidden = true; }

let currentUser = null;
const isAdmin = () => currentUser && currentUser.role === "admin";

async function api(path, options) {
  const res = await fetch(path, options);
  if (res.status === 401 && path !== "/api/auth/login") {
    showLogin("ログインの有効期限が切れました。もう一度ログインしてください。");
    throw new Error("ログインが必要です。");
  }
  if (!res.ok) {
    let detail = `エラーが発生しました(${res.status})`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch (_) { /* JSONでなければ既定の文言 */ }
    throw new Error(detail);
  }
  return res.status === 204 ? null : res.json();
}

function el(tag, className, text) {
  const e = document.createElement(tag);
  if (className) e.className = className;
  if (text !== undefined) e.textContent = text;
  return e;
}

function renderSources(ul, sources) {
  ul.replaceChildren();
  if (!sources.length) { ul.append(el("li", "", "出典はありません。")); return; }
  for (const s of sources) {
    const li = el("li");
    const label = s.page != null ? `${s.manual_name}(p.${s.page})` : s.manual_name;
    li.append(el("div", "src-name", s.ref != null ? `[${s.ref}] ${label}` : label));
    if (s.manual_id != null) {
      const a = el("a", "src-dl", "元のファイルをダウンロード");
      a.href = `/api/manuals/${s.manual_id}/file`;
      li.append(a);
    }
    li.append(el("div", "src-text", s.text));
    ul.append(li);
  }
}

// 回答への評価ボタン。同じボタンをもう一度押すと評価を取り消す。
function renderRating(box, historyId, current, onChange) {
  box.replaceChildren(el("span", "", "この回答は役に立ちましたか?"));
  for (const [value, label] of [["good", "役に立った"], ["bad", "役に立たなかった"]]) {
    const b = el("button", `${value}${current === value ? " on" : ""}`, label);
    b.type = "button";
    b.addEventListener("click", async () => {
      const next = current === value ? null : value;
      try {
        await api(`/api/history/${historyId}/rating`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ rating: next }),
        });
        renderRating(box, historyId, next, onChange);
        if (onChange) onChange(next);
      } catch (err) { showMessage(err.message, true); }
    });
    box.append(b);
  }
}

function formatSize(n) {
  return n < 1024 * 1024 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`;
}

// ---- タブ ----
document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b === btn));
    document.querySelectorAll(".panel").forEach((p) => { p.hidden = p.id !== `tab-${btn.dataset.tab}`; });
    clearMessage();
    if (btn.dataset.tab === "ask") loadScope();
    if (btn.dataset.tab === "manuals") loadManuals();
    if (btn.dataset.tab === "history") loadHistory();
    if (btn.dataset.tab === "users") loadUsers();
    if (btn.dataset.tab === "feedback") loadFeedback();
    if (btn.dataset.tab === "audit") loadAudit(true);
  });
});

// ---- 検索対象(分類・マニュアル選択) ----
let allManuals = [];

// 選んだ分類に合わせて、検索対象のマニュアルの選択肢を絞る。
function fillScopeManuals(list) {
  const sel = $("scope");
  const cat = $("scope-category").value;
  sel.replaceChildren(new Option("すべてのマニュアル", ""));
  for (const m of list.filter((x) => x.status === "ready" && (!cat || x.category === cat))) {
    sel.append(new Option(m.filename, String(m.id)));
  }
}
$("scope-category").addEventListener("change", () => { fillScopeManuals(allManuals); });

async function loadScope() {
  const sel = $("scope");
  const keep = sel.value;
  try {
    const list = await api("/api/manuals");
    const catSel = $("scope-category");
    const keepCat = catSel.value;
    const cats = [...new Set(list.filter((x) => x.status === "ready" && x.category).map((x) => x.category))].sort();
    catSel.replaceChildren(new Option("すべて", ""), ...cats.map((c) => new Option(c, c)));
    catSel.value = cats.includes(keepCat) ? keepCat : "";
    fillScopeManuals(list);
    sel.value = [...sel.options].some((o) => o.value === keep) ? keep : "";
    allManuals = list;
  } catch (_) { /* 取得できなくても質問自体は可能 */ }
}

// ---- ログイン ----
function showLogin(msg) {
  currentUser = null;
  $("app").hidden = true;
  $("login-view").hidden = false;
  const m = $("login-message");
  m.hidden = !msg;
  m.textContent = msg || "";
  $("login-pass").value = "";
}

function showApp(user) {
  currentUser = user;
  $("login-view").hidden = true;
  $("app").hidden = false;
  $("who").textContent = `${user.username}(${user.role === "admin" ? "管理者" : "一般"})`;
  document.querySelectorAll(".admin-only").forEach((e) => { e.hidden = !isAdmin(); });
  document.querySelector('.tab[data-tab="ask"]').click(); // 最初の画面に戻す
  $("ask-result").hidden = true;
  $("question").value = "";
}

$("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = $("login-btn");
  btn.disabled = true;
  try {
    const user = await api("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: $("login-user").value, password: $("login-pass").value }),
    });
    showApp(user);
  } catch (err) {
    showLogin(err.message);
  } finally {
    btn.disabled = false;
  }
});

$("logout-btn").addEventListener("click", async () => {
  try { await api("/api/auth/logout", { method: "POST" }); } catch (_) { /* 失敗してもログイン画面へ */ }
  showLogin();
});

// Server-Sent Events を読み、(イベント名, データ)ごとに onEvent を呼ぶ。
async function readSSE(res, onEvent) {
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  const handle = (block) => {
    let event = "message", data = "";
    for (const line of block.split("\n")) {
      if (line.startsWith("event: ")) event = line.slice(7);
      else if (line.startsWith("data: ")) data += line.slice(6);
    }
    if (data) onEvent(event, JSON.parse(data));
  };
  for (;;) {
    const { done, value } = await reader.read();
    buf += decoder.decode(value || new Uint8Array(), { stream: !done }).replace(/\r\n/g, "\n");
    let i;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      handle(buf.slice(0, i));
      buf = buf.slice(i + 2);
    }
    if (done) break;
  }
  if (buf.trim()) handle(buf);
}

// ---- 質問 ----
$("ask-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  clearMessage();
  const btn = $("ask-btn");
  btn.disabled = true;
  btn.textContent = "回答を作成中...";
  try {
    const res = await fetch("/api/ask/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: $("question").value,
        manual_id: $("scope").value ? Number($("scope").value) : null,
        category: $("scope-category").value || null,
      }),
    });
    if (res.status === 401) {
      showLogin("ログインの有効期限が切れました。もう一度ログインしてください。");
      return;
    }
    if (!res.ok) {
      let detail = `エラーが発生しました(${res.status})`;
      try { const b = await res.json(); if (typeof b.detail === "string") detail = b.detail; } catch (_) { /* 既定の文言 */ }
      throw new Error(detail);
    }
    $("answer").textContent = "";
    $("sources").replaceChildren();
    $("ask-rating").replaceChildren();
    $("ask-result").hidden = false;
    let finished = false;
    await readSSE(res, (event, data) => {
      if (event === "delta") {
        $("answer").textContent += data;
      } else if (event === "done") {
        finished = true;
        $("answer").textContent = data.answer; // 最終的な回答で置き換える
        renderSources($("sources"), data.sources);
        renderRating($("ask-rating"), data.id, null);
      } else if (event === "error") {
        throw new Error(data.detail || "回答の生成に失敗しました。");
      }
    });
    if (!finished) throw new Error("回答が途中で途切れました。もう一度お試しください。");
  } catch (err) {
    $("ask-result").hidden = true;
    showMessage(err.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = "質問する";
  }
});

// ---- マニュアル ----
$("manual-q").addEventListener("input", () => loadManuals());
async function loadManuals() {
  try {
    const all = await api("/api/manuals");
    const tbody = $("manual-list");
    tbody.replaceChildren();
    const opts = [...new Set(all.map((x) => x.category).filter(Boolean))].sort();
    $("category-options").replaceChildren(...opts.map((c) => new Option(c)));
    // 絞り込み(ファイル名・分類の部分一致。大文字小文字は区別しない。未分類は「未分類」で探せる)
    const kw = $("manual-q").value.trim().toLowerCase();
    const list = kw ? all.filter((m) => `${m.filename} ${m.category || "未分類"}`.toLowerCase().includes(kw)) : all;
    $("manual-empty").hidden = list.length > 0;
    $("manual-empty").textContent = all.length && !list.length ? "条件に合うマニュアルはありません。" : "登録されたマニュアルはありません。";
    for (const m of list) {
      const tr = el("tr");
      tr.append(el("td", "", m.filename), el("td", "", m.category || "未分類"), el("td", "", m.file_type), el("td", "", formatSize(m.file_size)));
      const st = el("td", m.status === "error" ? "status-error" : "",
        m.status === "ready" ? `登録済み(${m.chunk_count}件に分割)` : `失敗: ${m.error_message || ""}`);
      tr.append(st, el("td", "", m.updated_at ? `${m.created_at}(更新: ${m.updated_at})` : m.created_at));
      const td = el("td");
      const dl = el("a", "dl", "ダウンロード");
      dl.href = `/api/manuals/${m.id}/file`;
      td.append(dl, " ");
      if (isAdmin()) {
        const upd = el("button", "danger plain", "更新");
        upd.addEventListener("click", () => pickUpdateFile(m));
        td.append(upd, " ");
        const cat = el("button", "danger plain", "分類");
        cat.addEventListener("click", () => changeCategory(m));
        td.append(cat, " ");
        const del = el("button", "danger", "削除");
        del.addEventListener("click", async () => {
          if (!confirm(`「${m.filename}」を削除しますか?`)) return;
          try { await api(`/api/manuals/${m.id}`, { method: "DELETE" }); loadManuals(); }
          catch (err) { showMessage(err.message, true); }
        });
        td.append(del);
      }
      tr.append(td);
      tbody.append(tr);
    }
  } catch (err) { showMessage(err.message, true); }
}

// 分類を変更する(空にすると未分類)。
async function changeCategory(m) {
  const input = prompt(`「${m.filename}」の分類を入力してください(30文字以内・空欄で未分類)`, m.category || "");
  if (input === null) return;
  clearMessage();
  try {
    await api(`/api/manuals/${m.id}/category`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ category: input }),
    });
    showMessage("分類を変更しました。");
    loadManuals();
  } catch (err) { showMessage(err.message, true); }
}

// 登録済みマニュアルを新しいファイルで差し替える(ファイルを選ぶと、確認してから送信)。
function pickUpdateFile(m) {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = ".pdf,.docx,.txt";
  input.addEventListener("change", async () => {
    const f = input.files[0];
    if (!f) return;
    if (!confirm(`「${m.filename}」を「${f.name}」の内容に差し替えますか?`)) return;
    clearMessage();
    showMessage("更新中です...");
    try {
      const fd = new FormData();
      fd.append("file", f);
      await api(`/api/manuals/${m.id}`, { method: "PUT", body: fd });
      showMessage(`「${f.name}」の内容に更新しました。`);
      loadManuals();
    } catch (err) { showMessage(err.message, true); }
  });
  input.click();
}

$("upload-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  clearMessage();
  const btn = $("upload-btn");
  btn.disabled = true;
  btn.textContent = "登録中...";
  try {
    const fd = new FormData();
    fd.append("file", $("file").files[0]);
    fd.append("category", $("upload-category").value);
    const m = await api("/api/manuals", { method: "POST", body: fd });
    if (m.status === "error") showMessage(`解析に失敗しました: ${m.error_message}`, true);
    else showMessage(`「${m.filename}」を登録しました。`);
    $("upload-form").reset();
    loadManuals();
  } catch (err) {
    showMessage(err.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = "登録する";
  }
});

// ---- 履歴 ----
$("history-filter").addEventListener("submit", (e) => { e.preventDefault(); clearMessage(); loadHistory(); });
async function loadHistory() {
  $("history-detail").hidden = true;
  try {
    const params = new URLSearchParams();
    if ($("history-q").value.trim()) params.set("q", $("history-q").value.trim());
    if ($("history-rating").value) params.set("rating", $("history-rating").value);
    const list = await api("/api/history" + (params.toString() ? `?${params}` : ""));
    const ul = $("history-list");
    ul.replaceChildren();
    $("history-empty").hidden = list.length > 0;
    $("history-empty").textContent = params.toString() ? "条件に合う履歴はありません。" : "質問履歴はありません。";
    for (const h of list) {
      const li = el("li");
      const main = el("div", "h-main");
      const q = el("button", "link h-q", h.question);
      q.addEventListener("click", () => showHistory(h.id));
      const meta = el("div", "meta", `${h.created_at}・出典${h.source_count}件`);
      if (h.rating) meta.append(el("span", `badge ${h.rating}`, h.rating === "good" ? "役に立った" : "役に立たなかった"));
      main.append(q, meta);
      const del = el("button", "danger", "削除");
      del.addEventListener("click", async () => {
        if (!confirm("この履歴を削除しますか?")) return;
        try { await api(`/api/history/${h.id}`, { method: "DELETE" }); loadHistory(); }
        catch (err) { showMessage(err.message, true); }
      });
      li.append(main, del);
      ul.append(li);
    }
  } catch (err) { showMessage(err.message, true); }
}

// 評価を変えたあと、詳細は開いたまま一覧のバッジだけ更新する。
async function loadHistoryKeepDetail() {
  const open = !$("history-detail").hidden;
  await loadHistory();
  $("history-detail").hidden = !open;
}

async function showHistory(id) {
  clearMessage();
  try {
    const d = await api(`/api/history/${id}`);
    $("detail-date").textContent = d.created_at;
    $("detail-question").textContent = d.question;
    $("detail-answer").textContent = d.answer;
    renderSources($("detail-sources"), d.sources);
    renderRating($("detail-rating"), d.id, d.rating, loadHistoryKeepDetail);
    $("history-detail").hidden = false;
    $("history-detail").scrollIntoView({ behavior: "smooth" });
  } catch (err) { showMessage(err.message, true); }
}

// ---- 回答の評価の集計(管理者のみ) ----
async function loadFeedback() {
  try {
    const s = await api("/api/feedback/summary");
    const stats = $("fb-stats");
    stats.replaceChildren();
    const rated = s.good + s.bad;
    const items = [
      ["回答の総数", s.total], ["役に立った", s.good], ["役に立たなかった", s.bad], ["未評価", s.unrated],
      ["満足率", rated ? `${Math.round((s.good / rated) * 100)}%` : "-"],
    ];
    for (const [label, value] of items) {
      const box = el("div", "stat");
      box.append(el("b", "", String(value)), el("span", "meta", label));
      stats.append(box);
    }
    const tbody = $("fb-manuals");
    tbody.replaceChildren();
    $("fb-manuals-empty").hidden = s.by_manual.length > 0;
    for (const m of s.by_manual) {
      const tr = el("tr");
      tr.append(el("td", "", m.manual_name), el("td", "", String(m.good)), el("td", "", String(m.bad)));
      tbody.append(tr);
    }
    const ul = $("fb-bad");
    ul.replaceChildren();
    $("fb-empty").hidden = s.recent_bad.length > 0;
    for (const b of s.recent_bad) {
      const li = el("li");
      const main = el("div", "h-main");
      main.append(el("div", "h-q", b.question), el("div", "meta", `${b.username}・${b.created_at}`),
        el("div", "meta clamp", b.answer));
      li.append(main);
      ul.append(li);
    }
  } catch (err) { showMessage(err.message, true); }
}

// ---- 操作ログ(管理者のみ) ----
const AUDIT_LABELS = {
  login: "ログイン", login_failed: "ログイン失敗", logout: "ログアウト", password_change: "パスワード変更(本人)",
  user_create: "ユーザー追加", password_reset: "パスワードリセット(管理者)", user_delete: "ユーザー削除",
  manual_upload: "マニュアル登録", manual_update: "マニュアル更新", manual_delete: "マニュアル削除", manual_category: "マニュアル分類変更",
};
const AUDIT_PAGE = 100;
let auditOffset = 0;

for (const [value, label] of Object.entries(AUDIT_LABELS)) $("audit-action").append(new Option(label, value));
$("audit-action").addEventListener("change", () => loadAudit(true));
$("audit-more").addEventListener("click", () => loadAudit(false));

async function loadAudit(reset) {
  if (reset) { auditOffset = 0; $("audit-list").replaceChildren(); }
  try {
    const action = $("audit-action").value;
    const q = new URLSearchParams({ limit: AUDIT_PAGE, offset: auditOffset });
    if (action) q.set("action", action);
    const rows = await api(`/api/audit?${q}`);
    const tbody = $("audit-list");
    for (const r of rows) {
      const tr = el("tr");
      tr.append(
        el("td", "", r.created_at),
        el("td", r.action === "login_failed" ? "audit-failed" : "", AUDIT_LABELS[r.action] || r.action),
        el("td", "", r.username),
        el("td", "", r.detail),
        el("td", "", r.ip),
      );
      tbody.append(tr);
    }
    auditOffset += rows.length;
    $("audit-empty").hidden = auditOffset > 0;
    $("audit-more").hidden = rows.length < AUDIT_PAGE;
  } catch (err) { showMessage(err.message, true); }
}

// ---- ユーザー管理(管理者のみ) ----
async function loadUsers() {
  try {
    const list = await api("/api/users");
    const tbody = $("user-list");
    tbody.replaceChildren();
    for (const u of list) {
      const tr = el("tr");
      tr.append(el("td", "", u.username), el("td", "", u.role === "admin" ? "管理者" : "一般"), el("td", "", u.created_at));
      const td = el("td");
      const pw = el("button", "danger plain", "パスワード変更");
      pw.addEventListener("click", async () => {
        const p = prompt(`「${u.username}」の新しいパスワード(8文字以上)`);
        if (!p) return;
        try {
          await api(`/api/users/${u.id}/password`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ password: p }),
          });
          showMessage("パスワードを変更しました。");
        } catch (err) { showMessage(err.message, true); }
      });
      td.append(pw, " ");
      if (u.id !== currentUser.id) {
        const del = el("button", "danger", "削除");
        del.addEventListener("click", async () => {
          if (!confirm(`「${u.username}」と、その質問履歴を削除しますか?`)) return;
          try { await api(`/api/users/${u.id}`, { method: "DELETE" }); loadUsers(); }
          catch (err) { showMessage(err.message, true); }
        });
        td.append(del);
      }
      tr.append(td);
      tbody.append(tr);
    }
  } catch (err) { showMessage(err.message, true); }
}

$("user-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  clearMessage();
  try {
    await api("/api/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: $("new-user").value, password: $("new-pass").value, role: $("new-role").value }),
    });
    $("user-form").reset();
    showMessage("ユーザーを追加しました。");
    loadUsers();
  } catch (err) { showMessage(err.message, true); }
});

// ---- 自分のパスワード変更 ----
$("password-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  clearMessage();
  if ($("new-pass1").value !== $("new-pass2").value) {
    showMessage("新しいパスワードが一致しません。", true);
    return;
  }
  try {
    await api("/api/auth/password", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ current_password: $("cur-pass").value, new_password: $("new-pass1").value }),
    });
    $("password-form").reset();
    showMessage("パスワードを変更しました。他の端末ではログアウトされます。");
  } catch (err) { showMessage(err.message, true); }
});

// ---- 起動時: ログイン状態を確認 ----
(async () => {
  try {
    const res = await fetch("/api/auth/me");
    if (res.ok) showApp(await res.json());
    else showLogin();
  } catch (_) { showLogin("サーバーに接続できません。"); }
})();
