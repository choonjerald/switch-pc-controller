(function () {
  "use strict";
  function el(id) { return document.getElementById(id); }
  function show(id, value) { el(id).textContent = value; }
  function now() {
    return window.performance && window.performance.now ? window.performance.now() : Date.now();
  }
  var lines = [], tapCount = 0, confirmed = 0;
  var run = document.body.getAttribute("data-run");
  var wsPort = Number(document.body.getAttribute("data-ws"));
  function log(msg) {
    lines.unshift(Math.round(now()) + " ms  " + msg);
    if (lines.length > 15) { lines.pop(); }
    show("events", lines.join("\n"));
  }
  function request(message, done) {
    var started = now(), xhr, timer, finished = false;
    function finish(ok) {
      if (finished) { return; }
      finished = true;
      clearTimeout(timer);
      done(ok, now() - started);
    }
    try {
      xhr = new XMLHttpRequest();
      xhr.open("POST", "/echo", true);
      xhr.setRequestHeader("X-Diagnostic-Run", run);
      xhr.onreadystatechange = function () {
        if (xhr.readyState === 4) { finish(xhr.status === 200 && xhr.responseText === message); }
      };
      timer = setTimeout(function () { finish(false); xhr.abort(); }, 3000);
      xhr.send(message);
    } catch (err) { finish(false); }
  }
  var tap = el("tap");
  function sendTap() {
    var seq = ++tapCount;
    show("ack", "Sending tap " + seq);
    request("tap " + seq, function (ok, ms) {
      if (ok) { confirmed++; }
      show("ack", "Tap " + seq + (ok ? " acknowledged in " + ms.toFixed(1) + " ms" : " failed") +
        " | " + confirmed + " of " + tapCount + " confirmed");
    });
  }
  var activeContact = null;
  var trigger = el("trigger");
  trigger.onchange = function () { activeContact = null; };
  tap.onclick = function () { if (trigger.value === "click") { sendTap(); } };
  function releasedInside(contact) {
    var box = tap.getBoundingClientRect();
    return contact.clientX >= box.left && contact.clientX < box.right &&
      contact.clientY >= box.top && contact.clientY < box.bottom;
  }
  tap.addEventListener("touchstart", function (e) {
    if (trigger.value === "touch") {
      activeContact = e.touches.length === 1 ? e.touches[0].identifier : null;
    }
  }, false);
  tap.addEventListener("touchend", function (e) {
    if (trigger.value !== "touch") { return; }
    var contact = e.changedTouches[0];
    if (contact && activeContact === contact.identifier &&
        e.touches.length === 0 && releasedInside(contact)) { sendTap(); }
    activeContact = null;
  }, false);
  tap.addEventListener("pointerdown", function (e) {
    if (trigger.value === "pointer") { activeContact = e.isPrimary === false ? null : e.pointerId; }
  }, false);
  tap.addEventListener("pointerup", function (e) {
    if (trigger.value !== "pointer") { return; }
    if (activeContact === e.pointerId && releasedInside(e)) { sendTap(); }
    activeContact = null;
  }, false);
  tap.addEventListener("touchcancel", function () { if (trigger.value === "touch") { activeContact = null; } }, false);
  tap.addEventListener("pointercancel", function () { if (trigger.value === "pointer") { activeContact = null; } }, false);
  function observe(event) {
    var detail = event.type;
    if (event.changedTouches && event.changedTouches.length) {
      var contact = event.changedTouches[0];
      detail += " id=" + contact.identifier + " at " + contact.clientX + "," + contact.clientY +
        " contacts=" + event.touches.length;
    } else if (typeof event.pointerId === "number") {
      detail += " " + event.pointerType + "#" + event.pointerId + " at " + event.clientX + "," + event.clientY;
    } else if (event.type.indexOf("key") === 0) {
      detail += " " + (event.code || event.key || event.keyCode);
    }
    log(detail);
  }
  ("touchstart touchmove touchend touchcancel pointerdown pointermove pointerup pointercancel " +
    "mousedown mouseup click keydown keyup focus blur").split(" ").forEach(function (type) {
    tap.addEventListener(type, observe, false);
  });
  ["gamepadconnected", "gamepaddisconnected", "pageshow", "pagehide", "online", "offline"].forEach(function (type) {
    window.addEventListener(type, function () { log(type); }, false);
  });
  function inspectPads() {
    var getPads = navigator.getGamepads || navigator.webkitGetGamepads;
    if (!getPads) { show("pads", "Gamepad API absent"); return; }
    try {
      var pads = getPads.call(navigator), states = [];
      for (var i = 0; i < pads.length; i++) {
        var pad = pads[i];
        if (!pad) { continue; }
        var axes = [], buttons = [];
        for (var a = 0; a < pad.axes.length; a++) { axes.push(pad.axes[a].toFixed(2)); }
        for (var b = 0; b < pad.buttons.length; b++) {
          var button = pad.buttons[b], value = typeof button === "number" ? button : button.value;
          if (value || button.pressed) { buttons.push(b + "=" + Number(value || 1).toFixed(2)); }
        }
        states.push("Pad " + i + " " + pad.id + " | axes [" + axes.join(", ") + "] | pressed [" + buttons.join(", ") + "]");
      }
      var summary = states.length ? states.join("\n") : "Gamepad API returned no controller";
      if (el("pads").textContent !== summary) { show("pads", summary); log(summary); }
    } catch (err) { show("pads", "Gamepad read failed: " + err.name); }
  }
  function info() {
    show("info", window.innerWidth + " × " + window.innerHeight + " | secure context: " + window.isSecureContext +
      " | pointer: " + typeof window.PointerEvent + " | touchstart: " + ("ontouchstart" in window) +
      " | XHR: " + typeof window.XMLHttpRequest + " | WebSocket: " + typeof window.WebSocket + "\n" + navigator.userAgent);
  }
  info();
  window.addEventListener("resize", info, false);
  inspectPads();
  if (navigator.getGamepads || navigator.webkitGetGamepads) { setInterval(inspectPads, 50); }
  el("measure").onclick = function () {
    var samples = [], attempt = 0, missed = 0;
    el("measure").disabled = true;
    function next() {
      attempt++;
      show("stats", "Echo " + attempt + " of 105");
      request("ping " + attempt, function (ok, ms) {
        if (attempt > 5) {
          if (ok) { samples.push(ms); } else { missed++; }
        }
        if (attempt < 105) { setTimeout(next, 20); return; }
        el("measure").disabled = false;
        samples.sort(function (a, b) { return a - b; });
        function percentile(p) { return samples[Math.ceil(samples.length * p) - 1].toFixed(1); }
        show("stats", "HTTP RTT | " + samples.length + "/100 replies | " + missed + " missing" +
          (samples.length ? " | median " + percentile(0.5) + " ms | p95 " + percentile(0.95) + " ms" : ""));
      });
    }
    next();
  };
  el("socket").disabled = !wsPort || !window.WebSocket;
  show("socket-result", !wsPort ? "WebSocket listener off (optional --ws)" :
    !window.WebSocket ? "WebSocket API absent" : "Ready for echo test");
  el("socket").onclick = function () {
    var socket, timer, finished = false;
    el("socket").disabled = true;
    function finish(message) {
      if (finished) { return; }
      finished = true;
      clearTimeout(timer);
      show("socket-result", message);
      el("socket").disabled = false;
      if (socket) { socket.close(); }
    }
    try {
      socket = new WebSocket("ws://" + location.hostname + ":" + wsPort + "/echo");
      timer = setTimeout(function () { finish("WebSocket timed out"); }, 4000);
      socket.onopen = function () { socket.send("ping"); };
      socket.onmessage = function (e) { finish(e.data === "pong" ? "WebSocket echo confirmed" : "Unexpected reply"); };
      socket.onerror = socket.onclose = function () { finish("WebSocket failed"); };
    } catch (err) { finish("WebSocket failed: " + err.name); }
  };
  show("script", "JavaScript running");
}());
