// JARVIS HUD - talks to the FastAPI server in server.py.

const $ = (id) => document.getElementById(id);
const messages = $("messages");
const chatInput = $("chat-input");
const speakToggle = $("speak-toggle");

let shown = 0;         // how many history messages are on screen
let chatting = false;  // true while waiting for a chat reply
let speakTimer = null;

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

// ---------- the core: idle / thinking / speaking ----------
const LABELS = { idle: "STANDING BY", thinking: "PROCESSING", speaking: "SPEAKING" };

function setState(state) {
  document.body.classList.remove("idle", "thinking", "speaking");
  document.body.classList.add(state);
  $("core-label").textContent = LABELS[state];
}

// The Home Mini doesn't tell us when it stops talking, so guess from the length of the text.
function speakFor(text) {
  clearTimeout(speakTimer);
  setState("speaking");
  const seconds = Math.min(40, 1.5 + text.length * 0.065);
  speakTimer = setTimeout(() => setState("idle"), seconds * 1000);
}

let typeTimer = null;
function showCaption(text) {
  const el = $("caption");
  clearInterval(typeTimer);
  el.textContent = "";
  el.classList.add("typing");
  let i = 0;
  typeTimer = setInterval(() => {
    i += 2;
    el.textContent = text.slice(0, i);
    if (i >= text.length) { clearInterval(typeTimer); el.classList.remove("typing"); }
  }, 18);
}

// Draw the tick marks around the core and the waveform bars (once).
(function buildCore() {
  const g = $("ticks");
  for (let i = 0; i < 72; i++) {
    const long = i % 6 === 0;
    const a = (i / 72) * Math.PI * 2;
    const r1 = 150, r2 = long ? 162 : 157;
    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("x1", 200 + r1 * Math.cos(a)); line.setAttribute("y1", 200 + r1 * Math.sin(a));
    line.setAttribute("x2", 200 + r2 * Math.cos(a)); line.setAttribute("y2", 200 + r2 * Math.sin(a));
    if (long) line.classList.add("long");
    g.append(line);
  }
  const wave = $("wave");
  for (let i = 0; i < 28; i++) {
    const bar = document.createElement("span");
    const middle = 1 - Math.abs(i - 13.5) / 14;  // taller in the middle
    bar.style.setProperty("--h", `${8 + middle * 24 + Math.random() * 6}px`);
    bar.style.animationDelay = `${(Math.random() * 0.6).toFixed(2)}s`;
    wave.append(bar);
  }
})();

// ---------- transcript ----------
function addMessage(role, text) {
  $("empty")?.remove();
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  const who = document.createElement("span");
  who.className = "who";
  who.textContent = role === "user" ? "ALEX" : role === "jarvis" ? "JARVIS" : "SYSTEM";
  div.append(who, document.createTextNode(text));  // plain text: never runs HTML
  messages.append(div);
  messages.scrollTop = messages.scrollHeight;
  return div;
}

function autoGrow(el) {
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 140) + "px";
}

// ---------- chat ----------
$("chat-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = chatInput.value.trim();
  if (!text) return;

  chatInput.value = "";
  autoGrow(chatInput);
  addMessage("user", text);
  chatting = true;  // pause the history check so this message isn't shown twice
  setState("thinking");
  showCaption("…");
  $("send-btn").disabled = true;

  try {
    const { reply } = await api("/api/chat", { message: text, speak: speakToggle.checked });
    addMessage("jarvis", reply);
    showCaption(reply);
    if (speakToggle.checked) speakFor(reply); else setState("idle");
  } catch (err) {
    addMessage("error", err.message);
    showCaption("I couldn't answer that one. " + err.message);
    setState("idle");
  } finally {
    try { shown = (await api("/api/history")).history.length; } catch {}
    chatting = false;
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
  showCaption("Fresh start. What's on your mind, Alex?");
});

try { speakToggle.checked = localStorage.getItem("jarvis-speak") !== "off"; } catch {}
speakToggle.addEventListener("change", () => {
  try { localStorage.setItem("jarvis-speak", speakToggle.checked ? "on" : "off"); } catch {}
});

// History: on start, and every few seconds to catch yaps JARVIS starts himself.
async function loadHistory(first = false) {
  if (chatting) return;
  try {
    const { history } = await api("/api/history");
    for (let i = shown; i < history.length; i++) {
      const m = history[i], prev = history[i - 1];
      const div = addMessage(m.role === "user" ? "user" : "jarvis", m.content);
      // A JARVIS message that doesn't follow one of yours = he started it himself (a yap).
      if (m.role !== "user" && (!prev || prev.role !== "user")) {
        div.classList.add("yap");
        div.querySelector(".who").textContent = "JARVIS · DROPPED BY";
        if (!first) { showCaption(m.content); speakFor(m.content); }
      }
    }
    shown = history.length;
  } catch {}
}

// ---------- say this ----------
$("say-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = $("say-input").value.trim();
  const note = $("say-note");
  if (!text) return;

  $("say-btn").disabled = true;
  note.className = "note";
  note.textContent = "BROADCASTING…";
  speakFor(text);
  showCaption(text);
  try {
    await api("/api/say", { text });
    note.className = "note ok";
    note.textContent = "✓ DELIVERED";
    $("say-input").value = "";
  } catch (err) {
    note.className = "note bad";
    note.textContent = err.message;
    setState("idle");
  } finally {
    $("say-btn").disabled = false;
  }
});

// ---------- yapper ----------
async function refreshYapper() {
  try {
    const y = await api("/api/yapper");
    $("yap-toggle").checked = y.settings.enabled;
    $("yap-card").classList.toggle("off", !y.settings.enabled);
    let line = `TODAY: ${y.yaps_today} · `;
    if (!y.settings.enabled) line += "OFFLINE";
    else if (y.next_at) {
      const mins = Math.round((new Date(y.next_at) - Date.now()) / 60000);
      line += mins <= 0 ? "NEXT: ANY MOMENT" : mins < 120 ? `NEXT IN ~${mins} MIN` : `NEXT AT ${y.next_at.slice(11, 16)}`;
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
  note.textContent = "THINKING OF SOMETHING…";
  setState("thinking");
  try {
    await api("/api/yapper/now", { topic: $("yap-topic").value || null });
    // the yap lands in the transcript a few seconds later (picked up by loadHistory)
    setTimeout(() => { note.textContent = ""; $("yap-btn").disabled = false; }, 6000);
  } catch (err) {
    note.className = "note bad";
    note.textContent = err.message;
    $("yap-btn").disabled = false;
    setState("idle");
  }
});

// ---------- status, clock, weather ----------
async function refreshStatus() {
  const box = $("status");
  try {
    const s = await api("/api/status");
    box.className = "status " + (s.speaker ? "ok" : "idle");
    $("status-text").textContent = s.speaker ? s.speaker.toUpperCase() : "SPEAKER OFFLINE";
  } catch {
    box.className = "status down";
    $("status-text").textContent = "JARVIS OFFLINE";
  }
}

function tickClock() {
  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  $("clock").innerHTML = `${pad(now.getHours())}:${pad(now.getMinutes())}<small>:${pad(now.getSeconds())}</small>`;
  $("date").textContent = now.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" }).toUpperCase();
}

async function refreshWeather() {
  try {
    const w = await api("/api/weather");
    $("wx-temp").textContent = `${w.temp}°`;
    $("wx-desc").textContent = w.desc;
    $("wx-meta").textContent = `FEELS ${w.feels}° · HUM ${w.humidity}% · WIND ${w.wind} KM/H`;
    $("rainbars").innerHTML = w.next_hours.map((h) => {
      const pct = h.rain ?? 0;
      return `<div class="rainbar" title="${h.time}: ${pct}% chance of rain"><span>${pct}%</span><i style="height:${Math.max(4, pct * 0.42)}px"></i><span>${h.time.slice(0, 2)}h</span></div>`;
    }).join("");
  } catch {
    $("wx-desc").textContent = "Weather offline";
  }
}

// ---------- start ----------
loadHistory(true);
refreshStatus();
refreshYapper();
refreshWeather();
tickClock();
setInterval(tickClock, 1000);
setInterval(refreshStatus, 10000);
setInterval(() => { loadHistory(); refreshYapper(); }, 5000);
setInterval(refreshWeather, 10 * 60 * 1000);
chatInput.focus();
