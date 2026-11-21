(function () {
  "use strict";
  function el(id) { return document.getElementById(id); }
  function feedback(value) { if (el("feedback").textContent !== value) { el("feedback").textContent = value; } }
  var token = "", sequence = 0, layout = null, current = 0;
  var online = false, busy = false, refreshing = false;
  var desktop = setupDesktopControls(sendInput, feedback, function () { return online && !!token; });
  function connection(label, ready) {
    online = ready;
    if (!ready) { desktop.stopInput(); }
    el("connection").textContent = label;
    el("connection").className = ready ? "online" : "";
  }
  function request(path, body, done) {
    var xhr, timeout, finished = false;
    function finish(status, message) {
      if (finished) { return; }
      finished = true;
      clearTimeout(timeout);
      done(status, message);
    }
    try {
      xhr = new XMLHttpRequest();
      xhr.open("POST", path, true);
      xhr.setRequestHeader("X-Diagnostic-Run", document.body.getAttribute("data-run"));
      if (token) { xhr.setRequestHeader("X-Session", token); }
      xhr.onreadystatechange = function () {
        if (xhr.readyState === 4) { finish(xhr.status, xhr.responseText); }
      };
      timeout = setTimeout(function () { finish(0, ""); xhr.abort(); }, path === "/macro" ? 12000 : 4000);
      xhr.send(body);
    } catch (error) { finish(0, ""); }
  }
  function unpair() {
    token = ""; layout = null; busy = false;
    desktop.reset();
    el("dashboard").style.display = "none";
    el("pairing").style.display = "";
    connection("Unpaired", false);
    feedback("Select Enable pairing on the PC for a new code.");
  }
  function sendInput(path, value, done) {
    if (!token || !online || busy) { return false; }
    var session = token;
    busy = true;
    request(path, (++sequence) + " " + value, function (status, message) {
      if (session !== token) { return; }
      busy = false;
      if (status === 403) { unpair(); return; }
      if (!status) { connection("Reconnecting", false); refresh(); }
      done(status, message);
    });
    return true;
  }
  function run(slot, button) {
    if (!token || !online || busy) { return; }
    busy = true;
    var session = token;
    var label = layout.profiles[current].buttons[slot].label;
    button.className = "tile sending";
    feedback("Running " + label);
    request("/macro", [++sequence, layout.revision, current, slot].join(" "), function (status, message) {
      if (session !== token) { return; }
      busy = false;
      button.className = "tile";
      if (status === 403) { unpair(); return; }
      if (status === 0) { connection("Reconnecting", false); }
      feedback(status === 200 ? label + " completed" : message || "Reply lost. Check the target application.");
      if (status === 409 || !status) { refresh(); }
    });
  }
  // The applet's fonts can lack emoji and technical symbols even when text renders.
  var iconMarks = {
    "\u29c9": "CP", "\u25a4": "PA", "\u2702": "CT", "\u21b6": "UN", "\u2315": "?", "\u25a6": "ALL",
    "\u2193": "SV", "\u2317": "SS", "\u25a7": "TXT", "|\u25c0": "|<", "\u25b6\u2161": ">||",
    "\u25b6|": ">|", "\u2212": "-", "\u00d7": "X", "\u25a0": "STOP", "\u2193\u2193": "--"
  };
  function iconMark(item) {
    if (/^[\x20-\x7e]*$/.test(item.icon)) { return item.icon; }
    if (Object.prototype.hasOwnProperty.call(iconMarks, item.icon)) { return iconMarks[item.icon]; }
    var initials = item.label.match(/\b[A-Za-z0-9]/g);
    return initials ? initials.slice(0, 2).join("").toUpperCase() : "#";
  }
  function render() {
    var grid = el("grid");
    grid.textContent = "";
    layout.profiles[current].buttons.forEach(function (item, slot) {
      var cell = document.createElement("div"), button = document.createElement("button");
      cell.className = "cell";
      button.type = "button";
      button.className = "tile";
      if (item) {
        var icon = document.createElement("span"), label = document.createElement("span");
        icon.className = "icon"; icon.textContent = iconMark(item);
        icon.setAttribute("aria-hidden", "true");
        icon.style.color = button.style.borderLeftColor = item.color;
        label.className = "label"; label.textContent = item.label;
        if (icon.textContent) { button.appendChild(icon); }
        button.appendChild(label);
        button.onclick = function () { run(slot, button); };
      } else {
        button.className = "tile empty"; button.disabled = true;
        button.setAttribute("aria-label", "Empty slot");
      }
      cell.appendChild(button); grid.appendChild(cell);
    });
  }
  function selectProfile(index) {
    current = index;
    var buttons = el("profiles").children;
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].setAttribute("aria-pressed", String(i === current));
    }
    render();
  }
  function refresh() {
    if (!token || refreshing) { return; }
    var session = token;
    refreshing = true;
    request("/layout", "layout", function (status, message) {
      refreshing = false;
      if (session !== token) { return; }
      if (status === 403) { unpair(); return; }
      if (status !== 200) { connection("Reconnecting", false); return; }
      var updated;
      try { updated = JSON.parse(message); } catch (error) { connection("Invalid reply", false); return; }
      connection("Connected", true);
      if (layout && layout.revision === updated.revision) { return; }
      var name = layout ? layout.profiles[current].name : "";
      layout = updated;
      var profiles = el("profiles");
      profiles.textContent = "";
      current = 0;
      layout.profiles.forEach(function (profile, i) {
        var button = document.createElement("button");
        button.type = "button"; button.textContent = profile.name;
        button.onclick = function () { selectProfile(i); };
        profiles.appendChild(button);
        if (profile.name === name) { current = i; }
      });
      el("dashboard").style.display = "";
      selectProfile(current);
    });
  }
  el("pair").onclick = function () {
    var code = el("pin").value;
    if (!/^[0-9]{6}$/.test(code)) { feedback("Enter the six-digit code."); return; }
    el("pin").value = "";
    el("pair").disabled = true;
    request("/pair", code, function (status, message) {
      el("pair").disabled = false;
      if (status === 200 && /^[0-9a-f]{64}$/.test(message)) {
        token = message; sequence = 0;
        el("pairing").style.display = "none";
        feedback(""); connection("Connecting", false); refresh();
      } else { feedback(message || "Pairing failed. Reopen registration if the PC restarted."); }
    });
  };
  setInterval(refresh, 3000);
}());
