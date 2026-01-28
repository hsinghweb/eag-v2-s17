const jobsGrid = document.getElementById("jobsGrid");
const inboxList = document.getElementById("inboxList");
const notesList = document.getElementById("notesList");
const noteTitle = document.getElementById("noteTitle");
const noteBody = document.getElementById("noteBody");
const jobCount = document.getElementById("jobCount");
const inboxCount = document.getElementById("inboxCount");
const notesCount = document.getElementById("notesCount");

const modal = document.getElementById("modal");
const createBtn = document.getElementById("createBtn");
const closeModal = document.getElementById("closeModal");
const cancelModal = document.getElementById("cancelModal");
const scheduleBtn = document.getElementById("scheduleBtn");
const refreshBtn = document.getElementById("refreshBtn");
const themeToggle = document.getElementById("themeToggle");

const tabs = document.querySelectorAll(".tab");
const simpleTab = document.getElementById("simpleTab");
const advancedTab = document.getElementById("advancedTab");

const taskName = document.getElementById("taskName");
const frequency = document.getElementById("frequency");
const timeInput = document.getElementById("time");
const cronInput = document.getElementById("cron");
const instructionsInput = document.getElementById("instructions");

function setTheme(theme) {
  document.body.dataset.theme = theme;
  localStorage.setItem("theme", theme);
}

themeToggle.addEventListener("click", () => {
  const next = document.body.dataset.theme === "dark" ? "light" : "dark";
  setTheme(next);
});

tabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    tabs.forEach((t) => t.classList.remove("active"));
    tab.classList.add("active");
    if (tab.dataset.tab === "simple") {
      simpleTab.classList.add("active");
      advancedTab.classList.remove("active");
    } else {
      advancedTab.classList.add("active");
      simpleTab.classList.remove("active");
    }
  });
});

createBtn.addEventListener("click", () => modal.classList.remove("hidden"));
closeModal.addEventListener("click", () => modal.classList.add("hidden"));
cancelModal.addEventListener("click", () => modal.classList.add("hidden"));

refreshBtn.addEventListener("click", () => {
  loadAll();
});

async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status}`);
  }
  return res.json();
}

function renderJobs(jobs) {
  jobsGrid.innerHTML = "";
  jobCount.textContent = jobs.length;

  if (!jobs.length) {
    jobsGrid.innerHTML = `<div class="list-item">No scheduled jobs yet.</div>`;
    return;
  }

  jobs.forEach((job) => {
    const card = document.createElement("div");
    card.className = "job-card";
    card.innerHTML = `
      <h3>${job.name}</h3>
      <div class="pill">${job.enabled ? "Scheduled" : "Paused"}</div>
      <div class="job-meta">
        <span>Cron: ${job.cron_expression}</span>
        <span>Next: ${job.next_run || "n/a"}</span>
      </div>
      <div class="subtle">${job.query}</div>
    `;
    jobsGrid.appendChild(card);
  });
}

function renderInbox(items) {
  inboxList.innerHTML = "";
  inboxCount.textContent = items.length;

  if (!items.length) {
    inboxList.innerHTML = `<div class="list-item">No inbox items yet.</div>`;
    return;
  }

  items.forEach((item) => {
    const row = document.createElement("div");
    row.className = "list-item";
    row.innerHTML = `
      <strong>${item.title}</strong>
      <div class="subtle">${item.timestamp}</div>
      <div class="subtle">${item.body.slice(0, 140)}...</div>
    `;
    inboxList.appendChild(row);
  });
}

function renderNotes(notes) {
  notesList.innerHTML = "";
  notesCount.textContent = notes.length;

  if (!notes.length) {
    notesList.innerHTML = `<div class="list-item">No notes yet.</div>`;
    return;
  }

  notes.forEach((note) => {
    const row = document.createElement("div");
    row.className = "list-item";
    const button = document.createElement("button");
    button.textContent = note.path;
    button.addEventListener("click", () => openNote(note.path));
    row.appendChild(button);
    notesList.appendChild(row);
  });
}

async function openNote(path) {
  const data = await fetchJson(`/notes/read?path=${encodeURIComponent(path)}`);
  noteTitle.textContent = data.path;
  noteBody.textContent = data.content;
}

function buildCron() {
  const activeTab = document.querySelector(".tab.active").dataset.tab;
  if (activeTab === "advanced") {
    return cronInput.value.trim();
  }
  if (frequency.value === "daily") {
    const [hour, minute] = timeInput.value.split(":");
    return `${minute} ${hour} * * *`;
  }
  return "0 7 * * *";
}

scheduleBtn.addEventListener("click", async () => {
  const name = taskName.value.trim() || "Morning Briefing";
  const cron = buildCron();
  const instructions = instructionsInput.value.trim() || "Summarize overnight news and send a brief to inbox.";

  const safeName = name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  const dateTag = new Date().toISOString().slice(0, 10).replace(/-/g, "");
  const noteHint = `Save the final report to Notes/Scheduler/${safeName}_${dateTag}.md.`;
  const fullQuery = `${instructions}\n\n${noteHint}`;

  await fetch("/cron/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name,
      cron,
      agent_type: "PlannerAgent",
      query: fullQuery,
    }),
  });

  modal.classList.add("hidden");
  taskName.value = "";
  instructionsInput.value = "";
  await loadAll();
});

async function loadAll() {
  try {
    const [jobs, inbox, notes] = await Promise.all([
      fetchJson("/cron/jobs"),
      fetchJson("/inbox?limit=8"),
      fetchJson("/notes/list?limit=10"),
    ]);
    renderJobs(jobs);
    renderInbox(inbox);
    renderNotes(notes);
  } catch (err) {
    console.error(err);
  }
}

const storedTheme = localStorage.getItem("theme") || "dark";
setTheme(storedTheme);
loadAll();
