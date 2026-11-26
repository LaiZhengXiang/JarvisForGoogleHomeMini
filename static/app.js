// JARVIS dashboard - talks to the FastAPI server in server.py.

const $ = (id) => document.getElementById(id);
const messages = $("messages");
const chatInput = $("chat-input");
const speakToggle = $("speak-toggle");

let shown = 0;         // how many history messages are on screen
let chatting = false;  // true while waiting for a chat reply

// ---------- small helpers ----------
async function api(path, body) {
  const res = await fetch(path, body === undefined ? {} : {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Error ${res.status}`);
  return data;
}

function addMessage(role, text) {
  $("empty")?.remove();
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  const who = document.createElement("span");
  who.className = "who";
  who.textContent = role === "user" ? "YOU" : role === "jarvis" ? "JARVIS" : "PROBLEM";
  div.append(who, document.createTextNode(text));  // textContent-style: never runs HTML
  messages.append(div);
  messages.scrollTop = messages.scrollHeight;
  return div;
}

function showTyping() {
  const div = addMessage("jarvis", "");
  div.lastChild.remove();
  div.insertAdjacentHTML("beforeend", '<span class="typing"><span></span><span></span><span></span></span>');
  return div;
}

function autoGrow(el) {
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 160) + "px";
}

// ---------- chat ----------
$("chat-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = chatInput.value.trim();
  if (!text) return;

  chatInput.value = "";
  autoGrow(chatInput);
  addMessage("user", text);
  const typing = showTyping();
  chatting = true;  // pause the history check so this message isn't shown twice
  document.body.classList.add("thinking");
  $("send-btn").disabled = true;

  try {
    const { reply } = await api("/api/chat", { message: text, speak: speakToggle.checked });
    typing.remove();
    addMessage("jarvis", reply);
  } catch (err) {
    typing.remove();
    addMessage("error", err.message);
  } finally {
    try { shown = (await api("/api/history")).history.length; } catch {}
    chatting = false;
    document.body.classList.remove("thinking");
    $("send-btn").disabled = false;
    chatInput.focus();
  }
});

chatInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {  // isComposing: don't send mid-拼音
    e.preventDefault();
    $("chat-form").requestSubmit();
  }
});
chatInput.addEventListener("input", () => autoGrow(chatInput));

$("clear-btn").addEventListener("click", async () => {
  await api("/api/history/clear", {});
  messages.innerHTML = "";
  shown = 0;
  addMessage("jarvis", "Fresh start. What's on your mind?");
});

// Remember the "Speak replies" switch on this browser.
try {
  speakToggle.checked = localStorage.getItem("jarvis-speak") !== "off";
} catch {}
speakToggle.addEventListener("change", () => {
  try { localStorage.setItem("jarvis-speak", speakToggle.checked ? "on" : "off"); } catch {}
});

// ---------- say this ----------
$("say-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = $("say-input").value.trim();
  const note = $("say-note");
  if (!text) return;

  $("say-btn").disabled = true;
  note.className = "note";
  note.textContent = "Speaking…";
  try {
    await api("/api/say", { text });
    note.className = "note ok";
    note.textContent = "✓ Said it.";
    $("say-input").value = "";
  } catch (err) {
    note.className = "note bad";
    note.textContent = err.message;
  } finally {
    $("say-btn").disabled = false;
  }
});

// ---------- status light ----------
async function refreshStatus() {
  const box = $("status");
  try {
    const s = await api("/api/status");
    box.className = "status " + (s.speaker ? "ok" : "idle");
    $("status-text").textContent = s.speaker ? s.speaker : "Speaker not connected yet";
  } catch {
    box.className = "status down";
    $("status-text").textContent = "JARVIS is offline";
  }
}

// ---------- start ----------


function renderMessage(m, prev) {
  const div = addMessage(m.role === "user" ? "user" : "jarvis", m.content);
  // A JARVIS message that doesn't follow one of yours = he started it himself (a yap).
  if (m.role !== "user" && (!prev || prev.role !== "user")) {
    div.classList.add("yap");
    div.querySelector(".who").textContent = "JARVIS · dropped by";
  }
}

async function loadHistory() {
  if (chatting) return;
  try {
    const { history } = await api("/api/history");
    for (let i = shown; i < history.length; i++) renderMessage(history[i], history[i - 1]);
    shown = history.length;
  } catch {}
}

// ---------- yapper ----------
async function refreshYapper() {
  try {
    const y = await api("/api/yapper");
    $("yap-toggle").checked = y.settings.enabled;
    $("yap-card").classList.toggle("off", !y.settings.enabled);
    let line = `Today: ${y.yaps_today} yap${y.yaps_today === 1 ? "" : "s"}. `;
    if (!y.settings.enabled) line += "Yapper is off.";
    else if (y.next_at) {
      const mins = Math.round((new Date(y.next_at) - Date.now()) / 60000);
      line += mins <= 0 ? "Next one any moment…" : `Next one in about ${mins} min.`;
    }
    $("yap-next").textContent = line;
  } catch {}
}

$("yap-toggle").addEventListener("change", async () => {
  await api("/api/yapper/settings", { enabled: $("yap-toggle").checked });
  refreshYapper();
});

$("yap-btn").addEventListener("click", async () => {
  const note = $("yap-note");
  $("yap-btn").disabled = true;
  note.className = "note";
  note.textContent = "JARVIS is thinking of something to say…";
  try {
    await api("/api/yapper/now", { topic: $("yap-topic").value || null });
    // the yap lands in the chat a few seconds later (picked up by the history check)
    setTimeout(() => { note.textContent = ""; $("yap-btn").disabled = false; }, 6000);
  } catch (err) {
    note.className = "note bad";
    note.textContent = err.message;
    $("yap-btn").disabled = false;
  }
});

loadHistory();
refreshStatus();
refreshYapper();
setInterval(refreshStatus, 10000);
setInterval(() => { loadHistory(); refreshYapper(); }, 5000);  // pick up yaps JARVIS starts himself
chatInput.focus();
