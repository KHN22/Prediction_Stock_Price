const byId = id => document.getElementById(id);
const featureNames = {
  A_price_only: 'ราคาและตัวแปรเทคนิค',
  B_price_macro: 'ราคาและ Macro',
  C_price_macro_financials: 'ราคา, Macro และงบการเงิน',
};
const baselineNames = { zero: 'ราคาคงที่', historical_mean: 'ค่าเฉลี่ยย้อนหลัง', momentum_21d: 'โมเมนตัม 21 วัน' };
const monthNames = { '1m': '1 เดือน', '3m': '3 เดือน', '6m': '6 เดือน' };
const money = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' });
const dateFormat = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
const shortDate = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' });
const compact = new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 2 });
const dateText = value => dateFormat.format(new Date(value));
const pct = value => (value > 0 ? '+' : '') + (value * 100).toFixed(2) + '%';
const closeText = (value, currency) => currency === 'USD' ? money.format(value) :
  new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(value);
const text = (id, value) => { byId(id).textContent = value; };
const option = (value, label) => new Option(label, value);
const signClass = value => value < 0 ? 'down' : value > 0 ? 'up' : '';
const selected = { id: 'mu', horizon: '1m', view: 'forecast', feature: '' };
const loaded = new Map();
const models = new Map();
const chart = byId('chart');

async function fetchJSON(url, options) {
  const response = await fetch(url, options);
  const result = await response.json();
  if (!response.ok) throw new Error(result.error);
  return result;
}

async function selectModel(id) {
  selected.id = id;
  if (!loaded.has(id)) {
    const data = await fetchJSON('/api/snapshot/' + id);
    loaded.set(id, { data, source: data.updatedAt ? 'ชุดข้อมูลอัปเดตในเครื่อง' : 'ชุดข้อมูลในโปรเจกต์' });
  }
  if (selected.id === id) render();
}

function render() {
  const entry = loaded.get(selected.id);
  if (!entry) return;
  const { data, source } = entry;
  const model = models.get(selected.id);
  const format = value => closeText(value, model.currency);
  const features = [...new Set(data.results.map(row => row.feature_set))].sort();
  if (!features.includes(selected.feature)) selected.feature = features.at(-1);
  const rows = data.results.filter(row => row.feature_set === selected.feature)
    .sort((a, b) => a.sessions - b.sessions);
  if (!rows.some(row => row.horizon === selected.horizon)) selected.horizon = rows[0].horizon;
  const row = rows.find(item => item.horizon === selected.horizon);
  const last = data.history.at(-1);
  const backtest = selected.view === 'backtest';

  text('company', model.company);
  text('exchange', model.exchange + ' / ' + model.symbol);
  text('version', model.symbol + ' ' + model.version);
  text('source', source);
  text('last-close', format(last[1]));
  text('date', 'ข้อมูล ณ ' + dateText(data.asOf));
  const inputs = data.inputs ?? {};
  const financials = inputs.financialsAvailable ? 'งบใช้ได้ตั้งแต่ ' + dateText(inputs.financialsAvailable) : '';
  const macro = inputs.macroAvailable ? 'Macro ใช้ได้ตั้งแต่ ' + dateText(inputs.macroAvailable) : '';
  const pending = inputs.financialsImported > data.asOf ?
    'มีงบลงวันที่ ' + dateText(inputs.financialsImported) + ' หลังวันราคาปิดล่าสุด' : '';
  text('input-dates', [financials, macro, pending].filter(Boolean).join(' · ') ||
    (data.files.length === 1 ? 'รอบนี้ใช้เฉพาะข้อมูลราคา' : 'รันโมเดลอีกครั้งเพื่อดูวันที่ของข้อมูลแต่ละชุด'));
  const metric = (name, value) => value == null ? '' : name + ' ' + model.currency + ' ' + compact.format(value);
  text('input-values', [metric('รายได้', inputs.revenue), metric('FCF ตามสูตรโมเดล', inputs.fcf)].filter(Boolean).join(' · '));
  text('price-caption', 'ราคาคาดการณ์ · ' + monthNames[row.horizon]);
  text('forecast-price', format(row.forecast));
  text('sessions', row.sessions + ' วันซื้อขาย · ' + row.best_model);
  text('return', pct(row.return));
  byId('return').className = signClass(row.return);
  text('rmse', row.model_RMSE_log_return.toFixed(3));
  text('baseline-metric', 'Baseline ' + row.best_baseline_RMSE_log_return.toFixed(3) + ' · log return');
  text('chart-kicker', backtest ? 'HELD-OUT TEST' : 'PRICE OUTLOOK');
  text('graph-title', backtest ? 'ผลทดสอบย้อนหลัง' : 'แนวโน้มราคา');
  text('currency', model.currency + ' / SHARE');
  text('chart-period', backtest ? 'วันที่เป้าหมายในชุดทดสอบ' : 'ย้อนหลัง 90 วันซื้อขาย + จุดคาดการณ์');

  for (const button of document.querySelectorAll('[data-view]')) {
    button.setAttribute('aria-pressed', String(button.dataset.view === selected.view));
  }
  for (const button of document.querySelectorAll('[data-horizon]')) {
    button.disabled = !rows.some(item => item.horizon === button.dataset.horizon);
    button.setAttribute('aria-pressed', String(button.dataset.horizon === row.horizon));
  }
  byId('feature').replaceChildren(...features.map(key => option(key, featureNames[key] || key)));
  byId('feature').value = selected.feature;
  byId('outlooks').replaceChildren(...rows.map(item => {
    const button = document.createElement('button');
    button.className = 'outlook-row';
    button.setAttribute('aria-pressed', String(item.horizon === selected.horizon));
    for (const [value, className] of [[monthNames[item.horizon], ''], [format(item.forecast), ''], [pct(item.return), signClass(item.return)]]) {
      const span = document.createElement('span');
      span.textContent = value;
      span.className = className;
      button.append(span);
    }
    button.onclick = () => {
      selected.horizon = item.horizon;
      render();
      byId('outlooks').children[rows.indexOf(item)].focus();
    };
    return button;
  }));

  const assessment = byId('assessment');
  const beats = row.beats_best_baseline_RMSE;
  assessment.classList.toggle('good', beats);
  const heading = document.createElement('strong');
  heading.textContent = beats ? 'RMSE ต่ำกว่า Baseline' : 'โมเดลยังไม่ชนะ Baseline';
  assessment.replaceChildren(heading, document.createTextNode(
    (baselineNames[row.best_baseline] || row.best_baseline) + ' · ทายทิศทางถูก ' +
    (row.model_directional_accuracy * 100).toFixed(1) + '% จาก ' + row.n_test + ' จุดทดสอบ'
  ));

  drawChart(data.history.slice(-90), row, format, backtest);
}

const svgNS = 'http://www.w3.org/2000/svg';
function svgNode(tag, attributes = {}, label) {
  const element = document.createElementNS(svgNS, tag);
  for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, value);
  if (label) element.textContent = label;
  return element;
}

function drawChart(history, row, format, backtest) {
  const width = chart.clientWidth;
  const height = chart.clientHeight;
  if (!width || !height) return;
  const left = width < 450 ? 49 : 63;
  const right = width - 16;
  const top = 16;
  const bottom = height - 30;
  const series = backtest ? row.test : history;
  const last = history.at(-1);
  const end = backtest ? series.length - 1 : history.length - 1 + row.sessions;
  const values = series.flatMap(point => point.slice(1));
  if (!backtest) values.push(row.forecast);
  const low = Math.min(...values);
  const high = Math.max(...values);
  const rawStep = Math.max((high - low) / 4, Math.abs(high) * .00001, .01);
  const power = 10 ** Math.floor(Math.log10(rawStep));
  const step = [1, 2, 2.5, 5, 10].find(multiplier => multiplier * power >= rawStep) * power;
  const floor = Math.max(0, Math.floor((low - step * .14) / step) * step);
  const ceiling = Math.ceil((high + step * .14) / step) * step;
  const x = index => left + (right - left) * index / end;
  const y = value => bottom - (bottom - top) * (value - floor) / (ceiling - floor);
  const svg = svgNode('svg', { viewBox: '0 0 ' + width + ' ' + height, role: 'img',
    'aria-label': backtest ? 'กราฟราคาจริงเทียบโมเดลและ Baseline ในชุดทดสอบ' : 'กราฟราคาปิดและจุดคาดการณ์ ' + format(row.forecast) });
  const line = (x1, y1, x2, y2, stroke, extra = {}) => svgNode('line', { x1, y1, x2, y2, stroke, ...extra });
  const cutoff = x(history.length - 1);
  if (!backtest) svg.append(svgNode('rect', { x: cutoff, y: top, width: right - cutoff, height: bottom - top, fill: '#edf8f5' }));
  for (let value = floor; value <= ceiling + step * .001; value += step) {
    const pos = y(value);
    const label = value.toLocaleString('en-US', { maximumFractionDigits: step < 1 ? 2 : 0 });
    svg.append(line(left, pos, right, pos, '#e5edf1'),
      svgNode('text', { x: left - 9, y: pos + 4, 'text-anchor': 'end', class: 'axis' }, label));
  }

  const path = (points, color, dash, strokeWidth = 2) => {
    const d = points.map(([index, value], i) => (i ? 'L' : 'M') + x(index).toFixed(2) + ',' + y(value).toFixed(2)).join(' ');
    svg.append(svgNode('path', { d, fill: 'none', stroke: color, 'stroke-width': strokeWidth,
      'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'stroke-dasharray': dash || '' }));
  };
  const navy = '#263e53', green = '#008b78', ochre = '#a97540';
  const prices = series.map((point, i) => [i, point[1]]);
  if (backtest) {
    path(series.map((point, i) => [i, point[3]]), ochre, '2 4');
    path(series.map((point, i) => [i, point[2]]), green, '6 4');
  } else {
    const fillPath = prices.map(([i, value]) => 'L' + x(i) + ',' + y(value)).join(' ');
    svg.append(svgNode('path', { d: 'M' + left + ',' + bottom + ' ' + fillPath + ' L' + cutoff + ',' + bottom + ' Z', fill: '#f0f4f7' }));
    svg.append(line(cutoff, top, cutoff, bottom, '#79aa9e', { 'stroke-dasharray': '3 4' }));
    path([[history.length - 1, last[1]], [end, row.forecast]], green, '7 5');
    svg.append(svgNode('circle', { cx: right, cy: y(row.forecast), r: 5, fill: green, stroke: 'white', 'stroke-width': 2 }));
  }
  path(prices, navy, '', 2.25);

  const tickCount = width < 440 ? 2 : backtest ? 5 : 4;
  for (let i = 0; i < tickCount; i++) {
    const index = Math.round((series.length - 1) * i / (tickCount - 1));
    if (!backtest && i === tickCount - 1 && cutoff > right - 55) continue;
    svg.append(svgNode('text', { x: x(index), y: height - 7, class: 'axis',
      'text-anchor': i === 0 ? 'start' : i === tickCount - 1 ? 'end' : 'middle',
    }, shortDate.format(new Date(series[index][0]))));
  }
  if (!backtest) svg.append(svgNode('text', { x: right, y: height - 7, class: 'axis future', 'text-anchor': 'end' }, '+' + row.sessions + ' วันซื้อขาย'));

  const cursor = line(left, top, left, bottom, '#8ea2ac', { visibility: 'hidden', 'stroke-dasharray': '3 3' });
  svg.append(cursor);
  const tip = document.createElement('div');
  tip.className = 'tooltip';
  tip.hidden = true;
  svg.addEventListener('pointermove', event => {
    const relative = event.clientX - svg.getBoundingClientRect().left;
    const i = Math.max(0, Math.min(series.length - 1, Math.round((relative - left) * end / (right - left))));
    const point = series[i];
    const future = !backtest && relative > cutoff + 7;
    const pos = future ? right : x(i);
    const label = future ? '+' + row.sessions + ' วันซื้อขาย\nคาดการณ์ ' + format(row.forecast) :
      dateText(point[0]) + '\nราคาจริง ' + format(point[1]) +
      (backtest ? '\nโมเดล ' + format(point[2]) + '\nBaseline ' + format(point[3]) : '');
    cursor.setAttribute('x1', pos);
    cursor.setAttribute('x2', pos);
    cursor.setAttribute('visibility', 'visible');
    tip.textContent = label;
    tip.hidden = false;
    tip.style.top = '16px';
    tip.style.left = Math.max(0, Math.min(width - tip.offsetWidth, pos + 9)) + 'px';
  });
  svg.addEventListener('pointerleave', () => {
    cursor.setAttribute('visibility', 'hidden');
    tip.hidden = true;
  });
  chart.replaceChildren(svg, tip);

  const labels = [['', 'ราคาจริง'], ['predicted', backtest ? 'โมเดล' : 'จุดคาดการณ์ปลายช่วง']];
  if (backtest) labels.push(['baseline', 'Baseline · ' + (baselineNames[row.best_baseline] || row.best_baseline)]);
  const items = labels.map(([style, label]) => {
    const span = document.createElement('span');
    const swatch = document.createElement('i');
    swatch.className = 'swatch ' + style;
    span.append(swatch, label);
    return span;
  });
  byId('legend').replaceChildren(...items);
}

function showNotice(error) {
  text('notice', error.message);
  byId('notice').hidden = false;
}

for (const button of document.querySelectorAll('[data-view], [data-horizon]')) {
  button.addEventListener('click', () => {
    Object.assign(selected, button.dataset);
    render();
  });
}
byId('feature').onchange = event => { selected.feature = event.target.value; render(); };
byId('model').onchange = event => selectModel(event.target.value).catch(showNotice);
let previousWidth = 0;
let previousHeight = 0;
new ResizeObserver(() => {
  if (previousWidth === chart.clientWidth && previousHeight === chart.clientHeight) return;
  previousWidth = chart.clientWidth;
  previousHeight = chart.clientHeight;
  render();
}).observe(chart);

const dialog = byId('upload-dialog');
const fileInput = byId('files');
const importMode = byId('import-mode');
function configureImport() {
  const model = models.get(selected.id);
  const merge = importMode.value === 'update';
  const names = merge ? [...model.files, ...model.updateFiles] : model.files;
  text('import-help', merge
    ? 'เลือกเฉพาะไฟล์ที่มีข้อมูลเพิ่มหรือแก้ไข เช่น แถวราคาปิดรายวันหรือข้อมูลงบรายไตรมาส ใช้หน่วย USD เต็มสำหรับงบ'
    : 'เลือกไฟล์ราคาย้อนหลังหนึ่งไฟล์สำหรับตัวแปรเทคนิค หรือเลือกครบทั้ง 6 ไฟล์เพื่อรันชุดใหม่');
  text('upload-message', '');
  byId('templates').hidden = !merge;
  byId('file-list').replaceChildren(...names.map(name => {
    const item = document.createElement('li');
    item.textContent = name;
    return item;
  }));
}
importMode.onchange = () => { fileInput.value = ''; configureImport(); };
byId('upload').onclick = () => {
  const model = models.get(selected.id);
  if (!model) return;
  text('upload-symbol', model.symbol);
  importMode.options[0].disabled = !model.updateFiles;
  importMode.value = model.updateFiles ? 'update' : 'forecast';
  fileInput.value = '';
  configureImport();
  dialog.showModal();
};
byId('cancel').onclick = () => dialog.close();
dialog.addEventListener('cancel', event => { if (byId('run').disabled) event.preventDefault(); });
byId('upload-form').onsubmit = async event => {
  event.preventDefault();
  const id = selected.id;
  const model = models.get(id);
  const merge = importMode.value === 'update';
  const names = merge ? [...model.files, ...model.updateFiles] : model.files;
  const files = [...fileInput.files];
  const unique = new Set(files.map(file => file.name));
  if (!unique.size || (!merge && !(unique.size === names.length || (unique.size === 1 && unique.has(names[0])))) ||
      files.length !== unique.size || [...unique].some(name => !names.includes(name))) {
    text('upload-message', merge ? 'กรุณาเลือกไฟล์ชื่อเดียวกับแม่แบบหรือรายชื่อไฟล์ที่รองรับ' :
      'กรุณาเลือกไฟล์ราคาเพียงไฟล์เดียว หรือเลือกครบตามรายชื่อด้านบน');
    return;
  }
  if (files.reduce((total, file) => total + file.size, 0) > 11 * 1024 * 1024) {
    text('upload-message', 'กรุณาเลือกไฟล์รวมไม่เกิน 11 MB');
    return;
  }
  const controls = [fileInput, importMode, byId('run'), byId('cancel')];
  controls.forEach(control => { control.disabled = true; });
  text('upload-message', 'กำลังรัน Walk-forward และสร้างผลคาดการณ์ อาจใช้เวลาสักครู่…');
  try {
    const input = Object.fromEntries(await Promise.all(files.map(async file => [file.name, await file.text()])));
    const data = await fetchJSON('/api/' + (merge ? 'update' : 'forecast') + '/' + id, { method: 'POST',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input) });
    loaded.set(id, { data, source: merge ? 'ชุดข้อมูลอัปเดตในเครื่อง' : 'CSV ที่อัปโหลด · ' + files.length + ' ไฟล์' });
    selected.feature = '';
    byId('notice').hidden = true;
    text('upload-message', '');
    fileInput.value = '';
    render();
    dialog.close();
  } catch (error) {
    text('upload-message', error.message);
  } finally {
    controls.forEach(control => { control.disabled = false; });
  }
};

function setPresentation(active) {
  document.body.classList.toggle('presenting', active);
  byId('present').setAttribute('aria-pressed', String(active));
  byId('present').querySelector('span').textContent = active ? 'Exit Present' : 'Present';
}
byId('present').onclick = async () => {
  const active = !document.body.classList.contains('presenting');
  setPresentation(active);
  if (active && document.documentElement.requestFullscreen) {
    await document.documentElement.requestFullscreen().catch(() => {});
  } else if (!active && document.fullscreenElement) {
    await document.exitFullscreen();
  }
};
document.addEventListener('fullscreenchange', () => { if (!document.fullscreenElement) setPresentation(false); });
document.addEventListener('keydown', event => { if (event.key === 'Escape' && !document.fullscreenElement) setPresentation(false); });
setPresentation(false);

try {
  for (const model of await fetchJSON('/api/models')) models.set(model.id, model);
  byId('model').replaceChildren(...[...models.values()].map(model => option(model.id, model.symbol)));
  await selectModel(byId('model').value);
} catch (error) {
  showNotice(error);
}
