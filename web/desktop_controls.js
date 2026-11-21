/* Sends trackpad gestures and overlay key taps through the paired dashboard. */
function setupDesktopControls(send, feedback, connected) {
  "use strict";
  function el(id) { return document.getElementById(id); }
  var mode = "macros", pad = el("trackpad");
  var candidates = {}, owner = "", ignoreClickUntil = 0, ignoreMouseUntil = 0;
  var dx = 0, dy = 0, point = "", click = "";
  var timer = null, moving = false, generation = 0, lastPacket = 0;
  var shifted = false;

  function forgetGesture() {
    candidates = {}; owner = ""; pad.className = "";
  }
  function stopMotion() {
    generation++; forgetGesture(); dx = dy = 0; point = click = ""; moving = false;
    clearTimeout(timer); timer = null;
  }
  function schedule() {
    if (!moving && timer === null && (dx || dy || point || click)) {
      timer = setTimeout(flush, Math.max(0, Math.min(40, 40 - (Date.now() - lastPacket))));
    }
  }
  function flush() {
    timer = null;
    if (!connected() || mode !== "mouse") { stopMotion(); return; }
    var command, sx = 0, sy = 0, active = generation;
    if (point) { command = point; point = ""; }
    else if (dx || dy) {
      sx = Math.max(-512, Math.min(512, dx)); sy = Math.max(-512, Math.min(512, dy));
      command = "move " + sx + " " + sy; dx -= sx; dy -= sy;
    } else if (click) { command = click; click = ""; }
    else { return; }
    moving = true; lastPacket = Date.now();
    if (!send("/pointer", command, function (status, message) {
      if (active !== generation) { return; }
      moving = false;
      if (status === 429 && message === "Pointer updates are arriving too quickly.") {
        // This sample was explicitly declined. Preserve the gesture through Wi-Fi jitter.
        if (!point) {
          if (command.indexOf("point ") === 0) { point = command; }
          else { dx += sx; dy += sy; }
        }
        lastPacket = Date.now();
      } else if (status !== 200) {
        stopMotion(); feedback(message || "Pointer reply lost."); return;
      } else if (command === "left" || command === "right") {
        feedback(command === "left" ? "Left click" : "Right click");
      } else { feedback("Pointer moved"); }
      schedule();
    })) { stopMotion(); feedback("Wait for the current action."); }
  }
  function delta(mx, my) {
    dx = Math.max(-1024, Math.min(1024, dx + mx));
    dy = Math.max(-1024, Math.min(1024, dy + my));
    schedule();
  }
  function pointAt(px, py) {
    var box = pad.getBoundingClientRect(), w = box.right - box.left, h = box.bottom - box.top;
    if (!w || !h || !isFinite(px) || !isFinite(py) || px < box.left || py < box.top || px > box.right || py > box.bottom) {
      feedback("No tap position received. Use the arrows to move the pointer."); return;
    }
    point = "point " + Math.round(65535 * (px - box.left) / w) + " " + Math.round(65535 * (py - box.top) / h);
    dx = dy = 0; schedule();
  }
  function begin(family, id, x, y) {
    if (!connected() || mode !== "mouse" || owner || (family === "mouse" && Date.now() < ignoreMouseUntil)) { return; }
    candidates[family] = {id: id, x: Math.round(x), y: Math.round(y)};
    pad.className = "tracking";
  }
  function drag(family, id, x, y) {
    var c = candidates[family];
    if (!c || c.id !== id || (owner && owner !== family)) { return; }
    x = Math.round(x); y = Math.round(y);
    if (!owner && Math.max(Math.abs(x - c.x), Math.abs(y - c.y)) < 3) { return; }
    owner = family;
    delta(x - c.x, y - c.y); c.x = x; c.y = y;
  }
  function end(family, id, x, y) {
    var c = candidates[family];
    if (!c || c.id !== id || (owner && owner !== family)) { return; }
    drag(family, id, x, y);
    if (!owner) { pointAt(x, y); }
    ignoreClickUntil = Date.now() + 650;
    if (family !== "mouse") { ignoreMouseUntil = ignoreClickUntil; }
    forgetGesture();
  }
  // Some applets advertise PointerEvent but deliver TouchEvents or mouse events.
  // Listen to each family and let the first one with actual movement own the swipe.
  pad.addEventListener("pointerdown", function (e) {
    if (e.isPrimary === false || e.button > 0) { return; }
    begin("pointer", e.pointerId, e.clientX, e.clientY);
  }, false);
  function pointerMove(e) { drag("pointer", e.pointerId, e.clientX, e.clientY); }
  function pointerEnd(e) { end("pointer", e.pointerId, e.clientX, e.clientY); }
  pad.addEventListener("pointermove", pointerMove, false);
  window.addEventListener("pointermove", pointerMove, false);
  pad.addEventListener("pointerup", pointerEnd, false);
  window.addEventListener("pointerup", pointerEnd, false);
  function cancelFamily(family) {
    if (owner === family) { stopMotion(); }
    else { delete candidates[family]; }
  }
  pad.addEventListener("pointercancel", function () { cancelFamily("pointer"); }, false);
  pad.addEventListener("touchstart", function (e) {
    e.preventDefault();
    if (e.touches.length !== 1) { stopMotion(); return; }
    var t = e.touches[0]; begin("touch", t.identifier, t.clientX, t.clientY);
  }, false);
  function touchEvent(e) {
    e.preventDefault();
    for (var i = 0; i < e.changedTouches.length; i++) {
      var t = e.changedTouches[i];
      if (e.type === "touchend") { end("touch", t.identifier, t.clientX, t.clientY); }
      else { drag("touch", t.identifier, t.clientX, t.clientY); }
    }
  }
  pad.addEventListener("touchmove", touchEvent, false);
  pad.addEventListener("touchend", touchEvent, false);
  pad.addEventListener("touchcancel", function () { cancelFamily("touch"); }, false);
  pad.onmousedown = function (e) { if (e.button === 0) { begin("mouse", 0, e.clientX, e.clientY); } };
  window.addEventListener("mousemove", function (e) { if (candidates.mouse) { drag("mouse", 0, e.clientX, e.clientY); } }, false);
  window.addEventListener("mouseup", function (e) { if (candidates.mouse) { end("mouse", 0, e.clientX, e.clientY); } }, false);
  pad.onclick = function (e) {
    if (Date.now() >= ignoreClickUntil && connected() && mode === "mouse") { pointAt(e.clientX, e.clientY); }
  };
  [["left", -24, 0], ["right", 24, 0], ["up", 0, -24], ["down", 0, 24]].forEach(function (item) {
    el("nudge-" + item[0]).onclick = function () { delta(item[1], item[2]); };
  });
  ["left", "right"].forEach(function (button) {
    el(button + "-click").onclick = function () { if (!click) { click = button; schedule(); } };
  });

  // Send the first tap immediately, then group printable keys queued during its reply.
  var keyboardQueue = [], keyTimer = null, keySending = false, keyGeneration = 0, nextKeyAt = 0;
  function scheduleKey(delay) {
    if (!keySending && keyTimer === null && keyboardQueue.length) {
      keyTimer = setTimeout(flushKey, Math.max(delay, nextKeyAt - Date.now()));
    }
  }
  function flushKey() {
    keyTimer = null;
    if (!connected() || !keyboardQueue.length) { return; }
    var key = keyboardQueue[0], active = keyGeneration, count = 1, value = key.value;
    if (key.path === "/typing") {
      while (count < keyboardQueue.length && keyboardQueue[count].path === key.path) {
        value += keyboardQueue[count++].value;
      }
    }
    keySending = true;
    nextKeyAt = Date.now() + 30;
    if (!send(key.path, value, function (status, message) {
      if (active !== keyGeneration) { return; }
      keySending = false;
      if (status === 429 && message === "Keyboard input is arriving too quickly.") {
        // Windows explicitly declined this batch. It is safe to try again.
        nextKeyAt = Date.now() + 30;
        scheduleKey(0);
        return;
      }
      keyboardQueue.splice(0, count);
      if (status !== 200) {
        keyboardQueue = [];
        releaseBackspace();
        feedback(message || "Key delivery interrupted. Check the Windows app.");
        return;
      }
      if (key.label) { feedback(key.label); }
      if (key.complete) { key.complete(); }
      scheduleKey(0);
    })) {
      keySending = false;
      scheduleKey(35);
    }
  }
  function queueKey(path, value, label, complete) {
    if (!connected()) { feedback("Connect to the PC first."); return false; }
    if (keyboardQueue.length >= 24) { feedback("Keyboard busy. Pause briefly."); return false; }
    keyboardQueue.push({path: path, value: value, label: label, complete: complete});
    scheduleKey(0);
    return true;
  }
  function bindKey(button, activate) {
    var lastTouch = -Infinity;
    button.addEventListener("touchend", function (e) {
      var touch = e.changedTouches[0], box = button.getBoundingClientRect();
      if (!touch || touch.clientX < box.left || touch.clientX > box.right ||
          touch.clientY < box.top || touch.clientY > box.bottom) { return; }
      e.preventDefault();
      lastTouch = Date.now();
      activate();
    }, false);
    button.onclick = function () {
      if (Date.now() - lastTouch > 450) { activate(); }
    };
  }
  function buildKeys() {
    var keys = el("keys");
    keys.textContent = "";
    var rows = shifted ? ["!@#$%^&*()", "QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM?:\""]
                       : ["1234567890", "qwertyuiop", "asdfghjkl", "zxcvbnm,.'"];
    rows.forEach(function (chars) {
      var row = document.createElement("div");
      row.className = "keyrow";
      Array.prototype.forEach.call(chars, function (key) {
        var button = document.createElement("button");
        button.type = "button";
        button.textContent = key;
        bindKey(button, function () { queueKey("/typing", key, "Typing on PC"); });
        row.appendChild(button);
      });
      keys.appendChild(row);
    });
    el("shift-key").setAttribute("aria-pressed", String(shifted));
  }
  bindKey(el("shift-key"), function () { shifted = !shifted; buildKeys(); });
  bindKey(el("space-key"), function () { queueKey("/typing", " ", "Typing on PC"); });
  bindKey(el("tab-key"), function () { queueKey("/edit", "tab", "Tab sent"); });
  bindKey(el("enter-key"), function () { queueKey("/edit", "enter", "Enter sent"); });
  function showSwitcher(open) {
    el("app-switcher").style.display = open ? "" : "none";
    el("switch-app").setAttribute("aria-expanded", String(open));
  }
  bindKey(el("switch-app"), function () {
    queueKey("/edit", "switch-open", "Choose a window on the PC", function () { showSwitcher(true); });
  });
  bindKey(el("switch-left"), function () { queueKey("/edit", "switch-left"); });
  bindKey(el("switch-right"), function () { queueKey("/edit", "switch-right"); });
  bindKey(el("switch-select"), function () {
    queueKey("/edit", "enter", "Window selected", function () { showSwitcher(false); });
  });
  bindKey(el("switch-cancel"), function () {
    queueKey("/edit", "switch-cancel", "", function () { showSwitcher(false); });
  });
  buildKeys();
  var back = el("backspace-pc"), holding = false, repeats = 0, holdTimer = null, skipClickUntil = 0;
  function releaseBackspace() {
    if (holding && repeats) { skipClickUntil = Date.now() + 650; }
    holding = false; clearTimeout(holdTimer); holdTimer = null;
  }
  function eraseOnPC() {
    if (!connected() || mode !== "keyboard") { releaseBackspace(); return; }
    return queueKey("/edit", "backspace", "Backspace sent to PC");
  }
  function repeatBackspace() {
    if (!holding || repeats >= 20) { return; }
    if (!keyboardQueue.length && eraseOnPC()) { repeats++; }
    if (holding) { holdTimer = setTimeout(repeatBackspace, 160); }
  }
  function holdBackspace(e) {
    if (holding || !connected() || mode !== "keyboard" || e.button > 0) { return; }
    if (e.type === "mousedown" && Date.now() < skipClickUntil) { return; }
    holding = true; repeats = 0; skipClickUntil = 0;
    holdTimer = setTimeout(repeatBackspace, 500);
  }
  ["pointerdown", "touchstart", "mousedown"].forEach(function (type) { back.addEventListener(type, holdBackspace, false); });
  ["pointerup", "pointercancel", "touchend", "touchcancel", "mouseup"].forEach(function (type) {
    window.addEventListener(type, releaseBackspace, true);
  });
  back.addEventListener("pointerleave", releaseBackspace, false);
  back.addEventListener("mouseleave", releaseBackspace, false);
  back.oncontextmenu = function (e) { e.preventDefault(); };
  bindKey(back, function () {
    if (Date.now() >= skipClickUntil && !eraseOnPC()) { feedback("Wait for the current action."); }
  });
  function stopInput() {
    releaseBackspace(); stopMotion();
    keyboardQueue = []; keyGeneration++; keySending = false;
    clearTimeout(keyTimer); keyTimer = null;
  }
  window.addEventListener("pagehide", stopInput, false);
  window.addEventListener("blur", stopInput, false);
  document.addEventListener("visibilitychange", function () { if (document.hidden) { stopInput(); } }, false);
  var modes = ["macros", "mouse", "keyboard"];
  function showMode(next) {
    releaseBackspace(); stopMotion(); feedback(""); mode = next;
    el("workspace").className = mode === "macros" ? "" : "immersive";
    modes.forEach(function (name) {
      el("mode-" + name).setAttribute("aria-pressed", String(name === mode));
      el(name + "-panel").style.display = name === mode ? "" : "none";
    });
  }
  modes.forEach(function (name) { el("mode-" + name).onclick = function () { showMode(name); }; });
  function reset() {
    stopInput(); showSwitcher(false); showMode("macros"); shifted = false; buildKeys();
  }
  return {stopInput: stopInput, reset: reset};
}
