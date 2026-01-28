const jobsGrid = document.getElementById("jobsGrid");
const inboxList = document.getElementById("inboxList");
const notesList = document.getElementById("notesList");
const noteTitle = document.getElementById("noteTitle");
const noteBody = document.getElementById("noteBody");
const jobCount = document.getElementById("jobCount");
const inboxCount = document.getElementById("inboxCount");
const notesCount = document.getElementById("notesCount");
const historyList = document.getElementById("historyList");
const historyCount = document.getElementById("historyCount");
const pageTitle = document.getElementById("pageTitle");
const pageSubtitle = document.getElementById("pageSubtitle");

const pages = {
  scheduler: document.getElementById("pageScheduler"),
  inbox: document.getElementById("pageInbox"),
  notes: document.getElementById("pageNotes"),
  settings: document.getElementById("pageSettings"),
};

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

let selectedJobId = null;
let cachedInbox = [];

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

document.querySelectorAll(".nav-item").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".nav-item").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    const page = btn.dataset.page;
    Object.values(pages).forEach((p) => p.classList.remove("active"));
    pages[page].classList.add("active");
    const titles = {
      scheduler: ["Scheduler", "Automate daily tasks and briefings"],
      inbox: ["Inbox", "Latest notifications and summaries"],
      notes: ["Notes", "Saved briefings and reports"],
      settings: ["Settings", "Theme and delivery preferences"],
    };
    pageTitle.textContent = titles[page][0];
    pageSubtitle.textContent = titles[page][1];
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
      <div class="subtle">Last: ${job.last_run || "n/a"}</div>
      <div class="subtle">${job.last_output || ""}</div>
      <div class="subtle">${job.query}</div>
      <div class="job-actions">
        <button data-action="edit">Edit</button>
        <button data-action="history">History</button>
      </div>
    `;
    card.querySelector('[data-action="edit"]').addEventListener("click", () => openEdit(job));
    card.querySelector('[data-action="history"]').addEventListener("click", () => showHistory(job.id));
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

function showHistory(jobId) {
  selectedJobId = jobId;
  const matches = cachedInbox.filter((item) => item.metadata && item.metadata.job_id === jobId);
  historyList.innerHTML = "";
  historyCount.textContent = matches.length;
  if (!matches.length) {
    historyList.innerHTML = `<div class="list-item">No history yet for this job.</div>`;
    return;
  }
  matches.forEach((item) => {
    const row = document.createElement("div");
    row.className = "list-item";
    row.innerHTML = `
      <strong>${item.title}</strong>
      <div class="subtle">${item.timestamp}</div>
      <div class="subtle">${item.body.slice(0, 160)}...</div>
    `;
    historyList.appendChild(row);
  });
}

function openEdit(job) {
  modal.classList.remove("hidden");
  taskName.value = job.name;
  cronInput.value = job.cron_expression || "0 7 * * *";
  instructionsInput.value = job.query;
  document.querySelector('[data-tab="advanced"]').click();
  scheduleBtn.dataset.editing = job.id;
  scheduleBtn.textContent = "Save Changes";
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

  const payload = {
    name,
    cron,
    agent_type: "PlannerAgent",
    query: fullQuery,
  };
  const editingId = scheduleBtn.dataset.editing;
  if (editingId) {
    await fetch(`/cron/jobs/${editingId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } else {
    await fetch("/cron/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  }

  modal.classList.add("hidden");
  scheduleBtn.dataset.editing = "";
  scheduleBtn.textContent = "Schedule Task";
  taskName.value = "";
  instructionsInput.value = "";
  await loadAll();
});

async function loadAll() {
  try {
    const [jobs, inbox, notes] = await Promise.all([
      fetchJson("/cron/jobs"),
      fetchJson("/inbox?limit=50"),
      fetchJson("/notes/list?limit=10"),
    ]);
    renderJobs(jobs);
    cachedInbox = inbox;
    renderInbox(inbox);
    renderNotes(notes);
    if (selectedJobId) {
      showHistory(selectedJobId);
    }
  } catch (err) {
    console.error(err);
  }
}

const storedTheme = localStorage.getItem("theme") || "dark";
setTheme(storedTheme);
loadAll();
