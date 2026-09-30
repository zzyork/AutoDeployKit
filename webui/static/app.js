const state = { csrf: "", user: null, view: "workbench", conversation: null, job: null, eventSource: null, hosts: [], keys: [] };
const $ = (selector) => document.querySelector(selector);
const view = $("#view");
const sidebar = $("#side-pane");
const labels = { workbench: ["工作台", "巡检工作台"], jobs: ["任务", "执行记录"], reports: ["报告", "巡检报告"], hosts: ["主机", "资产管理"], settings: ["设置", "工作台设置"] };
const statusText = { queued: "等待中", running: "运行中", succeeded: "已完成", partial: "部分完成", failed: "失败", interrupted: "已中断" };

function element(tag, cls, text) {
  const item = document.createElement(tag);
  if (cls) item.className = cls;
  if (text !== undefined) item.textContent = String(text);
  return item;
}
function action(text, fn, cls = "secondary") {
  const item = element("button", cls, text);
  item.type = "button";
  item.addEventListener("click", fn);
  return item;
}
function title(text) { return element("h2", "", text); }
function detail(label, text) {
  const row = element("div", "detail");
  row.append(element("strong", "", label), element("div", "value", text ?? "-"));
  return row;
}
function notice(text, isError = false) {
  const item = $("#notice");
  item.textContent = text;
  item.classList.toggle("error", isError);
  item.hidden = false;
  clearTimeout(notice.timer);
  notice.timer = setTimeout(() => { item.hidden = true; }, 4500);
}
async function request(method, path, data, raw = false) {
  const headers = {};
  if (data !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET" && state.csrf) headers["X-CSRF-Token"] = state.csrf;
  const response = await fetch(path, { method, headers, credentials: "same-origin", body: data === undefined ? undefined : JSON.stringify(data) });
  if (response.status === 401 && path !== "/api/login") { showLogin(); throw new Error("会话已过期"); }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : `请求失败 (${response.status})`);
  }
  return raw ? response.text() : response.json();
}
async function attempt(fn) { try { return await fn(); } catch (error) { notice(error.message || "操作失败", true); } }
function showLogin() {
  state.csrf = "";
  state.user = null;
  state.job = null;
  state.conversation = null;
  if (state.eventSource) { state.eventSource.close(); state.eventSource = null; }
  $("#shell").hidden = true;
  $("#login-screen").hidden = false;
  $("#login-username").focus();
}
function showApp() {
  $("#login-screen").hidden = true;
  $("#shell").hidden = false;
  $("#logout").textContent = "退出登录";
  $("#logout").title = `当前账号：${state.user.username}`;
  navigate(state.view);
}

function navigate(name) {
  state.view = name;
  $("#section-label").textContent = labels[name][0];
  $("#page-title").textContent = labels[name][1];
  $("#header-actions").replaceChildren();
  sidebar.hidden = true;
  for (const item of $("#nav-items").children) item.setAttribute("aria-current", item.dataset.view === name ? "page" : "false");
  view.replaceChildren();
  const render = { workbench: renderWorkbench, jobs: renderJobs, reports: renderReports, hosts: renderHosts, settings: renderSettings }[name];
  attempt(render);
}
function badge(status) { return element("span", `status ${status}`, statusText[status] || status); }
function table(headers, records, makeRow) {
  const wrap = element("div", "table-wrap"), grid = element("table"), head = element("thead"), row = element("tr");
  headers.forEach((label) => row.append(element("th", "", label)));
  head.append(row);
  const body = element("tbody");
  records.forEach((record) => body.append(makeRow(record)));
  grid.append(head, body);
  wrap.append(grid);
  if (!records.length) wrap.append(element("div", "empty", "暂无记录"));
  return wrap;
}
function row(...cells) {
  const tr = element("tr");
  cells.forEach((cell) => {
    const td = element("td");
    td.append(cell instanceof Node ? cell : document.createTextNode(String(cell ?? "-")));
    tr.append(td);
  });
  return tr;
}

async function renderWorkbench() {
  const conversations = await request("GET", "/api/conversations");
  if (!state.job) {
    const jobs = await request("GET", "/api/jobs");
    const active = jobs.find((job) => ["queued", "running"].includes(job.status) && (!state.conversation || job.conversation_id === state.conversation));
    if (active) {
      state.conversation = active.conversation_id;
      state.job = active.id;
      watchJob(active.id);
    }
  }
  if (state.view !== "workbench") return;
  const page = element("div", "workbench"), history = element("section", "history"), chat = element("section", "conversation");
  const header = element("div", "section-header");
  header.append(title("会话"), action("新建", () => { state.conversation = null; navigate("workbench"); }));
  history.append(header);
  conversations.forEach((record) => {
    const item = action(record.title, () => { state.conversation = record.id; navigate("workbench"); }, record.id === state.conversation ? "active" : "");
    item.title = record.title;
    history.append(item);
  });
  const messages = element("div", "messages");
  messages.setAttribute("aria-live", "polite");
  if (state.conversation) {
    const entries = await request("GET", `/api/conversations/${state.conversation}/messages`);
    entries.forEach((entry) => appendMessage(messages, entry.role, entry.content));
  } else {
    messages.append(element("div", "empty", "开始新的巡检会话"));
  }
  const compose = element("form", "compose"), prompt = element("textarea");
  prompt.placeholder = "例如：巡检 webservers，并汇总风险";
  prompt.setAttribute("aria-label", "输入巡检请求");
  prompt.required = true;
  prompt.maxLength = 2000;
  const submit = element("button", "primary", "发送");
  submit.type = "submit";
  compose.append(prompt, submit);
  compose.addEventListener("submit", (event) => {
    event.preventDefault();
    const message = prompt.value.trim();
    if (!message) return;
    submit.disabled = true;
    attempt(async () => {
      const result = await request("POST", "/api/chat", { message, conversation_id: state.conversation });
      state.conversation = result.conversation_id;
      state.job = result.job_id;
      prompt.value = "";
      const empty = messages.querySelector(".empty");
      if (empty) empty.remove();
      appendMessage(messages, "user", message);
      watchJob(result.job_id);
      await renderProgress(result.job_id);
      const recent = await request("GET", "/api/conversations");
      if (recent[0] && history.children.length < 2) navigate("workbench");
    }).finally(() => { submit.disabled = false; });
  });
  chat.append(messages, compose);
  page.append(history, chat);
  view.append(page);
  messages.scrollTop = messages.scrollHeight;
  if (state.job) await renderProgress(state.job);
}
function appendMessage(container, role, content) {
  const item = element("div", `message ${role}`);
  item.append(element("small", "", role === "user" ? "你" : "助手"), element("div", "", content));
  container.append(item);
  container.scrollTop = container.scrollHeight;
}
async function renderProgress(jobId) {
  const job = await request("GET", `/api/jobs/${jobId}`);
  if (state.view !== "workbench") return;
  sidebar.hidden = false;
  sidebar.replaceChildren(title("任务进度"), badge(job.status));
  const results = job.result?.hosts || [];
  if (!results.length) sidebar.append(element("p", "muted", job.error || (job.status === "queued" ? "排队中" : job.status === "running" ? "正在处理" : statusText[job.status] || "任务已结束")));
  results.forEach((host) => {
    const line = element("div", "host-line");
    line.append(element("span", "", host.host), badge(host.status));
    sidebar.append(line);
  });
  if (results.length) sidebar.append(element("div", "summary-count", results.reduce((count, host) => count + host.risk_count, 0)), element("p", "muted", "风险项"));
  results.filter((host) => host.report_id).forEach((host) => sidebar.append(action(`${host.host} · 查看报告`, () => openReport(host.report_id), "text-button")));
}
function watchJob(jobId) {
  if (state.eventSource) state.eventSource.close();
  const source = new EventSource(`/api/jobs/${jobId}/events`);
  state.eventSource = source;
  for (const kind of ["job.snapshot", "job.started", "host.connecting", "host.inspecting", "host.succeeded", "host.failed"]) {
    source.addEventListener(kind, () => { if (state.view === "workbench") attempt(() => renderProgress(jobId)); });
  }
  source.addEventListener("assistant.message", (event) => {
    const message = JSON.parse(event.data);
    const messages = $(".messages");
    if (state.view === "workbench" && messages) appendMessage(messages, "assistant", message.content);
  });
  source.addEventListener("job.completed", () => { source.close(); if (state.view === "workbench") attempt(() => renderProgress(jobId)); });
  source.onerror = () => {
    source.close();
    setTimeout(() => attempt(async () => {
      const job = await request("GET", `/api/jobs/${jobId}`);
      if (state.view === "workbench") await renderProgress(jobId);
      if (["queued", "running"].includes(job.status)) watchJob(jobId);
      else if (state.view === "workbench") navigate("workbench");
    }), 1500);
  };
}

async function renderJobs() {
  const jobs = await request("GET", "/api/jobs");
  if (state.view !== "jobs") return;
  view.append(table(["时间", "工具", "状态", "主机", "操作"], jobs, (job) => row(
    new Date(job.created_at * 1000).toLocaleString(), job.tool_name || "模型决策", badge(job.status),
    job.result?.hosts?.length ?? "-", action("详情", () => showJobDetail(job), "text-button"),
  )));
}
function showJobDetail(job) {
  sidebar.hidden = false;
  sidebar.replaceChildren(title("任务详情"), badge(job.status), detail("任务 ID", job.id), detail("工具", job.tool_name || "-"));
  if (job.error) sidebar.append(detail("错误", job.error));
  (job.result?.hosts || []).forEach((host) => {
    const line = element("div", "host-line");
    line.append(element("span", "", host.host), badge(host.status));
    sidebar.append(line);
    if (host.report_id) sidebar.append(action("查看报告", () => openReport(host.report_id), "text-button"));
  });
}
async function renderReports() {
  const reports = await request("GET", "/api/reports");
  if (state.view !== "reports") return;
  view.append(table(["时间", "主机", "风险项", "报告"], reports, (report) => row(
    new Date(report.created_at * 1000).toLocaleString(), report.host, report.risk_count,
    action("查看", () => openReport(report.id), "text-button"),
  )));
}
async function openReport(reportId) {
  await attempt(async () => {
    navigate("reports");
    const content = await request("GET", `/api/reports/${reportId}`, undefined, true);
    sidebar.hidden = false;
    sidebar.replaceChildren(title("报告原文"), element("pre", "report-text", content));
  });
}

async function renderHosts() {
  const [hosts, keys] = await Promise.all([request("GET", "/api/hosts"), request("GET", "/api/ssh-keys")]);
  if (state.view !== "hosts") return;
  state.hosts = hosts; state.keys = keys;
  if (state.user.is_admin) $("#header-actions").append(action("登记资产", () => openHostDialog(), "primary"));
  const controls = element("div", "toolbar"), search = element("input"), group = element("select");
  search.placeholder = "搜索名称或地址"; search.setAttribute("aria-label", "搜索资产");
  group.append(new Option("全部分组", ""));
  [...new Set(hosts.map((host) => host.group_name))].sort().forEach((name) => group.append(new Option(name, name)));
  controls.append(search, group);
  const results = element("div");
  const fill = () => {
    const term = search.value.toLowerCase();
    const subset = hosts.filter((host) => (!group.value || host.group_name === group.value) && [host.name, host.address, host.username].some((value) => value.toLowerCase().includes(term)));
    results.replaceChildren(table(["资产", "地址", "分组", "认证", "状态", "操作"], subset, (host) => {
      const actions = element("div", "row-actions");
      if (state.user.is_admin) {
        const toggle = action(host.enabled ? "停用" : "启用", () => attempt(async () => {
          await request("PATCH", `/api/hosts/${host.id}`, { enabled: !host.enabled });
          notice(host.enabled ? "资产已停用" : "资产已启用");
          navigate("hosts");
        }), "text-button");
        toggle.classList.toggle("danger", !!host.enabled);
        actions.append(action("编辑", () => openHostDialog(host), "text-button"), toggle);
      }
      return row(host.name, `${host.address}:${host.port}`, host.group_name, host.has_password ? "密码" : "SSH 密钥", element("span", `status ${host.enabled ? "succeeded" : "failed"}`, host.enabled ? "已启用" : "已停用"), actions);
    }));
  };
  search.addEventListener("input", fill); group.addEventListener("change", fill);
  view.append(controls, results); fill();
}
function openHostDialog(host = null) {
  const form = $("#host-form"), dialog = $("#host-dialog");
  form.reset();
  $("#host-dialog-title").textContent = host ? "编辑资产" : "登记资产";
  for (const field of ["name", "address", "username", "group_name", "port", "tags"]) {
    form.elements[field].value = host ? field === "tags" ? host.tags.join(", ") : host[field] : field === "port" ? "22" : field === "group_name" ? "default" : "";
  }
  const keySelect = form.elements.ssh_key_id, proxySelect = form.elements.proxy_host_id;
  keySelect.replaceChildren(new Option("选择密钥", ""));
  state.keys.forEach((key) => keySelect.append(new Option(key.name, key.id)));
  proxySelect.replaceChildren(new Option("无", ""));
  state.hosts.filter((entry) => entry.enabled && entry.id !== host?.id && !entry.proxy_host_id).forEach((entry) => proxySelect.append(new Option(entry.name, entry.id)));
  form.elements.auth.value = host?.ssh_key_id ? "key" : "password";
  keySelect.value = host?.ssh_key_id || "";
  proxySelect.value = host?.proxy_host_id || "";
  form.elements.password.value = "";
  form.elements.admin_password.value = "";
  $("#reauth-field").hidden = !host;
  const syncAuth = () => { $("#password-field").hidden = form.elements.auth.value !== "password"; $("#key-field").hidden = form.elements.auth.value !== "key"; };
  syncAuth(); form.elements.auth.onchange = syncAuth;
  form.onsubmit = (event) => {
    event.preventDefault();
    attempt(async () => {
      const data = {
        name: form.elements.name.value.trim(), address: form.elements.address.value.trim(), port: Number(form.elements.port.value),
        group_name: form.elements.group_name.value.trim(), username: form.elements.username.value.trim(),
        tags: form.elements.tags.value.split(",").map((tag) => tag.trim()).filter(Boolean),
        proxy_host_id: form.elements.proxy_host_id.value || null,
      };
      if (form.elements.auth.value === "key") {
        if (!form.elements.ssh_key_id.value) throw new Error("请选择登录密钥");
        if (!host || host.ssh_key_id !== form.elements.ssh_key_id.value) data.ssh_key_id = form.elements.ssh_key_id.value;
      } else if (form.elements.password.value) {
        data.password = form.elements.password.value;
      } else if (host?.ssh_key_id) {
        throw new Error("请输入新的登录密码");
      } else if (!host) {
        throw new Error("请输入登录密码");
      }
      if (host) {
        data.admin_password = form.elements.admin_password.value;
        await request("PATCH", `/api/hosts/${host.id}`, data);
      } else {
        await request("POST", "/api/hosts", data);
      }
      dialog.close(); notice("资产已保存"); navigate("hosts");
    });
  };
  dialog.showModal();
}

async function renderSettings() {
  const stack = element("div", "stack");
  function field(text, type, name, value = "") {
    const label = element("label", "", text), input = element("input");
    input.type = type; input.name = name; input.value = value; label.append(input); return label;
  }
  if (state.user.is_admin) {
    const [settings, keys, accounts] = await Promise.all([request("GET", "/api/settings"), request("GET", "/api/ssh-keys"), request("GET", "/api/users")]);
    if (state.view !== "settings") return;
    const modelSection = element("section", "settings-section"), modelForm = element("form");
    modelSection.append(title("模型接口"));
    modelForm.append(field("接口地址", "url", "base_url", settings.base_url), field("模型名称", "text", "model", settings.model), field(settings.has_api_key ? "API Key（已配置，留空保持不变）" : "API Key", "password", "api_key"), field("管理员口令", "password", "admin_password"));
    const modelSubmit = element("button", "primary", "保存模型配置"); modelSubmit.type = "submit"; modelForm.append(modelSubmit);
    modelForm.addEventListener("submit", (event) => { event.preventDefault(); attempt(async () => {
      const values = Object.fromEntries(new FormData(modelForm));
      if (!values.api_key) delete values.api_key;
      await request("PATCH", "/api/settings", values); notice("模型配置已保存"); navigate("settings");
    }); });
    modelSection.append(modelForm);

    const keySection = element("section", "settings-section"), keyForm = element("form"), keyName = field("密钥名称", "text", "name");
    keySection.append(title("SSH 登录密钥"));
    keyName.querySelector("input").required = true;
    const keySubmit = element("button", "secondary", "生成密钥"); keySubmit.type = "submit";
    keyForm.append(keyName, keySubmit);
    keyForm.addEventListener("submit", (event) => { event.preventDefault(); attempt(async () => {
      await request("POST", "/api/ssh-keys", { name: keyName.querySelector("input").value.trim() });
      notice("密钥已生成"); navigate("settings");
    }); });
    keySection.append(keyForm);
    keys.forEach((key) => {
      const entry = element("div", "key-row");
      entry.append(element("strong", "", key.name), element("code", "", key.public_key), action("复制公钥", () => attempt(async () => { await navigator.clipboard.writeText(key.public_key); notice("公钥已复制"); }), "text-button"));
      keySection.append(entry);
    });
    stack.append(modelSection, keySection, renderAccounts(accounts, field));
  }
  const passwordSection = element("section", "settings-section"), passwordForm = element("form");
  passwordSection.append(title("修改登录口令"));
  passwordSection.append(element("p", "muted", `当前账号：${state.user.username}`));
  passwordForm.append(field("当前口令", "password", "current_password"), field("新口令", "password", "new_password"));
  passwordForm.elements.new_password.minLength = 12;
  const passwordSubmit = element("button", "secondary", "更新口令"); passwordSubmit.type = "submit"; passwordForm.append(passwordSubmit);
  passwordForm.addEventListener("submit", (event) => { event.preventDefault(); attempt(async () => {
    await request("PATCH", "/api/users/me/password", Object.fromEntries(new FormData(passwordForm)));
    notice("口令已更新，请重新登录"); showLogin();
  }); });
  passwordSection.append(passwordForm);
  stack.append(passwordSection);
  if (state.view === "settings") view.append(stack);
}

function renderAccounts(accounts, field) {
  const section = element("section", "settings-section"), form = element("form", "account-form");
  section.append(title("账号管理"));
  form.append(field("新账号", "text", "username"), field("初始口令", "password", "password"), field("管理员口令", "password", "admin_password"));
  form.elements.username.required = true;
  form.elements.username.pattern = "[a-z][a-z0-9_.-]{2,31}";
  form.elements.password.required = true;
  form.elements.password.minLength = 12;
  form.elements.admin_password.required = true;
  const submit = element("button", "secondary", "创建账号"); submit.type = "submit"; form.append(submit);
  form.addEventListener("submit", (event) => { event.preventDefault(); attempt(async () => {
    await request("POST", "/api/users", Object.fromEntries(new FormData(form)));
    notice("账号已创建"); navigate("settings");
  }); });
  section.append(form, table(["账号", "权限", "状态", "操作"], accounts, (account) => {
    const actions = element("div", "row-actions");
    if (!account.is_admin) {
      actions.append(action(account.is_active ? "停用" : "启用", () => attempt(async () => {
        const password = form.elements.admin_password.value;
        if (!password) throw new Error("请输入管理员口令");
        await request("PATCH", `/api/users/${account.id}/status`, { is_active: !account.is_active, admin_password: password });
        notice("账号状态已更新"); navigate("settings");
      }), "text-button"));
      actions.append(action("重置口令", () => openPasswordDialog(account), "text-button"));
    }
    return row(account.username, account.is_admin ? "管理员" : "普通用户", account.is_active ? "启用" : "停用", actions);
  }));
  return section;
}

function openPasswordDialog(account) {
  const dialog = element("dialog", "editor-dialog"), form = element("form", "password-dialog");
  form.append(title(`重置 ${account.username} 的口令`));
  const newLabel = element("label", "", "新口令"), newPassword = element("input");
  newPassword.type = "password"; newPassword.minLength = 12; newPassword.required = true; newPassword.autocomplete = "new-password"; newLabel.append(newPassword);
  const adminLabel = element("label", "", "管理员口令"), adminPassword = element("input");
  adminPassword.type = "password"; adminPassword.required = true; adminPassword.autocomplete = "current-password"; adminLabel.append(adminPassword);
  const controls = element("div", "dialog-actions"), cancel = action("取消", () => dialog.close());
  const submit = element("button", "primary", "更新口令"); submit.type = "submit";
  controls.append(cancel, submit); form.append(newLabel, adminLabel, controls); dialog.append(form);
  dialog.addEventListener("close", () => dialog.remove(), { once: true });
  form.addEventListener("submit", (event) => { event.preventDefault(); attempt(async () => {
    await request("PATCH", `/api/users/${account.id}/password`, { new_password: newPassword.value, admin_password: adminPassword.value });
    dialog.close(); notice("口令已重置");
  }); });
  document.body.append(dialog); dialog.showModal(); newPassword.focus();
}

$("#login-form").addEventListener("submit", (event) => { event.preventDefault();
  attempt(async () => {
    const result = await request("POST", "/api/login", { username: $("#login-username").value.trim(), password: $("#login-password").value });
    state.csrf = result.csrf_token; state.user = result.user; $("#login-password").value = ""; $("#login-error").textContent = ""; showApp();
  });
});
$("#logout").addEventListener("click", () => attempt(async () => { await request("POST", "/api/logout"); showLogin(); }));
$("#cancel-host").addEventListener("click", () => $("#host-dialog").close());
$("#close-host").addEventListener("click", () => $("#host-dialog").close());
for (const [id, text] of Object.entries({ workbench: "工作台", jobs: "任务", reports: "报告", hosts: "主机", settings: "设置" })) {
  const item = action(text, () => navigate(id));
  item.dataset.view = id;
  $("#nav-items").append(item);
}
fetch("/api/session", { credentials: "same-origin" }).then(async (response) => {
  if (response.status === 401) { showLogin(); return; }
  if (!response.ok) throw new Error("无法读取登录状态");
  const result = await response.json();
  state.csrf = result.csrf_token; state.user = result.user;
  showApp();
}).catch(() => showLogin());
