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

// The orb in the middle and the data rain behind everything follow JARVIS's mood.
const orb = window.JarvisOrb($("orb"));
const rain = window.DataRain($("rain"), {
  // the rain swirls around the orb, wherever it is on screen
  focus: () => {
    const r = $("orb").getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
  },
});
const ENERGY = { idle: 0, thinking: 0.35, speaking: 1 };

function setState(state) {
  document.body.classList.remove("idle", "thinking", "speaking");
  document.body.classList.add(state);
  $("core-label").textContent = LABELS[state];
  orb.setMode(state);
  rain.setEnergy(ENERGY[state]);
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

// Draw the waveform bars under the orb (once).
(function buildWave() {
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
    refreshReminders();
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

// ---------- reminders ----------
async function refreshReminders() {
  try {
    const { reminders } = await api("/api/reminders");
    const list = $("rem-list");
    list.innerHTML = "";
    if (!reminders.length) {
      list.innerHTML = '<li class="mono dim small">None yet. Try “remind me in 10 minutes to stretch”.</li>';
      return;
    }
    const today = new Date().toISOString().slice(0, 10);
    for (const r of reminders) {
      const li = document.createElement("li");
      li.className = "rem";
      const when = document.createElement("span");
      when.className = "rem-time";
      when.innerHTML = `${r.time}<small>${r.repeat === "daily" ? "DAILY" : r.date === today ? "TODAY" : r.date.slice(5)}</small>`;
      const text = document.createElement("span");
      text.textContent = r.text.length > 70 ? r.text.slice(0, 70) + "…" : r.text;
      if (r.kind === "think") {
        const tag = document.createElement("span");
        tag.className = "rem-tag";
        tag.textContent = "AI";
        text.append(tag);
      }
      const del = document.createElement("button");
      del.className = "rem-del";
      del.title = "Delete reminder";
      del.setAttribute("aria-label", `Delete reminder at ${r.time}`);
      del.textContent = "×";
      del.addEventListener("click", async () => { await api(`/api/reminders/${r.id}/delete`, {}); refreshReminders(); });
      li.append(when, text, del);
      list.append(li);
    }
  } catch {}
}

$("rem-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const note = $("rem-note");
  try {
    await api("/api/reminders", {
      time: $("rem-time").value,
      text: $("rem-text").value,
      repeat: $("rem-daily").checked ? "daily" : "once",
    });
    $("rem-text").value = "";
    note.className = "note ok";
    note.textContent = "✓ REMINDER SET";
    refreshReminders();
  } catch (err) {
    note.className = "note bad";
    note.textContent = err.message;
  }
  setTimeout(() => { note.textContent = ""; }, 4000);
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
refreshReminders();
refreshStatus();
refreshYapper();
refreshWeather();
tickClock();
setInterval(tickClock, 1000);
setInterval(refreshStatus, 10000);
setInterval(() => { loadHistory(); refreshYapper(); refreshReminders(); }, 5000);
setInterval(refreshWeather, 10 * 60 * 1000);
chatInput.focus();
