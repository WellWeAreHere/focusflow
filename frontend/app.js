// What the page DOES. JavaScript runs inside the browser. The plan:
//   1. when the page loads, ask the server for tasks and daily tasks and draw them;
//   2. when you submit a form, send it to the server, then ask again and redraw.
//
// Two ideas you have not met in C++:
//   - The DOM: the browser keeps the page as a tree of objects (one per tag). JavaScript can
//     find them with document.getElementById("...") and change them.
//   - async / await: asking the server takes time (it is a network call). `await` means
//     "pause THIS function until the answer arrives, but keep the page responsive".
//     A function that uses await must be declared `async`.
//
// Also: `const` is a variable that is never reassigned, `let` is one that can be.


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

function describeDue(dueDate) {
  if (dueDate === null) {
    return "no deadline";
  }
  return "due " + dueDate;
}


// ---------- drawing the lists ----------

function drawTasks(tasks) {
  const list = document.getElementById("task-list");
  clear(list);

  for (let i = 0; i < tasks.length; i++) {
    const task = tasks[i];
    const card = make("li", undefined, "card");

    const top = make("div", undefined, "card-top");
    const title = make("span", task.name, "card-title");
    if (task.recurring) {
      title.appendChild(make("span", "daily", "badge"));
    }
    top.appendChild(title);
    top.appendChild(make("span", task.category + " · guess " + task.guessed_minutes + " min · priority " +
      task.priority + " · " + describeDue(task.due_date), "meta"));
    card.appendChild(top);

    // Progress bar: an outer box with an inner box whose width is the percentage done.
    const bar = make("div", undefined, "bar");
    const fill = make("div", undefined, "bar-fill");
    fill.style.width = task.percent_done + "%";
    bar.appendChild(fill);
    card.appendChild(bar);
    card.appendChild(make("div", task.percent_done + "% done · " + task.spent_minutes +
      " min spent so far · worth " + task.value.toFixed(1) + " points", "meta"));

    card.appendChild(makeSessionForm(task));
    list.appendChild(card);
  }
}

// The little "I worked X minutes and finished Y%" form under each task.
function makeSessionForm(task) {
  const form = make("form", undefined, "session-form");
  form.dataset.taskId = task.id;   // remember which task this form belongs to

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
  form.appendChild(make("span", "% of it", "meta"));
  form.appendChild(make("button", "Log", "secondary"));

  form.addEventListener("submit", onSessionSubmit);
  return form;
}

function drawRecurring(templates) {
  const list = document.getElementById("recurring-list");
  clear(list);

  for (let i = 0; i < templates.length; i++) {
    const template = templates[i];
    const card = make("li", undefined, "card");
    const top = make("div", undefined, "card-top");
    top.appendChild(make("span", template.name, "card-title"));
    top.appendChild(make("span", template.category + " · guess " + template.guessed_minutes +
      " min · priority " + template.priority, "meta"));
    card.appendChild(top);

    const stop = make("button", "Stop repeating", "secondary");
    stop.dataset.templateId = template.id;
    stop.addEventListener("click", onStopClick);
    card.appendChild(stop);
    list.appendChild(card);
  }
}

function drawPlan(result) {
  const box = document.getElementById("plan-result");
  clear(box);

  if (result.plan.length === 0) {
    box.appendChild(make("p", "Nothing fits in " + result.minutes_available +
      " minutes. Add tasks, or try a longer slot.", "meta"));
  } else {
    box.appendChild(make("p", "Use " + result.minutes_used + " of your " + result.minutes_available +
      " minutes. Total value " + result.total_value.toFixed(1) + ".", "summary"));
  }

  const list = make("ol", undefined, "cards");
  for (let i = 0; i < result.plan.length; i++) {
    const item = result.plan[i];
    const card = make("li", undefined, "card");
    const top = make("div", undefined, "card-top");
    top.appendChild(make("span", item.name, "card-title"));
    top.appendChild(make("span", item.predicted_minutes + " min", "meta"));
    card.appendChild(top);
    card.appendChild(make("p", item.reason, "reason"));
    list.appendChild(card);
  }
  box.appendChild(list);

  // Be upfront about how the minutes were predicted.
  let how = "Predictor used: " + result.model;
  if (result.avg_error !== null) {
    how += " (average error " + result.avg_error.toFixed(1) + " min on your recent history)";
  }
  box.appendChild(make("p", how, "meta"));

  if (result.left_out.length > 0) {
    const names = [];
    for (let i = 0; i < result.left_out.length; i++) {
      names.push(result.left_out[i].name + " (" + result.left_out[i].predicted_minutes + " min)");
    }
    box.appendChild(make("p", "Left out: " + names.join(", "), "left-out"));
  }
}


// ---------- loading data ----------

async function refresh() {
  const tasks = await api("GET", "/tasks");
  const templates = await api("GET", "/recurring");
  drawTasks(tasks);
  drawRecurring(templates);
}

// A server call can fail (bad input, server stopped). `try { ... } catch (error) { ... }` means
// "attempt this; if anything inside throws an Error, jump to the catch part instead of crashing".
// Every handler below uses it so a failure shows up as a red message on the page.


// ---------- what happens when you click / submit ----------
// An event handler is a function the browser calls when something happens. `event.preventDefault()`
// stops the browser's default for a form, which is to reload the whole page.

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

async function onSessionSubmit(event) {
  event.preventDefault();
  const form = event.target;   // the form that was submitted
  try {
    const result = await api("POST", "/tasks/" + form.dataset.taskId + "/sessions", {
      minutes_spent: Number(form.elements.minutes.value),
      percent_gained: Number(form.elements.percent.value),
    });
    if (result.finished) {
      showMessage("Task finished. Nice work!", false);
    } else {
      showMessage("Saved. That task is now " + result.percent_done + "% done and stays on your list.", false);
    }
    await refresh();
  } catch (error) {
    showMessage(error.message, true);
  }
}

async function onStopClick(event) {
  try {
    await api("POST", "/recurring/" + event.target.dataset.templateId + "/stop");
    hideMessage();
    await refresh();
  } catch (error) {
    showMessage(error.message, true);
  }
}

async function onPlanSubmit(event) {
  event.preventDefault();
  try {
    const result = await api("POST", "/plan", {
      minutes: Number(document.getElementById("plan-minutes").value),
    });
    hideMessage();
    drawPlan(result);
    await refresh();   // the plan may have created today's daily tasks
  } catch (error) {
    showMessage(error.message, true);
  }
}


// ---------- start ----------

async function start() {
  try {
    await refresh();
  } catch (error) {
    showMessage("Could not reach the server: " + error.message, true);
  }
}

document.getElementById("task-form").addEventListener("submit", onTaskSubmit);
document.getElementById("recurring-form").addEventListener("submit", onRecurringSubmit);
document.getElementById("plan-form").addEventListener("submit", onPlanSubmit);
start();
