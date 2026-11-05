// The stopwatch LOGIC only: no page code in here, so it can be tested on its own (test_timer.js).
//
// A stopwatch that can be paused needs two numbers, not one:
//   elapsedMs  = time already counted from earlier running stretches
//   startedAt  = when the current running stretch began (null while paused)
// The time shown is elapsedMs + (now - startedAt). We store timestamps instead of adding 1 every
// second, so the count stays right even if the page is busy, hidden, or reloaded.
//
// A timer is a plain object:
//   { taskId, name, expectedMinutes, state, mode, elapsedMs, startedAt }
//   state: "running", "paused", or "asking" (stopped; waiting for the user to say how far they got)
//   mode:  "stop" or "finish": which button ended it (null until it ends)

function newTimer(taskId, name, expectedMinutes, now) {
  return {
    taskId: taskId,
    name: name,
    expectedMinutes: expectedMinutes,   // from the plan; null if the task was not in a plan
    state: "running",
    mode: null,
    elapsedMs: 0,
    startedAt: now,
  };
}

function timerElapsedMs(timer, now) {
  if (timer.state === "running") {
    return timer.elapsedMs + (now - timer.startedAt);
  }
  return timer.elapsedMs;
}

function pauseTimer(timer, now) {
  if (timer.state !== "running") {
    return;
  }
  timer.elapsedMs = timerElapsedMs(timer, now);
  timer.startedAt = null;
  timer.state = "paused";
}

function resumeTimer(timer, now) {
  if (timer.state !== "paused") {
    return;
  }
  timer.startedAt = now;
  timer.state = "running";
}

// Stop or Finish: freeze the time and move to the "asking" step.
function endTimer(timer, now, mode) {
  if (timer.state === "asking") {
    return;
  }
  timer.elapsedMs = timerElapsedMs(timer, now);
  timer.startedAt = null;
  timer.state = "asking";
  timer.mode = mode;
}

// 754000 ms -> "12:34". An hour or more -> "1:02:03".
function pad2(number) {
  return number < 10 ? "0" + number : String(number);
}

function formatClock(ms) {
  const totalSeconds = Math.floor(ms / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) {
    return hours + ":" + pad2(minutes) + ":" + pad2(seconds);
  }
  return pad2(minutes) + ":" + pad2(seconds);
}

// The server wants whole minutes, at least 1.
function minutesWorked(ms) {
  return Math.max(1, Math.round(ms / 60000));
}

// This file is also loaded by Node for testing; in the browser `module` does not exist and this is skipped.
if (typeof module !== "undefined") {
  module.exports = {
    newTimer: newTimer,
    timerElapsedMs: timerElapsedMs,
    pauseTimer: pauseTimer,
    resumeTimer: resumeTimer,
    endTimer: endTimer,
    formatClock: formatClock,
    minutesWorked: minutesWorked,
  };
}
