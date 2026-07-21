/* CrocBridge frontend controller: poll /api/status, route screens, render. */
(function () {
  "use strict";

  const $ = (sel) => document.querySelector(sel);

  const IDLE_MS = 2000;
  const ACTIVE_MS = 400; // >= 2 updates/sec during transfers

  let holdPairingScreen = false; // keep B's confirmation on screen until dismissed
  let prevSendState = "idle";
  let prevRecvState = "stopped";
  let lastHistoryLen = -1;

  /* ---------- helpers ---------- */

  function fmtBytes(n) {
    if (n == null) return "";
    if (n < 1000) return n + " B";
    const units = ["kB", "MB", "GB", "TB"];
    let u = -1;
    do { n /= 1000; u++; } while (n >= 1000 && u < units.length - 1);
    return n.toFixed(n >= 100 ? 0 : 1) + " " + units[u];
  }

  function fmtDuration(s) {
    if (s == null) return "";
    if (s < 60) return s.toFixed(0) + "s";
    return Math.floor(s / 60) + "m " + Math.round(s % 60) + "s";
  }

  function show(screen) {
    for (const id of ["screen-nocroc", "screen-pairing", "screen-main"]) {
      document.getElementById(id).hidden = id !== screen;
    }
  }

  /* ---------- render ---------- */

  function render(s) {
    $("#banner-offline").hidden = !!s;
    if (!s) return;

    if (!s.croc.installed || !s.croc.supported) {
      $("#nocroc-version-warning").hidden = s.croc.installed === false;
      show("screen-nocroc");
      return;
    }
    if (!s.paired || holdPairingScreen) {
      show("screen-pairing");
      return;
    }
    show("screen-main");

    $("#hdr-own-name").textContent = s.device_name;
    $("#hdr-peer-name").textContent = s.peer_name || "?";
    $("#bank-label-own").textContent = s.device_name;
    $("#bank-label-peer").textContent = s.peer_name || "?";

    renderReceiver(s);
    renderSend(s);
    renderRiver(s);
    if (s.history_len !== lastHistoryLen) {
      lastHistoryLen = s.history_len;
      refreshHistory();
    }
    prevSendState = s.send.state;
    prevRecvState = s.receiver.state;
  }

  function renderReceiver(s) {
    const chip = $("#receiver-chip");
    const labels = {
      listening: "Listening",
      receiving: "Receiving",
      error: "Problem",
      stopped: "Off",
    };
    chip.textContent = labels[s.receiver.state] || s.receiver.state;
    chip.className = "chip chip-" + s.receiver.state;

    const errEl = $("#receiver-error");
    errEl.hidden = !s.receiver.error;
    if (s.receiver.error) errEl.textContent = s.receiver.error;

    const list = $("#received-files");
    const files = s.receiver.received_files || [];
    $("#arrivals-empty").hidden = files.length > 0;
    list.innerHTML = "";
    for (const f of files.slice(0, 20)) {
      const li = document.createElement("li");
      const name = document.createElement("span");
      name.textContent = f.name;
      const size = document.createElement("span");
      size.className = "size";
      size.textContent = fmtBytes(f.bytes);
      li.append(name, size);
      list.append(li);
    }
  }

  function renderSend(s) {
    const chip = $("#send-chip");
    const st = s.send.state;
    const labels = {
      staging: "Preparing",
      connecting: "Reaching out",
      sending: "Crossing",
      done: "Delivered",
      cancelled: "Stopped",
      error: "Problem",
    };
    chip.hidden = st === "idle";
    if (!chip.hidden) {
      chip.textContent = labels[st] || st;
      chip.className =
        "chip " +
        (st === "sending" || st === "connecting" || st === "staging"
          ? "chip-sending"
          : st === "error"
          ? "chip-error"
          : "chip-listening");
    }

    const errEl = $("#send-error");
    errEl.hidden = !s.send.error;
    if (s.send.error) errEl.textContent = s.send.error;

    const list = $("#send-files");
    list.innerHTML = "";
    for (const name of s.send.files || []) {
      const li = document.createElement("li");
      const span = document.createElement("span");
      span.textContent = name;
      li.append(span);
      if (s.send.progress && s.send.progress.pct != null && st === "sending") {
        const pct = document.createElement("span");
        pct.className = "size";
        pct.textContent = s.send.progress.pct + "%";
        li.append(pct);
      }
      list.append(li);
    }
    $("#btn-cancel-send").hidden = !(st === "sending" || st === "connecting" || st === "staging");
  }

  function renderRiver(s) {
    const sendActive = ["staging", "connecting", "sending"].includes(s.send.state);
    const recvActive = s.receiver.state === "receiving";
    const plaque = $("#river-plaque");
    const hint = $("#river-hint");

    let mode = "idle";
    let progress = null;

    if (sendActive) {
      mode = "out";
      progress = s.send.progress;
    } else if (recvActive) {
      mode = "in";
      progress = s.receiver.progress;
    } else if (prevSendState === "sending" && s.send.state === "done") {
      mode = "done-out";
    } else if (prevRecvState === "receiving" && s.receiver.state === "listening") {
      mode = "done-in";
    } else if (window.CrocRiver.lastMode && window.CrocRiver.lastMode.startsWith("done")) {
      mode = window.CrocRiver.lastMode; // let the docked raft linger
    }

    const pct = progress && progress.pct != null ? progress.pct : null;
    window.CrocRiver.update(mode, pct);

    const active = mode === "out" || mode === "in";
    hint.hidden = active;
    plaque.hidden = !active;
    if (active) {
      const parts = [];
      if (progress && progress.file) parts.push(progress.file);
      parts.push(pct != null ? pct + "%" : "starting…");
      if (progress && progress.speed) parts.push(progress.speed);
      if (progress && progress.eta) parts.push(progress.eta + " left");
      plaque.textContent = parts.join(" · ");
    }

    const scene = $("#river-scene");
    scene.setAttribute("role", active ? "progressbar" : "button");
    if (active && pct != null) {
      scene.setAttribute("aria-valuenow", pct);
      scene.setAttribute("aria-valuemin", "0");
      scene.setAttribute("aria-valuemax", "100");
      scene.setAttribute("aria-label", (mode === "out" ? "Sending" : "Receiving") + ", " + pct + "%");
    } else if (!active) {
      scene.removeAttribute("aria-valuenow");
      scene.setAttribute("aria-label", "Send files: drop them here or press Enter to choose");
    }
  }

  async function refreshHistory() {
    try {
      const { transfers } = await (await fetch("/api/history")).json();
      const table = $("#history-table");
      const body = $("#history-body");
      $("#history-empty").hidden = transfers.length > 0;
      table.hidden = transfers.length === 0;
      body.innerHTML = "";
      for (const t of transfers) {
        const tr = document.createElement("tr");
        const cells = [
          { text: t.direction === "in" ? "← in" : "→ out", cls: "dir-" + t.direction },
          { text: t.files.join(", ") || "—", cls: "mono" },
          { text: fmtBytes(t.total_bytes), cls: "mono" },
          { text: fmtDuration(t.duration_s), cls: "mono" },
          { text: t.result, cls: "result-" + t.result },
        ];
        for (const c of cells) {
          const td = document.createElement("td");
          td.textContent = c.text;
          td.className = c.cls;
          tr.append(td);
        }
        body.append(tr);
      }
    } catch (e) {
      /* next poll retries */
    }
  }

  /* ---------- poll loop ---------- */

  async function tick() {
    let s = null;
    try {
      s = await (await fetch("/api/status")).json();
    } catch (e) {
      /* banner shown by render(null) */
    }
    render(s);
    const active =
      s &&
      (["staging", "connecting", "sending"].includes(s.send.state) ||
        s.receiver.state === "receiving");
    setTimeout(tick, active ? ACTIVE_MS : IDLE_MS);
  }

  /* ---------- sending ---------- */

  async function sendFiles(fileList) {
    if (!fileList || fileList.length === 0) return;
    const form = new FormData();
    for (const f of fileList) form.append("files[]", f, f.name);
    try {
      const res = await fetch("/api/send", { method: "POST", body: form });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        const errEl = $("#send-error");
        errEl.textContent = data.error || "Couldn't start the transfer.";
        errEl.hidden = false;
      }
    } catch (e) {
      /* status banner covers it */
    }
  }

  function wireDropZone() {
    const scene = $("#river-scene");
    const input = $("#file-input");

    scene.addEventListener("click", () => input.click());
    scene.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        input.click();
      }
    });
    $("#btn-pick-files").addEventListener("click", () => input.click());
    input.addEventListener("change", () => {
      sendFiles(input.files);
      input.value = "";
    });

    for (const evName of ["dragenter", "dragover"]) {
      scene.addEventListener(evName, (ev) => {
        ev.preventDefault();
        scene.classList.add("dragover");
      });
    }
    for (const evName of ["dragleave", "drop"]) {
      scene.addEventListener(evName, (ev) => {
        ev.preventDefault();
        scene.classList.remove("dragover");
      });
    }
    scene.addEventListener("drop", (ev) => sendFiles(ev.dataTransfer.files));
    // stray drops elsewhere must not navigate away from the app
    window.addEventListener("dragover", (ev) => ev.preventDefault());
    window.addEventListener("drop", (ev) => ev.preventDefault());
  }

  /* ---------- settings & unpair ---------- */

  function wireSettings() {
    const dialog = $("#settings-dialog");

    $("#btn-settings").addEventListener("click", async () => {
      try {
        const s = await (await fetch("/api/settings")).json();
        $("#set-device-name").value = s.device_name || "";
        $("#set-download-dir").value = s.download_dir || "";
        $("#set-relay").value = s.relay || "";
        $("#set-relay-pass").value = s.relay_pass || "";
        $("#set-socks5").value = s.socks5 || "";
        $("#set-overwrite").checked = !!s.overwrite;
        $("#settings-error").hidden = true;
        dialog.showModal();
      } catch (e) {
        /* status banner covers it */
      }
    });

    dialog.addEventListener("close", async () => {
      if (dialog.returnValue !== "save") return;
      const body = {
        device_name: $("#set-device-name").value.trim(),
        download_dir: $("#set-download-dir").value.trim(),
        relay: $("#set-relay").value.trim() || null,
        relay_pass: $("#set-relay-pass").value || null,
        socks5: $("#set-socks5").value.trim() || null,
        overwrite: $("#set-overwrite").checked,
      };
      const res = await fetch("/api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        $("#settings-error").textContent = data.error || "Couldn't save settings.";
        $("#settings-error").hidden = false;
        dialog.showModal();
      }
    });

    $("#btn-unpair").addEventListener("click", () => {
      $("#unpair-peer").textContent = $("#hdr-peer-name").textContent;
      $("#unpair-dialog").showModal();
    });

    $("#btn-unpair-confirm").addEventListener("click", async (ev) => {
      ev.preventDefault();
      await fetch("/api/unpair", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirm: true }),
      });
      $("#unpair-dialog").close();
      $("#settings-dialog").close();
      holdPairingScreen = false;
      location.reload();
    });
  }

  /* ---------- boot ---------- */

  document.addEventListener("DOMContentLoaded", () => {
    window.CrocRiver.init($("#river-scene"));
    window.CrocPairing.wire();
    wireDropZone();
    wireSettings();

    $("#btn-recheck-croc").addEventListener("click", () => location.reload());
    $("#btn-cancel-send").addEventListener("click", () =>
      fetch("/api/send/cancel", { method: "POST" })
    );
    $("#btn-open-folder").addEventListener("click", async () => {
      const data = await (await fetch("/api/open-folder", { method: "POST" })).json();
      const pathEl = $("#open-folder-path");
      pathEl.hidden = data.ok;
      if (!data.ok) pathEl.textContent = data.path;
    });

    // B side: after joining, keep the confirmation on screen until dismissed
    const joinResult = $("#join-result");
    const observer = new MutationObserver(() => {
      holdPairingScreen = !joinResult.hidden;
    });
    observer.observe(joinResult, { attributes: true, attributeFilter: ["hidden"] });
    $("#btn-join-done").addEventListener("click", () => {
      holdPairingScreen = false;
      joinResult.hidden = true;
    });

    tick();
  });
})();
