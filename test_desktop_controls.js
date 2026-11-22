// Simulate restricted applet event combinations without injecting Windows input.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

class Element {
  constructor() {
    this.style = {}; this.listeners = {}; this.value = ""; this.children = [];
  }
  setAttribute() {}
  set textContent(value) { this.text = value; this.children = []; }
  get textContent() { return this.text; }
  appendChild(node) { this.children.push(node); }
  getBoundingClientRect() { return {left: 10, top: 20, right: 210, bottom: 120}; }
  addEventListener(name, fn) { (this.listeners[name] ||= []).push(fn); }
  fire(type, fields = {}) {
    const e = {type, button: 0, preventDefault() {}, ...fields};
    for (const fn of this.listeners[type] || []) fn(e);
    if (this["on" + type]) this["on" + type](e);
  }
}

const elements = new Map();
function el(id) {
  if (!elements.has(id)) elements.set(id, new Element());
  return elements.get(id);
}
const window = new Element();
window.PointerEvent = function () {}; // Exposed even in the touch-only scenario.
const document = Object.assign(new Element(), {getElementById: el, createElement: () => new Element()});
let now = 1000, next = 1;
const timers = new Map();
function later(fn, delay) {
  const id = next++;
  timers.set(id, {at: now + delay, fn});
  return id;
}
function advance(ms) {
  const end = now + ms;
  while (timers.size) {
    const [id, event] = [...timers.entries()].sort((a, b) => a[1].at - b[1].at)[0];
    if (event.at > end) break;
    now = event.at;
    timers.delete(id); event.fn();
  }
  now = end;
}
const context = {window, document, Date: {now: () => now}, setTimeout: later, clearTimeout: id => timers.delete(id)};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, "web/desktop_controls.js"), "utf8"), context);
const requests = [];
let rejectMotion = false;
let replyDelay = 4;
const controls = context.setupDesktopControls((route, body, done) => {
  requests.push([route, body]);
  if (rejectMotion) {
    rejectMotion = false;
    later(() => done(429, "Pointer updates are arriving too quickly."), 4);
  } else later(() => done(200, "OK"), replyDelay);
  return true;
}, () => {}, () => true);

el("mode-mouse").fire("click");
const pad = el("trackpad");
const touch = (type, x, y) => {
  const point = {identifier: 4, clientX: x, clientY: y};
  pad.fire(type, {touches: type === "touchend" ? [] : [point], changedTouches: [point]});
};
touch("touchstart", 20, 40);
touch("touchmove", 45, 44);
touch("touchend", 45, 44);
pad.fire("click", {clientX: 45, clientY: 44});
advance(700);
assert.deepEqual(requests.splice(0), [["/pointer", "move 25 4"]]);

const pointer = (type, x) => pad.fire(type, {pointerId: 2, isPrimary: true, clientX: x, clientY: 40});
pointer("pointerdown", 20); touch("touchstart", 20, 40);
pointer("pointermove", 35); touch("touchmove", 35, 40);
touch("touchend", 35, 40); pointer("pointerup", 35);
advance(700);
assert.deepEqual(requests.splice(0), [["/pointer", "move 15 0"]]);

pad.fire("click", {clientX: 110, clientY: 70});
advance(100);
assert.deepEqual(requests.splice(0), [["/pointer", "point 32768 32768"]]);
rejectMotion = true;
pointer("pointerdown", 15); pointer("pointermove", 25);
advance(90); pointer("pointerup", 30); advance(100);
assert.deepEqual(requests.splice(0).map(r => r[1]), ["move 10 0", "move 10 0", "move 5 0"]);

el("mode-keyboard").fire("click");
function tapKey(key) {
  el("keys").children.flatMap(row => row.children).find(button => button.textContent === key).fire("click");
}
replyDelay = 80;
el("shift-key").fire("click");
const firstKey = el("keys").children.flatMap(row => row.children).find(button => button.textContent === "H");
firstKey.fire("touchend", {changedTouches: [{clientX: 50, clientY: 50}]});
firstKey.fire("click"); advance(1);
assert.deepEqual(requests, [["/typing", "H"]]);
el("symbols-key").fire("click");
assert.equal(el("keys").children[0].children[0].textContent, "-");
el("symbols-key").fire("click"); tapKey("i");
el("space-key").fire("click"); el("enter-key").fire("click");
el("switch-app").fire("click"); advance(81);
assert.deepEqual(requests, [["/typing", "H"], ["/typing", "i "]]);
advance(400);
assert.deepEqual(requests.splice(0), [
  ["/typing", "H"], ["/typing", "i "], ["/edit", "enter"], ["/edit", "switch-open"]
]);
replyDelay = 4;
assert.equal(el("app-switcher").style.display, "");
el("switch-right").fire("click"); el("switch-right").fire("click");
el("switch-left").fire("click"); el("switch-select").fire("click"); advance(200);
assert.deepEqual(requests.splice(0), [
  ["/edit", "switch-right"], ["/edit", "switch-right"], ["/edit", "switch-left"], ["/edit", "enter"]
]);
assert.equal(el("app-switcher").style.display, "none");
const back = el("backspace-pc");
back.fire("click"); advance(200);
assert.deepEqual(requests.splice(0), [["/edit", "backspace"]]);
back.fire("touchstart"); advance(850); window.fire("touchend"); back.fire("click"); advance(800);
assert.equal(requests.splice(0).length, 3);
back.fire("pointerdown"); advance(550); controls.stopInput(); advance(800);
assert.deepEqual(requests.splice(0), [["/edit", "backspace"]]);
tapKey("a"); tapKey("b"); controls.stopInput(); advance(400);
assert.deepEqual(requests.splice(0), []);
console.log("Trackpad, live keyboard ordering, app switching and remote Backspace passed.");
