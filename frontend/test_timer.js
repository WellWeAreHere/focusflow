// Tests for timer.js. Run with Node (no install needed):  node frontend/test_timer.js
const assert = require("assert");
const t = require("./timer.js");

// Counts while running.
let timer = t.newTimer(7, "report", 30, 1000);
assert.strictEqual(t.timerElapsedMs(timer, 1000), 0);
assert.strictEqual(t.timerElapsedMs(timer, 61000), 60000);

// Pausing freezes the time; time that passes while paused is NOT counted.
t.pauseTimer(timer, 61000);
assert.strictEqual(timer.state, "paused");
assert.strictEqual(t.timerElapsedMs(timer, 500000), 60000);

// Resuming continues from where it stopped.
t.resumeTimer(timer, 500000);
assert.strictEqual(timer.state, "running");
assert.strictEqual(t.timerElapsedMs(timer, 530000), 90000);

// Pausing twice or resuming while running changes nothing.
t.resumeTimer(timer, 540000);
assert.strictEqual(t.timerElapsedMs(timer, 530000), 90000);

// Stop moves to the asking step and freezes the time.
t.endTimer(timer, 530000, "stop");
assert.strictEqual(timer.state, "asking");
assert.strictEqual(timer.mode, "stop");
assert.strictEqual(t.timerElapsedMs(timer, 9999999), 90000);

// Ending again does not change the mode or the time.
t.endTimer(timer, 9999999, "finish");
assert.strictEqual(timer.mode, "stop");
assert.strictEqual(t.timerElapsedMs(timer, 9999999), 90000);

// Stopping straight from a paused timer keeps the paused time.
let paused = t.newTimer(1, "x", null, 0);
t.pauseTimer(paused, 120000);
t.endTimer(paused, 900000, "finish");
assert.strictEqual(t.timerElapsedMs(paused, 900000), 120000);
assert.strictEqual(paused.mode, "finish");

// Clock text.
assert.strictEqual(t.formatClock(0), "00:00");
assert.strictEqual(t.formatClock(754000), "12:34");
assert.strictEqual(t.formatClock(59999), "00:59");
assert.strictEqual(t.formatClock(3723000), "1:02:03");

// Minutes sent to the server: rounded, never below 1.
assert.strictEqual(t.minutesWorked(0), 1);
assert.strictEqual(t.minutesWorked(20000), 1);
assert.strictEqual(t.minutesWorked(89000), 1);
assert.strictEqual(t.minutesWorked(91000), 2);
assert.strictEqual(t.minutesWorked(25 * 60000), 25);

console.log("timer tests passed");
