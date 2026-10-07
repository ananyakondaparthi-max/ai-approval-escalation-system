// ================= LOGIN & SESSION =================
let token = localStorage.getItem("token");

// Reads the user's id and role from the login token
function getUser() {
  if (!token) return null;
  try {
    const part = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const payload = JSON.parse(atob(part));
    if (payload.exp && payload.exp * 1000 < Date.now()) return null; // expired
    return payload; // { sub: user id, role: "employee" / "manager" / "admin" }
  } catch { return null; }
}

// Sends a request to the backend with the login token attached
async function api(path, method = "GET", body = null) {
  const res = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json", "Authorization": "Bearer " + token },
    body: body ? JSON.stringify(body) : null,
  });
  if (res.status === 401) { logout(); throw new Error("Session expired. Please log in again."); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(errorText(data) || "Error " + res.status);
  return data;
}

function errorText(data) {
  if (typeof data.detail === "string") return data.detail;
  if (Array.isArray(data.detail)) return data.detail.map(d => d.loc.slice(-1)[0] + ": " + d.msg).join(", ");
  return "";
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

document.getElementById("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const err = document.getElementById("login-error");
  err.textContent = "";
  const email = document.getElementById("login-email").value;
  const form = new URLSearchParams();
  form.append("username", email);
  form.append("password", document.getElementById("login-password").value);
  try {
    const res = await fetch("/auth/token", { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok) throw new Error(errorText(data) || "Login failed");
    token = data.access_token;
    localStorage.setItem("token", token);
    localStorage.setItem("email", email);
    start();
  } catch (ex) { err.textContent = ex.message; }
});

function logout() {
  token = null;
  localStorage.removeItem("token");
  localStorage.removeItem("email");
  document.getElementById("app-view").classList.add("hidden");
  document.getElementById("login-view").classList.remove("hidden");
}

function start() {
  const user = getUser();
  if (!user) { logout(); return; }
  document.getElementById("login-view").classList.add("hidden");
  document.getElementById("app-view").classList.remove("hidden");
  document.getElementById("user-info").textContent =
    (localStorage.getItem("email") || "") + " · " + user.role;
  showPage("home");
}

function showPage(name) {
  document.querySelectorAll(".page").forEach(p => p.classList.add("hidden"));
  document.getElementById("page-" + name).classList.remove("hidden");
  if (name === "po") loadPOs();
}

// ================= PURCHASE ORDERS =================
function addItemRow() {
  const row = document.createElement("div");
  row.className = "item-row";
  row.innerHTML = `
    <input class="i-name" placeholder="Item name" required>
    <input class="i-desc" placeholder="Item description">
    <input class="i-qty" type="number" min="1" value="1" placeholder="Qty" required>
    <input class="i-price" type="number" min="0" step="0.01" placeholder="Unit price" required>
    <button type="button" class="btn small" onclick="this.parentElement.remove(); updateTotal()">✕</button>`;
  row.querySelectorAll("input").forEach(i => i.addEventListener("input", updateTotal));
  document.getElementById("po-items").appendChild(row);
}

function updateTotal() {
  let total = 0;
  document.querySelectorAll(".item-row").forEach(r => {
    total += (+r.querySelector(".i-qty").value || 0) * (+r.querySelector(".i-price").value || 0);
  });
  document.getElementById("po-total").textContent = total.toFixed(2);
}

// Remembers POs this user created (employees can't list all POs)
function myPOKey() { return "my_pos_" + getUser().sub; }
function rememberPO(id) {
  const ids = JSON.parse(localStorage.getItem(myPOKey()) || "[]");
  if (!ids.includes(id)) ids.unshift(id);
  localStorage.setItem(myPOKey(), JSON.stringify(ids));
}

document.getElementById("po-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  const msg = document.getElementById("po-msg");
  const items = [...document.querySelectorAll(".item-row")].map(r => ({
    item_name: r.querySelector(".i-name").value,
    item_description: r.querySelector(".i-desc").value,
    quantity: +r.querySelector(".i-qty").value,
    unit_price: +r.querySelector(".i-price").value,
  }));
  if (!items.length) { msg.textContent = "Add at least one item."; return; }
  try {
    const po = await api("/purchase-orders/", "POST", {
      department: f.department.value,
      vendor_name: f.vendor_name.value,
      vendor_email: f.vendor_email.value,
      vendor_phone: f.vendor_phone.value,
      purpose: f.purpose.value,
      description: f.description.value,
      items,
    });
    rememberPO(po.id);
    msg.textContent = `Saved ${po.po_number} as a draft. Click "Submit" in the list below to send it for approval.`;
    f.reset();
    document.getElementById("po-items").innerHTML = "";
    addItemRow();
    updateTotal();
    loadPOs();
  } catch (ex) { msg.textContent = ex.message; }
});

async function loadPOs() {
  const list = document.getElementById("po-list");
  const user = getUser();
  list.innerHTML = '<p class="muted">Loading...</p>';
  let pos;
  try {
    pos = await api("/purchase-orders/");               // managers / admins
  } catch {
    const ids = JSON.parse(localStorage.getItem(myPOKey()) || "[]"); // employees
    pos = (await Promise.all(ids.map(id => api("/purchase-orders/" + id).catch(() => null))))
      .filter(Boolean);
  }
  if (!pos.length) { list.innerHTML = '<p class="muted">No purchase orders yet.</p>'; return; }

  list.innerHTML = pos.map(po => {
    const canSubmit = po.status === "DRAFT" && po.requester_id === user.sub;
    const canApprove = po.status === "PENDING_APPROVAL" &&
      (po.approver_id === user.sub || user.role === "admin");
    return `
      <div class="po-row">
        <div>
          <b>${esc(po.po_number)}</b> · ${esc(po.vendor_name)} · ₹${po.total_amount}
          <div class="muted">${esc(po.purpose)} · ${new Date(po.created_at).toLocaleDateString()}</div>
          ${po.rejection_reason ? `<div class="error">Reason: ${esc(po.rejection_reason)}</div>` : ""}
        </div>
        <div class="actions">
          <span class="badge ${po.status}">${po.status.replace(/_/g, " ")}</span>
          ${canSubmit ? `<button class="btn primary small" onclick="poAction('${po.id}','submit')">Submit</button>` : ""}
          ${canApprove ? `
            <button class="btn approve small" onclick="poAction('${po.id}','approve')">Approve</button>
            <button class="btn reject small" onclick="poAction('${po.id}','reject')">Reject</button>` : ""}
        </div>
      </div>`;
  }).join("");
}

async function poAction(id, action) {
  let body = {};
  if (action === "reject") {
    const reason = prompt("Reason for rejection:");
    if (!reason) return;
    body = { reason: reason, rejection_reason: reason };
  }
  try {
    await api(`/purchase-orders/${id}/${action}`, "POST", body);
    loadPOs();
  } catch (ex) { alert(ex.message); }
}

// ================= START =================
addItemRow();
if (getUser()) start();