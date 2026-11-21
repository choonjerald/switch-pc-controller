// Run with node test_client.js. One gesture can emit all three event families.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const elements = new Map();
function element(id) {
  if (!elements.has(id)) {
    const listeners = new Map();
    elements.set(id, {
      textContent: "",
      addEventListener(type, listener) {
        if (!listeners.has(type)) listeners.set(type, []);
        listeners.get(type).push(listener);
      },
      emit(type, data) {
        for (const listener of listeners.get(type) || []) listener({type, ...data});
      },
      getBoundingClientRect() { return {left: 0, right: 100, top: 0, bottom: 80}; }
    });
  }
  return elements.get(id);
}
const messages = [];
class Echo {
  open(method, url) { assert.equal(method, "POST"); assert.equal(url, "/echo"); }
  setRequestHeader(name, token) { assert.equal(token, "trial"); }
  send(message) {
    messages.push(message);
    this.status = 200;
    this.readyState = 4;
    this.responseText = message;
    this.onreadystatechange();
  }
}
vm.runInNewContext(fs.readFileSync(path.join(__dirname, "web", "diagnostic.js"), "utf8"), {
  document: {getElementById: element, body: {getAttribute: key => key === "data-ws" ? "0" : "trial"}},
  navigator: {}, window: {addEventListener() {}}, XMLHttpRequest: Echo, setTimeout, clearTimeout
});
const tap = element("tap");
function gesture(x) {
  const point = {identifier: 1, pointerId: 1, clientX: x, clientY: 24};
  tap.emit("pointerdown", point);
  tap.emit("touchstart", {touches: [point], changedTouches: [point]});
  tap.emit("pointerup", point);
  tap.emit("touchend", {touches: [], changedTouches: [point]});
  tap.onclick();
}
for (const mode of ["click", "touch", "pointer"]) {
  element("trigger").value = mode;
  const count = messages.length;
  gesture(24);
  assert.equal(messages.length, count + 1);
  if (mode !== "click") {
    gesture(150);
    assert.equal(messages.length, count + 1);
  }
}
assert.deepEqual(messages, ["tap 1", "tap 2", "tap 3"]);
console.log("All three activation modes acknowledged one tap per gesture.");
