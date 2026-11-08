/*!
 * finspider spider widget - <fin-spider>
 *
 * A blue-and-white spider reads a company's financial statements: for each key metric it
 * walks to the statement sheet, picks up the exact figures, carries them to the scorecard
 * web and works out the result in a "Workings" panel - with the source of every number.
 *
 * Usage (any page / dashboard):
 *   load this file with a script tag (src="finspider-spider.js"), then
 *   <fin-spider src="spider.json"></fin-spider>
 *   ...or el.data = {...}  ...or an inline JSON script child (type="application/json").
 *
 * Attributes:
 *   src          URL of a spider.json produced by finspider
 *   theme        auto (default) | light | dark
 *   speed        animation speed multiplier (default 1)
 *   autoplay     "false" to wait for el.play()
 *   transparent  present -> no card background (blend into your page)
 *   compact      present -> web only: no statements sheet, no workings (small tiles)
 *
 * CSS custom properties: --fs-font (font family), --fs-mono (numbers).
 * Events: "fin-spider:pick" {detail: metric}, "fin-spider:done" {detail: data}
 * No dependencies. Respects prefers-reduced-motion. Clicking a statement figure opens its source.
 */
(() => {
  if (customElements.get("fin-spider")) return;

  const NS = "http://www.w3.org/2000/svg";
  const TAU = Math.PI * 2;
  const S = 0.88;                       // spider scale on the stage
  const CANCEL = Symbol("cancel");

  // Two stage layouts: statements sheet + web ("full"), or the web alone ("web").
  const LAYOUTS = {
    full: { vb: { x: 0, y: 0, w: 1160, h: 600 }, cx: 826, cy: 304, R: 180,
            sheet: { x: 6, y: 10, w: 462, h: 580 } },
    web: { vb: { x: -80, y: 0, w: 760, h: 620 }, cx: 300, cy: 312, R: 218, sheet: null },
  };
  const FULL_MIN_WIDTH = 720;            // narrower than this -> web layout

  const svg = (tag, attrs = {}, parent) => {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  };
  const html = (tag, cls, parent, text) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    if (parent) parent.appendChild(e);
    return e;
  };
  const lerp = (a, b, t) => a + (b - a) * t;
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const easeInOut = t => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2);
  const easeOut = t => 1 - Math.pow(1 - t, 3);
  const angDiff = (a, b) => { let d = (b - a) % TAU; if (d > Math.PI) d -= TAU; if (d < -Math.PI) d += TAU; return d; };
  const fmt = (v, d = 1) => (v == null ? "n/a" : Number(v).toFixed(d));
  const safeUrl = u => (/^https:\/\//.test(u || "") ? u : null);

  const FLAG = {
    good: { icon: "✓", text: "Strong" },
    ok: { icon: "•", text: "OK" },
    bad: { icon: "!", text: "Concern" },
    unverified: { icon: "?", text: "Unverified" },
    "n/a": { icon: "–", text: "No data" },
  };
  const STATUS = {
    official: { label: "Official filing", short: "Filing" },
    verified: { label: "Verified: two sources agree", short: "Verified" },
    single: { label: "Single source", short: "1 source" },
    mismatch: { label: "Sources disagree: not scored", short: "Disputed" },
  };
  const VERDICT_TONE = { "Strong Accumulate": "good", "Accumulate": "good", "Hold": "ok", "Avoid": "bad" };

  const CSS = `
  :host{display:block;container-type:inline-size;font-family:var(--fs-font,system-ui,-apple-system,"Segoe UI",sans-serif);
    --bg:#ffffff;--ink:#0b1a33;--ink2:#41526e;--muted:#6f7d96;--line:#dde6f3;--card:#f5f8fd;--card-on:#eaf2fd;
    --silk:#c9ddf6;--silk2:#93bdee;--accent:#2a78d6;--accent-ink:#1c5cab;--accent-soft:#e3eefc;
    --sheet:#fbfcfe;--cell-hl:#d6e7fb;
    --sp-body:#1f63c2;--sp-body2:#2a78d6;--sp-dark:#0f3f86;--sp-white:#ffffff;--sp-shadow:rgba(16,52,110,.18);
    --poly:rgba(42,120,214,.12);--poly-line:#2a78d6;
    --good:#0f7d0f;--ok:#a86f00;--bad:#c22f2f;--good-bg:#e3f4e3;--ok-bg:#fdf1d6;--bad-bg:#fbe3e3;
    --st-official:#2a78d6;--st-verified:#0f8a0f;--st-single:#97a3b6;--st-mismatch:#d48a00;}
  :host([theme="dark"]){--bg:#0d1a2e;--ink:#eef4ff;--ink2:#b8c7e2;--muted:#8394b0;--line:#1f3459;--card:#122544;--card-on:#173262;
    --silk:rgba(255,255,255,.15);--silk2:rgba(255,255,255,.4);--accent:#6aa6ef;--accent-ink:#9cc4f5;--accent-soft:#18325c;
    --sheet:#10213b;--cell-hl:#1f4479;
    --sp-body:#3a88e8;--sp-body2:#5a9cec;--sp-dark:#1c5cab;--sp-white:#ffffff;--sp-shadow:rgba(0,0,0,.22);
    --poly:rgba(106,166,239,.16);--poly-line:#8fbdf3;
    --good:#45c845;--ok:#f4b232;--bad:#ff7070;--good-bg:rgba(69,200,69,.14);--ok-bg:rgba(244,178,50,.14);--bad-bg:rgba(255,112,112,.14);
    --st-official:#6aa6ef;--st-verified:#45c845;--st-single:#6c7a92;--st-mismatch:#f4b232;}
  @media (prefers-color-scheme: dark){:host(:not([theme="light"])){--bg:#0d1a2e;--ink:#eef4ff;--ink2:#b8c7e2;--muted:#8394b0;--line:#1f3459;--card:#122544;--card-on:#173262;
    --silk:rgba(255,255,255,.15);--silk2:rgba(255,255,255,.4);--accent:#6aa6ef;--accent-ink:#9cc4f5;--accent-soft:#18325c;
    --sheet:#10213b;--cell-hl:#1f4479;
    --sp-body:#3a88e8;--sp-body2:#5a9cec;--sp-dark:#1c5cab;--sp-white:#ffffff;--sp-shadow:rgba(0,0,0,.22);
    --poly:rgba(106,166,239,.16);--poly-line:#8fbdf3;
    --good:#45c845;--ok:#f4b232;--bad:#ff7070;--good-bg:rgba(69,200,69,.14);--ok-bg:rgba(244,178,50,.14);--bad-bg:rgba(255,112,112,.14);
    --st-official:#6aa6ef;--st-verified:#45c845;--st-single:#6c7a92;--st-mismatch:#f4b232;}}
  :host([transparent]){--bg:transparent}
  *{box-sizing:border-box}
  .fs{position:relative;display:flex;flex-direction:column;gap:14px;background:var(--bg);border-radius:14px;
    padding:16px;color:var(--ink);border:1px solid var(--line)}
  :host([transparent]) .fs{border:none;padding:0}
  .num,.val,.wval,.wres,.vscore{font-family:var(--fs-mono,inherit);font-variant-numeric:tabular-nums}
  /* header */
  .bar{display:flex;flex-wrap:wrap;align-items:flex-end;justify-content:space-between;gap:12px 20px}
  .co{font-weight:650;font-size:17px;line-height:1.25}
  .tk{font-weight:500;color:var(--muted);font-size:13px;margin-left:6px}
  .sub{color:var(--muted);font-size:12.5px;margin-top:3px}
  .right{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
  .vpill{font-weight:650;font-size:14px;padding:6px 12px;border-radius:999px;background:var(--card);color:var(--ink2);transition:background .5s,color .5s}
  .vpill.good{background:var(--good-bg);color:var(--good)} .vpill.ok{background:var(--ok-bg);color:var(--ok)}
  .vpill.bad{background:var(--bad-bg);color:var(--bad)}
  .vscore{font-size:24px;font-weight:700} .vscore small{font-size:12px;color:var(--muted);font-weight:500}
  button{font:inherit;font-size:12.5px;font-weight:600;color:var(--accent-ink);background:var(--card);border:1px solid var(--line);
    border-radius:999px;padding:6px 12px;cursor:pointer}
  button:hover{border-color:var(--accent)}
  button:focus-visible,li:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
  .status{font-size:12.5px;color:var(--ink2);display:flex;align-items:center;gap:8px;min-height:18px}
  .dot{width:7px;height:7px;border-radius:50%;background:var(--accent);animation:pulse 1.2s infinite;flex:none}
  .status.done .dot{animation:none;opacity:.35}
  @keyframes pulse{50%{opacity:.25;transform:scale(.7)}}
  .vnote{font-size:12px;color:var(--muted)}
  .notice{font-size:12.5px;color:var(--ink2);background:var(--ok-bg);border-left:3px solid var(--st-mismatch);
    border-radius:0 8px 8px 0;padding:8px 12px;line-height:1.45}
  :host([compact]) .notice{display:none}
  /* stage */
  .stage{position:relative;min-width:0}
  .stage svg{width:100%;height:auto;display:block;overflow:hidden;touch-action:manipulation}
  .tip{position:absolute;pointer-events:none;background:var(--bg);color:var(--ink);border:1px solid var(--line);
    box-shadow:0 6px 24px rgba(10,40,90,.16);border-radius:10px;padding:8px 10px;font-size:12px;max-width:260px;
    opacity:0;transform:translate(-50%,calc(-100% - 12px));transition:opacity .15s;z-index:3}
  .tip b{display:block;font-size:12.5px;margin-bottom:2px}
  .tip .t2{color:var(--ink2);line-height:1.4}
  /* workings */
  .work{display:flex;flex-direction:column;gap:10px}
  .whead{display:flex;justify-content:space-between;align-items:baseline;gap:10px;flex-wrap:wrap;border-top:1px solid var(--line);padding-top:12px}
  .whead h3{margin:0;font-size:14px;font-weight:650;letter-spacing:.02em}
  .whead span{font-size:12px;color:var(--muted)}
  .legend{display:flex;gap:14px;flex-wrap:wrap;font-size:11.5px;color:var(--muted)}
  .legend i{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px;vertical-align:0}
  ol{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:10px}
  li{background:var(--card);border-radius:12px;padding:12px 14px;cursor:pointer;border:1px solid transparent;
    animation:cardIn .5s cubic-bezier(.2,.9,.25,1.1) both;transition:background .25s,border-color .25s;display:flex;flex-direction:column;gap:8px}
  li:hover{border-color:var(--silk2)} li.on{background:var(--card-on);border-color:var(--accent)}
  @keyframes cardIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
  .row{display:flex;align-items:center;gap:8px}
  .numb{flex:none;width:20px;height:20px;border-radius:50%;background:var(--accent);color:#fff;font-size:11px;font-weight:700;display:grid;place-items:center}
  .nm{font-weight:650;font-size:13.5px;flex:1;min-width:0}
  .wres{font-weight:700;font-size:14px;transition:opacity .3s} .wres.pending{opacity:.35}
  .formula{font-size:12px;color:var(--muted)}
  dl{margin:0;display:flex;flex-direction:column;gap:4px;border-top:1px dashed var(--line);padding-top:7px}
  dl div{display:grid;grid-template-columns:minmax(0,1fr) auto auto;gap:8px;align-items:center;font-size:12.3px}
  dt{color:var(--ink2);min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  dd{margin:0}
  .wval{font-weight:600;transition:color .3s} .wval.pending{color:var(--muted)}
  .wval.flash{animation:flash .9s}
  @keyframes flash{0%{background:var(--cell-hl)}100%{background:transparent}}
  .src{font-size:10.5px;font-weight:650;padding:1px 7px;border-radius:999px;border:1px solid currentColor;text-decoration:none;white-space:nowrap}
  .src.official{color:var(--st-official)} .src.verified{color:var(--st-verified)} .src.single{color:var(--st-single)}
  .src.mismatch{color:var(--st-mismatch)}
  a.src:hover{background:var(--accent-soft)}
  .meta{display:flex;gap:6px;flex-wrap:wrap;align-items:center;font-size:11px;color:var(--muted)}
  .badge{font-weight:650;padding:2px 8px;border-radius:999px;font-size:11px}
  .badge.good{background:var(--good-bg);color:var(--good)} .badge.ok{background:var(--ok-bg);color:var(--ok)}
  .badge.bad{background:var(--bad-bg);color:var(--bad)} .badge.unverified{background:var(--card-on);color:var(--st-mismatch)}
  .sent{font-size:12.2px;color:var(--ink2);margin:0;line-height:1.45}
  .rf{font-size:11.5px;color:var(--bad);line-height:1.35}
  .foot{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;font-size:11.5px;color:var(--muted)}
  .ghost{position:absolute;left:0;top:0;z-index:4;pointer-events:none;font:600 12px var(--fs-mono,inherit);
    background:var(--accent);color:#fff;border-radius:999px;padding:3px 9px;box-shadow:0 4px 14px rgba(20,70,150,.3);white-space:nowrap}
  .err{padding:24px;color:var(--muted);font-size:13px}
  :host([compact]) .bar,:host([compact]) .work,:host([compact]) .status,:host([compact]) .vnote{display:none}
  :host([compact]) .fs{padding:10px}
  /* stage drawing */
  .spoke{stroke:var(--silk2);stroke-width:1.2;fill:none} .radial{stroke:var(--silk);stroke-width:.8;fill:none}
  .ring{stroke:var(--silk);stroke-width:.9;fill:none} .ring.major{stroke:var(--silk2);stroke-width:1}
  .spoke.na{stroke-dasharray:3 4}
  .clab{fill:var(--ink);font-size:13.5px;font-weight:650} .cval{fill:var(--muted);font-size:12px;font-variant-numeric:tabular-nums}
  :host([compact]) .clab{font-size:18px} :host([compact]) .cval{font-size:15px}
  .ringlab{fill:var(--muted);font-size:9.5px}
  .node{fill:var(--accent);stroke:var(--bg);stroke-width:1.5;opacity:.38;transition:opacity .4s} .node.picked{opacity:1}
  .halo{fill:none;stroke-width:2.2;opacity:0}
  .halo.good,.rip.good{stroke:var(--good)} .halo.ok,.rip.ok{stroke:var(--ok)} .halo.bad,.rip.bad{stroke:var(--bad)}
  .halo.unverified,.rip.unverified{stroke:var(--st-mismatch)}
  .hit{fill:transparent;cursor:pointer} .rip{fill:none;stroke-width:2}
  .tag rect{fill:var(--bg);stroke:var(--line)} .tag text{fill:var(--ink);font-size:12px;font-weight:600}
  :host([compact]) .tag text{font-size:16px}
  .tag .tv{fill:var(--accent-ink);font-weight:700}
  .poly{fill:var(--poly);stroke:var(--poly-line);stroke-width:2;stroke-linejoin:round;opacity:0}
  .trail{fill:none;stroke:var(--sp-white);stroke-width:1.6;stroke-linecap:round;stroke-linejoin:round;filter:drop-shadow(0 0 1px var(--poly-line))}
  .thread{stroke:var(--silk2);stroke-width:1.2} .carry-thread{stroke:var(--silk2);stroke-width:1.1;fill:none}
  .pill rect{fill:var(--accent)} .pill text{fill:#fff;font-size:12px;font-weight:650;font-variant-numeric:tabular-nums}
  .cverdict{fill:var(--ink);font-size:20px;font-weight:700;opacity:0}
  :host(:not([compact])) .cverdict{display:none}
  /* statement sheet */
  .sh-bg{fill:var(--sheet);stroke:var(--line)}
  .sh-title{fill:var(--ink);font-size:16px;font-weight:650} .sh-unit{fill:var(--muted);font-size:12.5px}
  .sh-tab{fill:var(--muted);font-size:14px;font-weight:600;cursor:pointer} .sh-tab.on{fill:var(--accent-ink)}
  .sh-ul{fill:var(--accent);transition:transform .35s cubic-bezier(.3,.7,.3,1),width .35s}
  .sh-rule{stroke:var(--line)} .sh-yr{fill:var(--muted);font-size:12.5px;font-weight:600}
  .sh-lab{fill:var(--ink2);font-size:15px} .sh-lab.on{fill:var(--ink);font-weight:650}
  .sh-val{fill:var(--ink);font-size:15px;font-variant-numeric:tabular-nums;cursor:pointer}
  .sh-val.mismatch{fill:var(--st-mismatch)}
  .sh-note{fill:var(--muted);font-size:10.5px}
  .sh-hl{fill:var(--cell-hl);opacity:0;transition:opacity .3s} .sh-hl.on{opacity:1}
  .sh-dot.official{fill:var(--st-official)} .sh-dot.verified{fill:var(--st-verified)} .sh-dot.single{fill:var(--st-single)}
  .sh-dot.mismatch{fill:var(--st-mismatch)}
  .sh-src-h{fill:var(--muted);font-size:11.5px;font-weight:650;letter-spacing:.06em}
  .sh-src{fill:var(--ink2);font-size:13px} .sh-link{fill:var(--accent-ink);cursor:pointer}
  .sh-leg{fill:var(--muted);font-size:12px}
  .sh-note{fill:var(--muted);font-size:11.5px}
  .sp-shadow{fill:var(--sp-shadow)}
  .leg{fill:none;stroke:var(--sp-body);stroke-linecap:round;stroke-linejoin:round}
  .leg-f{stroke-width:3.6}.leg-t{stroke-width:2.3;stroke:var(--sp-body2)}
  .joint{fill:var(--sp-white)} .tipdot{fill:var(--sp-dark)}
  .b1{fill:var(--sp-body)} .b2{fill:var(--sp-body2)} .bdark{fill:var(--sp-dark)}
  .mark{fill:none;stroke:var(--sp-white);stroke-width:2.2;stroke-linecap:round;stroke-linejoin:round}
  .markf{fill:var(--sp-white)} .gloss{fill:#fff;opacity:.28}
  .eye{fill:var(--sp-white)} .pupil{fill:#0a1f44}
  .palp{fill:none;stroke:var(--sp-dark);stroke-width:2.2;stroke-linecap:round}
  `;

  // ------------------------------------------------------------------ spider
  class Spider {
    constructor(parent, x) {
      this.x = x; this.y = -120; this.a = Math.PI / 2;
      this.speed = 0; this.maxSpeed = 175; this.turnRate = 5.2; this.arriveK = 3.4; this.t = 0; this.still = 0;
      this.pose = 0.5; this.mode = "hang"; this.target = null; this.faceTo = null;
      this.spinning = false; this.trailPts = []; this.trail = null;

      this.shadow = svg("ellipse", { class: "sp-shadow", rx: 34 * S, ry: 26 * S, filter: "url(#fs-blur)" }, parent);
      this.thread = svg("line", { class: "thread" }, parent);
      this.g = svg("g", {}, parent);
      this.legsG = svg("g", {}, this.g);
      this.bodyG = svg("g", {}, this.g);
      this.abd = svg("g", {}, this.bodyG);
      // abdomen: blue with white chevrons and spots
      svg("ellipse", { cx: -22, cy: 0, rx: 19, ry: 14.5, class: "b1" }, this.abd);
      svg("ellipse", { cx: -24, cy: 0, rx: 13, ry: 9, class: "b2" }, this.abd);
      svg("path", { class: "mark", d: "M-35,-4.5 L-30,0 L-35,4.5 M-28,-6.5 L-22.5,0 L-28,6.5 M-20.5,-7 L-15,0 L-20.5,7" }, this.abd);
      svg("circle", { cx: -12, cy: -8.5, r: 2, class: "markf" }, this.abd);
      svg("circle", { cx: -12, cy: 8.5, r: 2, class: "markf" }, this.abd);
      svg("ellipse", { cx: -18, cy: -7, rx: 7, ry: 3, class: "gloss" }, this.abd);
      // pedicel + cephalothorax
      svg("ellipse", { cx: -5, cy: 0, rx: 3.5, ry: 3, class: "bdark" }, this.bodyG);
      svg("ellipse", { cx: 3, cy: 0, rx: 11.5, ry: 9.5, class: "b1" }, this.bodyG);
      svg("path", { class: "mark", d: "M-4,0 L5,0", "stroke-width": 1.6 }, this.bodyG);
      svg("ellipse", { cx: 1, cy: -4.5, rx: 5, ry: 2, class: "gloss" }, this.bodyG);
      svg("path", { class: "palp", d: "M12,-4 q6,-2 9,1.5 M12,4 q6,2 9,-1.5" }, this.bodyG);
      this.pupils = [];
      for (const y of [-3.4, 3.4]) {
        svg("circle", { cx: 10.2, cy: y, r: 2.6, class: "eye" }, this.bodyG);
        this.pupils.push(svg("circle", { cx: 11, cy: y, r: 1.15, class: "pupil" }, this.bodyG));
        svg("circle", { cx: 7, cy: y * 1.9, r: 1.1, class: "eye" }, this.bodyG);
      }

      const hips = [[8, 5.5], [4, 8], [-1, 8.5], [-5, 7]];
      const rests = [[42, 29], [19, 45], [-15, 45], [-40, 31]];
      this.legs = [];
      for (const side of [-1, 1]) {
        for (let i = 0; i < 4; i++) {
          const hip = { x: hips[i][0], y: hips[i][1] * side };
          const rest = { x: rests[i][0], y: rests[i][1] * side };
          const L = Math.hypot(rest.x - hip.x, rest.y - hip.y);
          const g = svg("g", {}, this.legsG);
          this.legs.push({
            side, i, hip, rest, a: L * 0.66, b: L * 0.7, group: (i + (side > 0 ? 1 : 0)) % 2,
            foot: null, step: null, tap: null, lift: 0,
            femur: svg("path", { class: "leg leg-f" }, g), tibia: svg("path", { class: "leg leg-t" }, g),
            knee: svg("circle", { r: 1.7, class: "joint" }, g), tip: svg("circle", { r: 1.4, class: "tipdot" }, g),
          });
        }
      }
    }

    toWorld(lx, ly) {
      const c = Math.cos(this.a), s = Math.sin(this.a);
      return { x: this.x + (lx * c - ly * s) * S, y: this.y + (lx * s + ly * c) * S };
    }
    toLocal(wx, wy) {
      const c = Math.cos(this.a), s = Math.sin(this.a), dx = (wx - this.x) / S, dy = (wy - this.y) / S;
      return { x: dx * c + dy * s, y: -dx * s + dy * c };
    }
    restWorld(leg) {
      const p = this.pose;
      return this.toWorld(leg.hip.x + (leg.rest.x - leg.hip.x) * p, leg.hip.y + (leg.rest.y - leg.hip.y) * p);
    }
    spinneret() { return this.toWorld(-41, 0); }

    walkTo(x, y, { arrive = true } = {}) {
      return new Promise(res => { this.target = { x, y, arrive, res }; this.faceTo = null; });
    }
    face(angle) {
      return new Promise(res => { this.target = null; this.faceTo = { angle, res }; });
    }
    tap(x, y, dur = 0.75) {
      return new Promise(res => {
        let left = 2;
        for (const leg of this.legs) {
          if (leg.i !== 0) continue;
          // each front leg taps its own side of the point so they never cross
          const perp = { x: -Math.sin(this.a) * leg.side * 9 * S, y: Math.cos(this.a) * leg.side * 9 * S };
          leg.step = null;
          leg.tap = { from: { ...leg.foot }, to: { x: x + perp.x, y: y + perp.y }, t: 0, dur,
            res: () => { if (--left === 0) res(); } };
        }
      });
    }

    update(dt) {
      this.t += dt;
      if (this.mode === "free") {
        if (this.target) {
          const dx = this.target.x - this.x, dy = this.target.y - this.y, d = Math.hypot(dx, dy);
          const diff = angDiff(this.a, Math.atan2(dy, dx));
          this.a += clamp(diff, -this.turnRate * dt, this.turnRate * dt);
          const align = Math.max(0, Math.cos(diff));
          const want = (this.target.arrive ? Math.min(this.maxSpeed, d * this.arriveK) : this.maxSpeed) * align * align;
          this.speed = lerp(this.speed, want, 1 - Math.exp(-7 * dt));
          if (d < 26) {      // close in directly so we never orbit the target
            const k = Math.min(1, (this.speed * dt) / Math.max(d, 1e-6));
            this.x += dx * k; this.y += dy * k;
          } else {
            this.x += Math.cos(this.a) * this.speed * dt; this.y += Math.sin(this.a) * this.speed * dt;
          }
          if (d < (this.target.arrive ? 1.2 : 16)) {
            const r = this.target.res; this.target = null; if (!this.spinning) this.speed *= 0.5; r();
          }
        } else {
          this.speed = lerp(this.speed, 0, 1 - Math.exp(-10 * dt));
          if (this.faceTo) {
            const diff = angDiff(this.a, this.faceTo.angle);
            this.a += clamp(diff, -this.turnRate * 0.8 * dt, this.turnRate * 0.8 * dt);
            if (Math.abs(diff) < 0.02) { const r = this.faceTo.res; this.faceTo = null; r(); }
          }
        }
      }
      const moving = this.speed > 10 || !!this.faceTo;
      this.still = moving ? 0 : this.still + dt;

      // legs: alternating tetrapod gait (two groups of four)
      const vx = Math.cos(this.a) * this.speed, vy = Math.sin(this.a) * this.speed;
      const busy = [false, false];
      for (const l of this.legs) if (l.step) busy[l.group] = true;
      for (const leg of this.legs) {
        const rw = this.restWorld(leg);
        const desired = { x: rw.x + vx * 0.17, y: rw.y + vy * 0.17 };
        if (this.mode === "hang" || !leg.foot) {
          const w = this.mode === "hang" ? Math.sin(this.t * 7 + leg.i * 1.4 + (leg.side > 0 ? 0.8 : 0)) * 3 * S : 0;
          const ux = rw.x - this.x, uy = rw.y - this.y, ul = Math.hypot(ux, uy) || 1;
          leg.foot = { x: rw.x + (ux / ul) * w, y: rw.y + (uy / ul) * w }; leg.lift = 0; continue;
        }
        if (leg.tap) {
          const tp = leg.tap; tp.t += dt / tp.dur;
          const k = Math.abs(Math.sin(Math.PI * 2 * Math.min(tp.t, 1)));  // two taps
          leg.foot = { x: lerp(tp.from.x, tp.to.x, k), y: lerp(tp.from.y, tp.to.y, k) };
          leg.lift = k * 0.8;
          if (tp.t >= 1) { leg.foot = { ...tp.from }; leg.tap = null; leg.lift = 0; tp.res(); }
          continue;
        }
        if (leg.step) {
          const st = leg.step; st.t += dt / st.dur;
          const k = easeInOut(Math.min(st.t, 1));
          leg.foot = { x: lerp(st.from.x, st.to.x, k), y: lerp(st.from.y, st.to.y, k) };
          leg.lift = Math.sin(Math.PI * Math.min(st.t, 1));
          if (st.t >= 1) { leg.step = null; leg.lift = 0; }
          continue;
        }
        const dist = Math.hypot(leg.foot.x - desired.x, leg.foot.y - desired.y);
        if (dist > 90 * S) { leg.foot = { ...desired }; continue; }
        const thresh = moving ? 17 * S : (this.still > 0.18 ? 3 * S : Infinity);
        if (dist > thresh && !busy[1 - leg.group]) {
          const over = moving ? 0.35 : 0;
          leg.step = {
            from: { ...leg.foot },
            to: { x: desired.x + (desired.x - leg.foot.x) * over, y: desired.y + (desired.y - leg.foot.y) * over },
            t: 0, dur: moving ? clamp(16 / Math.max(this.speed, 1), 0.07, 0.14) : 0.12,
          };
          busy[leg.group] = true;
        }
      }

      if (this.threadOn) {
        const sp = this.spinneret();
        const top = this.threadTop ?? -20;
        this.thread.setAttribute("x1", this.threadX ?? this.x); this.thread.setAttribute("y1", top);
        this.thread.setAttribute("x2", this.threadX ?? sp.x);
        this.thread.setAttribute("y2", this.threadRetract != null ? lerp(sp.y, top, this.threadRetract) : sp.y);
      }
      if (this.spinning && this.trail) {
        const sp = this.spinneret(), last = this.trailPts[this.trailPts.length - 1];
        if (!last || Math.hypot(sp.x - last[0], sp.y - last[1]) > 2) {
          this.trailPts.push([sp.x, sp.y]);
          this.trail.setAttribute("points", this.trailPts.map(p => p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" "));
        }
      }
      this.render();
    }

    render() {
      const deg = (this.a * 180) / Math.PI;
      this.g.setAttribute("transform", `translate(${this.x.toFixed(2)},${this.y.toFixed(2)}) rotate(${deg.toFixed(2)}) scale(${S})`);
      this.shadow.setAttribute("cx", (this.x + 5).toFixed(1));
      this.shadow.setAttribute("cy", (this.y + 9).toFixed(1));
      const walk = clamp(this.speed / this.maxSpeed, 0, 1);
      const bob = Math.sin(this.t * 22) * 1.1 * walk;
      const sway = Math.sin(this.t * 11) * 5 * walk + Math.sin(this.t * 1.7) * 1.2;
      const breathe = 1 + Math.sin(this.t * 2.4) * 0.025;
      this.bodyG.setAttribute("transform", `translate(${bob.toFixed(2)},0)`);
      this.abd.setAttribute("transform", `rotate(${sway.toFixed(2)},-7,0) translate(-7,0) scale(${breathe.toFixed(3)}) translate(7,0)`);
      const look = Math.sin(this.t * 0.9) > 0.85 ? 0.5 : Math.sin(this.t * 0.9) < -0.9 ? -0.5 : 0;
      this.pupils.forEach((p, k) => p.setAttribute("cy", ((k ? 3.4 : -3.4) + look).toFixed(2)));

      for (const leg of this.legs) {
        if (!leg.foot) continue;
        let f = this.toLocal(leg.foot.x, leg.foot.y);
        const h = leg.hip;
        let dx = f.x - h.x, dy = f.y - h.y, d = Math.hypot(dx, dy);
        // Seen from above, a spider's knee rises *up*, so it projects just outside the
        // hip->foot line. The shorter the projected reach, the higher (further out) the knee.
        const reach = leg.a + leg.b;
        const maxD = reach * 0.82, minD = 6;
        if (d > maxD || d < minD) {
          const k = clamp(d, minD, maxD) / Math.max(d, 1e-6);
          f = { x: h.x + dx * k, y: h.y + dy * k }; dx = f.x - h.x; dy = f.y - h.y; d = Math.hypot(dx, dy);
        }
        let px = -dy / d, py = dx / d;
        const flip = Math.abs(py) >= 0.2 ? py * leg.side < 0 : px * (leg.i < 2 ? 1 : -1) < 0;
        if (flip) { px = -px; py = -py; }
        const rise = Math.sqrt(Math.max(0, (reach * 0.82) ** 2 - d * d)) * 0.38 + 3 + leg.lift * 7;
        const knee = { x: h.x + dx * 0.42 + px * rise, y: h.y + dy * 0.42 + py * rise };
        const mx = (h.x + knee.x) / 2 + px * 2, my = (h.y + knee.y) / 2 + py * 2;
        leg.femur.setAttribute("d", `M${h.x},${h.y} Q${mx.toFixed(2)},${my.toFixed(2)} ${knee.x.toFixed(2)},${knee.y.toFixed(2)}`);
        const tx = (knee.x + f.x) / 2 + px * 1.5, ty = (knee.y + f.y) / 2 + py * 1.5;
        leg.tibia.setAttribute("d", `M${knee.x.toFixed(2)},${knee.y.toFixed(2)} Q${tx.toFixed(2)},${ty.toFixed(2)} ${f.x.toFixed(2)},${f.y.toFixed(2)}`);
        leg.knee.setAttribute("cx", knee.x.toFixed(2)); leg.knee.setAttribute("cy", knee.y.toFixed(2));
        leg.tip.setAttribute("cx", f.x.toFixed(2)); leg.tip.setAttribute("cy", f.y.toFixed(2));
        leg.tip.setAttribute("r", (1.4 + leg.lift * 0.8).toFixed(2));
      }
    }
  }

  // ------------------------------------------------------------------ widget
  class FinSpider extends HTMLElement {
    static get observedAttributes() { return ["src", "compact"]; }

    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this._run = 0; this._timers = []; this._clock = 0; this._last = 0; this._visible = true;
      this._tick = this._tick.bind(this);
    }

    connectedCallback() {
      if (this._started) return;
      this._started = true;
      const inline = this.querySelector('script[type="application/json"]');
      if (this._pending) this.data = this._pending;
      else if (inline) { try { this.data = JSON.parse(inline.textContent); } catch (e) { this._error("Invalid inline JSON: " + e.message); } }
      else if (this.getAttribute("src")) this._load(this.getAttribute("src"));
      this._io = new IntersectionObserver(es => { this._visible = es.some(e => e.isIntersecting); });
      this._io.observe(this);
      // switch between the full and web-only layout when the space changes
      this._ro = new ResizeObserver(() => {
        if (this._data && this._layoutName() !== this._layoutKey) { this._build(); this._finalState(); }
      });
      this._ro.observe(this);
    }
    disconnectedCallback() {
      cancelAnimationFrame(this._raf); this._raf = null;
      this._io && this._io.disconnect(); this._ro && this._ro.disconnect();
      this._run++; this._started = false;
    }
    attributeChangedCallback(name, old, val) {
      if (name === "src" && this._started && val && old !== val) this._load(val);
      if (name === "compact" && this._data && old !== val) { this._build(); this._finalState(); }
    }

    get data() { return this._data; }
    set data(d) {
      if (!this.isConnected) { this._pending = d; return; }
      this._data = d; this._build(); if (this.getAttribute("autoplay") !== "false") this.play();
    }

    async _load(url) {
      try {
        const r = await fetch(url);
        if (!r.ok) throw new Error("HTTP " + r.status);
        this.data = await r.json();
      } catch (e) { this._error(`Could not load ${url}: ${e.message}`); }
    }
    _error(msg) {
      this.shadowRoot.innerHTML = `<style>${CSS}</style><div class="fs"><div class="err"></div></div>`;
      this.shadowRoot.querySelector(".err").textContent = "finspider: " + msg;
    }
    get speed() { return clamp(parseFloat(this.getAttribute("speed") || "1") || 1, 0.25, 4); }
    get reduced() { return window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches; }
    _layoutName() {
      if (this.hasAttribute("compact") || !this._data || !this._data.statements) return "web";
      const w = this.clientWidth || 1000;
      return w < FULL_MIN_WIDTH ? "web" : "full";
    }

    // ---------- clock (pauses when off-screen or tab hidden)
    _tick(now) {
      // clamp: never run backwards (out-of-order timestamps) or jump after a long pause
      const dt = clamp((now - (this._last || now)) / 1000, 0, 0.05) * (this._visible ? 1 : 0) * this.speed;
      this._last = Math.max(now, this._last || 0);
      this._clock += dt;
      if (this.spider && dt > 0) { this.spider.update(dt); this._updateCarry(dt); }
      const due = [];
      this._timers = this._timers.filter(t => (this._clock >= t.at ? (due.push(t), false) : true));
      due.forEach(t => t.res());
      this._raf = requestAnimationFrame(this._tick);
    }
    sleep(ms) { return new Promise(res => this._timers.push({ at: this._clock + ms / 1000, res })); }
    tween(sec, fn) {          // runs fn(t) for t in 0..1 on the animation clock
      const t0 = this._clock;
      return new Promise(res => {
        const step = () => {
          const t = Math.min(1, (this._clock - t0) / sec);
          fn(t);
          if (t < 1) this._timers.push({ at: this._clock + 0.001, res: step }); else res();
        };
        step();
      });
    }

    // ---------- build
    _build() {
      const d = this._data;
      this._layoutKey = this._layoutName();
      const G = this._G = LAYOUTS[this._layoutKey];
      const root = this.shadowRoot;
      root.innerHTML = `<style>${CSS}</style>`;
      const fs = this.$fs = html("div", "fs", root);
      fs.setAttribute("part", "root");

      // header
      const bar = html("div", "bar", fs);
      const left = html("div", "", bar);
      const co = html("div", "co", left, d.company.name);
      html("span", "tk", co, d.company.ticker);
      const v = d.verification;
      const srcLine = !v ? "" : v.primary === "SEC EDGAR" ? `${v.official} figures from SEC 10-K filings`
        : v.verified > 0 ? `${v.verified} figures verified across two sources`
        : `Single source: ${v.primary} (no second source to cross-check)`;
      html("div", "sub", left, [d.profile === "financial" ? "Bank / NBFC profile" : "General profile",
        srcLine, `data as of ${d.generated}`].filter(Boolean).join(" · "));
      const right = html("div", "right", bar);
      this.$vpill = html("span", "vpill", right, "Verdict pending…");
      this.$vscore = html("span", "vscore", right);
      const replay = html("button", "", right, "↻ Replay");
      replay.type = "button";
      replay.addEventListener("click", () => this.play());
      this.$status = html("div", "status", fs);
      html("span", "dot", this.$status);
      this.$statusText = html("span", "", this.$status, "");
      this.$vnote = html("div", "vnote", fs);
      // data caveats worth a reader's attention (cross-check unavailable, disputed figures...)
      const notes = (d.notes || []).filter(n => /unavailable|differ|could not|not used/i.test(n));
      if (notes.length) html("div", "notice", fs, notes.slice(0, 2).join(" "));

      // stage
      const stage = html("div", "stage", fs);
      const vb = G.vb;
      const s = svg("svg", { viewBox: `${vb.x} ${vb.y} ${vb.w} ${vb.h}`, role: "img",
        "aria-label": `finspider analysis of ${d.company.name}: verdict ${d.verdict}, score ${fmt(d.overall)} out of 10` }, null);
      stage.appendChild(s);
      this.$tip = html("div", "tip", stage);
      const defs = svg("defs", {}, s);
      const f = svg("filter", { id: "fs-blur", x: "-50%", y: "-50%", width: "200%", height: "200%" }, defs);
      svg("feGaussianBlur", { stdDeviation: 4 }, f);
      this.$sheetL = svg("g", {}, s);
      this.$web = svg("g", {}, s);
      this.$poly = svg("path", { class: "poly" }, s);
      this.$trailG = svg("g", {}, s);
      this.$labels = svg("g", {}, s);
      this.$nodes = svg("g", {}, s);
      this.$fx = svg("g", {}, s);
      this.$tags = svg("g", {}, s);
      this.$carryG = svg("g", {}, s);
      this.$spiderG = svg("g", {}, s);
      this.$cverdict = svg("text", { class: "cverdict", x: vb.x + 10, y: 30 }, s);
      this.$svg = s;

      // workings
      const work = html("section", "work", fs);
      const wh = html("div", "whead", work);
      html("h3", "", wh, "Workings");
      const leg = html("div", "legend", wh);
      for (const k of ["official", "verified", "single", "mismatch"]) {
        const sp = html("span", "", leg);
        const i = html("i", "", sp); i.style.background = `var(--st-${k})`;
        sp.appendChild(document.createTextNode(STATUS[k].label));
      }
      this.$list = html("ol", "", work);
      const foot = html("div", "foot", work);
      html("span", "", foot, d.disclaimer || "Not investment advice.");
      html("span", "", foot, "Click any figure on the statements to open its source.");

      this._layout();
      if (G.sheet) this._buildSheet();
      if (!this._raf) this._raf = requestAnimationFrame(this._tick);
    }

    _layout() {
      const d = this._data, G = this._G;
      const cats = d.categories;
      const n = cats.length;
      const ang = i => -Math.PI / 2 + (i * TAU) / n;
      const rad = score => 22 + (clamp(score, 0, 10) / 10) * (G.R - 22);
      const radials = [];
      const per = 3;
      for (let i = 0; i < n * per; i++) radials.push({ a: -Math.PI / 2 + (i * TAU) / (n * per), major: i % per === 0, cat: cats[Math.floor(i / per)] });
      this._webPaths = [];
      for (const r of radials) {
        const p = svg("path", { class: r.major ? "spoke" + (r.cat.score == null ? " na" : "") : "radial",
          d: `M${G.cx},${G.cy} L${G.cx + Math.cos(r.a) * (G.R + 8)},${G.cy + Math.sin(r.a) * (G.R + 8)}` }, this.$web);
        this._webPaths.push({ p, delay: r.major ? 0 : 120, dur: 520 });
      }
      for (let lv = 1; lv <= 10; lv++) {
        const rr = rad(lv);
        let dd = "";
        radials.forEach((r, i) => {
          const r2 = radials[(i + 1) % radials.length];
          const p1 = [G.cx + Math.cos(r.a) * rr, G.cy + Math.sin(r.a) * rr];
          const p2 = [G.cx + Math.cos(r2.a) * rr, G.cy + Math.sin(r2.a) * rr];
          const c = [G.cx + ((p1[0] + p2[0]) / 2 - G.cx) * 0.93, G.cy + ((p1[1] + p2[1]) / 2 - G.cy) * 0.93];
          dd += (i === 0 ? `M${p1[0].toFixed(1)},${p1[1].toFixed(1)}` : "") + ` Q${c[0].toFixed(1)},${c[1].toFixed(1)} ${p2[0].toFixed(1)},${p2[1].toFixed(1)}`;
        });
        const p = svg("path", { class: "ring" + (lv % 2 === 0 ? " major" : ""), d: dd }, this.$web);
        this._webPaths.push({ p, delay: 520 + lv * 75, dur: 650 });
      }
      for (const lv of [5, 10]) {
        const t = svg("text", { class: "ringlab", x: G.cx + 4, y: G.cy - rad(lv) - 3 }, this.$labels);
        t.textContent = lv;
      }
      cats.forEach((c, i) => {
        const a = ang(i), lr = G.R + 30;
        const x = G.cx + Math.cos(a) * lr, y = G.cy + Math.sin(a) * lr;
        const anchor = Math.abs(Math.cos(a)) < 0.25 ? "middle" : Math.cos(a) > 0 ? "start" : "end";
        const yy = y + (Math.sin(a) > 0.5 ? 10 : Math.sin(a) < -0.5 ? -12 : 0);
        const t = svg("text", { class: "clab", x, y: yy, "text-anchor": anchor }, this.$labels);
        t.textContent = c.name;
        const v = svg("text", { class: "cval", x, y: yy + 15, "text-anchor": anchor }, this.$labels);
        v.textContent = c.score == null ? "not rated" : `${fmt(c.score)}/10 · ${Math.round(c.weight * 100)}%`;
      });
      this.$labels.style.opacity = 0;

      this._nodes = {};
      const catIdx = Object.fromEntries(cats.map((c, i) => [c.key, i]));
      const byCat = {};
      for (const m of d.metrics) if (m.score != null || m.flag === "unverified") (byCat[m.category] = byCat[m.category] || []).push(m);
      for (const [ck, ms] of Object.entries(byCat)) {
        const i = catIdx[ck];
        const step = Math.min((TAU / n) * 0.62 / Math.max(ms.length - 1, 1), 0.2);
        ms.forEach((m, j) => {
          const a = ang(i) + (j - (ms.length - 1) / 2) * step;
          const r = rad(m.score ?? 0);
          const x = G.cx + Math.cos(a) * r, y = G.cy + Math.sin(a) * r;
          const g = svg("g", {}, this.$nodes);
          const halo = svg("circle", { class: "halo " + m.flag, cx: x, cy: y, r: 9 }, g);
          const dot = svg("circle", { class: "node", cx: x, cy: y, r: 0 }, g);
          const hit = svg("circle", { class: "hit", cx: x, cy: y, r: 13, tabindex: 0 }, g);
          hit.addEventListener("pointerenter", () => this._tipMetric(m, x, y));
          hit.addEventListener("pointerleave", () => this._hideTip());
          hit.addEventListener("focus", () => this._tipMetric(m, x, y));
          hit.addEventListener("blur", () => this._hideTip());
          hit.addEventListener("click", () => this._goto(m.key));
          this._nodes[m.key] = { m, x, y, a, r, dot, halo };
        });
      }
      this._verts = cats.map((c, i) => (c.score == null ? null : {
        x: G.cx + Math.cos(ang(i)) * rad(c.score), y: G.cy + Math.sin(ang(i)) * rad(c.score) })).filter(Boolean);
      this.$poly.setAttribute("d", this._verts.length > 2
        ? "M" + this._verts.map(v => `${v.x.toFixed(1)},${v.y.toFixed(1)}`).join(" L") + " Z" : "");
    }

    // ---------- statement sheet
    _buildSheet() {
      const st = this._data.statements, srcs = this._data.sources || [];
      const { x, w } = this._G.sheet;
      // size the sheet to its tallest tab, centred vertically on the stage
      const tallest = Math.max(4, ...st.tabs.map(t => (t.key === "market" ? Math.ceil(t.rows.length * 40 / 34) : t.rows.length)));
      const h = Math.min(this._G.sheet.h, 124 + tallest * 34 + 116);
      const y = this._G.vb.y + (this._G.vb.h - h) / 2;
      const g = svg("g", {}, this.$sheetL);
      svg("rect", { x, y, width: w, height: h, rx: 12, class: "sh-bg" }, g);
      svg("text", { class: "sh-title", x: x + 18, y: y + 30 }, g).textContent = "Financial statements";
      const unit = svg("text", { class: "sh-unit", x: x + w - 18, y: y + 30, "text-anchor": "end" }, g);
      unit.textContent = `${st.unit} · fiscal years`;

      // tabs
      this._tabs = {};
      let tx = x + 18;
      const ul = svg("rect", { class: "sh-ul", x: 0, y: y + 62, height: 2.5, width: 10, rx: 1.2 }, g);
      this._tabUL = ul;
      svg("line", { class: "sh-rule", x1: x + 12, x2: x + w - 12, y1: y + 64.5, y2: y + 64.5 }, g);
      for (const tab of st.tabs) {
        const t = svg("text", { class: "sh-tab", x: tx, y: y + 54 }, g);
        t.textContent = tab.key === "income" ? "Income" : tab.key === "balance" ? "Balance sheet" : tab.key === "cashflow" ? "Cash flow" : "Market";
        const tw = t.getComputedTextLength ? t.getComputedTextLength() : 60;
        t.addEventListener("click", () => this._setTab(tab.key));
        this._tabs[tab.key] = { label: t, x: tx, w: tw, g: svg("g", { style: "display:none" }, g) };
        tx += tw + 22;
      }

      // rows
      this._cells = {};
      this._rowLabels = {};
      const years = st.years;
      const labW = 150, right = x + w - 12;
      const colW = (right - (x + labW)) / years.length;
      for (const tab of st.tabs) {
        const tg = this._tabs[tab.key].g;
        if (tab.key !== "market") {
          years.forEach((yr, i) => {
            const t = svg("text", { class: "sh-yr", x: x + labW + colW * (i + 1) - 10, y: y + 90, "text-anchor": "end" }, tg);
            t.textContent = "FY" + String(yr).slice(2);
          });
          tab.rows.forEach((row, r) => {
            const ry = y + 124 + r * 34;
            if (r) svg("line", { class: "sh-rule", x1: x + 12, x2: right, y1: ry - 21, y2: ry - 21, "stroke-opacity": 0.55 }, tg);
            const lab = svg("text", { class: "sh-lab", x: x + 18, y: ry }, tg);
            lab.textContent = row.label;
            this._rowLabels[`${tab.key}:${row.field}`] = lab;
            years.forEach((yr, i) => {
              const c = row.cells[String(yr)];
              if (!c) return;
              const cx1 = x + labW + colW * i, cxr = cx1 + colW;
              const hl = svg("rect", { class: "sh-hl", x: cx1 + 3, y: ry - 17, width: colW - 4, height: 25, rx: 5 }, tg);
              const tv = svg("text", { class: "sh-val " + c.s, x: cxr - 6, y: ry, "text-anchor": "end" }, tg);
              tv.textContent = c.d;
              // thin status bar under each figure (filing / verified / single source / disputed)
              svg("rect", { class: "sh-dot " + c.s, x: cx1 + 8, y: ry + 4, width: colW - 14, height: 2, rx: 1, opacity: 0.75 }, tg);
              const src = c.src != null ? srcs[c.src] : null;
              const cell = { tab: tab.key, hl, x: cx1 + colW / 2, y: ry - 5, right: cxr, label: row.label, year: yr,
                             display: c.d, status: c.s, src, check: c.check };
              this._cells[`${tab.key}:${row.field}:${yr}`] = cell;
              tv.addEventListener("pointerenter", () => this._tipCell(cell));
              tv.addEventListener("pointerleave", () => this._hideTip());
              tv.addEventListener("click", () => { const u = safeUrl(src && src.url); if (u) window.open(u, "_blank", "noopener"); });
            });
          });
        } else {
          tab.rows.forEach((row, r) => {
            const ry = y + 104 + r * 40;
            if (r) svg("line", { class: "sh-rule", x1: x + 12, x2: right, y1: ry - 22, y2: ry - 22, "stroke-opacity": 0.55 }, tg);
            const lab = svg("text", { class: "sh-lab", x: x + 18, y: ry }, tg);
            lab.textContent = row.label;
            if (row.note) svg("text", { class: "sh-note", x: x + 18, y: ry + 14 }, tg).textContent = row.note;
            const hl = svg("rect", { class: "sh-hl", x: right - 130, y: ry - 16, width: 130, height: 23, rx: 5 }, tg);
            const tv = svg("text", { class: "sh-val", x: right - 10, y: ry, "text-anchor": "end" }, tg);
            tv.textContent = row.display;
            this._cells[`market:${row.label}`] = { tab: "market", hl, x: right - 60, y: ry - 5, right, label: row.label,
              display: row.display, status: row.s, src: { source: "Yahoo Finance", doc: "Yahoo Finance market data (latest)",
              url: `https://finance.yahoo.com/quote/${encodeURIComponent(this._data.company.ticker)}/` } };
          });
        }
      }

      // source footer + legend
      const fy = y + h - 104;
      svg("line", { class: "sh-rule", x1: x + 12, x2: right, y1: fy, y2: fy }, g);
      svg("text", { class: "sh-src-h", x: x + 18, y: fy + 20 }, g).textContent = "SOURCE";
      this.$srcText = svg("text", { class: "sh-src", x: x + 18, y: fy + 38 }, g);
      this.$srcLink = svg("text", { class: "sh-src sh-link", x: x + 18, y: fy + 74 }, g);
      this.$srcLink.addEventListener("click", () => { const u = safeUrl(this._srcUrl); if (u) window.open(u, "_blank", "noopener"); });
      let lx = x + 18;
      for (const k of ["official", "verified", "single", "mismatch"]) {
        svg("circle", { class: "sh-dot " + k, cx: lx + 3, cy: y + h - 16, r: 3 }, g);
        const t = svg("text", { class: "sh-leg", x: lx + 10, y: y + h - 12 }, g);
        t.textContent = STATUS[k].short;
        lx += (t.getComputedTextLength ? t.getComputedTextLength() : 50) + 26;
      }
      this._setTab("income", true);
      this._showSource(null);
    }

    _setTab(key, instant) {
      if (!this._tabs || !this._tabs[key]) return;
      for (const [k, t] of Object.entries(this._tabs)) {
        t.g.style.display = k === key ? "" : "none";
        t.label.classList.toggle("on", k === key);
      }
      const t = this._tabs[key];
      if (instant) this._tabUL.style.transition = "none";
      this._tabUL.setAttribute("width", t.w);
      this._tabUL.style.transform = `translateX(${t.x}px)`;
      if (instant) requestAnimationFrame(() => (this._tabUL.style.transition = ""));
      this._tab = key;
    }

    _wrap(textEl, str, maxChars) {
      textEl.textContent = "";
      const words = String(str || "").split(/\s+/);
      let line = "", lines = [];
      for (const w of words) {
        if ((line + " " + w).trim().length > maxChars) { lines.push(line.trim()); line = w; } else line += " " + w;
      }
      if (line.trim()) lines.push(line.trim());
      lines.slice(0, 2).forEach((l, i) => {
        const ts = svg("tspan", { x: textEl.getAttribute("x"), dy: i ? 16 : 0 }, textEl);
        ts.textContent = l;
      });
    }

    _showSource(cell) {
      if (!this.$srcText) return;
      const v = this._data.verification || {};
      if (!cell) {
        const base = v.primary === "SEC EDGAR" ? "Official SEC 10-K filings, cross-checked against Yahoo Finance."
          : v.primary === "Screener.in" ? `Screener.in (company filings), each figure cross-checked against Yahoo Finance (±${v.tolerance_pct}%).`
          : "Yahoo Finance annual statements.";
        this._wrap(this.$srcText, base, 56);
        this.$srcLink.textContent = ""; this._srcUrl = null;
        return;
      }
      const s = cell.src || {};
      const what = `${cell.label}${cell.year ? " FY" + cell.year : ""}: ${s.doc || s.source || "source"}`;
      this._wrap(this.$srcText, what, 56);
      const u = safeUrl(s.url);
      this._srcUrl = u;
      this.$srcLink.textContent = u ? `${STATUS[cell.status] ? STATUS[cell.status].label : ""}${cell.check ? " (" + cell.check + ")" : ""} · open source ↗` : "";
    }

    // ---------- tooltips
    _tipAt(x, y) {
      const vb = this._G.vb, t = this.$tip;
      t.style.left = ((x - vb.x) / vb.w) * 100 + "%";
      t.style.top = ((y - vb.y) / vb.h) * 100 + "%";
      t.style.opacity = 1;
    }
    _tipMetric(m, x, y) {
      const t = this.$tip; t.innerHTML = "";
      html("b", "", t, `${m.label}: ${m.display}`);
      html("div", "t2", t, m.sentence);
      this._tipAt(x, y);
    }
    _tipCell(c) {
      const t = this.$tip; t.innerHTML = "";
      html("b", "", t, `${c.label}${c.year ? " · FY" + c.year : ""}: ${c.display}`);
      html("div", "t2", t, `${STATUS[c.status] ? STATUS[c.status].label : ""}. ${c.src ? c.src.doc : ""}${c.check ? ". " + c.check : ""}`);
      this._tipAt(c.x, c.y);
      this._showSource(c);
    }
    _hideTip() { this.$tip.style.opacity = 0; }

    // ---------- choreography
    _reset() {
      this._run++;
      this._timers = [];
      this.$spiderG.innerHTML = ""; this.$trailG.innerHTML = ""; this.$fx.innerHTML = ""; this.$tags.innerHTML = "";
      this.$carryG.innerHTML = ""; this._carry = [];
      this._tagBoxes = [];
      this.$list.innerHTML = "";
      this.$fs.querySelectorAll(".ghost").forEach(g => g.remove());
      this.$poly.style.opacity = 0; this.$poly.style.transition = "none";
      this.$labels.style.transition = "none"; this.$labels.style.opacity = 0;
      for (const n of Object.values(this._nodes)) {
        n.dot.classList.remove("picked"); n.dot.setAttribute("r", 0); n.halo.style.opacity = 0; n.picked = false;
      }
      for (const w of this._webPaths) { w.p.getAnimations?.().forEach(a => a.cancel()); w.p.style.strokeDasharray = ""; w.p.style.strokeDashoffset = ""; }
      this._clearHighlights();
      if (this._tabs) { this._setTab("income", true); this._showSource(null); }
      this.$vpill.className = "vpill"; this.$vpill.textContent = "Verdict pending…";
      this.$vscore.innerHTML = ""; this.$vnote.textContent = "";
      this.$cverdict.style.transition = "none"; this.$cverdict.style.opacity = 0;
      this.$status.classList.remove("done");
      this.spider = new Spider(this.$spiderG, this._G.cx);
      if (this._G.sheet) {            // longer trips in the full layout: walk faster, turn quicker
        Object.assign(this.spider, { maxSpeed: 470, turnRate: 8, arriveK: 5.5 });
      }
      this._cards = {};
      return this._run;
    }
    _check(run) { if (run !== this._run) throw CANCEL; }

    async play() {
      if (!this._data) return;
      const run = this._reset();
      const d = this._data, G = this._G;
      if (this.reduced) { this._finalState(); return; }
      try {
        this._status(`Opening ${d.company.name}'s financial statements…`);
        for (const w of this._webPaths) {
          const len = w.p.getTotalLength();
          w.p.style.strokeDasharray = len; w.p.style.strokeDashoffset = len;
          w.p.animate([{ strokeDashoffset: len }, { strokeDashoffset: 0 }],
            { duration: w.dur / this.speed, delay: w.delay / this.speed, easing: "cubic-bezier(.3,.6,.3,1)", fill: "forwards" });
        }
        await this.sleep(700); this._check(run);
        this.$labels.style.transition = "opacity .8s"; this.$labels.style.opacity = 1;
        Object.values(this._nodes).sort((a, b) => a.r - b.r).forEach((n, k) => {
          n.dot.setAttribute("r", 4.2);
          n.dot.animate([{ r: 0 }, { r: 4.2 }], { duration: 380, delay: (k * 35) / this.speed,
            easing: "cubic-bezier(.3,1.6,.5,1)", fill: "backwards" });
        });
        await this.sleep(900); this._check(run);

        await this._drop(run);
        this._status(`Reading ${d.picks.length} key figures from the statements…`);
        for (let i = 0; i < d.picks.length; i++) {
          const node = this._nodes[d.picks[i]];
          if (!node) continue;
          if (G.sheet) await this._collect(node, i, run);
          else { await this._visit(node, run); this._pick(node, i); this._fillCard(node.m.key, true); }
          await this.sleep(G.sheet ? 250 : 1000); this._check(run);
        }

        this._status("Spinning the score web…");
        this._clearHighlights(); this._showSource(null);
        await this._spin(run);
        await this.spider.walkTo(G.cx, G.cy + 2); this._check(run);
        await this.spider.face(-Math.PI / 2); this._check(run);
        this._reveal();
      } catch (e) {
        if (e !== CANCEL) { console.error(e); this._finalState(); }
      }
    }

    async _drop(run) {
      const sp = this.spider, G = this._G;
      sp.mode = "hang"; sp.a = Math.PI / 2; sp.x = G.cx; sp.y = -110; sp.pose = 0.42;
      sp.threadOn = true; sp.threadX = null; sp.threadTop = -20;
      await this.tween(1.5, t => {
        const sprg = 1 - Math.exp(-5.5 * t) * Math.cos(8.5 * t);
        sp.y = lerp(-110, G.cy, t < 1 ? sprg : 1);
        sp.x = G.cx + Math.sin(this._clock * 3) * 4 * (1 - t);
      });
      this._check(run);
      sp.mode = "free";
      await this.tween(0.45, t => { sp.pose = lerp(0.42, 1, easeOut(t)); });
      this._check(run);
      sp.threadX = sp.spinneret().x;
      await this.tween(0.5, t => { sp.threadRetract = easeInOut(t); });
      sp.threadOn = false; sp.thread.remove();
      await this.sleep(250); this._check(run);
    }

    async _visit(node, run) {
      const sp = this.spider;
      const dx = node.x - sp.x, dy = node.y - sp.y, d = Math.hypot(dx, dy) || 1;
      const stand = 21 * S;
      if (d > stand + 2) { await sp.walkTo(node.x - (dx / d) * stand, node.y - (dy / d) * stand); this._check(run); }
      await sp.face(Math.atan2(node.y - sp.y, node.x - sp.x)); this._check(run);
      const tap = sp.tap(node.x, node.y, this._G.sheet ? 0.5 : 0.7);
      await this.sleep(180);
      this._ripple(node);
      await tap; this._check(run);
    }

    // statement cells an input refers to
    _cellsFor(inp) {
      if (!this._cells) return [];
      if (inp.statement === "market") return this._cells[`market:${inp.label}`] ? [this._cells[`market:${inp.label}`]] : [];
      if (!["income", "balance", "cashflow"].includes(inp.statement)) return [];
      return (inp.years || []).map(y => this._cells[`${inp.statement}:${inp.field}:${y}`]).filter(Boolean);
    }
    _clearHighlights() {
      if (!this._cells) return;
      for (const c of Object.values(this._cells)) c.hl.classList.remove("on");
      for (const l of Object.values(this._rowLabels || {})) l.classList.remove("on");
    }

    // Full layout: fetch each input from the statements, carry it to the web, work it out.
    async _collect(node, i, run) {
      const sp = this.spider, m = node.m;
      const inputs = (m.workings && m.workings.inputs) || [];
      const card = this._card(m, i, false);
      this._clearHighlights();
      const carried = [];
      for (let k = 0; k < inputs.length; k++) {
        const cells = this._cellsFor(inputs[k]);
        if (!cells.length) continue;
        if (this._tab !== cells[0].tab) { this._setTab(cells[0].tab); await this.sleep(180); this._check(run); }
        const target = cells[cells.length - 1];
        // stand just right of the figure, facing it
        await sp.walkTo(target.right + 30 * S, target.y); this._check(run);
        await sp.face(Math.PI); this._check(run);
        const tap = sp.tap(target.right - 14, target.y, 0.42);
        const lab = this._rowLabels[`${target.tab}:${inputs[k].field}`];
        if (lab) lab.classList.add("on");
        for (const c of cells) { c.hl.classList.add("on"); await this.sleep(45); }
        this._showSource(cells[0]);
        await tap; this._check(run);
        carried.push({ k, pill: this._makePill(inputs[k].display, target.x, target.y) });
        this._carry = carried.map(c => c.pill);
        card.slots[k].val.textContent = "carrying…";
      }
      await this._visit(node, run);
      // deposit: the carried figures fly from the web into their lines in the workings
      this._carry = [];
      await Promise.all(carried.map(async ({ k, pill }, n) => {
        await this.sleep(n * 140);
        if (run !== this._run) return;
        const from = this._svgToHost(pill.x, pill.y);
        pill.g.remove();
        await this._fly(inputs[k].display, from, card.slots[k].val);
        this._fillSlot(card.slots[k], inputs[k]);
      }));
      this._check(run);
      inputs.forEach((inp, k) => { if (!this._cellsFor(inp).length) this._fillSlot(card.slots[k], inp); });
      this._finishCard(card, m);
      this._pick(node, i);
    }

    _makePill(text, x, y) {
      const g = svg("g", { class: "pill" }, this.$carryG);
      const thread = svg("line", { class: "carry-thread" }, this.$carryG);
      const r = svg("rect", { rx: 10, ry: 10, height: 20 }, g);
      const t = svg("text", { "text-anchor": "middle", y: 4 }, g);
      t.textContent = text;
      const w = (t.getComputedTextLength ? t.getComputedTextLength() : 50) + 16;
      r.setAttribute("x", -w / 2); r.setAttribute("y", -10); r.setAttribute("width", w);
      const pill = { g, thread, x, y };
      g.setAttribute("transform", `translate(${x},${y})`);
      g.animate([{ opacity: 0, transform: `translate(${x}px,${y}px) scale(.6)` }, { opacity: 1, transform: `translate(${x}px,${y}px) scale(1)` }],
        { duration: 250 });
      g.remove = (orig => () => { thread.remove(); orig.call(g); })(g.remove);
      return pill;
    }
    _updateCarry(dt) {
      if (!this._carry || !this._carry.length || !this.spider) return;
      const sp = this.spider, s0 = sp.spinneret();
      const back = { x: -Math.cos(sp.a), y: -Math.sin(sp.a) };
      this._carry.forEach((p, i) => {
        const tx = s0.x + back.x * (26 + i * 24), ty = s0.y + back.y * (26 + i * 24) + 4;
        const k = 1 - Math.exp(-9 * dt);
        p.x = lerp(p.x, tx, k); p.y = lerp(p.y, ty, k);
        p.g.setAttribute("transform", `translate(${p.x.toFixed(1)},${p.y.toFixed(1)})`);
        p.thread.setAttribute("x1", s0.x); p.thread.setAttribute("y1", s0.y);
        p.thread.setAttribute("x2", p.x); p.thread.setAttribute("y2", p.y);
      });
    }
    _svgToHost(x, y) {
      const ctm = this.$svg.getScreenCTM(), host = this.$fs.getBoundingClientRect();
      if (!ctm) return { x: 0, y: 0 };
      const pt = new DOMPoint(x, y).matrixTransform(ctm);
      return { x: pt.x - host.left, y: pt.y - host.top };
    }
    // A figure flies along an arc from the web into its line in the workings (on the animation clock).
    async _fly(text, from, toEl) {
      const host = this.$fs.getBoundingClientRect(), r = toEl.getBoundingClientRect();
      const to = { x: r.left - host.left + r.width / 2, y: r.top - host.top + r.height / 2 };
      const g = html("div", "ghost", this.$fs, text);
      const gw = g.offsetWidth / 2, gh = g.offsetHeight / 2;
      const ctrl = { x: (from.x + to.x) / 2, y: Math.min(from.y, to.y) - 60 };
      await this.tween(0.55, t => {
        const k = easeInOut(t), u = 1 - k;
        const x = u * u * from.x + 2 * u * k * ctrl.x + k * k * to.x;
        const y = u * u * from.y + 2 * u * k * ctrl.y + k * k * to.y;
        g.style.transform = `translate(${(x - gw).toFixed(1)}px,${(y - gh).toFixed(1)}px) scale(${(1 - 0.12 * k).toFixed(3)})`;
        g.style.opacity = String(1 - 0.7 * Math.max(0, k - 0.75) / 0.25);
      });
      g.remove();
    }

    _ripple(node) {
      for (let k = 0; k < 2; k++) {
        const c = svg("circle", { class: "rip " + node.m.flag, cx: node.x, cy: node.y, r: 5 }, this.$fx);
        const an = c.animate([{ r: 5, opacity: 0.9 }, { r: 30, opacity: 0 }],
          { duration: 900 / this.speed, delay: (k * 260) / this.speed, easing: "cubic-bezier(.2,.7,.3,1)", fill: "forwards" });
        an.onfinish = () => c.remove();
      }
    }

    _pick(node, i, instant = false) {
      if (node.picked) return;
      node.picked = true;
      const m = node.m, G = this._G, vb = G.vb;
      node.dot.classList.add("picked");
      node.dot.setAttribute("r", 5.5);
      node.halo.style.transition = instant ? "none" : "opacity .5s";
      node.halo.style.opacity = 1;
      const dir = node.r > G.R * 0.6 ? -1 : 1;
      const out = { x: Math.cos(node.a) * dir, y: Math.sin(node.a) * dir };
      const tx = node.x + out.x * 18, ty = node.y + out.y * 18;
      const g = svg("g", { class: "tag" }, this.$tags);
      const rect = svg("rect", { rx: 7, ry: 7 }, g);
      const t = svg("text", { x: tx, y: ty + 4 }, g);
      svg("tspan", {}, t).textContent = `${i + 1}. ${m.short} `;
      svg("tspan", { class: "tv" }, t).textContent = m.display;
      const w = t.getBBox().width;
      let x0 = out.x >= 0 ? tx : tx - w;
      if (Math.abs(out.x) < 0.3) x0 = tx - w / 2;
      const minX = G.sheet ? G.sheet.x + G.sheet.w + 8 : vb.x + 4;   // tags never cover the sheet
      x0 = clamp(x0, minX, vb.x + vb.w - w - 4);
      let y0 = ty;
      const hits = yy => this._tagBoxes.some(b => x0 - 6 < b.x + b.w && x0 + w + 6 > b.x && yy - 10 < b.y + b.h && yy + 10 > b.y);
      for (let k = 1; k < 8 && hits(y0); k++) y0 = ty + Math.ceil(k / 2) * 23 * (k % 2 ? 1 : -1);
      this._tagBoxes.push({ x: x0 - 6, y: y0 - 10, w: w + 12, h: 20 });
      t.setAttribute("x", x0); t.setAttribute("y", y0 + 4);
      rect.setAttribute("x", x0 - 6); rect.setAttribute("y", y0 - 10);
      rect.setAttribute("width", w + 12); rect.setAttribute("height", 20);
      if (!instant) g.animate([{ opacity: 0, transform: "translateY(4px)" }, { opacity: 1, transform: "none" }], { duration: 400, fill: "forwards" });
      this.dispatchEvent(new CustomEvent("fin-spider:pick", { detail: m }));
    }

    // ---------- workings cards
    _card(m, i, instant) {
      if (this._cards[m.key]) return this._cards[m.key];
      const li = html("li", "", null);
      li.tabIndex = 0;
      if (instant) li.style.animation = "none";
      const row = html("div", "row", li);
      html("span", "numb", row, String(i + 1));
      html("span", "nm", row, m.label);
      const res = html("span", "wres pending", row, "…");
      const w = m.workings || { formula: "", inputs: [] };
      if (w.formula) html("div", "formula", li, w.formula);
      const dl = html("dl", "", li);
      const slots = (w.inputs || []).map(inp => {
        const dv = html("div", "", dl);
        const yrs = inp.years || [];
        const yl = /FY/.test(inp.label) ? "" : yrs.length === 1 ? ` · FY${yrs[0]}`
          : yrs.length === 2 ? ` · FY${yrs[0]}–${String(yrs[1]).slice(2)}` : "";
        html("dt", "", dv, inp.label + yl).title = inp.label + yl;
        const dd = html("dd", "", dv);
        const val = html("span", "wval pending", dd, "—");
        const chip = html("span", "", dv);
        return { inp, val, chip };
      });
      const meta = html("div", "meta", li);
      const foot = html("p", "sent", li);
      li.addEventListener("click", () => this._goto(m.key));
      li.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); this._goto(m.key); } });
      for (const c of this.$list.children) c.classList.remove("on");
      li.classList.add("on");
      this.$list.appendChild(li);
      const card = { li, res, slots, meta, foot, m };
      this._cards[m.key] = card;
      return card;
    }
    _fillSlot(slot, inp) {
      slot.val.textContent = inp.display + (inp.note ? ` (${inp.note})` : "");
      slot.val.classList.remove("pending");
      slot.val.classList.add("flash");
      const cells = this._cellsFor(inp);
      const src = cells[0] && cells[0].src;
      const st = inp.status || "single";
      const u = safeUrl(src && src.url);
      const chip = document.createElement(u ? "a" : "span");
      chip.className = "src " + st;
      chip.textContent = inp.statement === "derived" ? "computed" : (st === "official" ? "10-K" : STATUS[st] ? STATUS[st].short : st);
      chip.title = [STATUS[st] && STATUS[st].label, src && src.doc, cells[0] && cells[0].check].filter(Boolean).join(" · ");
      if (u) { chip.href = u; chip.target = "_blank"; chip.rel = "noopener"; chip.addEventListener("click", e => e.stopPropagation()); }
      slot.chip.replaceWith(chip); slot.chip = chip;
    }
    _finishCard(card, m) {
      card.res.textContent = m.display;
      card.res.classList.remove("pending");
      const fl = FLAG[m.flag] || FLAG["n/a"];
      const cat = this._data.categories.find(c => c.key === m.category);
      card.meta.innerHTML = "";
      html("span", "badge " + m.flag, card.meta, `${fl.icon} ${fl.text}`);
      html("span", "", card.meta, `${cat ? cat.name : ""}${m.score != null ? ` · ${fmt(m.score)}/10` : ""}`);
      card.foot.textContent = m.sentence;
      for (const rf of m.red_flags || []) html("div", "rf", card.li, `⚠ ${rf.text}`);
    }
    _fillCard(key, instant) {
      const node = this._nodes[key]; if (!node) return;
      const i = this._data.picks.indexOf(key);
      const card = this._card(node.m, i, instant);
      card.slots.forEach(s => this._fillSlot(s, s.inp));
      this._finishCard(card, node.m);
      if (instant) card.slots.forEach(s => s.val.classList.remove("flash"));
    }

    async _spin(run) {
      const sp = this.spider, vs = this._verts;
      if (vs.length < 3) return;
      await sp.walkTo(vs[0].x, vs[0].y); this._check(run);
      const trail = svg("polyline", { class: "trail" }, this.$trailG);
      sp.trail = trail; sp.trailPts = []; sp.spinning = true;
      const loop = vs.slice(1).concat([vs[0]]);
      for (let k = 0; k < loop.length; k++) {
        await sp.walkTo(loop[k].x, loop[k].y, { arrive: k === loop.length - 1 }); this._check(run);
      }
      sp.spinning = false;
      this.$poly.style.transition = "opacity 1s";
      this.$poly.style.opacity = 1;
      trail.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 1200, fill: "forwards" });
      await this.sleep(300); this._check(run);
    }

    _reveal(instant = false) {
      const d = this._data;
      this.$vpill.className = "vpill " + (VERDICT_TONE[d.verdict] || "ok");
      this.$vpill.textContent = d.verdict;
      this.$vnote.textContent = d.verdict_note ? "Note: " + d.verdict_note : "";
      const target = d.overall ?? 0;
      const setScore = v => { this.$vscore.innerHTML = `${v.toFixed(1)}<small> / 10</small>`; };
      if (instant || d.overall == null) setScore(target);
      else {
        const t0 = performance.now(), run = this._run;
        const step = now => {
          if (run !== this._run) return;
          const t = Math.min(1, (now - t0) / 900);
          setScore(target * easeOut(t));
          if (t < 1) requestAnimationFrame(step);
        };
        requestAnimationFrame(step);
      }
      const cv = this.$cverdict, vb = this._G.vb;
      cv.textContent = "";
      const l1 = svg("tspan", { x: vb.x + 10, dy: 0, "font-size": 16, "font-weight": 500, fill: "var(--muted)" }, cv);
      l1.textContent = d.company.ticker;
      svg("tspan", { x: vb.x + 10, dy: 24 }, cv).textContent = `${d.verdict} · ${fmt(d.overall)}`;
      cv.style.transition = instant ? "none" : "opacity .6s";
      cv.style.opacity = 1;
      const nflags = (d.red_flags || []).length;
      this._status(nflags ? `Done · ${nflags} red flag${nflags > 1 ? "s" : ""} found` : "Done · no red flags", true);
      this.dispatchEvent(new CustomEvent("fin-spider:done", { detail: d }));
    }

    _status(text, done = false) {
      this.$statusText.textContent = text;
      this.$status.classList.toggle("done", done);
    }

    // Jump to the finished state (reduced motion, layout change, or a click mid-tour).
    _finalState(keepSpider = false) {
      if (!keepSpider) { this._run++; this._timers = []; }
      if (!this.spider) this.spider = new Spider(this.$spiderG, this._G.cx);
      for (const w of this._webPaths) { w.p.getAnimations?.().forEach(a => a.finish()); w.p.style.strokeDasharray = ""; w.p.style.strokeDashoffset = ""; }
      this.$labels.style.transition = "none"; this.$labels.style.opacity = 1;
      for (const n of Object.values(this._nodes)) { n.dot.getAnimations?.().forEach(a => a.finish()); n.dot.setAttribute("r", n.picked ? 5.5 : 4.2); }
      this._data.picks.forEach((k, i) => { if (this._nodes[k]) { this._pick(this._nodes[k], i, true); this._fillCard(k, true); } });
      this.$carryG.innerHTML = ""; this._carry = [];
      this.$fs.querySelectorAll(".ghost").forEach(g => g.remove());
      this._clearHighlights(); this._showSource(null);
      this.$poly.style.transition = "none"; this.$poly.style.opacity = 1;
      this.$trailG.innerHTML = "";
      const sp = this.spider, G = this._G;
      sp.mode = "free"; sp.pose = 1; sp.spinning = false; sp.threadOn = false; sp.thread.remove();
      if (!keepSpider) {
        sp.x = G.cx; sp.y = G.cy + 2; sp.a = -Math.PI / 2; sp.target = null; sp.faceTo = null;
        sp.legs.forEach(l => { l.foot = null; l.step = null; l.tap = null; });
      }
      this._reveal(true);
    }

    async _goto(key) {
      const node = this._nodes[key];
      if (!node || !this.spider) return;
      if (!this.$status.classList.contains("done")) this._finalState(true);
      const run = ++this._run;
      for (const [k, c] of Object.entries(this._cards)) c.li.classList.toggle("on", k === key);
      // show where the figures came from
      this._clearHighlights();
      const inputs = (node.m.workings && node.m.workings.inputs) || [];
      const first = inputs.map(i => this._cellsFor(i)).find(c => c.length);
      if (first) {
        this._setTab(first[0].tab);
        inputs.forEach(i => this._cellsFor(i).filter(c => c.tab === first[0].tab).forEach(c => c.hl.classList.add("on")));
        this._showSource(first[0]);
      }
      if (this.reduced) { this._ripple(node); return; }
      try { await this._visit(node, run); } catch (e) { if (e !== CANCEL) throw e; }
    }
  }

  FinSpider.Spider = Spider;   // exposed for testing / custom scenes
  customElements.define("fin-spider", FinSpider);
})();
