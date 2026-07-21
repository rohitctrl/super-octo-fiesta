/* Pairing wizard: create / join / confirm. Exposes window.CrocPairing. */
(function () {
  "use strict";

  const $ = (sel) => document.querySelector(sel);

  async function post(url, body) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || "Something went wrong. Try again.");
    return data;
  }

  function showError(el, err) {
    el.textContent = err.message || String(err);
    el.hidden = false;
  }

  function ownName() {
    return $("#own-name").value.trim();
  }

  function renderQR(text) {
    const tile = $("#qr-tile");
    try {
      const qr = window.qrcode(0, "M");
      qr.addData(text);
      qr.make();
      tile.innerHTML = qr.createSvgTag({ cellSize: 4, margin: 0, scalable: true });
    } catch (e) {
      tile.hidden = true; // string too long for QR? text copy still works
    }
  }

  function wire() {
    $("#btn-create-pairing").addEventListener("click", async () => {
      const errEl = $("#create-error");
      errEl.hidden = true;
      if (!ownName()) return showError(errEl, new Error("Name this device first."));
      try {
        const { pairing_string } = await post("/api/pair/create", { device_name: ownName() });
        $("#pairing-string-out").value = pairing_string;
        renderQR(pairing_string);
        $("#create-result").hidden = false;
        $("#btn-create-pairing").hidden = true;
      } catch (e) {
        showError(errEl, e);
      }
    });

    $("#btn-finish-pairing").addEventListener("click", async () => {
      const errEl = $("#create-error");
      errEl.hidden = true;
      try {
        await post("/api/pair/confirm", {
          confirmation_string: $("#confirmation-in").value.trim(),
        });
        // main screen takes over on the next status poll
      } catch (e) {
        showError(errEl, e);
      }
    });

    $("#btn-join-pairing").addEventListener("click", async () => {
      const errEl = $("#join-error");
      errEl.hidden = true;
      if (!ownName()) return showError(errEl, new Error("Name this device first."));
      try {
        const data = await post("/api/pair/accept", {
          pairing_string: $("#pairing-string-in").value.trim(),
          device_name: ownName(),
        });
        $("#join-peer-name").textContent = data.peer_name;
        $("#confirmation-out").value = data.confirmation_string;
        $("#join-result").hidden = false;
        $("#btn-join-pairing").hidden = true;
      } catch (e) {
        showError(errEl, e);
      }
    });

    document.querySelectorAll(".btn-copy").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const target = $(btn.dataset.copy);
        try {
          await navigator.clipboard.writeText(target.value);
        } catch (e) {
          target.select();
          document.execCommand("copy");
        }
        const old = btn.textContent;
        btn.textContent = "Copied";
        setTimeout(() => (btn.textContent = old), 1200);
      });
    });
  }

  window.CrocPairing = { wire };
})();
