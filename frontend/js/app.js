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
    li.append(el("div", "src-name", s.page != null ? `${s.manual_name}(p.${s.page})` : s.manual_name));
    li.append(el("div", "src-text", s.text));
    ul.append(li);
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
    if (btn.dataset.tab === "manuals") loadManuals();
    if (btn.dataset.tab === "history") loadHistory();
    if (btn.dataset.tab === "users") loadUsers();
  });
});

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

// ---- 質問 ----
$("ask-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  clearMessage();
  const btn = $("ask-btn");
  btn.disabled = true;
  btn.textContent = "回答を作成中...";
  try {
    const r = await api("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: $("question").value }),
    });
    $("answer").textContent = r.answer;
    renderSources($("sources"), r.sources);
    $("ask-result").hidden = false;
  } catch (err) {
    $("ask-result").hidden = true;
    showMessage(err.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = "質問する";
  }
});

// ---- マニュアル ----
async function loadManuals() {
  try {
    const list = await api("/api/manuals");
    const tbody = $("manual-list");
    tbody.replaceChildren();
    $("manual-empty").hidden = list.length > 0;
    for (const m of list) {
      const tr = el("tr");
      tr.append(el("td", "", m.filename), el("td", "", m.file_type), el("td", "", formatSize(m.file_size)));
      const st = el("td", m.status === "error" ? "status-error" : "",
        m.status === "ready" ? `登録済み(${m.chunk_count}件に分割)` : `失敗: ${m.error_message || ""}`);
      tr.append(st, el("td", "", m.created_at));
      const td = el("td");
      if (isAdmin()) {
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

$("upload-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  clearMessage();
  const btn = $("upload-btn");
  btn.disabled = true;
  btn.textContent = "登録中...";
  try {
    const fd = new FormData();
    fd.append("file", $("file").files[0]);
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
async function loadHistory() {
  $("history-detail").hidden = true;
  try {
    const list = await api("/api/history");
    const ul = $("history-list");
    ul.replaceChildren();
    $("history-empty").hidden = list.length > 0;
    for (const h of list) {
      const li = el("li");
      const main = el("div", "h-main");
      const q = el("button", "link h-q", h.question);
      q.addEventListener("click", () => showHistory(h.id));
      main.append(q, el("div", "meta", `${h.created_at}・出典${h.source_count}件`));
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

async function showHistory(id) {
  clearMessage();
  try {
    const d = await api(`/api/history/${id}`);
    $("detail-date").textContent = d.created_at;
    $("detail-question").textContent = d.question;
    $("detail-answer").textContent = d.answer;
    renderSources($("detail-sources"), d.sources);
    $("history-detail").hidden = false;
    $("history-detail").scrollIntoView({ behavior: "smooth" });
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

// ---- 起動時: ログイン状態を確認 ----
(async () => {
  try {
    const res = await fetch("/api/auth/me");
    if (res.ok) showApp(await res.json());
    else showLogin();
  } catch (_) { showLogin("サーバーに接続できません。"); }
})();
