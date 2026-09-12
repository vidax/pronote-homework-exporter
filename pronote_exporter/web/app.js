"use strict";

const elements = {
  studentLine: document.querySelector("#student-line"),
  syncLabel: document.querySelector("#sync-label"),
  statusDot: document.querySelector("#status-dot"),
  weekTitle: document.querySelector("#week-title"),
  weekGrid: document.querySelector("#week-grid"),
  notice: document.querySelector("#notice"),
  totalCount: document.querySelector("#total-count"),
  pendingCount: document.querySelector("#pending-count"),
  completedCount: document.querySelector("#completed-count"),
  previousWeek: document.querySelector("#previous-week"),
  currentWeek: document.querySelector("#current-week"),
  nextWeek: document.querySelector("#next-week"),
};

const today = atNoon(new Date());
const requestedWeek = parseDate(new URLSearchParams(window.location.search).get("week"));
const state = {
  document: null,
  weekStart: startOfWeek(requestedWeek || today),
};

function atNoon(value) {
  const date = new Date(value);
  date.setHours(12, 0, 0, 0);
  return date;
}

function parseDate(value) {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return null;
  }
  const [year, month, day] = value.split("-").map(Number);
  const date = new Date(year, month - 1, day, 12);
  return Number.isNaN(date.getTime()) ? null : date;
}

function dateKey(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function addDays(date, amount) {
  const result = atNoon(date);
  result.setDate(result.getDate() + amount);
  return result;
}

function startOfWeek(date) {
  const result = atNoon(date);
  const offset = (result.getDay() + 6) % 7;
  result.setDate(result.getDate() - offset);
  return result;
}

function sameDay(first, second) {
  return dateKey(first) === dateKey(second);
}

function createElement(tagName, className, text) {
  const element = document.createElement(tagName);
  if (className) {
    element.className = className;
  }
  if (text !== undefined) {
    element.textContent = text;
  }
  return element;
}

function showLoading() {
  elements.weekGrid.replaceChildren();
  for (let index = 0; index < 5; index += 1) {
    elements.weekGrid.append(createElement("div", "loading-column"));
  }
  elements.weekGrid.setAttribute("aria-busy", "true");
}

function safeColor(value) {
  return /^#[0-9a-f]{6}$/i.test(value || "") ? value : "#315d4f";
}

function safeLink(value) {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

function homeworkCard(homework) {
  const card = createElement("article", "homework-card");
  card.style.setProperty("--subject-color", safeColor(homework.color));
  if (homework.done) {
    card.classList.add("is-done");
  }

  const topLine = createElement("div", "card-topline");
  topLine.append(createElement("h3", "subject-name", homework.subject || "Homework"));
  if (homework.done) {
    topLine.append(createElement("span", "done-badge", "Done"));
  }
  card.append(topLine);
  card.append(
    createElement(
      "p",
      "homework-description",
      homework.description || "No description provided."
    )
  );

  if (Array.isArray(homework.attachments) && homework.attachments.length > 0) {
    const list = createElement("ul", "attachment-list");
    homework.attachments.forEach((attachment) => {
      const item = document.createElement("li");
      const href = safeLink(attachment.url);
      if (href) {
        const link = createElement("a", "", `Attachment · ${attachment.name || "Open"}`);
        link.href = href;
        link.target = "_blank";
        link.rel = "noreferrer noopener";
        item.append(link);
      } else {
        item.append(
          createElement("span", "", `Attachment · ${attachment.name || "File"}`)
        );
      }
      list.append(item);
    });
    card.append(list);
  }
  return card;
}

function dayColumn(date, homework) {
  const column = createElement("article", "day-column");
  if (sameDay(date, today)) {
    column.classList.add("is-today");
  }

  const header = createElement("header", "day-header");
  const words = document.createElement("div");
  words.append(
    createElement(
      "span",
      "weekday",
      new Intl.DateTimeFormat(undefined, { weekday: "long" }).format(date)
    )
  );
  words.append(
    createElement(
      "span",
      "day-month",
      new Intl.DateTimeFormat(undefined, { month: "long" }).format(date)
    )
  );
  header.append(words);
  header.append(createElement("span", "day-number", String(date.getDate())));
  column.append(header);

  const content = createElement("div", "day-content");
  if (homework.length === 0) {
    content.append(createElement("p", "empty-day", "Nothing due"));
  } else {
    homework.forEach((item) => content.append(homeworkCard(item)));
  }
  column.append(content);
  return column;
}

function setNotice(message) {
  elements.notice.textContent = message || "";
  elements.notice.hidden = !message;
}

function updateNavigation(range) {
  const previousFriday = dateKey(addDays(state.weekStart, -3));
  const nextMonday = dateKey(addDays(state.weekStart, 7));
  elements.previousWeek.disabled = Boolean(range && previousFriday < range.from);
  elements.nextWeek.disabled = Boolean(range && nextMonday > range.to);
  elements.currentWeek.disabled = sameDay(state.weekStart, startOfWeek(today));
}

function updateAddress() {
  const url = new URL(window.location.href);
  if (sameDay(state.weekStart, startOfWeek(today))) {
    url.searchParams.delete("week");
  } else {
    url.searchParams.set("week", dateKey(state.weekStart));
  }
  window.history.replaceState({}, "", url);
}

function render() {
  if (!state.document) {
    return;
  }

  const friday = addDays(state.weekStart, 4);
  const rangeFormatter = new Intl.DateTimeFormat(undefined, {
    day: "numeric",
    month: "long",
    year: state.weekStart.getFullYear() !== friday.getFullYear() ? "numeric" : undefined,
  });
  const fridayFormatter = new Intl.DateTimeFormat(undefined, {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
  elements.weekTitle.textContent = `${rangeFormatter.format(state.weekStart)} — ${fridayFormatter.format(friday)}`;

  const first = dateKey(state.weekStart);
  const last = dateKey(friday);
  const weeklyHomework = state.document.homework.filter(
    (item) => item.due >= first && item.due <= last
  );
  const pending = weeklyHomework.filter((item) => !item.done).length;
  elements.totalCount.textContent = String(weeklyHomework.length);
  elements.pendingCount.textContent = String(pending);
  elements.completedCount.textContent = String(weeklyHomework.length - pending);

  elements.weekGrid.replaceChildren();
  for (let index = 0; index < 5; index += 1) {
    const day = addDays(state.weekStart, index);
    const key = dateKey(day);
    elements.weekGrid.append(
      dayColumn(
        day,
        weeklyHomework.filter((item) => item.due === key)
      )
    );
  }
  elements.weekGrid.setAttribute("aria-busy", "false");

  const range = state.document.range;
  if (range && (first < range.from || last > range.to)) {
    setNotice(
      `The cached snapshot covers ${range.from} through ${range.to}; part of this week is outside that range.`
    );
  } else {
    setNotice("");
  }
  updateNavigation(range);
  updateAddress();
}

function setConnection(status, message) {
  elements.syncLabel.textContent = message;
  elements.statusDot.classList.toggle("is-online", status === "online");
  elements.statusDot.classList.toggle("is-error", status === "error");
}

async function loadHomework() {
  setConnection("loading", "Loading the latest snapshot");
  try {
    const response = await fetch("/planner.json", { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`The homework service returned HTTP ${response.status}.`);
    }

    const document = await response.json();
    if (!document || document.schema_version !== 1 || !Array.isArray(document.homework)) {
      throw new Error("The homework snapshot has an unsupported format.");
    }

    state.document = document;
    const student = document.student || {};
    elements.studentLine.textContent = [student.name, student.class, student.establishment]
      .filter(Boolean)
      .join(" · ") || "Weekly homework planner";
    const generated = new Date(document.generated_at);
    const formatted = Number.isNaN(generated.getTime())
      ? "Snapshot loaded"
      : `Updated ${new Intl.DateTimeFormat(undefined, {
          dateStyle: "medium",
          timeStyle: "short",
        }).format(generated)}`;
    setConnection("online", formatted);
    render();
    return true;
  } catch (error) {
    setConnection("error", "The homework service is unavailable");
    setNotice(error instanceof Error ? error.message : "Unable to load homework.");
    elements.weekGrid.setAttribute("aria-busy", "false");
    return false;
  }
}

elements.previousWeek.addEventListener("click", () => {
  state.weekStart = addDays(state.weekStart, -7);
  render();
});

elements.nextWeek.addEventListener("click", () => {
  state.weekStart = addDays(state.weekStart, 7);
  render();
});

elements.currentWeek.addEventListener("click", () => {
  state.weekStart = startOfWeek(today);
  render();
});

showLoading();
loadHomework();
