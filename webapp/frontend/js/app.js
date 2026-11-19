/**
 * Config Wizard — Main Application Logic
 *
 * Handles: step navigation, map interaction, form state, config export.
 */

/* Recursive JSON editing and review helpers. Never split keys on periods. */
const credentialConfigKey = key => /apikey|password|passwd|secret|token|credential|authorization|privatekey|accesskey|username|clientid|cookie/i.test(String(key).replace(/[^a-z0-9]/gi, ''));
function hiddenConfigPath(path) {
  return path.some(key => String(key).startsWith('_') || credentialConfigKey(key)) ||
    JSON.stringify(path) === JSON.stringify(['coordinates', 'utm_epsg']);
}
function privateConfigURL(value) {
  if (typeof value !== 'string' || !value.includes('://')) return false;
  try {
    const url = new URL(value);
    return !!(url.username || url.password) || [...url.searchParams.keys()].some(credentialConfigKey);
  } catch { return true; }
}

function configDifferences(before, after, path = []) {
  if (JSON.stringify(before) === JSON.stringify(after)) return [];
  const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
  if (object(before) && object(after)) {
    return [...new Set([...Object.keys(before), ...Object.keys(after)])].flatMap(key =>
      hiddenConfigPath([...path, key]) ? [] : configDifferences(before[key], after[key], [...path, key]));
  }
  return hiddenConfigPath(path) ? [] : [{path, before, after}];
}

function safeReviewValue(value) {
  function redact(item) {
    if (privateConfigURL(item)) return '[credential URL hidden]';
    if (Array.isArray(item)) return item.map(redact);
    if (item && typeof item === 'object') return Object.fromEntries(Object.entries(item)
      .filter(([key]) => !hiddenConfigPath([key])).map(([key, child]) => [key, redact(child)]));
    return item;
  }
  return value === undefined ? '(absent)' : JSON.stringify(redact(value), null, 2);
}


// ==========================================================================
// Constants
// ==========================================================================
const configuration = new ConfigurationState();
let selectedPresetId = null;
let presetRequest = 0;
let baselineConfig = null;
let sourceWarnings = [];      // Diagnostics from loading a preset (shown on review).
let dataDirReplaced = null;   // {from, to} when a preset's server data folder was replaced.
let hostInfo = null;          // {cpus, ram_gb} of this computer, from /api/host.
let selectedPresetName = '';
let selectedPresetCounties = [];
let reviewRequest = 0;

const STEPS = [
  { id: 'region',     label: 'Select Region' },
  { id: 'surveys',    label: 'Surveys' },
  { id: 'modes',      label: 'Modes' },
  { id: 'transit',    label: 'Transit' },
  { id: 'demand',     label: 'Demand' },
  { id: 'time',       label: 'Time' },
  { id: 'simulation', label: 'Simulation' },
  { id: 'review', label: 'Review' },
];

const DURATION_ACTIVITIES = ['Work', 'School', 'Shopping', 'Escort', 'Dining', 'Social', 'Other'];

// ==========================================================================
// State
// ==========================================================================
let currentStep = 0;
const completedSteps = new Set();  // Steps that passed validation; they stay green.
let selectedCounties = {};   // { GEOID: { name, population, feature } }
let countyGeoJSON = null;
let map = null;
let countyLayer = null;
let zoomMessageEl = null;

// ==========================================================================
// Step Progress Bar
// ==========================================================================

function renderStepProgress() {
  const container = document.getElementById('stepProgress');
  container.innerHTML = '';

  STEPS.forEach((step, i) => {
    const done = completedSteps.has(i) && i !== currentStep;
    if (i > 0) {
      const sep = document.createElement('div');
      sep.className = 'step-progress__separator';
      if (completedSteps.has(i - 1)) sep.classList.add('step-progress__item--completed');
      container.appendChild(sep);
    }

    // Every tab is clickable, in both directions. goToStep() checks the
    // steps in between when moving forward.
    const item = document.createElement('button');
    item.type = 'button';
    item.setAttribute('aria-label', `${i + 1}. ${step.label}${done ? ' (completed)' : ''}`);
    if (i === currentStep) item.setAttribute('aria-current', 'step');
    item.className = 'step-progress__item';
    item.title = i === currentStep ? `You are here: ${step.label}` : `Go to ${step.label}`;
    if (i === currentStep) item.classList.add('step-progress__item--active');
    if (done) item.classList.add('step-progress__item--completed');
    item.onclick = () => { if (i !== currentStep) goToStep(i); };

    const icon = document.createElement('span');
    icon.className = 'step-progress__icon';
    if (done) {
      icon.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" width="14" height="14"><polyline points="20 6 9 17 4 12"/></svg>';
    } else {
      icon.textContent = i + 1;
    }

    const label = document.createElement('span');
    label.textContent = step.label;

    item.appendChild(icon);
    item.appendChild(label);
    container.appendChild(item);
  });
}

function goToStep(stepIndex) {
  if (stepIndex > currentStep) {
    // Moving forward: the current step and every step in between must be valid.
    // Stop on the first invalid step and show it with its message.
    for (let i = currentStep; i < stepIndex; i++) {
      if (validateStep(i, {quiet: i !== currentStep})) { completedSteps.add(i); continue; }
      completedSteps.delete(i);
      if (i !== currentStep) { showStep(i); validateStep(i); } else renderStepProgress();
      return;
    }
  } else if (STEPS[currentStep].id === 'review') {
    // Review turns green only after a successful export (see exportConfig).
  } else if (validateStep(currentStep, {quiet: true})) {
    // Moving back never blocks; a valid step stays green.
    completedSteps.add(currentStep);
  } else {
    completedSteps.delete(currentStep);
  }
  showStep(stepIndex);
}

function showStep(stepIndex) {
  currentStep = stepIndex;
  renderStepProgress();

  // Show/hide panels
  STEPS.forEach((step, i) => {
    const panel = document.getElementById(`panel-${step.id}`);
    panel.classList.toggle('panel--active', i === currentStep);
    panel.classList.toggle('panel--completed', completedSteps.has(i) && i !== currentStep);
  });

  // Scroll to active panel
  const activePanel = document.getElementById(`panel-${STEPS[currentStep].id}`);
  activePanel.scrollIntoView({ behavior: 'smooth', block: 'start' });

  // Re-invalidate map size if returning to region step
  const heading = activePanel.querySelector('.panel__title');
  heading.tabIndex = -1;
  heading.focus({preventScroll: true});
  if (STEPS[currentStep].id === 'region' && map) {
    setTimeout(() => { map.invalidateSize(); fitSelectedRegion(); }, 100);
  }
  if (STEPS[currentStep].id === 'review') { renderReview(); }
}

// quiet: check only, with no alert or browser message (for steps not on screen).
function validateStep(stepIndex, {quiet = false} = {}) {
  const panel = document.getElementById(`panel-${STEPS[stepIndex].id}`);
  for (const input of panel.querySelectorAll('input[data-edited], select[data-edited]')) {
    if (!(quiet ? input.checkValidity() : input.reportValidity())) return false;
  }
  switch (STEPS[stepIndex].id) {
    case 'region': // Region
      if (!configuration.config || Object.keys(selectedCounties).length === 0) {
        if (!quiet) alert('Please select at least one county.');
        return false;
      }
      updateBadge('region', `${Object.keys(selectedCounties).length} counties`);
      return true;

    case 'surveys': // Surveys
      const nhts = document.getElementById('chkNhts').checked;
      const custom = document.getElementById('chkCustomSurvey').checked;
      const surveys = configuration.config?.data?.surveys;
      const active = Array.isArray(surveys) && surveys.some(s => s && typeof s === 'object' &&
        ((s.weight ?? 1) > 0 || Object.values(s.roles || {}).some(weight => weight > 0)));
      if (!active) {
        if (!quiet) alert('At least one survey must be selected.');
        return false;
      }
      updateBadge('surveys', nhts && custom ? '2 surveys' : '1 survey');
      return true;

    default:
      // Mark badge as completed
      updateBadge(STEPS[stepIndex].id, 'Done');
      return true;
  }
}

function updateBadge(panelId, text) {
  const badge = document.getElementById(`badge-${panelId}`);
  if (badge) {
    badge.textContent = text;
    badge.classList.remove('hidden');
  }
}

// ==========================================================================
// Navigation Buttons
// ==========================================================================

function setupNavigation() {
  // Next buttons
  for (let i = 0; i < STEPS.length - 1; i++) {
    const btn = document.getElementById(`btnNext${i}`);
    if (btn) btn.onclick = () => goToStep(i + 1);
  }

  // Back buttons
  for (let i = 1; i < STEPS.length; i++) {
    const btn = document.getElementById(`btnBack${i}`);
    if (btn) btn.onclick = () => goToStep(i - 1);
  }
}

// ==========================================================================
// Map (Panel 1 — Region)
// ==========================================================================

async function initMap() {
  map = L.map('countyMap', {
    center: [39.8, -98.5],
    zoom: 4,
    minZoom: 3,
    maxZoom: 12,
  });

  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19,
    className: 'basemap-muted',
  }).addTo(map);

  zoomMessageEl = document.getElementById('mapMessage');
  // Experiment markers load independently of county data and selection.
  setupExperimentMarkers();

  // Load county data
  try {
    const resp = await fetch('/api/counties');
    countyGeoJSON = await resp.json();
    if (!resp.ok) throw new Error('County data unavailable');
    addCountyLayer();
    syncSelectedRegion();
    if (selectedPresetId && selectedPresetId !== 'custom') fitSelectedRegion();
  } catch (err) {
    console.error('Failed to load counties:', err);
    zoomMessageEl.textContent = 'Failed to load county data. Is the server running?';
  }

  // Show/hide counties based on zoom
  map.on('zoomend', updateCountyVisibility);
  updateCountyVisibility();
}

async function setupExperimentMarkers() {
  try {
    const {presets} = await fetchJSON('/api/config/presets');
    const regions = new Map();
    for (const preset of presets) {
      if (preset.location == null) continue;
      if (!regions.has(preset.region)) regions.set(preset.region, []);
      regions.get(preset.region).push(preset);
    }
    for (const [region, experiments] of regions) {
      const popup = document.createElement('div');
      const title = document.createElement('strong');
      title.textContent = region;
      const list = document.createElement('ul');
      list.className = 'experiment-list';
      for (const experiment of experiments) {
        const item = document.createElement('li');
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'btn btn--secondary';
        button.textContent = experiment.display_name;
        button.title = experiment.description || '';
        button.onclick = () => choosePresetFromMap(experiment);
        item.appendChild(button);
        list.appendChild(item);
      }
      const hint = document.createElement('div');
      hint.className = 'text-sm text-muted';
      hint.textContent = 'Pick an experiment to apply its counties and parameters. You can change them later.';
      popup.append(title, hint, list);
      const {lat, lng} = experiments[0].location;
      L.marker([lat, lng], {title: region, bubblingMouseEvents: false})
        .bindPopup(popup).addTo(map);
    }
  } catch (error) {
    document.getElementById('configurationStatus').textContent = `Could not load experiments: ${error.message}`;
  }
}

function addCountyLayer() {
  countyLayer = L.geoJSON(countyGeoJSON, {
    style: countyStyle,
    onEachFeature: (feature, layer) => {
      const props = feature.properties;
      layer.on({
        click: () => toggleCounty(props.GEOID, props.name, props.population, feature, layer),
        mouseover: (e) => {
          if (!selectedCounties[props.GEOID]) {
            e.target.setStyle({ fillOpacity: 0.3, weight: 2 });
          }
          layer.bindTooltip(
            `<strong>${props.name}</strong><br>Pop: ${formatNumber(props.population)}`,
            { sticky: true }
          ).openTooltip();
        },
        mouseout: (e) => {
          if (!selectedCounties[props.GEOID]) {
            countyLayer.resetStyle(e.target);
          }
          layer.closeTooltip();
        },
      });
    },
  });

  countyLayer.addTo(map);
}

function countyStyle(feature) {
  const geoid = feature.properties.GEOID;
  const isSelected = !!selectedCounties[geoid];
  return {
    fillColor: isSelected ? '#2563eb' : '#94a3b8',
    weight: isSelected ? 2.5 : 1,
    opacity: 1,
    color: isSelected ? '#1d4ed8' : '#cbd5e1',
    fillOpacity: isSelected ? 0.45 : 0.1,
  };
}

function updateCountyVisibility() {
  if (!countyLayer) return;
  const zoom = map.getZoom();
  const show = zoom >= 6;

  if (show) {
    if (!map.hasLayer(countyLayer)) map.addLayer(countyLayer);
    zoomMessageEl.style.display = 'none';
  } else {
    if (map.hasLayer(countyLayer)) map.removeLayer(countyLayer);
    zoomMessageEl.style.display = 'block';
  }
}

function toggleCounty(geoid, name, population, feature, layer) {
  if (selectedCounties[geoid]) {
    // Deselect
    delete selectedCounties[geoid];
    countyLayer.resetStyle(layer);
  } else {
    selectedCounties[geoid] = { name, population, feature };
    layer.setStyle({
      fillColor: '#2563eb',
      weight: 2.5,
      color: '#1d4ed8',
      fillOpacity: 0.45,
    });
  }

  updateMapStats();
  updateSelectedCountiesList();
  updateRegionSelection();
}

function getTotalPopulation() {
  return Object.values(selectedCounties).reduce((sum, c) => sum + (c.population || 0), 0);
}

function updateMapStats() {
  const count = Object.keys(selectedCounties).length;
  const pop = getTotalPopulation();
  document.getElementById('statCountyCount').textContent = count;

  const popEl = document.getElementById('statPopulation');
  popEl.textContent = formatNumber(pop);
  popEl.className = 'map-overlay__value';

}

function updateSelectedCountiesList() {
  const container = document.getElementById('selectedCountiesList');
  container.innerHTML = '';

  Object.entries(selectedCounties).forEach(([geoid, data]) => {
    const tag = document.createElement('span');
    tag.className = 'tag tag--primary';
    tag.append(document.createTextNode(`${data.name} (${formatNumber(data.population)}) `));
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'tag__remove';
    remove.textContent = '×';
    remove.setAttribute('aria-label', `Remove ${data.name}`);
    remove.onclick = () => removeCounty(geoid);
    tag.appendChild(remove);
    container.appendChild(tag);
  });
}

function removeCounty(geoid) {
  delete selectedCounties[geoid];
  // Reset style on the map layer
  if (countyLayer) {
    countyLayer.eachLayer((layer) => {
      if (layer.feature.properties.GEOID === geoid) {
        countyLayer.resetStyle(layer);
      }
    });
  }
  updateMapStats();
  updateSelectedCountiesList();
  updateRegionSelection();
}

function updateRegionSelection() {
  document.getElementById('btnNext0').disabled = !configuration.config || Object.keys(selectedCounties).length === 0;
  if (configuration.config) configuration.set(['region', 'counties'], Object.keys(selectedCounties));
  updateExperimentLabel();
}

// Tell the user when the counties no longer match the selected experiment:
// its calibrated settings then apply to a different area.
function updateExperimentLabel() {
  const label = document.getElementById('selectedExperiment');
  const isPreset = selectedPresetId && selectedPresetId !== 'custom';
  label.classList.toggle('hidden', !isPreset);
  document.getElementById('btnCustomConfiguration').classList.toggle('hidden', !isPreset);
  if (!isPreset) { label.textContent = ''; return; }
  const current = [...Object.keys(selectedCounties)].sort();
  const changed = JSON.stringify(current) !== JSON.stringify([...selectedPresetCounties].sort());
  label.textContent = changed ?
    `Based on experiment: ${selectedPresetName}. The counties are changed, so its calibrated settings may not fit the new area.` :
    `Selected experiment: ${selectedPresetName}`;
}

function syncSelectedRegion() {
  const value = configuration.get(['region', 'counties']);
  const counties = Array.isArray(value) ? value : [];
  selectedCounties = {};
  for (const geoid of counties) {
    const feature = countyGeoJSON?.features.find(f => f.properties.GEOID === geoid);
    selectedCounties[geoid] = {name: feature?.properties.name || geoid,
      population: feature?.properties.population || 0, feature};
  }
  if (countyLayer) countyLayer.setStyle(countyStyle);
  updateMapStats();
  updateSelectedCountiesList();
  // Hydration must not rewrite array order or add configuration fields.
  document.getElementById('btnNext0').disabled = !configuration.config || counties.length === 0;
}

function fitSelectedRegion() {
  if (!countyLayer || !map) return;
  const layers = [];
  countyLayer.eachLayer(layer => { if (selectedCounties[layer.feature.properties.GEOID]) layers.push(layer); });
  if (layers.length) map.fitBounds(L.featureGroup(layers).getBounds(), {padding: [20, 20], maxZoom: 9});
}

// ==========================================================================
// Panel 2 — Surveys
// ==========================================================================

function setupSurveys() {
  const chkNhts = document.getElementById('chkNhts');
  const chkCustom = document.getElementById('chkCustomSurvey');
  const cardNhts = document.getElementById('card-nhts');
  const cardCustom = document.getElementById('card-custom-survey');
  const customOptions = document.getElementById('customSurveyOptions');

  chkNhts.addEventListener('change', () => {
    cardNhts.classList.toggle('card--selected', chkNhts.checked);
  });

  chkCustom.addEventListener('change', () => {
    cardCustom.classList.toggle('card--selected', chkCustom.checked);
    customOptions.classList.toggle('hidden', !chkCustom.checked);
  });


}

// ==========================================================================
// Panel 3 — Modes
// ==========================================================================

function setupModes() {
  const modes = ['car', 'bus', 'rail', 'walk', 'bike'];
  modes.forEach(mode => {
    const toggle = document.getElementById(`modeEnable-${mode}`);
    const card = document.getElementById(`modeCard-${mode}`);
    if (toggle && card) {
      toggle.addEventListener('change', () => {
        card.classList.toggle('mode-card--enabled', toggle.checked);
        card.classList.toggle('mode-card--disabled', !toggle.checked);
      });
    }
  });
}

// ==========================================================================
// Panel 4 — Transit
// ==========================================================================

function setupTransit() {
  const transitToggle = document.getElementById('transit-enabled');
  const transitSettings = document.getElementById('transitSettings');
  transitToggle.addEventListener('change', () => {
    transitSettings.style.display = transitToggle.checked ? 'block' : 'none';
  });
}

// ==========================================================================
// Panel 5 — Demand
// ==========================================================================

function setupDemand() {
  const targetSelect = document.getElementById('demand-target_plans');
  const customInput = document.getElementById('demand-target_plans_custom');
  targetSelect.addEventListener('change', () => {
    customInput.classList.toggle('hidden', targetSelect.value !== 'custom');
    customInput.disabled = targetSelect.value !== 'custom';
  });
}

// ==========================================================================
// Panel 6 — Time & Duration
// ==========================================================================

function buildDurationTable() {
  const tbody = document.getElementById('durationTable');
  tbody.innerHTML = '';

  DURATION_ACTIVITIES.forEach(activity => {
    const row = document.createElement('tr');
    row.style.borderBottom = '1px solid var(--color-gray-200)';
    row.innerHTML = `
      <td style="padding:8px 12px;font-weight:500;">${activity}</td>
      <td style="padding:8px 12px;">
        <input type="number" class="form-input" id="dur-${activity}-min"
               min="1" max="1440" style="width:80px;">
      </td>
      <td style="padding:8px 12px;">
        <input type="number" class="form-input" id="dur-${activity}-max"
               min="1" max="1440" style="width:80px;">
      </td>
      <td style="padding:8px 12px;">
        <select class="form-select" id="dur-${activity}-priority" style="width:120px;">
          <option value="1" >1 — Mandatory</option>
          <option value="2" >2 — Default</option>
          <option value="3" >3 — Discretionary</option>
        </select>
      </td>
    `;
    tbody.appendChild(row);
  });
}

// ==========================================================================
// Panel 7 — Simulation
// ==========================================================================

function setupSimulation() {
  const countsToggle = document.getElementById('counts-enabled');
  const countsSettings = document.getElementById('countsSettings');
  countsToggle.addEventListener('change', () => {
    countsSettings.style.display = countsToggle.checked ? 'block' : 'none';
  });

  const evalToggle = document.getElementById('eval-run');
  const evalSettings = document.getElementById('evalSettings');
  evalToggle.addEventListener('change', () => {
    evalSettings.style.display = evalToggle.checked ? 'block' : 'none';
  });
}

// ==========================================================================
// Slider value sync
// ==========================================================================

function setupSliders() {
  const sliders = [
    ['nhtsWeight',                   'nhtsWeightVal'],
    ['customSurveyWeight',           'customSurveyWeightVal'],
    ['mode-bus-blend_weight',        'mode-bus-blend_weight_val'],
    ['mode-rail-blend_weight',       'mode-rail-blend_weight_val'],
    ['demand-scaling_factor',        'demand-scaling_factor_val'],
    ['nonwork-trip_share',           'nonwork-trip_share_val'],
    ['purpose-shopping-blend_weight','purpose-shopping-blend_weight_val'],
    ['purpose-school-blend_weight',  'purpose-school-blend_weight_val'],
    ['purpose-social-blend_weight',  'purpose-social-blend_weight_val'],
    ['purpose-dining-blend_weight',  'purpose-dining-blend_weight_val'],
    ['purpose-other-blend_weight',   'purpose-other-blend_weight_val'],
    ['counts-fha_weight',            'counts-fha_weight_val'],
  ];

  sliders.forEach(([inputId, displayId]) => {
    const input = document.getElementById(inputId);
    const display = document.getElementById(displayId);
    if (input && display) {
      const update = () => {
        display.textContent = input.value === '' ? 'Not set' : String(Number(input.value));
        // Special: update scaling hint
        if (inputId === 'demand-scaling_factor') {
          const pct = (parseFloat(input.value) * 100).toFixed(1);
          document.getElementById('demand-scaling_hint').textContent = input.value === '' ?
            'Scaling factor is not set.' : `Simulating ~${pct}% of the population`;
        }
      };
      input.addEventListener('input', update);
      input.addEventListener('config-populate', update);
      update(); // init
    }
  });
}

// ==========================================================================
// Collapsible sections
// ==========================================================================

function toggleCollapsible(id) {
  const el = document.getElementById(id);
  if (el) el.classList.toggle('collapsible--open');
}

// Wire up all collapsible triggers
function setupCollapsibles() {
  document.querySelectorAll('.collapsible__trigger').forEach(trigger => {
    const collapsible = trigger.closest('.collapsible');
    if (collapsible && !trigger.hasAttribute('onclick')) {
      trigger.addEventListener('click', () => {
        collapsible.classList.toggle('collapsible--open');
      });
    }
  });
}

// ==========================================================================
// Info Popup positioning (fixed, never clipped)
// ==========================================================================

function setupInfoPopups() {
  document.querySelectorAll('.info-icon').forEach(icon => {
    const popup = icon.querySelector('.info-popup');
    if (!popup) return;

    // Move popup to body so it's never clipped by overflow
    document.body.appendChild(popup);

    function showPopup() {
      const rect = icon.getBoundingClientRect();
      const popupW = 300;
      const margin = 8;

      // Horizontal: center on the icon, but clamp to viewport
      let left = rect.left + rect.width / 2 - popupW / 2;
      left = Math.max(margin, Math.min(left, window.innerWidth - popupW - margin));

      // Vertical: prefer above the icon; if not enough room, show below
      popup.style.left = left + 'px';
      popup.style.width = popupW + 'px';
      popup.classList.remove('info-popup--above', 'info-popup--below');

      // Temporarily show to measure height
      popup.style.visibility = 'hidden';
      popup.classList.add('info-popup--visible');
      const popupH = popup.offsetHeight;
      popup.classList.remove('info-popup--visible');
      popup.style.visibility = '';

      if (rect.top - popupH - margin > 0) {
        // Above
        popup.style.top = (rect.top - popupH - margin) + 'px';
        popup.classList.add('info-popup--above');
      } else {
        // Below
        popup.style.top = (rect.bottom + margin) + 'px';
        popup.classList.add('info-popup--below');
      }

      // Adjust arrow horizontal position to point at the icon center
      const arrowLeft = rect.left + rect.width / 2 - left;
      popup.style.setProperty('--arrow-left', arrowLeft + 'px');

      popup.classList.add('info-popup--visible');
    }

    function hidePopup() {
      popup.classList.remove('info-popup--visible');
    }

    icon.addEventListener('mouseenter', showPopup);
    icon.addEventListener('mouseleave', hidePopup);
    icon.addEventListener('focus', showPopup);
    icon.addEventListener('blur', hidePopup);
  });
}

// ==========================================================================
// Purpose card expand/collapse
// ==========================================================================

function togglePurposeCard(purpose) {
  const card = document.getElementById(`purposeCard-${purpose}`);
  if (card) card.classList.toggle('purpose-card--expanded');
}

// ==========================================================================
// Export Config
// ==========================================================================

function collectFormData() {
  if (!configuration.config) throw new Error('Choose a starting configuration first.');
  return configuration.snapshot();
}

// Populate controls without dispatching edit events. Only user events write state.
function populateControl(el, value) {
  if (!el) return;
  delete el.dataset.edited;
  if (el.type === 'checkbox') {
    el.checked = value === true;
    el.indeterminate = value == null;
  } else {
    if (el.tagName === 'SELECT' && !Array.from(el.options).some(o => o.value === String(value ?? ''))) {
      const option = document.createElement('option');
      option.value = String(value ?? '');
      option.textContent = value == null ? 'Not set' : String(value);
      el.appendChild(option);
    }
    if (el.type === 'range') {
      el.step = 'any';
      if (value == null) el.type = 'number';
      else {
        el.min = Math.min(Number(el.min), Number(value));
        el.max = Math.max(Number(el.max), Number(value));
      }
    }
    el.value = value ?? '';
    el.placeholder = value == null ? 'Not set (engine default)' : el.placeholder;
  }
  el.title = value === undefined ? 'Not configured; preserved until edited.' : '';
  el.dispatchEvent(new Event('config-populate'));
}

function inputValue(el) {
  if (el.type === 'checkbox') return el.checked;
  if (el.type === 'range' || el.type === 'number' || el.id === 'counts-fha_month' || /-priority$/.test(el.id)) {
    return el.value === '' ? null : Number(el.value);
  }
  if (el.id === 'mode-car-survey_rate' && el.value !== 'auto') return el.value === '' ? null : Number(el.value);
  return el.value;
}

function refreshControlAppearance() {
  for (const mode of ['car', 'bus', 'rail', 'walk', 'bike']) {
    const enabled = document.getElementById(`modeEnable-${mode}`).checked;
    document.getElementById(`modeCard-${mode}`).classList.toggle('mode-card--enabled', enabled);
    document.getElementById(`modeCard-${mode}`).classList.toggle('mode-card--disabled', !enabled);
  }
  for (const purpose of ['shopping', 'school', 'social', 'dining', 'other']) {
    document.getElementById(`purposeCard-${purpose}`).classList.toggle('purpose-card--enabled',
      document.getElementById(`purpose-${purpose}-enabled`).checked);
  }
  for (const [control, content] of [['transit-enabled', 'transitSettings'], ['counts-enabled', 'countsSettings'], ['eval-run', 'evalSettings']]) {
    document.getElementById(content).style.display = document.getElementById(control).checked ? 'block' : 'none';
  }
  document.getElementById('demand-target_plans_custom').classList.toggle('hidden',
    document.getElementById('demand-target_plans').value !== 'custom');
  document.getElementById('demand-target_plans_custom').disabled =
    document.getElementById('demand-target_plans').value !== 'custom';
}

const SURVEY_BINDINGS = {
  customSurveyType: 'type', customSurveyYear: 'year', customSurveyWeight: 'weight',
  customSurveyFile: 'file', customSurveyPerson: 'person_file', customSurveyDay: 'day_file',
  customSurveyLinked: 'linked_trip_file',
};

function populateSurveys() {
  for (const [custom, checkbox, card] of [[false, 'chkNhts', 'card-nhts'], [true, 'chkCustomSurvey', 'card-custom-survey']]) {
    const entry = configuration.survey(custom);
    document.getElementById(checkbox).checked = !!entry;
    document.getElementById(card).classList.toggle('card--selected', !!entry);
  }
  const regional = configuration.survey(true);
  for (const [id, key] of Object.entries(SURVEY_BINDINGS)) populateControl(document.getElementById(id), regional?.[key]);
  populateControl(document.getElementById('nhtsWeight'), configuration.survey(false)?.weight);
  document.getElementById('customSurveyOptions').classList.toggle('hidden', !regional);
  document.getElementById('nhtsWeight').disabled = !configuration.survey(false);
}

function populateConfiguration() {
  for (const [id, path] of Object.entries(CONFIG_BINDINGS)) populateControl(document.getElementById(id), configuration.get(path));
  const target = configuration.get(['plan_generation', 'target_plans']);
  populateControl(document.getElementById('demand-target_plans'), target === 'all' ? 'all' : 'custom');
  populateControl(document.getElementById('demand-target_plans_custom'), target === 'all' ? undefined : target);
  document.getElementById('demand-target_plans_custom').required = target !== 'all';
  populateSurveys();
  refreshControlAppearance();
  syncSelectedRegion();
}

function setupConfigurationBindings() {
  for (const [id, path] of Object.entries(CONFIG_BINDINGS)) {
    const el = document.getElementById(id);
    if (!el) continue;
    const update = () => {
      el.dataset.edited = 'true';
      if (!configuration.config || (el.validity && !el.validity.valid)) return;
      configuration.set(path, inputValue(el));
      refreshControlAppearance();
    };
    el.addEventListener('input', update);
    el.addEventListener('change', update);
  }
  for (const [id, custom] of [['chkNhts', false], ['chkCustomSurvey', true]]) {
    document.getElementById(id).addEventListener('change', event => {
      configuration.includeSurvey(custom, event.target.checked);
      populateSurveys();
    });
  }
  for (const [id, key] of Object.entries(SURVEY_BINDINGS)) {
    document.getElementById(id).addEventListener('input', event => {
      event.target.dataset.edited = 'true';
      if (!event.target.validity.valid) return;
      const index = configuration.surveyIndex(true);
      if (index >= 0) configuration.set(['data', 'surveys', index, key], inputValue(event.target));
    });
  }
  document.getElementById('nhtsWeight').addEventListener('input', event => {
    const index = configuration.surveyIndex(false);
    if (index >= 0) configuration.set(['data', 'surveys', index, 'weight'], inputValue(event.target));
  });
  document.getElementById('demand-target_plans').addEventListener('change', event => {
    if (event.target.value === 'all') configuration.set(['plan_generation', 'target_plans'], 'all');
    else {
      const custom = document.getElementById('demand-target_plans_custom');
      custom.required = true;
      custom.dataset.edited = 'true';
      if (custom.value && custom.validity.valid) configuration.set(['plan_generation', 'target_plans'], Number(custom.value));
      custom.focus();
    }
    if (event.target.value === 'all') document.getElementById('demand-target_plans_custom').required = false;
  });
  document.getElementById('demand-target_plans_custom').addEventListener('input', event => {
    if (event.target.validity.valid && event.target.value) configuration.set(['plan_generation', 'target_plans'], Number(event.target.value));
  });
  // Existing form markup uses visual labels; give every editing control a name.
  document.querySelectorAll('.panel input, .panel select').forEach(el => {
    if (!el.labels?.length && !el.hasAttribute('aria-label')) {
      const label = el.closest('.form-group')?.querySelector('.form-label');
      el.setAttribute('aria-label', label?.childNodes[0]?.textContent.trim() || el.id.replaceAll('-', ' '));
    }
  });
}

async function fetchJSON(url) {
  const response = await fetch(url);
  const body = await response.json();
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Unable to retrieve configuration.');
  return body;
}

// Short message at the top of the page that goes away by itself.
let toastTimer = null;
function showToast(message, kind = 'success') {
  const toast = document.getElementById('toast');
  toast.textContent = message;
  toast.className = `toast toast--${kind} toast--visible`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove('toast--visible'), 4000);
}

// Returns 'selected' (new configuration loaded), 'same' (already selected), or null (cancelled or failed).
let selectedSnapshot = null;
async function selectPreset(preset) {
  if (selectedPresetId === preset.id) {
    ++presetRequest; // Cancel a different pending selection while retaining edits.
    fitSelectedRegion();
    return 'same';
  }
  if (selectedSnapshot && JSON.stringify(configuration.config) !== selectedSnapshot &&
      !window.confirm('Changing the starting configuration replaces your current edits. Continue?')) {
    return null;
  }
  const requestId = ++presetRequest;
  try {
    const response = preset.id === 'custom' ? {config: structuredClone(baselineConfig), warnings: []} :
      await fetchJSON(`/api/config/presets/${encodeURIComponent(preset.id)}`);
    if (requestId !== presetRequest) return null;
    if (!response.config) throw new Error('Starting configuration is unavailable.');
    if (preset.id === 'custom') response.config.region.counties = [];
    // Set before load(): load() notifies the review, which reads these.
    sourceWarnings = response.warnings || [];
    dataDirReplaced = response.data_dir_replaced || null;
    configuration.load(response.config);
    // Templates are used only when a user explicitly adds an absent source.
    for (const custom of [false, true]) {
      const template = baselineConfig?.data?.surveys.find(s => custom ? s.type !== 'nhts' : s.type === 'nhts');
      if (template) configuration.surveyCache[custom] = structuredClone(template);
    }
    selectedPresetId = preset.id;
    const region = response.region || preset.region;
    const name = response.display_name || preset.display_name || preset.id;
    selectedPresetName = region ? `${region} — ${name}` : name;
    // A new starting configuration: earlier steps must be checked again.
    completedSteps.clear();
    renderStepProgress();
    selectedPresetCounties = structuredClone(response.config.region?.counties || []);
    selectedSnapshot = JSON.stringify(configuration.config);
    populateConfiguration();
    document.querySelectorAll('.panel__badge').forEach(el => el.classList.add('hidden'));
    updateExperimentLabel();
    document.getElementById('configurationStatus').textContent = '';
    if (preset.id !== 'custom') fitSelectedRegion();
    return 'selected';
  } catch (error) {
    if (requestId !== presetRequest) return null;
    document.getElementById('configurationStatus').textContent = `Could not load configuration: ${error.message}`;
    showToast(`Could not load the example: ${error.message}`, 'error');
    return null;
  }
}

// From a map pin popup: close the popup, then confirm the choice at the top of the page.
async function choosePresetFromMap(experiment) {
  map.closePopup();
  const result = await selectPreset(experiment);
  if (result === 'selected' || result === 'same') {
    showToast(`Example selected: ${selectedPresetName}. Its counties and parameters are applied. ` +
      'You can change any value in the next steps.');
  }
}

async function setupConfiguration() {
  const status = document.getElementById('configurationStatus');
  const retry = document.getElementById('btnRetryConfiguration');
  retry.onclick = setupConfiguration;
  document.getElementById('btnCustomConfiguration').onclick = async () => {
    if (await selectPreset({id: 'custom'}) === 'selected') {
      showToast('Custom configuration started. Click counties on the map to select your region.');
    }
  };
  retry.classList.add('hidden');
  status.textContent = 'Loading configuration…';
  try {
    baselineConfig = await fetchJSON('/api/defaults');
    if (!configuration.config) await selectPreset({id: 'custom'});
    status.textContent = '';
  } catch (error) {
    status.textContent = `Could not load configuration: ${error.message}`;
    retry.classList.remove('hidden');
  }
}

function fillReviewList(id, messages) {
  const list = document.getElementById(id); list.replaceChildren();
  for (const message of messages) {
    const item = document.createElement('li'); item.textContent = message; list.appendChild(item);
  }
}

// ==========================================================================
// "Your changes" table: readable name, step, starting value and new value
// ==========================================================================

// Settings that are not edited through a CONFIG_BINDINGS control.
const SPECIAL_SETTINGS = {
  '["region","counties"]': {label: 'Counties', step: 'Select Region'},
  '["data","surveys"]': {label: 'Surveys', step: 'Surveys'},
  '["plan_generation","target_plans"]': {label: 'Target Plans', step: 'Travel Demand'},
};

// Name of a wizard control, as the user sees it on the page.
function controlLabel(el) {
  if (el.labels?.length) return el.labels[0].textContent.trim().replace(/\s+/g, ' ');
  const label = el.closest('.form-group')?.querySelector('.form-label');
  return label?.childNodes[0]?.textContent.trim() || el.getAttribute('aria-label') || el.id;
}

function settingInfo(path) {
  const key = JSON.stringify(path.map(String));
  if (SPECIAL_SETTINGS[key]) return SPECIAL_SETTINGS[key];
  if (path[0] === 'duration_constraints' && path[1] === 'activity_durations' && path.length === 4) {
    const field = {min_minutes: 'minimum minutes', max_minutes: 'maximum minutes', trim_priority: 'trim priority'}[path[3]] || path[3];
    return {label: `${path[2]} duration: ${field}`, step: 'Time'};
  }
  for (const [id, bound] of Object.entries(CONFIG_BINDINGS)) {
    if (JSON.stringify(bound) !== key) continue;
    const el = document.getElementById(id);
    if (!el) break;
    const panel = el.closest('.panel')?.id.replace('panel-', '');
    return {label: controlLabel(el), step: STEPS.find(step => step.id === panel)?.label || ''};
  }
  // Not a wizard field: use the last key as a readable name.
  const last = String(path.at(-1)).split('.').at(-1);
  return {label: last.replace(/([a-z])([A-Z])/g, '$1 $2').replace(/_/g, ' ').replace(/^./, c => c.toUpperCase()), step: ''};
}

function countyName(geoid) {
  const feature = countyGeoJSON?.features.find(f => f.properties.GEOID === geoid);
  return feature ? feature.properties.name : geoid;
}

// Short, readable value (no JSON indentation, credentials hidden).
function displayValue(value, path) {
  if (value === undefined || value === null || value === '') return 'Not set';
  if (typeof value === 'boolean') return value ? 'On' : 'Off';
  if (privateConfigURL(value)) return '[hidden]';
  const key = JSON.stringify(path.map(String));
  if (key === '["region","counties"]' && Array.isArray(value)) {
    return value.length ? `${value.length}: ${value.map(countyName).join(', ')}` : 'None';
  }
  if (key === '["data","surveys"]' && Array.isArray(value)) {
    return value.length ? value.map(s => `${String(s?.type || 'survey').toUpperCase()} (weight ${s?.weight ?? 1})`).join(', ') : 'None';
  }
  if (Array.isArray(value) && value.every(v => v === null || typeof v !== 'object')) {
    return value.length ? value.join(', ') : 'None';
  }
  if (typeof value === 'object') return JSON.stringify(JSON.parse(safeReviewValue(value)));
  return String(value);
}

function renderChangeTable(id, changes) {
  const container = document.getElementById(id);
  container.replaceChildren();
  if (!changes.length) {
    const empty = document.createElement('p');
    empty.className = 'review-empty';
    empty.textContent = 'You did not change any value.';
    container.appendChild(empty);
    return;
  }
  const stepOrder = label => { const i = STEPS.findIndex(step => step.label === label); return i < 0 ? STEPS.length : i; };
  const rows = changes.map(change => ({...change, info: settingInfo(change.path)}))
    .sort((a, b) => stepOrder(a.info.step) - stepOrder(b.info.step));
  const table = document.createElement('table');
  table.className = 'change-table';
  const head = table.createTHead().insertRow();
  for (const title of ['Setting', 'Starting value', 'Your value']) {
    const th = document.createElement('th'); th.textContent = title; head.appendChild(th);
  }
  const body = table.createTBody();
  for (const {path, before, after, info} of rows) {
    const row = body.insertRow();
    const setting = row.insertCell();
    const label = document.createElement('span');
    label.className = 'change-table__label';
    label.textContent = info.label;
    const meta = document.createElement('span');
    meta.className = 'change-table__meta';
    if (info.step) meta.append(`${info.step} step · `);
    const code = document.createElement('code');
    code.textContent = path.join('.');
    meta.appendChild(code);
    setting.append(label, meta);
    for (const [value, className] of [[before, 'change-table__before'], [after, 'change-table__after']]) {
      const cell = row.insertCell();
      cell.className = className;
      cell.textContent = displayValue(value, path);
    }
  }
  container.appendChild(table);
}

const issueText = issue => `${issue.path ? issue.path + ': ' : ''}${issue.message}`;

// ==========================================================================
// Computer resources: compare settings with this computer (/api/host)
// ==========================================================================

// [control id, label, wizard step, engine default when the value is not set]
const CPU_SETTINGS = [
  ['demand-num_processes', 'Plan generation processes', 'Travel Demand', null],
  ['pt2m-numOfThreads', 'Transit mapping threads', 'Transit', null],
  ['sim-global_threads', 'MATSim threads', 'Simulation', null],
  ['sim-qsim_threads', 'Mobility simulation threads', 'Simulation', null],
];
const MEMORY_SETTINGS = [
  ['sim-heap_size_gb', 'Simulation memory', 'Simulation', 32],        // matsim/runner.py default
  ['sim-network_heap_size_gb', 'Network build memory', 'Simulation', 8], // network_generator.py default
];
const VERY_LARGE_MEMORY_GB = 64;  // Used only when the RAM of this computer is unknown.

function settingValue(id, fallback) {
  const value = configuration.get(CONFIG_BINDINGS[id]);
  return value == null || value === '' ? fallback : Number(value);
}

// The engine limits Java memory to heap_ram_fraction (0.1-0.9, default 0.7) of RAM, never below 2 GB.
function javaMemoryLimit() {
  if (!hostInfo?.ram_gb) return null;
  const raw = settingValue('sim-heap_ram_fraction', 0.7);
  const fraction = Math.min(Math.max(Number.isFinite(raw) ? raw : 0.7, 0.1), 0.9);
  return {fraction, limit: Math.max(2, Math.floor(hostInfo.ram_gb * fraction))};
}

// {control id: {label, step, text}} for settings that do not fit this computer.
function resourceProblems() {
  const problems = {};
  if (!configuration.config || !hostInfo) return problems;
  for (const [id, label, step] of CPU_SETTINGS) {
    const value = settingValue(id, null);
    if (hostInfo.cpus && value > hostInfo.cpus) {
      problems[id] = {label, step, text: `${value}, but this computer has ${hostInfo.cpus} CPU cores.`};
    }
  }
  const memory = javaMemoryLimit();
  for (const [id, label, step, fallback] of MEMORY_SETTINGS) {
    const value = settingValue(id, fallback);
    if (memory && value > memory.limit) {
      problems[id] = {label, step,
        text: `${value} GB, but Java can use only ${memory.limit} GB on this computer. The engine will lower it.`};
    } else if (!memory && value >= VERY_LARGE_MEMORY_GB) {
      problems[id] = {label, step, text: `${value} GB is very large. Check the RAM of the computer that runs the simulation.`};
    }
  }
  return problems;
}

// Hint under each resource field: this computer's limit, or the problem.
function updateResourceHints() {
  const problems = resourceProblems();
  const memory = javaMemoryLimit();
  for (const hint of document.querySelectorAll('[data-resource-hint]')) {
    const id = hint.dataset.resourceHint;
    const isMemory = MEMORY_SETTINGS.some(([settingId]) => settingId === id);
    hint.style.color = problems[id] ? 'var(--color-warning)' : '';
    hint.textContent = problems[id] ? problems[id].text :
      !hostInfo ? '' :
      isMemory ? (memory ? `This computer: Java can use up to ${memory.limit} GB ` +
        `(${Math.round(memory.fraction * 100)}% of ${hostInfo.ram_gb} GB RAM).` : '') :
      hostInfo.cpus ? `This computer: ${hostInfo.cpus} CPU cores.` : '';
  }
}

async function loadHostInfo() {
  try {
    hostInfo = await fetchJSON('/api/host');
    const parts = [hostInfo.cpus && `${hostInfo.cpus} CPU cores`, hostInfo.ram_gb && `${hostInfo.ram_gb} GB RAM`].filter(Boolean);
    if (parts.length) {
      document.getElementById('hostInfo').textContent = `This computer (where this web page runs): ${parts.join(', ')}. ` +
        'Set these values for the computer that runs the simulation.';
    }
  } catch { hostInfo = null; }
  updateResourceHints();
  renderReviewChecks();
}

// One check line from text parts; {code: '...'} parts show as code.
function checkItem(parts, warning = false) {
  const item = document.createElement('li');
  if (warning) item.className = 'check--warning';
  for (const part of parts) {
    if (typeof part === 'string') { item.append(part); continue; }
    const code = document.createElement('code');
    code.textContent = part.code;
    item.appendChild(code);
  }
  return item;
}

// "Check before you run": short lines for the data folder, resource problems, and other notes.
function renderReviewChecks(exportIssues = []) {
  const list = document.getElementById('reviewChecks');
  list.replaceChildren();
  if (!configuration.config) return;
  const dir = configuration.get(['data', 'data_dir']);
  const data = ['Data folder: ', {code: String(dir)}, '. With config.json saved in ', {code: 'config/'},
    ', this is the repository\'s ', {code: 'data/'}, ' folder. If your data is somewhere else, change ',
    {code: 'data_dir'}, ' in config.json.'];
  if (dataDirReplaced && dir === dataDirReplaced.to) data.push(' (The example used a server path, which was replaced.)');
  list.appendChild(checkItem(data));
  for (const {label, step, text} of Object.values(resourceProblems())) {
    list.appendChild(checkItem([`${label} (${step} step): ${text}`], true));
  }
  for (const message of new Set([...sourceWarnings, ...exportIssues].map(issueText))) {
    list.appendChild(checkItem([message], true));
  }
}

function renderReview() {
  renderChangeTable('reviewChanges', configDifferences(configuration.original, configuration.config));
  renderReviewChecks();
}

function draftValidationErrors() {
  const errors = [];
  for (const input of document.querySelectorAll('input[data-edited], select[data-edited]')) {
    if (!input.disabled && !input.validity.valid) errors.push(`${input.getAttribute('aria-label') || input.id}: ${input.validationMessage}`);
  }
  return [...new Set(errors)];
}

function invalidateReview() {
  ++reviewRequest;
  // Any edit after an export means the downloaded file is out of date.
  const review = STEPS.findIndex(step => step.id === 'review');
  if (completedSteps.delete(review)) renderStepProgress();
  document.getElementById('btnExport').disabled = !configuration.config;
  fillReviewList('reviewErrors', []);
  renderReviewChecks();  // Checks follow the current values.
}

function setupReview() {
  configuration.subscribe(invalidateReview);
  configuration.subscribe(updateResourceHints);
}

async function exportConfig() {
  const request = ++reviewRequest;
  const button = document.getElementById('btnExport');
  button.disabled = true;
  try {
    if (!validateStep(currentStep)) return;
    if (STEPS[currentStep].id !== 'review') {
      goToStep(STEPS.findIndex(step => step.id === 'review'));
      return;
    }
    const errors = draftValidationErrors();
    fillReviewList('reviewErrors', errors);
    if (errors.length) return;
    const formData = collectFormData(), fingerprint = JSON.stringify(formData);
    const resp = await fetch('/api/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(formData),
    });
    const config = await resp.json();
    if (request !== reviewRequest || fingerprint !== JSON.stringify(configuration.config)) return;
    if (!resp.ok) throw new Error(config.detail || 'Configuration could not be exported.');
    // Export issues (for example other absolute paths) join the checks, without duplicates.
    renderReviewChecks(JSON.parse(resp.headers.get('X-Config-Issues') || '[]'));

    // Download as file
    const blob = new Blob([JSON.stringify(config, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'config.json';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    completedSteps.add(currentStep);
    renderStepProgress();
  } catch (err) {
    if (request !== reviewRequest) return;
    console.error('Export failed:', err);
    fillReviewList('reviewErrors', [`Export failed: ${err.message}`]);
  } finally {
    if (request === reviewRequest) button.disabled = !configuration.config;
  }
}

// ==========================================================================
// Utilities
// ==========================================================================

function formatNumber(n) {
  if (n == null) return '0';
  return n.toLocaleString('en-US');
}

// ==========================================================================
// Init
// ==========================================================================

// The sticky step bar sits under the sticky header; both heights change with the window width.
function updateStickyOffsets() {
  const root = document.documentElement.style;
  root.setProperty('--header-height', `${document.querySelector('.app-header')?.offsetHeight || 0}px`);
  root.setProperty('--steps-height', `${document.getElementById('stepProgress')?.offsetHeight || 0}px`);
}

document.addEventListener('DOMContentLoaded', () => {
  renderStepProgress();
  updateStickyOffsets();
  window.addEventListener('resize', updateStickyOffsets);
  setupNavigation();
  if (typeof L !== 'undefined') initMap();
  else document.getElementById('mapMessage').textContent = 'Map unavailable. You can still remove selected counties and edit settings.';
  setupSurveys();
  setupModes();
  setupTransit();
  setupDemand();
  buildDurationTable();
  setupSimulation();
  setupSliders();
  setupCollapsibles();
  setupInfoPopups();
  setupConfigurationBindings();
  setupReview();
  setupConfiguration();
  loadHostInfo();

  // Export button
  document.getElementById('btnExport').addEventListener('click', exportConfig);
});
