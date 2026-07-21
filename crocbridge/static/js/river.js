/* The river crossing: CrocBridge's progress indicator.
 * Two banks, drifting water, and a raft that carries the package across.
 * Position = transfer percent. Sending crosses left->right, receiving
 * right->left. Exposes window.CrocRiver = { init, update }.
 */
(function () {
  "use strict";

  const X_START = 150;   // raft x at 0% (left bank edge)
  const X_END = 750;     // raft x at 100% (right bank edge)

  const SCENE = `
<svg viewBox="0 0 900 170" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
  <defs>
    <linearGradient id="waterFill" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="var(--water-glint)" stop-opacity="0.35"/>
      <stop offset="1" stop-color="var(--water)"/>
    </linearGradient>
  </defs>

  <!-- water -->
  <rect x="0" y="86" width="900" height="84" fill="url(#waterFill)"/>
  <g class="water-a" stroke="var(--water-glint)" stroke-width="2" fill="none" opacity="0.55">
    <path d="M-60 104 q 20 -6 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0"/>
  </g>
  <g class="water-b" stroke="var(--water-glint)" stroke-width="1.5" fill="none" opacity="0.3">
    <path d="M-60 132 q 25 -5 50 0 t 50 0 t 50 0 t 50 0 t 50 0 t 50 0 t 50 0 t 50 0 t 50 0 t 50 0 t 50 0 t 50 0 t 50 0 t 50 0 t 50 0 t 50 0 t 50 0 t 50 0 t 50 0 t 50 0"/>
  </g>

  <!-- banks -->
  <g fill="var(--bank-raised)">
    <path d="M0 170 L0 60 Q 60 52 110 70 Q 150 84 165 100 L 170 170 Z"/>
    <path d="M900 170 L900 60 Q 840 52 790 70 Q 750 84 735 100 L 730 170 Z"/>
  </g>
  <!-- reeds -->
  <g stroke="var(--sage-dim)" stroke-width="2.5" stroke-linecap="round" fill="none">
    <path d="M48 96 q -3 -20 2 -34"/><path d="M60 98 q 2 -24 -2 -38"/><path d="M74 100 q -1 -18 4 -30"/>
    <path d="M852 96 q 3 -20 -2 -34"/><path d="M840 98 q -2 -24 2 -38"/><path d="M826 100 q 1 -18 -4 -30"/>
  </g>
  <!-- lanterns on each bank -->
  <g>
    <circle id="lantern-own" cx="118" cy="58" r="5" fill="var(--amber-dim)"/>
    <line x1="118" y1="63" x2="118" y2="82" stroke="var(--bank-edge)" stroke-width="2.5"/>
    <circle id="lantern-peer" cx="782" cy="58" r="5" fill="var(--amber-dim)"/>
    <line x1="782" y1="63" x2="782" y2="82" stroke="var(--bank-edge)" stroke-width="2.5"/>
  </g>

  <!-- the raft -->
  <g id="raft" class="raft-hidden">
    <g class="raft-bob">
      <g id="raft-face">
        <!-- wake -->
        <g stroke="var(--water-glint)" stroke-width="2" fill="none" opacity="0.7">
          <path d="M-34 16 q -8 3 -16 2"/>
          <path d="M-30 22 q -10 4 -20 3"/>
        </g>
        <!-- plank -->
        <rect x="-30" y="8" width="60" height="10" rx="4" fill="#3a5a4b"/>
        <line x1="-22" y1="8" x2="-22" y2="18" stroke="var(--river-deep)" stroke-width="1.5"/>
        <line x1="0" y1="8" x2="0" y2="18" stroke="var(--river-deep)" stroke-width="1.5"/>
        <line x1="22" y1="8" x2="22" y2="18" stroke="var(--river-deep)" stroke-width="1.5"/>
        <!-- package -->
        <rect x="-14" y="-16" width="28" height="24" rx="3" fill="var(--amber)"/>
        <line x1="0" y1="-16" x2="0" y2="8" stroke="var(--amber-dim)" stroke-width="2.5"/>
        <line x1="-14" y1="-4" x2="14" y2="-4" stroke="var(--amber-dim)" stroke-width="2.5"/>
      </g>
    </g>
  </g>
</svg>`;

  let raft, raftFace, lanternOwn, lanternPeer;
  let lastMode = null;

  function init(container) {
    container.insertAdjacentHTML("afterbegin", SCENE);
    raft = container.querySelector("#raft");
    raftFace = container.querySelector("#raft-face");
    lanternOwn = container.querySelector("#lantern-own");
    lanternPeer = container.querySelector("#lantern-peer");
  }

  function place(pct, dir) {
    // dir 'out': own(left) -> peer(right); 'in': peer -> own
    const t = Math.max(0, Math.min(100, pct)) / 100;
    const x = dir === "in" ? X_END - (X_END - X_START) * t : X_START + (X_END - X_START) * t;
    raft.setAttribute("transform", `translate(${x.toFixed(1)} 118)`);
    // wake trails behind the direction of travel
    raftFace.setAttribute("transform", dir === "in" ? "scale(-1 1)" : "");
  }

  /* update({mode, pct}) — mode: idle | out | in | done-out | done-in */
  function update(mode, pct) {
    if (!raft) return;
    const active = mode === "out" || mode === "in";
    raft.classList.toggle("raft-hidden", mode === "idle");

    if (active) {
      place(pct == null ? 2 : pct, mode);
      raft.classList.remove("dock-glow");
    } else if (mode === "done-out" || mode === "done-in") {
      place(100, mode === "done-in" ? "in" : "out");
      raft.classList.add("dock-glow");
      const dockLantern = mode === "done-in" ? lanternOwn : lanternPeer;
      dockLantern.setAttribute("fill", "var(--amber-bright)");
      setTimeout(() => {
        dockLantern.setAttribute("fill", "var(--amber-dim)");
        raft.classList.remove("dock-glow");
      }, 2500);
    }
    lastMode = mode;
  }

  window.CrocRiver = { init, update, get lastMode() { return lastMode; } };
})();
