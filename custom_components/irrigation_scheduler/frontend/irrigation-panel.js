// Sidebar panel for the Irrigation Scheduler integration.
// Plain web component, no build step. Talks to the websocket API in websocket_api.py.

const DOMAIN = "irrigation_scheduler";

const DAYS = [
  ["mon", "Montag", "Mo"],
  ["tue", "Dienstag", "Di"],
  ["wed", "Mittwoch", "Mi"],
  ["thu", "Donnerstag", "Do"],
  ["fri", "Freitag", "Fr"],
  ["sat", "Samstag", "Sa"],
  ["sun", "Sonntag", "So"],
];
const DAY_NAME = Object.fromEntries(DAYS.map(([k, n]) => [k, n]));

const STATUS = {
  idle: "Bereit",
  watering: "Bewässert",
  skipped_rain: "Übersprungen (Regen)",
  skipped_no_duration: "Übersprungen (keine Dauer)",
  error: "Fehler",
};
const RESULT = {
  completed: "Abgeschlossen",
  stopped: "Gestoppt",
  error: "Fehler",
  skipped_rain: "Übersprungen (Regen)",
  skipped_no_duration: "Übersprungen (keine Dauer)",
};
const SOURCE = { auto: "Automatik", manual: "Manuell" };

const CHART_DAYS = 30;

// Units the backend understands for water tracking (volume meter or flow rate).
const WATER_UNITS = ["L", "mL", "m³", "gal", "ft³", "CCF", "MCF", "fl. oz.",
  "L/min", "L/h", "L/s", "mL/s", "m³/h", "m³/min", "m³/s", "gal/min", "gal/h", "gal/d", "ft³/min"];

const fmtMoney = (v, currency) => {
  if (v === null || v === undefined) return "–";
  try {
    return Number(v).toLocaleString("de", { style: "currency", currency: currency || "EUR" });
  } catch (e) {
    return `${fmtNum(v, 2)} ${currency || ""}`;
  }
};

// Finished runs with a measured amount but no cost (e.g. from before tariffs existed).
const uncostedRuns = (z) =>
  (z?.history || []).filter((h) => h.end != null && h.water_l != null && h.cost == null);

const fmtLiters = (v) => (v === null || v === undefined ? "–" : `${fmtNum(v, v < 100 ? 1 : 0)} L`);

const esc = (v) =>
  String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

const fmtNum = (v, digits = 0) =>
  v === null || v === undefined ? "–" : Number(v).toLocaleString("de", { maximumFractionDigits: digits });

const dayKey = (d) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

const fmtDateTime = (iso) =>
  iso
    ? new Date(iso).toLocaleString("de", { weekday: "short", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })
    : "–";
const fmtTime = (iso) => (iso ? new Date(iso).toLocaleTimeString("de", { hour: "2-digit", minute: "2-digit" }) : "–");
const fmtDate = (iso) => (iso ? new Date(iso).toLocaleDateString("de", { weekday: "short", day: "2-digit", month: "2-digit", year: "numeric" }) : "–");

const toMinutes = (hhmm) => {
  const [h, m] = hhmm.split(":").map(Number);
  return h * 60 + m;
};
const fromMinutes = (min) => {
  const m = ((min % 1440) + 1440) % 1440;
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
};

// Same rule as logic.window_slots: start + k*interval while before end; end <= start spans midnight.
function windowSlots(start, end, intervalHours) {
  const s = toMinutes(start);
  let e = toMinutes(end);
  if (e <= s) e += 1440;
  const step = Math.max(intervalHours, 1) * 60;
  const slots = [];
  for (let t = s; t < e; t += step) slots.push(fromMinutes(t));
  return slots;
}

const STYLE = `
  :host {
    display: block;
    min-height: 100vh;
    /* Safety net: nothing inside may widen the page (iOS WebKit sizes grids/selects by content). */
    max-width: 100%;
    overflow-x: hidden;
  }
  *, *::before, *::after { box-sizing: border-box; }
  :host {
    background: var(--primary-background-color);
    color: var(--primary-text-color);
    font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif);
  }
  .toolbar {
    display: flex; align-items: center; gap: 8px;
    height: var(--header-height, 56px); padding: 0 12px;
    background: var(--app-header-background-color, var(--primary-color));
    color: var(--app-header-text-color, var(--text-primary-color, #fff));
    font-size: 20px;
  }
  .toolbar .title { flex: 1; }
  .content { max-width: 1100px; margin: 0 auto; padding: 16px; display: grid; gap: 16px; grid-template-columns: minmax(0, 1fr); }
  .tabs { display: flex; gap: 8px; flex-wrap: wrap; }
  .tabs button.active { background: var(--primary-color); color: var(--text-primary-color, #fff); }
  .card {
    background: var(--card-background-color, #fff);
    border-radius: var(--ha-card-border-radius, 12px);
    box-shadow: var(--ha-card-box-shadow, none);
    border: 1px solid var(--divider-color, #e0e0e0);
    padding: 16px;
  }
  .card h2 { margin: 0 0 12px; font-size: 18px; font-weight: 500; }
  .grid2 { display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(min(320px, 100%), 1fr)); }
  .grid2 > *, #main > * { min-width: 0; }
  .kv dd { overflow-wrap: anywhere; }
  .kv { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: 6px 16px; }
  .kv dt { color: var(--secondary-text-color); }
  .kv dd { margin: 0; }
  .badge {
    display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 13px;
    background: var(--secondary-background-color, #eee);
  }
  .badge.watering { background: var(--primary-color); color: var(--text-primary-color, #fff); }
  .badge.error { background: var(--error-color, #db4437); color: #fff; }
  .row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-top: 12px; }
  button {
    font: inherit; font-size: 14px; cursor: pointer;
    padding: 6px 14px; border-radius: 18px;
    border: 1px solid var(--divider-color, #ccc);
    background: var(--card-background-color, #fff); color: var(--primary-text-color);
  }
  button.primary { background: var(--primary-color); color: var(--text-primary-color, #fff); border-color: transparent; }
  button:disabled { opacity: .5; cursor: default; }
  input, select {
    font: inherit; font-size: 14px; padding: 5px 8px; border-radius: 6px;
    border: 1px solid var(--divider-color, #ccc);
    background: var(--secondary-background-color, #fafafa); color: var(--primary-text-color);
  }
  select { max-width: 100%; text-overflow: ellipsis; }
  input[type=number] { width: 80px; }
  label.toggle { display: inline-flex; gap: 6px; align-items: center; margin-right: 16px; cursor: pointer; }
  table { width: 100%; border-collapse: collapse; font-size: 14px; }
  th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--divider-color, #e0e0e0); }
  th { color: var(--secondary-text-color); font-weight: 500; }
  td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
  tr.today td:first-child { font-weight: 600; color: var(--primary-color); }
  tr.off td { color: var(--secondary-text-color); }
  .slots { color: var(--secondary-text-color); font-size: 13px; }
  .form { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: 10px 16px; align-items: center; }
  .form select, .form input { max-width: 100%; }
  .form select { width: 100%; min-width: 0; }
  .hint { color: var(--secondary-text-color); font-size: 13px; }
  .tiles { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(min(140px, 100%), 1fr)); margin-bottom: 16px; }
  .tile .v { font-size: 26px; font-weight: 500; font-variant-numeric: tabular-nums; }
  .tile .l { color: var(--secondary-text-color); font-size: 13px; }
  .chart { position: relative; }
  .chart svg { width: 100%; height: 180px; display: block; overflow: visible; }
  .chart .grid { stroke: var(--divider-color, #e0e0e0); stroke-width: 1; }
  .chart .axis { fill: var(--secondary-text-color); font-size: 11px; }
  .chart .bar { fill: var(--primary-color); }
  .chart .hit { fill: transparent; }
  .chart .hit:hover + .bar, .chart .bar.hover { opacity: .75; }
  .tooltip {
    position: absolute; pointer-events: none; z-index: 2; white-space: nowrap;
    background: var(--card-background-color, #fff); color: var(--primary-text-color);
    border: 1px solid var(--divider-color, #ccc); border-radius: 8px;
    padding: 6px 10px; font-size: 13px; box-shadow: 0 2px 8px rgba(0,0,0,.15);
    transform: translate(-50%, calc(-100% - 8px));
  }
  .tooltip .muted { color: var(--secondary-text-color); }
  .scroll { max-height: 420px; overflow: auto; }
  .xscroll { overflow-x: auto; }
  .narrow-only { display: none; }
  .empty { color: var(--secondary-text-color); padding: 24px; text-align: center; }
  @media (max-width: 600px) {
    .content { padding: 8px; }
    .form { grid-template-columns: minmax(0, 1fr); gap: 4px; }
    /* iOS zooms into inputs below 16px, which makes the page pan sideways. */
    input, select { font-size: 16px; }
    .hide-narrow { display: none; }
    .narrow-only { display: inline; }
    th, td { padding: 6px 4px; }
    #week input[type=number] { width: 52px; }
    #week input[type=time] { width: 108px; padding: 5px 4px; }
  }
`;

class IrrigationSchedulerPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._zones = [];
    this._selected = null;
    this._settingsDirty = false;
    this._renderedZone = null;
    this._unsub = null;
  }

  set hass(hass) {
    this._hass = hass;
    if (this._menuButton) this._menuButton.hass = hass;
    this._subscribe();
  }
  get hass() {
    return this._hass;
  }
  set narrow(narrow) {
    this._narrow = narrow;
    if (this._menuButton) this._menuButton.narrow = narrow;
  }
  set panel(panel) {
    this._panel = panel;
  }

  connectedCallback() {
    if (!this._skeleton) this._buildSkeleton();
    this._subscribe();
    this._onResize = () => {
      clearTimeout(this._resizeTimer);
      this._resizeTimer = setTimeout(() => this._zone && this._renderHistory(this._zone), 150);
    };
    window.addEventListener("resize", this._onResize);
  }

  disconnectedCallback() {
    window.removeEventListener("resize", this._onResize);
    if (this._unsub) {
      this._unsub.then((unsub) => unsub()).catch(() => {});
      this._unsub = null;
    }
  }

  _subscribe() {
    if (this._unsub || !this._hass || !this.isConnected) return;
    this._unsub = this._hass.connection.subscribeMessage(
      (msg) => {
        this._zones = msg.zones || [];
        if (!this._zones.some((z) => z.entry_id === this._selected)) {
          this._selected = this._zones[0]?.entry_id ?? null;
        }
        this._update();
      },
      { type: `${DOMAIN}/subscribe` },
    );
  }

  _ws(type, data = {}) {
    return this._hass
      .callWS({ type: `${DOMAIN}/${type}`, entry_id: this._selected, ...data })
      .catch((err) => {
        alert(`Fehler: ${err.message || err}`);
        throw err;
      });
  }

  get _zone() {
    return this._zones.find((z) => z.entry_id === this._selected);
  }

  // ------------------------------------------------------------ skeleton

  _buildSkeleton() {
    this._skeleton = true;
    const root = this.shadowRoot;
    root.innerHTML = `
      <style>${STYLE}</style>
      <div class="toolbar"><span id="menu"></span><span class="title">Bewässerung</span></div>
      <div class="content">
        <div class="tabs" id="tabs"></div>
        <div id="empty" class="card empty" hidden>Keine Zone eingerichtet. Unter Einstellungen &gt; Geräte &amp; Dienste "Irrigation Scheduler" hinzufügen.</div>
        <div id="main">
          <div class="grid2">
            <div class="card"><h2>Status</h2><div id="status"></div><div id="manual"></div></div>
            <div class="card"><h2>Einstellungen</h2><div id="flags"></div><div id="settings"></div><div id="costs"></div></div>
          </div>
          <div class="card" style="margin-top:16px"><h2>Wochenplan</h2><div id="week"></div></div>
          <div class="card" style="margin-top:16px"><h2>Verlauf</h2><div id="history"></div></div>
        </div>
      </div>`;

    this._menuButton = document.createElement("ha-menu-button");
    this._menuButton.hass = this._hass;
    this._menuButton.narrow = this._narrow;
    root.getElementById("menu").appendChild(this._menuButton);

    const $ = (id) => root.getElementById(id);

    $("tabs").addEventListener("click", (ev) => {
      const id = ev.target.dataset?.entry;
      if (id && id !== this._selected) {
        this._selected = id;
        this._settingsDirty = false;
        this._update();
      }
    });

    $("manual").addEventListener("click", (ev) => {
      const action = ev.target.dataset?.action;
      if (action === "start") {
        const minutes = Number(root.getElementById("manual-min").value);
        if (minutes > 0) this._ws("run", { duration: minutes });
      } else if (action === "stop") {
        this._ws("stop");
      }
    });

    $("flags").addEventListener("change", (ev) => {
      const flag = ev.target.dataset?.flag;
      if (flag) this._ws("set_flags", { [flag]: ev.target.checked });
    });

    $("week").addEventListener("change", (ev) => {
      const { day, field } = ev.target.dataset || {};
      if (!day || !field) return;
      const value = field === "duration" ? Number(ev.target.value) : ev.target.value;
      if (field === "duration" && !(value >= 0)) return;
      if (field !== "duration" && !value) return;
      this._ws("set_day", { day, [field]: value });
    });
    $("week").addEventListener("focusout", () => setTimeout(() => this._update(), 0));

    $("costs").addEventListener("click", async (ev) => {
      if (ev.target.dataset?.action !== "recalculate") return;
      const z = this._zone;
      const count = uncostedRuns(z).length;
      const tariff = fmtMoney(z.price_per_m3, z.currency);
      if (!confirm(`Kosten für ${count} ${count === 1 ? "Lauf" : "Läufe"} ohne Kosten mit dem aktuellen Tarif (${tariff}/m³) berechnen?`)) return;
      ev.target.disabled = true;
      try {
        const result = await this._ws("recalculate_costs");
        alert(`${result.count} ${result.count === 1 ? "Lauf" : "Läufe"} berechnet.`);
      } finally {
        ev.target.disabled = false;
      }
    });

    $("settings").addEventListener("input", () => {
      this._settingsDirty = true;
      this._renderSettingsButtons();
    });
    $("settings").addEventListener("click", async (ev) => {
      const action = ev.target.dataset?.action;
      if (action === "reset") {
        this._settingsDirty = false;
        this._renderedZone = null;
        this._update();
      } else if (action === "save") {
        const options = {};
        root.querySelectorAll("#settings [data-option]").forEach((el) => {
          options[el.dataset.option] =
            el.type === "number" ? Number(el.value) : el.type === "checkbox" ? el.checked : el.value;
        });
        ev.target.disabled = true;
        try {
          await this._ws("update_options", { options });
          this._settingsDirty = false;
        } finally {
          ev.target.disabled = false;
        }
      }
    });
  }

  // -------------------------------------------------------------- render

  _update() {
    if (!this._skeleton) return;
    const root = this.shadowRoot;
    const zone = this._zone;
    root.getElementById("empty").hidden = !!zone;
    root.getElementById("main").hidden = !zone;
    this._renderTabs();
    if (!zone) return;

    const zoneChanged = this._renderedZone !== zone.entry_id;
    const focused = (id) => root.activeElement && root.getElementById(id).contains(root.activeElement);

    this._renderStatus(zone);
    if (zoneChanged || !focused("manual")) this._renderManual(zone);
    this._renderFlags(zone);
    if (zoneChanged || !(this._settingsDirty || focused("settings"))) this._renderSettings(zone);
    this._renderCosts(zone);
    if (zoneChanged || !focused("week")) this._renderWeek(zone);
    this._renderHistory(zone);
    this._renderedZone = zone.entry_id;
  }

  _renderTabs() {
    const tabs = this.shadowRoot.getElementById("tabs");
    tabs.hidden = this._zones.length < 2;
    tabs.innerHTML = this._zones
      .map((z) => `<button data-entry="${esc(z.entry_id)}" class="${z.entry_id === this._selected ? "active" : ""}">${esc(z.title)}</button>`)
      .join("");
  }

  _renderStatus(z) {
    const rain = z.rain;
    const rainText = rain
      ? `${fmtNum(rain.amount_mm, 1)} mm, ${rain.max_probability == null ? "–" : fmtNum(rain.max_probability)} % ${rain.skip ? "(Lauf wird übersprungen)" : ""}`
      : "keine Vorhersage";
    this.shadowRoot.getElementById("status").innerHTML = `
      <dl class="kv">
        <dt>Status</dt><dd><span class="badge ${esc(z.status)}">${esc(STATUS[z.status] || z.status)}</span></dd>
        ${z.running ? `<dt>Läuft bis</dt><dd>${fmtTime(z.run_end)}</dd>` : ""}
        <dt>Nächster Lauf</dt><dd>${
          z.next_run ? `${fmtDateTime(z.next_run)}, ${fmtNum(z.next_run_duration)} min` : "keiner geplant"
        }${z.auto_enabled ? "" : " (Automatik aus)"}</dd>
        <dt>Letzter Lauf</dt><dd>${fmtDateTime(z.last_run)}${z.water_entity ? `, ${fmtLiters(z.last_water_l)}` : ""}</dd>
        ${z.water_entity ? `<dt>Wasser gesamt</dt><dd>${fmtLiters(z.water_total_l)}${
          z.price_per_m3 > 0 || z.cost_total > 0 ? `, ${fmtMoney(z.cost_total, z.currency)}` : ""
        }</dd>` : ""}
        <dt>Regen (${fmtNum(z.options.lookahead_hours)} h)</dt><dd>${rainText}${z.rain_check_enabled ? "" : " (Prüfung aus)"}</dd>
      </dl>`;
  }

  _renderManual(z) {
    const today = DAYS[(new Date().getDay() + 6) % 7][0];
    const todayMin = z.days.find((d) => d.day === today)?.duration || 10;
    this.shadowRoot.getElementById("manual").innerHTML = `
      <div class="row">
        <input id="manual-min" type="number" min="1" max="240" value="${esc(todayMin)}"> min
        <button class="primary" data-action="start" ${z.running ? "disabled" : ""}>Jetzt bewässern</button>
        <button data-action="stop" ${z.running ? "" : "disabled"}>Stopp</button>
      </div>
      <div class="hint">Manuelle Läufe ignorieren die Regenprüfung.</div>`;
  }

  _renderFlags(z) {
    this.shadowRoot.getElementById("flags").innerHTML = `
      <div style="margin-bottom:12px">
        <label class="toggle"><input type="checkbox" data-flag="auto_enabled" ${z.auto_enabled ? "checked" : ""}> Automatik</label>
        <label class="toggle"><input type="checkbox" data-flag="rain_check_enabled" ${z.rain_check_enabled ? "checked" : ""}> Regenprüfung</label>
      </div>`;
  }

  _entityOptions(domains, selected, { filter = () => true, empty = null } = {}) {
    const states = this._hass?.states || {};
    const ids = Object.keys(states)
      .filter((id) => domains.includes(id.split(".")[0]) && filter(states[id]))
      .sort();
    if (selected && !ids.includes(selected)) ids.unshift(selected);
    const emptyOption = empty === null ? "" : `<option value="" ${selected ? "" : "selected"}>${esc(empty)}</option>`;
    return emptyOption + ids
      .map((id) => {
        const name = states[id]?.attributes?.friendly_name;
        return `<option value="${esc(id)}" ${id === selected ? "selected" : ""}>${esc(name ? `${name} (${id})` : id)}</option>`;
      })
      .join("");
  }

  _renderSettings(z) {
    const o = z.options;
    const num = (key, min, max, step, unit) =>
      `<span><input type="number" data-option="${key}" min="${min}" max="${max}" step="${step}" value="${esc(o[key])}"> ${unit}</span>`;
    this.shadowRoot.getElementById("settings").innerHTML = `
      <div class="form">
        <label>Ventil</label>
        <select data-option="valve_entity">${this._entityOptions(["switch", "valve", "input_boolean"], o.valve_entity)}</select>
        <label>Wetter</label>
        <select data-option="weather_entity">${this._entityOptions(["weather"], o.weather_entity)}</select>
        <label>Intervall</label>${num("interval_hours", 1, 24, 1, "h")}
        <label>Regenmenge ab</label>${num("rain_threshold_mm", 0, 100, 0.1, "mm (0 = aus)")}
        <label>Regenwahrsch. ab</label>${num("rain_probability", 0, 100, 1, "% (0 = aus)")}
        <label>Vorhersagefenster</label>${num("lookahead_hours", 1, 72, 1, "h")}
        <label>Wassersensor</label>
        <select data-option="water_entity">${this._entityOptions(["sensor"], o.water_entity, {
          filter: (st) => WATER_UNITS.includes(st?.attributes?.unit_of_measurement),
          empty: "– keiner –",
        })}</select>
        <label>Wasserpreis</label>${num("water_price", 0, 100, 0.01, `${esc(z.currency)}/m³`)}
        <label>Abwasserpreis</label>${num("wastewater_price", 0, 100, 0.01, `${esc(z.currency)}/m³`)}
        <label>Abwasser</label>
        <label class="toggle"><input type="checkbox" data-option="wastewater_enabled" ${o.wastewater_enabled !== false ? "checked" : ""}> berechnen</label>
      </div>
      <div class="hint">Kosten brauchen einen Wassersensor. Es gilt der Preis zum Zeitpunkt des Laufs.</div>
      <div class="row" id="settings-buttons"></div>`;
    this._renderSettingsButtons();
  }

  _renderCosts(z) {
    const el = this.shadowRoot.getElementById("costs");
    if (!z.water_entity) {
      el.innerHTML = "";
      return;
    }
    const count = uncostedRuns(z).length;
    const hint = !(z.price_per_m3 > 0)
      ? "Zuerst einen Wasser- oder Abwasserpreis speichern."
      : count
        ? `${count} ${count === 1 ? "Lauf hat" : "Läufe haben"} eine Wassermenge, aber keine Kosten.`
        : "Alle Läufe mit Wassermenge haben Kosten.";
    el.innerHTML = `
      <div class="row">
        <button data-action="recalculate" ${count && z.price_per_m3 > 0 ? "" : "disabled"}>Kosten rückwirkend berechnen</button>
      </div>
      <div class="hint">${hint} Bereits berechnete Kosten bleiben unverändert.</div>`;
  }

  _renderSettingsButtons() {
    const el = this.shadowRoot.getElementById("settings-buttons");
    if (!el) return;
    el.innerHTML = `
      <button class="primary" data-action="save" ${this._settingsDirty ? "" : "disabled"}>Speichern</button>
      <button data-action="reset" ${this._settingsDirty ? "" : "disabled"}>Verwerfen</button>`;
  }

  _renderWeek(z) {
    const today = DAYS[(new Date().getDay() + 6) % 7][0];
    const interval = Number(z.options.interval_hours) || 24;
    const rows = DAYS.map(([key, name, short]) => {
      const d = z.days.find((x) => x.day === key) || { duration: 0, start: "06:00", end: "22:00" };
      const off = !(d.duration > 0);
      const slots = off ? "kein Lauf" : windowSlots(d.start, d.end, interval).join(", ");
      return `
        <tr class="${key === today ? "today" : ""} ${off ? "off" : ""}">
          <td><span class="hide-narrow">${name}</span><span class="narrow-only">${short}</span></td>
          <td><input type="number" min="0" max="240" step="1" data-day="${key}" data-field="duration" value="${esc(d.duration)}"><span class="hide-narrow"> min</span></td>
          <td><input type="time" data-day="${key}" data-field="start" value="${esc(d.start)}"></td>
          <td><input type="time" data-day="${key}" data-field="end" value="${esc(d.end)}"></td>
          <td class="slots hide-narrow">${esc(slots)}</td>
        </tr>`;
    }).join("");
    this.shadowRoot.getElementById("week").innerHTML = `
      <div class="xscroll">
      <table>
        <thead><tr><th>Tag</th><th>Dauer<span class="narrow-only"> (min)</span></th><th>Von</th><th>Bis</th><th class="hide-narrow">Starts (alle ${fmtNum(interval)} h)</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
      </div>
      <div class="hint" style="margin-top:8px">Dauer 0 = an diesem Tag keine Bewässerung. Ist "Bis" früher als "Von", läuft das Fenster über Mitternacht.</div>`;
  }

  _renderHistory(z) {
    const history = z.history || [];
    const now = new Date();
    const since = (days) => now.getTime() - days * 86400000;
    const done = history.filter((h) => h.actual_min > 0);
    const sum = (list) => list.reduce((acc, h) => acc + (h.actual_min || 0), 0);
    const water = (list) => list.reduce((acc, h) => acc + (h.water_l || 0), 0);
    const showWater = !!z.water_entity || history.some((h) => h.water_l != null);
    const cost = (list) => list.reduce((acc, h) => acc + (h.cost || 0), 0);
    const showCost = showWater && (z.price_per_m3 > 0 || history.some((h) => h.cost > 0));
    const in7 = done.filter((h) => new Date(h.start).getTime() >= since(7));
    const in30 = done.filter((h) => new Date(h.start).getTime() >= since(30));
    const skipped30 = history.filter((h) => h.result === "skipped_rain" && new Date(h.start).getTime() >= since(30));

    const tiles = `
      <div class="tiles">
        <div class="tile"><div class="v">${fmtNum(sum(in7))} min</div><div class="l">letzte 7 Tage</div></div>
        <div class="tile"><div class="v">${fmtNum(sum(in30))} min</div><div class="l">letzte 30 Tage</div></div>
        <div class="tile"><div class="v">${in30.length}</div><div class="l">Läufe (30 Tage)</div></div>
        <div class="tile"><div class="v">${skipped30.length}</div><div class="l">wegen Regen übersprungen (30 Tage)</div></div>
        ${showWater ? `
        <div class="tile"><div class="v">${fmtLiters(water(in7))}</div><div class="l">Wasser letzte 7 Tage</div></div>
        <div class="tile"><div class="v">${fmtLiters(water(in30))}</div><div class="l">Wasser letzte 30 Tage</div></div>` : ""}
        ${showCost ? `
        <div class="tile"><div class="v">${fmtMoney(cost(in7), z.currency)}</div><div class="l">Kosten letzte 7 Tage</div></div>
        <div class="tile"><div class="v">${fmtMoney(cost(in30), z.currency)}</div><div class="l">Kosten letzte 30 Tage</div></div>` : ""}
      </div>`;

    const rows = history
      .slice()
      .reverse()
      .map((h) => {
        const running = h.end === null;
        const result = running ? "Läuft" : RESULT[h.result] || h.result;
        const dur = running ? `${fmtNum(h.planned_min)} geplant` : h.actual_min > 0 ? fmtNum(h.actual_min, 1) : "–";
        const rain =
          h.rain_mm == null && h.rain_probability == null
            ? "–"
            : `${fmtNum(h.rain_mm, 1)} mm / ${h.rain_probability == null ? "–" : fmtNum(h.rain_probability)} %`;
        return `<tr>
          <td>${fmtDate(h.start)}</td>
          <td class="hide-narrow">${fmtTime(h.start)}</td>
          <td class="hide-narrow">${running ? "–" : fmtTime(h.end)}</td>
          <td class="num">${dur}</td>
          ${showWater ? `<td class="num">${h.water_l == null ? "–" : fmtLiters(h.water_l)}</td>` : ""}
          ${showCost ? `<td class="num">${h.cost == null ? "–" : fmtMoney(h.cost, z.currency)}</td>` : ""}
          <td class="hide-narrow">${esc(SOURCE[h.source] || h.source)}</td>
          <td>${esc(result)}</td>
          <td class="hide-narrow">${rain}</td>
        </tr>`;
      })
      .join("");

    const table = history.length
      ? `<div class="scroll"><table>
          <thead><tr><th>Datum</th><th class="hide-narrow">Start</th><th class="hide-narrow">Ende</th><th class="num">Minuten</th>${showWater ? `<th class="num">Wasser</th>` : ""}${showCost ? `<th class="num">Kosten</th>` : ""}
          <th class="hide-narrow">Quelle</th><th>Ergebnis</th><th class="hide-narrow">Regen</th></tr></thead>
          <tbody>${rows}</tbody></table></div>`
      : `<div class="empty">Noch keine Läufe aufgezeichnet.</div>`;

    const el = this.shadowRoot.getElementById("history");
    el.innerHTML = `${tiles}<div class="chart" id="chart"></div>${table}`;
    this._renderChart(el.querySelector("#chart"), history, showWater, showCost ? z.currency : null);
  }

  // Minutes watered per day, last CHART_DAYS days. Single series: no legend, hover tooltip per day.
  _renderChart(container, history, showWater, currency) {
    const days = [];
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    for (let i = CHART_DAYS - 1; i >= 0; i--) {
      const d = new Date(today);
      d.setDate(today.getDate() - i);
      days.push({ key: dayKey(d), date: d, minutes: 0, runs: 0, skipped: 0, liters: 0, cost: 0 });
    }
    const byKey = Object.fromEntries(days.map((d) => [d.key, d]));
    for (const h of history) {
      const d = byKey[dayKey(new Date(h.start))];
      if (!d) continue;
      if (h.actual_min > 0) {
        d.minutes += h.actual_min;
        d.runs += 1;
        d.liters += h.water_l || 0;
        d.cost += h.cost || 0;
      } else if (h.result === "skipped_rain") {
        d.skipped += 1;
      }
    }

    const W = Math.max(container.clientWidth || 600, 200);
    const H = 180;
    const padL = 32;
    const padB = 20;
    const padT = 8;
    const plotW = W - padL;
    const plotH = H - padB - padT;
    const rawMax = Math.max(...days.map((d) => d.minutes), 0);
    const tick = rawMax <= 20 ? 5 : rawMax <= 60 ? 15 : rawMax <= 180 ? 30 : 60;
    const yMax = Math.max(tick, Math.ceil(rawMax / tick) * tick);
    const slot = plotW / days.length;
    const gap = 2;
    const barW = Math.max(slot - gap, 1);
    const y = (v) => padT + plotH - (v / yMax) * plotH;

    let grid = "";
    for (let v = 0; v <= yMax; v += tick) {
      grid += `<line class="grid" x1="${padL}" x2="${W}" y1="${y(v)}" y2="${y(v)}"></line>
               <text class="axis" x="${padL - 6}" y="${y(v) + 4}" text-anchor="end">${v}</text>`;
    }

    let bars = "";
    let labels = "";
    days.forEach((d, i) => {
      const x = padL + i * slot + gap / 2;
      bars += `<rect class="hit" data-i="${i}" x="${padL + i * slot}" y="${padT}" width="${slot}" height="${plotH}"></rect>`;
      if (d.minutes > 0) {
        const h = Math.max(plotH - (y(d.minutes) - padT), 1);
        const top = padT + plotH - h;
        const r = Math.min(4, h, barW / 2);
        bars += `<path class="bar" data-i="${i}" d="M${x},${padT + plotH} V${top + r} Q${x},${top} ${x + r},${top} H${x + barW - r} Q${x + barW},${top} ${x + barW},${top + r} V${padT + plotH} Z"></path>`;
      }
      if (i % 7 === (CHART_DAYS - 1) % 7) {
        labels += `<text class="axis" x="${x + barW / 2}" y="${H - 4}" text-anchor="middle">${d.date.toLocaleDateString("de", { day: "2-digit", month: "2-digit" })}</text>`;
      }
    });

    container.innerHTML = `
      <div class="hint">Bewässerte Minuten pro Tag, letzte ${CHART_DAYS} Tage</div>
      <svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="Bewässerte Minuten pro Tag">${grid}${bars}${labels}</svg>
      <div class="tooltip" hidden></div>`;

    const svg = container.querySelector("svg");
    const tip = container.querySelector(".tooltip");
    svg.addEventListener("mousemove", (ev) => {
      const i = ev.target.dataset?.i;
      svg.querySelectorAll(".bar.hover").forEach((b) => b.classList.remove("hover"));
      if (i === undefined) {
        tip.hidden = true;
        return;
      }
      const d = days[Number(i)];
      svg.querySelector(`.bar[data-i="${i}"]`)?.classList.add("hover");
      tip.innerHTML = `<strong>${d.date.toLocaleDateString("de", { weekday: "short", day: "2-digit", month: "2-digit" })}</strong><br>
        ${fmtNum(d.minutes, 1)} min in ${d.runs} ${d.runs === 1 ? "Lauf" : "Läufen"}
        ${showWater && d.runs ? `<br>${fmtLiters(d.liters)}${currency ? `, ${fmtMoney(d.cost, currency)}` : ""}` : ""}
        ${d.skipped ? `<br><span class="muted">${d.skipped}× wegen Regen übersprungen</span>` : ""}`;
      const box = container.getBoundingClientRect();
      const svgBox = svg.getBoundingClientRect();
      tip.style.left = `${svgBox.left - box.left + ((padL + (Number(i) + 0.5) * slot) / W) * svgBox.width}px`;
      tip.style.top = `${svgBox.top - box.top + (y(d.minutes) / H) * svgBox.height}px`;
      tip.hidden = false;
    });
    svg.addEventListener("mouseleave", () => {
      tip.hidden = true;
      svg.querySelectorAll(".bar.hover").forEach((b) => b.classList.remove("hover"));
    });
  }
}

customElements.define("irrigation-scheduler-panel", IrrigationSchedulerPanel);
