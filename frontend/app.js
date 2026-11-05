// What the page DOES. JavaScript runs inside the browser. The plan:
//   1. when the page loads, ask the server for tasks and daily tasks and draw them;
//   2. when you click, drag or submit a form, send it to the server, then ask again and redraw.
// The stopwatch maths lives in timer.js (loaded before this file), so its functions are available here.
//
// Ideas you have not met in C++:
//   - The DOM: the browser keeps the page as a tree of objects (one per tag). JavaScript can
//     find them with document.getElementById("...") and change them.
//   - async / await: asking the server takes time (it is a network call). `await` means
//     "pause THIS function until the answer arrives, but keep the page responsive".
//     A function that uses await must be declared `async`.
//   - drag and drop: the browser tells us when a row starts being dragged, when it is held over a
//     list, and when it is let go (the "drop"). See the section "dragging tasks" below.
//
// Also: `const` is a variable that is never reassigned, `let` is one that can be.


// ---------- what the page remembers while it is open ----------

let timer = null;        // the stopwatch in use (see timer.js), or null when nothing is running
let lastTasks = [];      // the open tasks from the last time we asked the server
let planIds = [];        // ids of the tasks in "Today's plan" (column 3), in order
let fullPredicted = {};  // task id -> predicted minutes for the WHOLE task, from the last "Make plan"
let planBudget = null;   // the minutes you typed when you made the plan, or null
let planNote = "";       // "Predictor used: ..." text shown under the plan
let planSlice = {};      // task id -> {minutes, percent}: a task planned only PARTLY, to fill the spare minutes

const TIMER_KEY = "focusflow-timer";
const PLAN_KEY = "focusflow-plan";


// ---------- keeping the stopwatch and the plan across a page reload ----------
// localStorage is a small store inside the browser. Saving things there means a refresh (or closing
// the tab by accident) does not lose them. It can be unavailable (for example in a private window),
// so every use is wrapped in try/catch.

function saveTimer() {
  try {
    if (timer === null) {
      localStorage.removeItem(TIMER_KEY);
    } else {
      localStorage.setItem(TIMER_KEY, JSON.stringify(timer));
    }
  } catch (error) {
    // Not saving is fine: the timer still works until the page is closed.
  }
}

function loadTimer() {
  try {
    const text = localStorage.getItem(TIMER_KEY);
    if (text === null) {
      return null;
    }
    const saved = JSON.parse(text);
    if (typeof saved.taskId === "number" && typeof saved.state === "string" && typeof saved.elapsedMs === "number") {
      return saved;
    }
  } catch (error) {
    // Unreadable data: behave as if nothing was saved.
  }
  return null;
}

function savePlan() {
  try {
    localStorage.setItem(PLAN_KEY, JSON.stringify({
      ids: planIds, full: fullPredicted, budget: planBudget, note: planNote, slice: planSlice,
    }));
  } catch (error) {
    // Not saving is fine.
  }
}

function loadPlan() {
  try {
    const text = localStorage.getItem(PLAN_KEY);
    if (text === null) {
      return;
    }
    const saved = JSON.parse(text);
    if (Array.isArray(saved.ids)) {
      planIds = saved.ids;
      fullPredicted = saved.full || {};
      planBudget = saved.budget === undefined ? null : saved.budget;
      planNote = saved.note || "";
      planSlice = saved.slice || {};
    }
  } catch (error) {
    // Unreadable data: start with an empty plan.
  }
}


// ---------- talking to the server ----------

// Sends a request and returns the answer already converted from JSON text into an object.
// If the server answers with an error (400s/500s), this throws an Error carrying a readable message.
async function api(method, path, body) {
  const options = { method: method, headers: {} };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);   // object -> JSON text
  }
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(describeError(data));
  }
  return data;
}

// The server reports errors in two shapes: {"detail": "text"} or, for a rule broken in a form,
// {"detail": [{"loc": ["body","priority"], "msg": "..."}]}. Turn either into one line.
function describeError(data) {
  if (typeof data.detail === "string") {
    return data.detail;
  }
  if (Array.isArray(data.detail)) {
    const parts = [];
    for (let i = 0; i < data.detail.length; i++) {
      const item = data.detail[i];
      parts.push(item.loc[item.loc.length - 1] + ": " + item.msg);
    }
    return parts.join("; ");
  }
  return "Something went wrong.";
}


// ---------- small helpers for building the page ----------

// Makes <tag class="className">text</tag>.
// We always set text with `textContent`, never `innerHTML`. textContent shows text exactly as typed,
// so a task named "<script>..." is displayed as plain words instead of being run as code.
function make(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) {
    element.textContent = text;
  }
  if (className !== undefined) {
    element.className = className;
  }
  return element;
}

function clear(element) {
  element.textContent = "";
}

function showMessage(text, isError) {
  const box = document.getElementById("message");
  box.textContent = text;
  box.className = "message " + (isError ? "error" : "ok");
  box.hidden = false;
}

function hideMessage() {
  document.getElementById("message").hidden = true;
}

// "11-06" (month-day is enough in a one-line row), or "no due".
function shortDue(dueDate) {
  if (dueDate === null) {
    return "no due";
  }
  return dueDate.slice(5);
}

// The task with this id from the last list we loaded, or null.
function findTask(taskId) {
  for (let i = 0; i < lastTasks.length; i++) {
    if (lastTasks[i].id === taskId) {
      return lastTasks[i];
    }
  }
  return null;
}

function inPlan(taskId) {
  return planIds.indexOf(taskId) !== -1;
}

// How many minutes this task still needs: the predicted time for the whole task (from the last plan;
// before any plan we only have your own guess) times the share that is left.
function plannedMinutes(task) {
  // A task planned only partly ("do 40% of it") is planned for just that slice of time.
  if (inPlan(task.id) && planSlice[task.id] !== undefined) {
    return planSlice[task.id].minutes;
  }
  let whole = task.guessed_minutes;
  if (fullPredicted[task.id] !== undefined) {
    whole = fullPredicted[task.id];
  }
  return Math.max(1, Math.round(whole * (100 - task.percent_done) / 100));
}


// ---------- drawing one task as ONE line ----------
// zone is "pool" (column 2, not in the plan) or "plan" (column 3).

function makeTaskRow(task, zone) {
  const row = make("li", undefined, "task-row");
  if (timer !== null && timer.taskId === task.id) {
    row.className = "task-row active";
  }
  row.draggable = true;
  row.dataset.taskId = task.id;   // dragging reads this to know which task is being moved
  row.addEventListener("dragstart", onDragStart);
  row.addEventListener("dragend", onDragEnd);

  row.appendChild(make("span", "⋮⋮", "drag"));   // the "grip" dots: a hint that rows can be dragged

  const name = make("span", task.name, "t-name");
  name.title = taskTooltip(task, zone);   // hover for the full details
  row.appendChild(name);
  // The tags are separate from the name: the name is cut off with "..." when the row is tight, the tags never are.
  if (task.recurring) {
    const daily = make("span", "↻", "tag");   // the "repeat" arrow: short, so the row still fits on one line
    daily.title = "Repeats every day";
    row.appendChild(daily);
  }
  if (zone === "plan" && planSlice[task.id] !== undefined) {
    // Just "66%": short enough to keep the row on one line. The tooltip and the message above the plan explain it.
    const part = make("span", planSlice[task.id].percent + "%", "tag part");
    part.title = "Planned as a slice: about " + planSlice[task.id].percent + "% of the whole task, to use your spare minutes";
    row.appendChild(part);
  }

  // category, (your guess,) priority, deadline: kept short, with no spaces, so the whole task fits on one line.
  let details = task.category + "·";
  if (zone === "pool") {
    details = details + task.guessed_minutes + "m·";
  }
  details = details + "P" + task.priority + "·" + shortDue(task.due_date);
  row.appendChild(make("span", details, "t-meta"));

  if (zone === "plan") {
    row.appendChild(make("span", "~" + plannedMinutes(task) + "m", "t-min"));
  }

  // Progress: a tiny bar (an outer box with an inner box as wide as the percentage) and the number.
  const bar = make("span", undefined, "mini-bar");
  const fill = make("span", undefined, "mini-fill");
  fill.style.width = task.percent_done + "%";
  fill.style.display = "block";
  bar.appendChild(fill);
  row.appendChild(bar);
  row.appendChild(make("span", task.percent_done + "%", "t-pct"));

  row.appendChild(makeStartButton(task.id));

  const move = make("button", zone === "pool" ? "→" : "←", "small secondary");
  move.title = zone === "pool" ? "Add to today's plan" : "Move back to all tasks";
  move.dataset.taskId = task.id;
  move.dataset.toPlan = zone === "pool" ? "yes" : "no";
  move.addEventListener("click", onMoveClick);
  row.appendChild(move);

  const log = make("button", "Log", "small secondary");
  log.title = "Log time you worked without the stopwatch";
  log.addEventListener("click", onLogToggle);
  row.appendChild(log);

  row.appendChild(makeManualForm(task));
  return row;
}

function taskTooltip(task, zone) {
  let text = task.name + "\n" + task.category + " · you guessed " + task.guessed_minutes + " min · priority " +
    task.priority + " · " + (task.due_date === null ? "no deadline" : "due " + task.due_date) + "\n" + task.percent_done + "% done, " +
    task.spent_minutes + " min spent so far · worth " + task.value.toFixed(1) + " points";
  if (zone === "plan" && planSlice[task.id] !== undefined) {
    text = text + "\nPlanned as a slice: about " + planSlice[task.id].percent + "% of the task in " +
      planSlice[task.id].minutes + " min, to use your spare time (the whole rest needs about " +
      Math.max(1, Math.round((fullPredicted[task.id] || task.guessed_minutes) * (100 - task.percent_done) / 100)) + " min)";
  } else if (zone === "plan") {
    text = text + "\nExpected about " + plannedMinutes(task) + " min for what is left";
  }
  return text;
}

function makeStartButton(taskId) {
  const button = make("button", "Start", "small start");
  button.dataset.taskId = taskId;   // remember which task this button belongs to
  if (timer !== null) {
    button.disabled = true;
    if (timer.taskId === taskId) {
      button.textContent = "Working";
    }
  }
  button.addEventListener("click", onStartClick);
  return button;
}

// For work you did without the stopwatch: "I worked X minutes and finished Y%". Hidden until you press Log.
function makeManualForm(task) {
  const form = make("form", undefined, "session-form");
  form.hidden = true;
  form.dataset.taskId = task.id;

  const minutes = make("input");
  minutes.type = "number";
  minutes.min = 1;
  minutes.required = true;
  minutes.placeholder = "min";
  minutes.name = "minutes";

  const percent = make("input");
  percent.type = "number";
  percent.min = 1;
  percent.max = 100;
  percent.required = true;
  percent.placeholder = "% done";
  percent.name = "percent";

  form.appendChild(make("span", "I worked", "meta"));
  form.appendChild(minutes);
  form.appendChild(make("span", "min and finished", "meta"));
  form.appendChild(percent);
  form.appendChild(make("span", "%", "meta"));
  form.appendChild(make("button", "Save", "small"));

  form.addEventListener("submit", onManualSubmit);
  return form;
}


// ---------- drawing: the task lists, the plan summary, daily tasks ----------

function drawLists() {
  const pool = document.getElementById("pool-list");
  const plan = document.getElementById("plan-list");
  clear(pool);
  clear(plan);

  for (let i = 0; i < lastTasks.length; i++) {
    if (!inPlan(lastTasks[i].id)) {
      pool.appendChild(makeTaskRow(lastTasks[i], "pool"));
    }
  }
  // The plan keeps the order you built it in.
  for (let i = 0; i < planIds.length; i++) {
    const task = findTask(planIds[i]);
    if (task !== null) {
      plan.appendChild(makeTaskRow(task, "plan"));
    }
  }
  drawPlanSummary();
}

// "3 tasks · about 88 of 90 min · value 110.0", turning red when the plan is longer than your time.
function drawPlanSummary() {
  const box = document.getElementById("plan-summary");
  clear(box);
  document.getElementById("plan-note").textContent = planNote;

  let minutes = 0;
  let value = 0;
  let count = 0;
  for (let i = 0; i < planIds.length; i++) {
    const task = findTask(planIds[i]);
    if (task !== null) {
      minutes = minutes + plannedMinutes(task);
      value = value + task.value;
      count = count + 1;
    }
  }
  if (count === 0) {
    return;
  }

  let text = count + (count === 1 ? " task" : " tasks") + " · about " + minutes;
  if (planBudget !== null) {
    text = text + " of " + planBudget;
  }
  text = text + " min · value " + value.toFixed(1);
  const over = planBudget !== null && minutes > planBudget;
  if (over) {
    text = text + " · over your time";
  }
  box.appendChild(make("div", text, over ? "summary over" : "summary"));
}

function drawRecurring(templates) {
  const list = document.getElementById("recurring-list");
  clear(list);

  for (let i = 0; i < templates.length; i++) {
    const template = templates[i];
    const row = make("li", undefined, "task-row");
    row.appendChild(make("span", template.name, "t-name"));
    row.appendChild(make("span", template.category + " · " + template.guessed_minutes + "m · P" + template.priority, "t-meta"));
    const stop = make("button", "Stop", "small secondary");
    stop.title = "Stop repeating this task every day";
    stop.dataset.templateId = template.id;
    stop.addEventListener("click", onStopRecurringClick);
    row.appendChild(stop);
    list.appendChild(row);
  }
}


// ---------- drawing: the stopwatch (right column) ----------

function makeTimerButton(text, className, handler) {
  const button = make("button", text, className);
  button.addEventListener("click", handler);
  return button;
}

function drawTimer() {
  const box = document.getElementById("timer-box");
  clear(box);

  if (timer === null) {
    box.appendChild(make("p", "Nothing running. Pick a task and press Start.", "meta"));
    return;
  }

  box.appendChild(make("div", timer.name, "timer-name"));

  const task = findTask(timer.taskId);
  let info = "";
  if (task !== null) {
    info = task.percent_done + "% done so far";
  }
  if (timer.expectedMinutes !== null) {
    if (info !== "") {
      info = info + " · ";
    }
    info = info + "expected about " + timer.expectedMinutes + " min";
  }
  if (planSlice[timer.taskId] !== undefined) {
    info = info + " · plan: about " + planSlice[timer.taskId].percent + "% of the task";
  }
  if (info !== "") {
    box.appendChild(make("div", info, "meta"));
  }

  const clock = make("div", formatClock(timerElapsedMs(timer, Date.now())),
    timer.state === "running" ? "clock" : "clock paused");
  clock.id = "clock";
  box.appendChild(clock);

  if (timer.state === "asking") {
    box.appendChild(makeProgressForm());
    return;
  }

  const buttons = make("div", undefined, "timer-buttons");
  if (timer.state === "running") {
    buttons.appendChild(makeTimerButton("Pause", "secondary", onTimerPause));
  } else {
    buttons.appendChild(makeTimerButton("Resume", undefined, onTimerResume));
  }
  buttons.appendChild(makeTimerButton("Stop", "danger", onTimerStop));
  buttons.appendChild(makeTimerButton("Finish", "good", onTimerFinish));
  box.appendChild(buttons);
  box.appendChild(make("p", "Stop = I will continue another time. Finish = the task is done.", "hint"));
}

// Shown after Stop or Finish: ask how far you got, and save it.
function makeProgressForm() {
  const task = findTask(timer.taskId);
  const remaining = task === null ? 100 : 100 - task.percent_done;
  const worked = minutesWorked(timerElapsedMs(timer, Date.now()));

  const form = make("form", undefined, "progress-box stack");
  form.id = "progress-form";
  form.appendChild(make("div", "You worked " + worked + " min.", "timer-name"));
  let question = "How much of the whole task did you finish in this sitting? (" + remaining + "% was left.)";
  if (planSlice[timer.taskId] !== undefined) {
    question = question + " The plan aimed for about " + planSlice[timer.taskId].percent + "%.";
  }
  form.appendChild(make("div", question, "meta"));

  const row = make("div", undefined, "row");
  const percent = make("input");
  percent.type = "number";
  percent.id = "progress-percent";
  percent.min = 1;
  percent.max = remaining;
  percent.required = true;
  percent.placeholder = "%";
  if (timer.mode === "finish") {
    percent.value = remaining;   // "Finish" means everything that was left
  }
  row.appendChild(percent);
  row.appendChild(make("span", "% of the task", "meta"));
  form.appendChild(row);

  const buttons = make("div", undefined, "timer-buttons");
  buttons.appendChild(make("button", "Save progress"));
  const discard = make("button", "Discard", "secondary");
  discard.type = "button";   // a plain button: it must not submit the form
  discard.addEventListener("click", onDiscardClick);
  buttons.appendChild(discard);
  form.appendChild(buttons);

  form.addEventListener("submit", onProgressSubmit);
  return form;
}

// Called every second: only the numbers change, so we just rewrite the clock text.
function updateClock() {
  if (timer === null || timer.state !== "running") {
    return;
  }
  const clock = document.getElementById("clock");
  if (clock !== null) {
    clock.textContent = formatClock(timerElapsedMs(timer, Date.now()));
  }
}


// ---------- loading data ----------

function redrawAll() {
  drawLists();
  drawTimer();
}

// Asks the server for the task list and the daily tasks. A task that no longer exists (finished,
// or a skipped daily copy) is also dropped from the plan.
async function loadData() {
  lastTasks = await api("GET", "/tasks");
  const templates = await api("GET", "/recurring");
  drawRecurring(templates);

  const kept = [];
  for (let i = 0; i < planIds.length; i++) {
    if (findTask(planIds[i]) !== null) {
      kept.push(planIds[i]);
    }
  }
  if (kept.length !== planIds.length) {
    planIds = kept;
    savePlan();
  }
}

async function refresh() {
  await loadData();
  redrawAll();
}


// ---------- dragging tasks between "All tasks" and "Today's plan" ----------
// The browser's drag-and-drop works with these events:
//   dragstart  - you pick a row up. We note which task it is (the browser carries that text along).
//   dragover   - the row is held above a list. By default a drop is NOT allowed, so we call
//                event.preventDefault() to say "yes, you may drop here". We also highlight the list.
//   drop       - you let go over a list. We read which task it was and move it there.
//   dragend    - the drag is over (dropped or cancelled): remove the "being dragged" look.
// Touch screens do not support this, which is why every row also has a ← / → button.

function onDragStart(event) {
  event.dataTransfer.setData("text/plain", event.currentTarget.dataset.taskId);
  event.dataTransfer.effectAllowed = "move";
  event.currentTarget.classList.add("dragging");
}

function onDragEnd(event) {
  event.currentTarget.classList.remove("dragging");
  document.getElementById("pool-list").classList.remove("drop-over");
  document.getElementById("plan-list").classList.remove("drop-over");
  clearDropMarks();
}

// Where would a task dropped at this mouse height land in the list? Walk down the rows: the first row
// whose middle is below the mouse is the one we land BEFORE. If the mouse is below every row, we land last.
function dropIndex(list, mouseY) {
  const rows = list.querySelectorAll(".task-row");
  for (let i = 0; i < rows.length; i++) {
    const box = rows[i].getBoundingClientRect();
    if (mouseY < box.top + box.height / 2) {
      return i;
    }
  }
  return rows.length;
}

function clearDropMarks() {
  const marks = document.querySelectorAll(".insert-before, .insert-after");
  for (let i = 0; i < marks.length; i++) {
    marks[i].classList.remove("insert-before");
    marks[i].classList.remove("insert-after");
  }
}

// Draws a blue line where the dragged task would land: above row `index`, or below the last row.
function markDropPlace(list, index) {
  clearDropMarks();
  const rows = list.querySelectorAll(".task-row");
  if (rows.length === 0) {
    return;
  }
  if (index < rows.length) {
    rows[index].classList.add("insert-before");
  } else {
    rows[rows.length - 1].classList.add("insert-after");
  }
}

function onDragOver(event) {
  event.preventDefault();   // allow dropping here
  event.dataTransfer.dropEffect = "move";
  event.currentTarget.classList.add("drop-over");
  if (event.currentTarget.dataset.zone === "plan") {
    markDropPlace(event.currentTarget, dropIndex(event.currentTarget, event.clientY));
  }
}

function onDragLeave(event) {
  // dragleave also fires when the pointer moves onto a row INSIDE the list; ignore that case.
  if (!event.currentTarget.contains(event.relatedTarget)) {
    event.currentTarget.classList.remove("drop-over");
    clearDropMarks();
  }
}

function onDrop(event) {
  event.preventDefault();
  const list = event.currentTarget;
  list.classList.remove("drop-over");
  const toPlan = list.dataset.zone === "plan";
  // In the plan the drop position matters (you are choosing the order); "All tasks" has no order of its own.
  const position = toPlan ? dropIndex(list, event.clientY) : undefined;
  clearDropMarks();
  moveTask(Number(event.dataTransfer.getData("text/plain")), toPlan, position);
}

// Puts a task into the plan (toPlan = true) or back into "All tasks" (false).
// `position` is the place in the plan to insert at (0 = first); leave it out to add at the end.
// A task already in the plan is first taken out, so this also REORDERS the plan.
function moveTask(taskId, toPlan, position) {
  if (findTask(taskId) === null) {
    return;
  }
  const oldIndex = planIds.indexOf(taskId);
  if (toPlan) {
    let place = position === undefined ? planIds.length : position;
    if (oldIndex !== -1) {
      planIds.splice(oldIndex, 1);
      if (oldIndex < place) {
        place = place - 1;   // taking the task out shifted everything after it up by one
      }
    }
    planIds.splice(place, 0, taskId);
  } else if (oldIndex !== -1) {
    planIds.splice(oldIndex, 1);
    delete planSlice[taskId];   // back in "All tasks" it is just a normal task again
  }
  savePlan();
  drawLists();
}


// ---------- what happens when you click / submit ----------
// An event handler is a function the browser calls when something happens. `event.preventDefault()`
// stops the browser's default for a form, which is to reload the whole page.
// A server call can fail (bad input, server stopped). `try { ... } catch (error) { ... }` means
// "attempt this; if anything inside throws an Error, jump to the catch part instead of crashing".
// Every handler that talks to the server uses it, so a failure shows up as a red message.

async function onTaskSubmit(event) {
  event.preventDefault();
  try {
    const due = document.getElementById("task-due").value;   // "" when left empty
    await api("POST", "/tasks", {
      name: document.getElementById("task-name").value,
      category: document.getElementById("task-category").value,
      guessed_minutes: Number(document.getElementById("task-minutes").value),
      priority: Number(document.getElementById("task-priority").value),
      due_date: due === "" ? null : due,
    });
    document.getElementById("task-form").reset();
    hideMessage();
    await refresh();
  } catch (error) {
    showMessage(error.message, true);
  }
}

async function onRecurringSubmit(event) {
  event.preventDefault();
  try {
    await api("POST", "/recurring", {
      name: document.getElementById("rec-name").value,
      category: document.getElementById("rec-category").value,
      guessed_minutes: Number(document.getElementById("rec-minutes").value),
      priority: Number(document.getElementById("rec-priority").value),
    });
    document.getElementById("recurring-form").reset();
    hideMessage();
    await refresh();
  } catch (error) {
    showMessage(error.message, true);
  }
}

async function onStopRecurringClick(event) {
  try {
    await api("POST", "/recurring/" + event.target.dataset.templateId + "/stop");
    hideMessage();
    await refresh();
  } catch (error) {
    showMessage(error.message, true);
  }
}

// Asks the server for a plan, then moves the chosen tasks into column 3.
async function runPlan(minutes) {
  try {
    const result = await api("POST", "/plan", { minutes: minutes });
    await loadData();   // the plan may have created today's daily tasks

    // The server gives minutes for the part that is LEFT. Turn that back into "the whole task" so the
    // number stays right after you make more progress on the task.
    fullPredicted = {};
    const all = result.plan.concat(result.left_out);
    if (result.partial !== null) {
      all.push(result.partial);
    }
    for (let i = 0; i < all.length; i++) {
      const task = findTask(all[i].id);
      const share = task === null ? 1 : (100 - task.percent_done) / 100;
      fullPredicted[all[i].id] = all[i].predicted_minutes / share;
    }

    planIds = [];
    planSlice = {};
    for (let i = 0; i < result.plan.length; i++) {
      planIds.push(result.plan[i].id);
    }
    // The spare minutes: the server suggests a slice of one more task, last in the plan.
    if (result.partial !== null) {
      planIds.push(result.partial.id);
      planSlice[result.partial.id] = { minutes: result.partial.minutes, percent: result.partial.percent };
    }
    planBudget = result.minutes_available;
    planNote = "Predictor used: " + result.model;
    if (result.avg_error !== null) {
      planNote = planNote + " (average error " + result.avg_error.toFixed(1) + " min on your recent history)";
    }
    savePlan();

    if (result.plan.length === 0 && result.partial === null) {
      showMessage("Nothing fits in " + minutes + " minutes. Drag tasks into the plan yourself, or try a longer slot.", false);
    } else if (result.partial !== null) {
      showMessage("Spare time filled: " + result.partial.name + " is planned for about " + result.partial.percent +
        "% of the task (" + result.partial.minutes + " min), because the whole task does not fit.", false);
    } else {
      hideMessage();
    }
    redrawAll();
  } catch (error) {
    showMessage(error.message, true);
  }
}

async function onPlanSubmit(event) {
  event.preventDefault();
  await runPlan(Number(document.getElementById("plan-minutes").value));
}

function onMoveClick(event) {
  moveTask(Number(event.target.dataset.taskId), event.target.dataset.toPlan === "yes");
}

// Show or hide the "I worked X minutes" form inside this row. closest("li") finds the row the button is in.
function onLogToggle(event) {
  const form = event.target.closest("li").querySelector(".session-form");
  form.hidden = !form.hidden;
}

// Work done without the stopwatch.
async function onManualSubmit(event) {
  event.preventDefault();
  const form = event.target;
  try {
    const result = await api("POST", "/tasks/" + form.dataset.taskId + "/sessions", {
      minutes_spent: Number(form.elements.minutes.value),
      percent_gained: Number(form.elements.percent.value),
    });
    reportSaved(result);
    await refresh();
  } catch (error) {
    showMessage(error.message, true);
  }
}

function reportSaved(result) {
  if (result.finished) {
    showMessage("Task finished. Nice work!", false);
  } else {
    showMessage("Saved. That task is now " + result.percent_done + "% done and stays on your list.", false);
  }
}


// ---------- stopwatch buttons ----------

function onStartClick(event) {
  if (timer !== null) {
    showMessage("Finish or stop the task you are working on first.", true);
    return;
  }
  const task = findTask(Number(event.target.dataset.taskId));
  if (task === null) {
    return;
  }
  // If the task is in the plan we know how long it should take.
  let expected = null;
  if (inPlan(task.id)) {
    expected = plannedMinutes(task);
  }
  timer = newTimer(task.id, task.name, expected, Date.now());
  saveTimer();
  hideMessage();
  redrawAll();
}

function onTimerPause() {
  pauseTimer(timer, Date.now());
  saveTimer();
  drawTimer();
}

function onTimerResume() {
  resumeTimer(timer, Date.now());
  saveTimer();
  drawTimer();
}

function onTimerStop() {
  endTimer(timer, Date.now(), "stop");
  saveTimer();
  drawTimer();
}

function onTimerFinish() {
  endTimer(timer, Date.now(), "finish");
  saveTimer();
  drawTimer();
}

// The "how far did you get?" form: log the sitting, and the predictor learns from it.
async function onProgressSubmit(event) {
  event.preventDefault();
  try {
    const result = await api("POST", "/tasks/" + timer.taskId + "/sessions", {
      minutes_spent: minutesWorked(timerElapsedMs(timer, Date.now())),
      percent_gained: Number(document.getElementById("progress-percent").value),
    });
    const workedId = timer.taskId;
    timer = null;
    saveTimer();
    // The planned slice is done now. From here the task is planned for whatever is left of it.
    delete planSlice[workedId];
    savePlan();
    reportSaved(result);
    await refresh();   // a finished task leaves the plan; an unfinished one stays with fewer minutes left
  } catch (error) {
    // The timer is kept, so you do not lose the time you measured.
    showMessage(error.message, true);
  }
}

function onDiscardClick() {
  if (!window.confirm("Throw this timer away without saving anything?")) {
    return;
  }
  timer = null;
  saveTimer();
  redrawAll();
}


// ---------- start ----------

async function start() {
  timer = loadTimer();
  loadPlan();
  try {
    await refresh();
  } catch (error) {
    showMessage("Could not reach the server: " + error.message, true);
    return;
  }
  // Opening the page as /?plan=60 makes the plan straight away (handy for demos and screenshots).
  const wanted = new URLSearchParams(window.location.search).get("plan");
  if (wanted !== null) {
    document.getElementById("plan-minutes").value = wanted;
    await runPlan(Number(wanted));
  }
}

document.getElementById("task-form").addEventListener("submit", onTaskSubmit);
document.getElementById("recurring-form").addEventListener("submit", onRecurringSubmit);
document.getElementById("plan-form").addEventListener("submit", onPlanSubmit);

// The two lists accept dropped tasks.
const zones = [document.getElementById("pool-list"), document.getElementById("plan-list")];
for (let i = 0; i < zones.length; i++) {
  zones[i].addEventListener("dragover", onDragOver);
  zones[i].addEventListener("dragleave", onDragLeave);
  zones[i].addEventListener("drop", onDrop);
}

setInterval(updateClock, 1000);   // call updateClock once a second
start();
