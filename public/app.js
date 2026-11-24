const byId = id => document.getElementById(id);
let language = 'th';
try { if (localStorage.getItem('model411-language') === 'en') language = 'en'; } catch {}
const t = (thai, english) => language === 'en' ? english : thai;
const staticLabels = [...document.querySelectorAll('[data-en]')].map(node => [node, node.textContent]);
const accessibleLabels = [...document.querySelectorAll('[data-en-label]')].map(node => [node, node.getAttribute('aria-label')]);

function applyLanguage() {
  document.documentElement.lang = language;
  for (const [node, thai] of staticLabels) node.textContent = t(thai, node.dataset.en);
  for (const [node, thai] of accessibleLabels) node.setAttribute('aria-label', t(thai, node.dataset.enLabel));
  const toggle = byId('language-toggle');
  toggle.lang = t('en', 'th');
  toggle.textContent = t('English', 'ไทย');
  toggle.setAttribute('aria-label', t('Switch to English', 'เปลี่ยนเป็นภาษาไทย'));
}

const featureNames = {
  A_price_only: ['ราคาและตัวแปรเทคนิค', 'Price and technical indicators'],
  B_price_macro: ['ราคาและ Macro', 'Price and macro indicators'],
  C_price_macro_financials: ['ราคา, Macro และงบการเงิน', 'Price, macro and financials'],
};
const baselineNames = { zero: ['ราคาคงที่', 'Unchanged price'], historical_mean: ['ค่าเฉลี่ยย้อนหลัง', 'Historical mean'], momentum_21d: ['โมเมนตัม 21 วัน', '21-day momentum'] };
const monthNames = { '1m': ['1 เดือน', '1 month'], '3m': ['3 เดือน', '3 months'], '6m': ['6 เดือน', '6 months'] };
const horizonRoles = {
  '1m': ['มุมมองเสริมระยะสั้น', 'Short-term context'],
  '3m': ['มุมมองหลัก', 'Primary outlook'],
  '6m': ['มุมมองเสริม · อยู่ระหว่างทดสอบ', 'Supporting outlook · Under evaluation'],
};
function horizonRole(horizon, feature) {
  if (horizon === '3m' && feature !== 'B_price_macro') {
    return t('ชุดตัวแปรเปรียบเทียบ', 'Alternative feature set');
  }
  return translatedName(horizonRoles, horizon);
}
const translatedName = (names, key) => names[key] ? t(...names[key]) : key;
const money = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' });
const dateFormats = {};
for (const [lang, locale] of [['th', 'th-TH-u-ca-gregory'], ['en', 'en-GB']]) {
  const options = { day: 'numeric', month: 'short', timeZone: 'UTC' };
  dateFormats[lang] = {
    short: new Intl.DateTimeFormat(locale, options),
    full: new Intl.DateTimeFormat(locale, { ...options, year: 'numeric' }),
  };
}
const compact = new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 2 });
const dateText = value => dateFormats[language].full.format(new Date(value));
const pct = value => (value > 0 ? '+' : '') + (value * 100).toFixed(2) + '%';
const closeText = (value, currency) => currency === 'USD' ? money.format(value) :
  new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(value);
const text = (id, value) => { byId(id).textContent = value; };
const option = (value, label) => new Option(label, value);
const signClass = value => value < 0 ? 'down' : value > 0 ? 'up' : '';
const selected = { id: 'mu', horizon: '3m', view: 'forecast', feature: 'B_price_macro' };
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
    loaded.set(id, { data, source: () => data.updatedAt ? t('ชุดข้อมูลอัปเดตในเครื่อง', 'Updated local dataset') : t('ชุดข้อมูลในโปรเจกต์', 'Project dataset') });
  }
  if (selected.id === id) render();
}

const sourceLabels = new Map([
  ['Macro ใช้ค่าที่ FRED เผยแพร่ล่าสุดพร้อม lag ตามโมเดล ประวัติอาจถูกปรับย้อนหลัง · GDP ใช้หลังจบไตรมาสและเลื่อน 1 เดือน · EPS estimate และ surprise อาจขาด', ['Macro ใช้ค่าที่ FRED เผยแพร่ล่าสุดพร้อม lag ตามโมเดล ประวัติอาจถูกปรับย้อนหลัง · GDP ใช้หลังจบไตรมาสและเลื่อน 1 เดือน · EPS estimate และ surprise อาจขาด', 'Macro inputs use the latest FRED release with the model lag. Historical data may be revised. GDP is used one month after quarter end. EPS estimates and earnings surprises may be missing.']],
  ['CPI', ['ดัชนีราคาผู้บริโภค (CPI)', 'Consumer price index (CPI)']],
  ['Fed funds', ['อัตราดอกเบี้ยเฟด', 'Federal funds rate']],
  ['Unemployment', ['อัตราการว่างงาน', 'Unemployment rate']],
  ['Treasury 10Y', ['ผลตอบแทนพันธบัตรสหรัฐฯ 10 ปี', '10-year Treasury yield']],
  ['Real GDP', ['GDP ที่แท้จริง', 'Real GDP']],
  ['Index 1982–84=100', ['ดัชนี ฐาน 1982–84 = 100', 'Index (1982–84 = 100)']],
  ['Billions of chained 2017 USD, SAAR', ['พันล้านดอลลาร์สหรัฐ ณ ราคาปี 2017 แบบลูกโซ่ ปรับฤดูกาลและเทียบเป็นรายปี', 'Billions of chained 2017 USD, SAAR']],
  ['Yahoo Finance · adjusted daily OHLC', ['Yahoo Finance · ราคา OHLC รายวันที่ปรับแล้ว', 'Yahoo Finance · adjusted daily OHLC']],
]);
const sourceText = value => sourceLabels.has(value) ? t(...sourceLabels.get(value)) : value;

// Fixed forecast vintage: keep the evidence comparable when online data changes.
let showDownCalls = true;
function renderThesis() {
  const panel = byId('thesis');
  panel.hidden = selected.id !== 'mu' || selected.horizon !== '3m' || selected.feature !== 'B_price_macro';
  if (panel.hidden) return;
  const total = showDownCalls ? 25 : 239;
  const correct = showDownCalls ? 0 : 177;
  byId('thesis-down').setAttribute('aria-pressed', String(showDownCalls));
  byId('thesis-all').setAttribute('aria-pressed', String(!showDownCalls));
  text('thesis-count', t('ถูก ' + correct + ' จาก ' + total + ' ครั้ง', correct + ' correct out of ' + total));
  byId('thesis-dots').replaceChildren(...Array.from({length: total}, (_, i) => {
    const dot = document.createElement('i');
    if (i < correct) dot.className = 'correct';
    return dot;
  }));
  text('thesis-explain', showDownCalls
    ? t('วงกลมละ 1 ครั้งที่โมเดลทายลง ทั้ง 25 ครั้งราคาปลายช่วงสูงกว่าวันเริ่มต้น', 'Each dot is one down call. All 25 ended above their starting price.')
    : t('จุดทึบคือครั้งที่ทายถูก (74.1%) ส่วน Momentum 21 วันทายถูก 75.3% อย่างไรก็ตาม โมเดลมี RMSE ต่ำกว่า (0.4524 เทียบกับ 0.4972) จึงประมาณขนาดการเปลี่ยนแปลงได้ดีกว่าในชุดนี้', 'Filled dots are correct calls (74.1%). The 21-day momentum benchmark got 75.3% right. The model had lower RMSE (0.4524 vs 0.4972), so its return estimates had smaller squared errors overall.'));
}
for (const id of ['thesis-down','thesis-all']) {
  byId(id).onclick = () => { showDownCalls = id === 'thesis-down'; renderThesis(); };
}

function renderStatementThesis(data, horizon) {
  const f = data.financialReview;
  const panel = byId('statement-thesis');
  panel.hidden = selected.id !== 'mu' || !f?.lines || selected.feature !== 'C_price_macro_financials';
  if (panel.hidden) return;
  const labels = {
    revenue: ['รายได้','Revenue'], grossProfit: ['กำไรขั้นต้น','Gross profit'],
    operatingIncome: ['กำไรจากการดำเนินงาน','Operating income'], netIncome: ['กำไรสุทธิ','Net income'],
    assets: ['สินทรัพย์รวม','Total assets'], liabilities: ['หนี้สินรวม','Total liabilities'],
    operatingCash: ['กระแสเงินสดจากการดำเนินงาน','Operating cash flow'],
  };
  const ratio = (a, b, period) => {
    const numerator = f.lines[a]?.[period];
    const denominator = f.lines[b]?.[period];
    return Number.isFinite(numerator) && denominator > 0 ? (100 * numerator / denominator).toFixed(1) + '%' : '—';
  };
  const change = (a, b) => ['previous','actual'].map(k => ratio(a,b,k)).join(' → ');
  text('statement-period', t('งวดสิ้นสุด ', 'Quarter ended ') + dateText(f.quarter) +
    t(' · โมเดลใช้งบตั้งแต่ ', ' · Available to the model from ') + dateText(f.release));
  text('statement-profit', t('อัตรากำไรขั้นต้น ', 'Gross margin ') + change('grossProfit','revenue') +
    t(' · อัตรากำไรสุทธิ ', ' · Net margin ') + change('netIncome','revenue'));
  text('statement-balance', t('หนี้สินต่อสินทรัพย์ ', 'Liabilities as a share of assets ') + change('liabilities','assets') +
    t(' สัดส่วนที่สูงขึ้นหมายถึงภาระผูกพันต่อสินทรัพย์ที่มากขึ้น ควรอ่านคู่กับสภาพคล่องและกำหนดชำระ', '. A rising share means more claims against assets. Check liquidity and payment schedules alongside it.'));
  const price = data.results.find(r => r.horizon === horizon && r.feature_set === 'B_price_macro');
  const statements = data.results.find(r => r.horizon === horizon && r.feature_set === selected.feature);
  text('statement-rmse', price && statements ? t('ทดสอบราคาย้อนหลัง · RMSE ชุดราคา + Macro ', 'Return backtest · RMSE for price + macro ') +
    price.model_RMSE_log_return.toFixed(4) + t(' เทียบกับชุดเพิ่มงบ ', ' vs. with statements ') +
    statements.model_RMSE_log_return.toFixed(4) + t(' (ต่ำกว่าดีกว่า)', ' (lower is better)') : '');
  const billions = v => Number.isFinite(v) ? (v / 1e9).toFixed(2) : '—';
  byId('statement-rows').replaceChildren(...Object.entries(labels).map(([key, label]) => {
    const line = f.lines[key] || {};
    const tr = document.createElement('tr');
    const rule = line.rule === 'trend' ? t('ต่อแนวโน้มครึ่งหนึ่ง','Half trend') : line.rule === 'carry' ? t('คงค่าล่าสุด','Last value') : '—';
    for (const value of [t(...label),billions(line.previous),billions(line.actual),billions(line.estimate),rule,billions(line.testMAE),line.testQuarters ?? '—']) {
      const cell = document.createElement('td');
      cell.textContent = value;
      tr.append(cell);
    }
    return tr;
  }));
}

function render() {
  const entry = loaded.get(selected.id);
  if (!entry) return;
  const { data, source } = entry;
  const model = models.get(selected.id);
  const format = value => closeText(value, model.currency);
  const features = [...new Set(data.results.map(row => row.feature_set))].sort();
  if (!features.includes(selected.feature)) {
    selected.feature = selected.id === 'mu' && features.includes('B_price_macro') ? 'B_price_macro' : features.at(-1);
  }
  const rows = data.results.filter(row => row.feature_set === selected.feature)
    .sort((a, b) => a.sessions - b.sessions);
  if (!rows.some(row => row.horizon === selected.horizon)) selected.horizon = rows[0].horizon;
  const row = rows.find(item => item.horizon === selected.horizon);
  const last = data.history.at(-1);
  const backtest = selected.view === 'backtest';

  text('company', model.company);
  text('exchange', model.exchange + ' / ' + model.symbol);
  text('version', model.symbol + ' ' + model.version);
  text('source', data.sources ? [sourceText(data.sources.prices), data.sources.financials, data.sources.macro ? 'FRED Macro' : ''].filter(Boolean).join(' / ') : source());
  text('last-close', format(last[1]));
  text('date', t('ข้อมูล ณ ', 'As of ') + dateText(data.asOf));
  const macroSeries = data.sources?.macroSeries ?? [];
  byId('macro-details').hidden = !macroSeries.length;
  byId('macro-rows').replaceChildren(...macroSeries.map(item => {
    const tr = document.createElement('tr');
    const label = document.createElement('td');
    const link = document.createElement('a');
    link.href = 'https://fred.stlouisfed.org/series/' + encodeURIComponent(item.series);
    link.textContent = sourceText(item.label);
    label.append(link);
    tr.append(label);
    for (const value of [dateText(item.observationDate),
      item.latestValue.toLocaleString('en-US', {maximumFractionDigits: 3}) + ' ' + sourceText(item.units),
      item.usedValue == null ? '—' : item.usedValue.toLocaleString('en-US', {maximumFractionDigits: 3})]) {
      const cell = document.createElement('td');
      cell.textContent = value;
      tr.append(cell);
    }
    return tr;
  }));
  const inputs = data.inputs ?? {};
  const financials = inputs.financialsAvailable ? t('งบใช้ได้ตั้งแต่ ', 'Financial statements available from ') + dateText(inputs.financialsAvailable) : '';
  const macro = inputs.macroAvailable ? t('Macro ตาม lag ณ ', 'Lagged macro inputs as of ') + dateText(inputs.macroAvailable) : '';
  const pending = inputs.financialsImported > data.asOf ?
    t('มีงบลงวันที่ ', 'Financial statements dated ') + dateText(inputs.financialsImported) + t(' หลังวันราคาปิดล่าสุด', ' fall after the latest close') : '';
  text('input-dates', [financials, macro, pending, sourceText(data.sources?.note)].filter(Boolean).join(' · ') ||
    (data.files.length === 1 ? t('รอบนี้ใช้เฉพาะข้อมูลราคา', 'This run uses price data only') : t('รันโมเดลอีกครั้งเพื่อดูวันที่ของข้อมูลแต่ละชุด', 'Run the model again to see the dates of the inputs')));
  const metric = (name, value) => value == null ? '' : name + ' ' + model.currency + ' ' + compact.format(value);
  text('input-values', [metric(t('รายได้', 'Revenue'), inputs.revenue), metric(t('กำไรสุทธิ', 'Net income'), inputs.netIncome)].filter(Boolean).join(' · '));
  const muView = selected.id === 'mu';
  const role = muView ? horizonRole(row.horizon, selected.feature) : '';
  text('horizon-role', role);
  byId('horizon-role').hidden = !role;
  text('price-caption', t('ราคาคาดการณ์ · ', 'Forecast price · ') + translatedName(monthNames, row.horizon));
  text('forecast-price', format(row.forecast));
  text('sessions', row.sessions + t(' วันซื้อขาย · ', ' trading sessions · ') + (row.best_model === 'RandomForest' ? 'Random Forest' : row.best_model));
  text('return', pct(row.return));
  byId('return').className = signClass(row.return);
  text('rmse', row.model_RMSE_log_return.toFixed(4));
  const benchmark = translatedName(baselineNames, row.best_baseline);
  text('baseline-metric', benchmark + ' ' + row.best_baseline_RMSE_log_return.toFixed(4) + ' · log return');
  text('chart-kicker', backtest ? t('ชุดทดสอบ', 'HELD-OUT TEST') : t('คาดการณ์ราคา', 'PRICE OUTLOOK'));
  text('graph-title', backtest ? t('ผลทดสอบย้อนหลัง', 'Backtest results') : t('แนวโน้มราคา', 'Price outlook'));
  text('currency', model.currency + t(' / หุ้น', ' / SHARE'));
  text('chart-period', backtest ? t('วันที่เป้าหมายในชุดทดสอบ', 'Target dates in the test set') : t('ย้อนหลัง 90 วันซื้อขาย + จุดคาดการณ์', 'Last 90 trading sessions and forecast'));

  for (const button of document.querySelectorAll('[data-view]')) {
    button.setAttribute('aria-pressed', String(button.dataset.view === selected.view));
  }
  for (const button of document.querySelectorAll('[data-horizon]')) {
    button.disabled = !rows.some(item => item.horizon === button.dataset.horizon);
    button.setAttribute('aria-pressed', String(button.dataset.horizon === row.horizon));
  }
  byId('feature').replaceChildren(...features.map(key => option(key, translatedName(featureNames, key))));
  byId('feature').value = selected.feature;
  byId('outlooks').replaceChildren(...rows.map(item => {
    const button = document.createElement('button');
    button.className = 'outlook-row';
    button.setAttribute('aria-pressed', String(item.horizon === selected.horizon));
    for (const [value, className] of [[translatedName(monthNames, item.horizon), ''], [format(item.forecast), ''], [pct(item.return), signClass(item.return)]]) {
      const span = document.createElement('span');
      span.textContent = value;
      span.className = className;
      button.append(span);
    }
    if (muView) {
      const roleLabel = document.createElement('small');
      roleLabel.className = 'outlook-role';
      roleLabel.textContent = horizonRole(item.horizon, selected.feature);
      button.firstElementChild.append(roleLabel);
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
  heading.textContent = (beats ? t('RMSE ต่ำกว่า ', 'Lower RMSE than ') : t('RMSE ไม่ต่ำกว่า ', 'RMSE at or above ')) + benchmark;
  assessment.replaceChildren(heading, document.createTextNode(
    t('ทายทิศทางถูก · โมเดล ', 'Directional accuracy · Model ') +
    (row.model_directional_accuracy * 100).toFixed(1) + '% / ' + translatedName(baselineNames, row.best_baseline) +
    (Number.isFinite(row.baseline_directional_accuracy) ? ' ' + (100 * row.baseline_directional_accuracy).toFixed(1) + '%' : '') +
    t(' จาก ', ' across ') + row.n_test + t(' จุดทดสอบ', ' test observations')
  ));

  renderThesis();
  renderStatementThesis(data, row.horizon);
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
    'aria-label': backtest ? t('กราฟราคาจริงเทียบโมเดลและ Baseline ในชุดทดสอบ', 'Actual, model and baseline prices in the test set') : t('กราฟราคาปิดและจุดคาดการณ์ ', 'Closing prices and forecast of ') + format(row.forecast) });
  const line = (x1, y1, x2, y2, stroke, extra = {}) => svgNode('line', { x1, y1, x2, y2, stroke, ...extra });
  const cutoff = x(history.length - 1);
  if (!backtest) svg.append(svgNode('rect', { x: cutoff, y: top, width: right - cutoff, height: bottom - top, fill: 'var(--chart-future)' }));
  for (let value = floor; value <= ceiling + step * .001; value += step) {
    const pos = y(value);
    const label = value.toLocaleString('en-US', { maximumFractionDigits: step < 1 ? 2 : 0 });
    svg.append(line(left, pos, right, pos, 'var(--chart-grid)'),
      svgNode('text', { x: left - 9, y: pos + 4, 'text-anchor': 'end', class: 'axis' }, label));
  }

  const path = (points, color, dash, strokeWidth = 2) => {
    const d = points.map(([index, value], i) => (i ? 'L' : 'M') + x(index).toFixed(2) + ',' + y(value).toFixed(2)).join(' ');
    svg.append(svgNode('path', { d, fill: 'none', stroke: color, 'stroke-width': strokeWidth,
      'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'stroke-dasharray': dash || '' }));
  };
  const navy = 'var(--chart-line)', green = 'var(--chart-predicted)', ochre = 'var(--chart-baseline)';
  const prices = series.map((point, i) => [i, point[1]]);
  if (backtest) {
    path(series.map((point, i) => [i, point[3]]), ochre, '2 4');
    path(series.map((point, i) => [i, point[2]]), green, '6 4');
  } else {
    const fillPath = prices.map(([i, value]) => 'L' + x(i) + ',' + y(value)).join(' ');
    svg.append(svgNode('path', { d: 'M' + left + ',' + bottom + ' ' + fillPath + ' L' + cutoff + ',' + bottom + ' Z', fill: 'var(--chart-area)' }));
    svg.append(line(cutoff, top, cutoff, bottom, 'var(--chart-cutoff)', { 'stroke-dasharray': '3 4' }));
    path([[history.length - 1, last[1]], [end, row.forecast]], green, '7 5');
    svg.append(svgNode('circle', { cx: right, cy: y(row.forecast), r: 5, fill: green, stroke: 'var(--surface)', 'stroke-width': 2 }));
  }
  path(prices, navy, '', 2.25);

  const tickCount = width < 440 ? 2 : backtest ? 5 : 4;
  for (let i = 0; i < tickCount; i++) {
    const index = Math.round((series.length - 1) * i / (tickCount - 1));
    if (!backtest && i === tickCount - 1 && cutoff > right - 55) continue;
    svg.append(svgNode('text', { x: x(index), y: height - 7, class: 'axis',
      'text-anchor': i === 0 ? 'start' : i === tickCount - 1 ? 'end' : 'middle',
    }, dateFormats[language].short.format(new Date(series[index][0]))));
  }
  if (!backtest) svg.append(svgNode('text', { x: right, y: height - 7, class: 'axis future', 'text-anchor': 'end' }, '+' + row.sessions + t(' วันซื้อขาย', ' trading sessions')));

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
    const label = future ? '+' + row.sessions + t(' วันซื้อขาย\nคาดการณ์ ', ' trading sessions\nForecast ') + format(row.forecast) :
      dateText(point[0]) + t('\nราคาจริง ', '\nActual ') + format(point[1]) +
      (backtest ? t('\nโมเดล ', '\nModel ') + format(point[2]) + '\nBaseline ' + format(point[3]) : '');
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

  const labels = [['', t('ราคาจริง', 'Actual price')], ['predicted', backtest ? t('โมเดล', 'Model') : t('จุดคาดการณ์ปลายช่วง', 'Forecast at horizon end')]];
  if (backtest) labels.push(['baseline', 'Baseline · ' + (translatedName(baselineNames, row.best_baseline))]);
  const items = labels.map(([style, label]) => {
    const span = document.createElement('span');
    const swatch = document.createElement('i');
    swatch.className = 'swatch ' + style;
    span.append(swatch, label);
    return span;
  });
  byId('legend').replaceChildren(...items);
}

const errorTranslations = new Map([
  ['ไม่พบหน้าหรือโมเดล', 'Page or model not found.'],
  ['Origin ไม่ถูกต้อง', 'The request came from an invalid origin.'],
  ['ระบบกำลังประมวลผล กรุณารอสักครู่', 'A calculation is in progress. Please try again shortly.'],
  ['ระบบกำลังประมวลผลอีกชุด กรุณารอสักครู่', 'Another calculation is in progress. Please try again shortly.'],
  ['ต้องส่งข้อมูลรูปแบบ JSON', 'The request must contain JSON data.'],
  ['คำขอนี้ใช้กับเส้นทางนี้ไม่ได้', 'This operation is unavailable for the selected model.'],
  ['ขนาดไฟล์รวมเกิน 12 MB', 'The files exceed the 12 MB limit.'],
  ['ข้อมูลอัปโหลดไม่สมบูรณ์', 'The uploaded data is incomplete.'],
  ['ชื่อหรือเนื้อหาไฟล์ไม่ตรงกับโมเดล', 'The filenames or contents do not match this model.'],
  ['เกิดข้อผิดพลาดในการโหลดข้อมูลหรือรันโมเดล', 'The data could not be loaded or the model could not run.'],
  ['รันโมเดลไม่สำเร็จ กรุณาตรวจสอบ Python และข้อมูล', 'The model could not run. Check Python and the input data.'],
  ['ประวัติ Macro จาก FRED ไม่ครอบคลุมอย่างน้อย 60 เดือน', 'At least 60 months of FRED macro history are required.'],
  ['เลือก mu_prices.csv เพียงไฟล์เดียว หรือเลือกชุดข้อมูลครบทั้ง 6 ไฟล์', 'Select mu_prices.csv alone or all six files.'],
  ['ข้อมูลราคามีวันที่หรือค่า OHLCV ที่อ่านไม่ได้', 'Price data contains invalid dates or OHLCV values.'],
  ['ต้องมีราคาปิดรายวันอย่างน้อย 1,100 วันซื้อขายเพื่อประเมินครบทั้งสามช่วง', 'At least 1,100 daily closes are required to evaluate all three horizons.'],
  ['อ่านรายงานรายไตรมาสไม่ได้ กรุณาใช้รูปแบบ raw CSV ของโน้ตบุ๊ก', 'The quarterly report must use the original raw CSV format.'],
  ['รายงานรายไตรมาสต้องมี fiscalDateEnding', 'The quarterly report must include fiscalDateEnding.'],
  ['ไฟล์ Macro ต้องมีวันที่และตัวแปรเศรษฐกิจ', 'The macro file must include dates and economic indicators.'],
  ['โมเดลให้ราคานอกช่วงที่แสดงผลได้', 'The forecast price is outside the supported range.'],
  ['ข้อมูลที่ผ่านการตรวจสอบยังไม่พอสำหรับทุกช่วงคาดการณ์', 'There is insufficient valid data to evaluate all horizons.'],
  ['งบมีวันสิ้นไตรมาสซ้ำ หรือวันประกาศอยู่ก่อนวันสิ้นไตรมาส', 'Check for duplicate quarter ends or release dates before quarter end.'],
  ['ระบุตัวเลขของงบอย่างน้อยหนึ่งรายการ โดยใช้หน่วย USD เต็มและไม่มีเครื่องหมายคั่นหลัก', 'Enter at least one financial figure in whole US dollars without thousands separators.'],
  ['ไตรมาสใหม่ต้องมีรายได้และกระแสเงินสดจากการดำเนินงาน', 'New quarters require revenue and operating cash flow.'],
  ['Yahoo Finance ไม่ส่งข้อมูลราคา MU', 'Yahoo Finance returned no MU price data.'],
  ['สัญลักษณ์หรือสกุลเงินราคาจาก Yahoo ไม่ตรงกับ MU', 'The ticker or currency returned by Yahoo does not match MU.'],
  ['Yahoo ส่งข้อมูล OHLCV ที่ไม่ถูกต้อง', 'Yahoo returned invalid OHLCV data.'],
  ['ข้อมูลราคาจาก Yahoo มีประวัติไม่พอสำหรับโมเดล', 'Yahoo returned insufficient price history for the model.'],
  ['SEC ส่งข้อมูลบริษัทไม่ตรงกับ MU', 'The SEC company data does not match MU.'],
  ['SEC ส่งข้อมูลรายไตรมาสไม่ครบเพียงพอ', 'The SEC returned insufficient quarterly data.'],
]);
const variableErrors = [
  [/^ดึง Macro (.+) จาก FRED ไม่สำเร็จ กรุณาลองใหม่ภายหลัง$/, 'Could not fetch $1 from FRED. Please try again later.'],
  [/^ดึงข้อมูลจาก (.+) ไม่สำเร็จ กรุณาลองใหม่ภายหลัง$/, 'Could not fetch data from $1. Please try again later.'],
  [/^ตาราง FRED ไม่ตรงกับ (.+)$/, 'FRED table does not match $1.'],
  [/^ไม่พบข้อมูลในตาราง FRED (.+)$/, 'FRED table $1 contains no data.'],
  [/^รูปแบบ CSV ของ FRED (.+) ไม่ถูกต้อง$/, 'Invalid CSV format for FRED series $1.'],
  [/^FRED (.+) มีข้อมูลไม่เพียงพอหรือไม่ถูกต้อง$/, 'FRED series $1 contains insufficient or invalid data.'],
  [/^(.+): ไฟล์ว่างหรือขาดคอลัมน์ (.+)$/, '$1 is empty or missing columns $2.'],
  [/^(.+): พบวันที่ไม่ถูกต้อง$/, '$1 contains invalid dates.'],
  [/^(.+): ต้องมีข้อมูลและคอลัมน์ (.+)$/, '$1 must contain data and columns $2.'],
  [/^(.+): พบวันที่ซ้ำในไฟล์อัปเดต$/, '$1 contains duplicate dates.'],
  [/^(.+): ค่า OHLCV ไม่ถูกต้อง$/, '$1 contains invalid OHLCV values.'],
  [/^(.+): ต้องใช้รายงาน raw ตามรูปแบบเดิม หรือใช้ (.+)$/, 'Use the original raw report format for $1 or use $2.'],
  [/^(.+): กรุณาใช้หัวคอลัมน์จากไฟล์แม่แบบ$/, 'Use template column headers in $1.'],
  [/^(.+) อยู่ใกล้ไตรมาสเดิม (.+) ให้ใช้วันที่เดิมเมื่อต้องการแก้ไตรมาสเดียวกัน$/, '$1 is close to the existing quarter $2. Use the existing date to update that quarter.'],
  [/^(.+): วันประกาศเดิมคือ (.+) ให้ใช้วันเดิมเมื่ออัปเดตไตรมาสเดียวกัน$/, 'Use the original release date $2 when updating quarter $1.'],
  [/^(.+): (.+) อาจซ้ำกับไตรมาสเดิม ให้ใช้วันที่เดิมหรือรันชุด CSV ใหม่ทั้งหมด$/, '$1 contains a possible duplicate quarter ($2). Use the existing date or run a full new CSV dataset.'],
];
function errorText(error) {
  const message = error.message;
  if (message === 'Failed to fetch') return t('เชื่อมต่อเซิร์ฟเวอร์ไม่ได้ กรุณาลองอีกครั้ง', 'Could not reach the server. Please try again.');
  if (language === 'th') return message;
  if (errorTranslations.has(message)) return errorTranslations.get(message);
  for (const [pattern, english] of variableErrors) {
    if (pattern.test(message)) return message.replace(pattern, english);
  }
  return message;
}

let noticeMessage;
function setNotice(message) {
  noticeMessage = message;
  text('notice', message());
}

function showNotice(error) {
  setNotice(() => errorText(error));
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
    ? t('เลือกเฉพาะไฟล์ที่มีข้อมูลเพิ่มหรือแก้ไข เช่น แถวราคาปิดรายวันหรือข้อมูลงบรายไตรมาส ใช้หน่วย USD เต็มสำหรับงบ', 'Select only files with new or revised data, such as daily closes or quarterly financials. Enter financial amounts in whole US dollars.')
    : t('เลือกไฟล์ราคาย้อนหลังหนึ่งไฟล์สำหรับตัวแปรเทคนิค หรือเลือกครบทั้ง 6 ไฟล์เพื่อรันชุดใหม่', 'Select the historical price file for technical indicators, or all six files to run the full dataset.'));
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
    text('upload-message', merge ? t('กรุณาเลือกไฟล์ชื่อเดียวกับแม่แบบหรือรายชื่อไฟล์ที่รองรับ', 'Use a filename from the templates or supported filenames list.') :
      t('กรุณาเลือกไฟล์ราคาเพียงไฟล์เดียว หรือเลือกครบตามรายชื่อด้านบน', 'Select only the price file, or select every file listed above.'));
    return;
  }
  if (files.reduce((total, file) => total + file.size, 0) > 11 * 1024 * 1024) {
    text('upload-message', t('กรุณาเลือกไฟล์รวมไม่เกิน 11 MB', 'Select files totaling 11 MB or less.'));
    return;
  }
  const controls = [fileInput, importMode, byId('run'), byId('cancel')];
  controls.forEach(control => { control.disabled = true; });
  text('upload-message', t('กำลังรัน Walk-forward และสร้างผลคาดการณ์ อาจใช้เวลาสักครู่…', 'Running walk-forward validation and generating forecasts. This may take a moment…'));
  try {
    const input = Object.fromEntries(await Promise.all(files.map(async file => [file.name, await file.text()])));
    const data = await fetchJSON('/api/' + (merge ? 'update' : 'forecast') + '/' + id, { method: 'POST',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input) });
    loaded.set(id, { data, source: () => merge ? t('ชุดข้อมูลอัปเดตในเครื่อง', 'Updated local dataset') : t('CSV ที่อัปโหลด · ' + files.length + ' ไฟล์', 'Uploaded CSV files · ' + files.length) });
    selected.feature = '';
    byId('notice').hidden = true;
    text('upload-message', '');
    fileInput.value = '';
    render();
    dialog.close();
  } catch (error) {
    text('upload-message', errorText(error));
  } finally {
    controls.forEach(control => { control.disabled = false; });
  }
};

function setPresentation(active) {
  document.body.classList.toggle('presenting', active);
  byId('present').setAttribute('aria-pressed', String(active));
  byId('present').querySelector('span').textContent = active ? t('ออกจากการนำเสนอ', 'Exit Present') : t('นำเสนอ', 'Present');
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
function refreshLanguage() {
  applyLanguage();
  setPresentation(document.body.classList.contains('presenting'));
  if (noticeMessage) text('notice', noticeMessage());
  render();
}

byId('language-toggle').onclick = () => {
  language = t('en', 'th');
  try { localStorage.setItem('model411-language', language); } catch {}
  refreshLanguage();
};
refreshLanguage();

try {
  for (const model of await fetchJSON('/api/models')) models.set(model.id, model);
  byId('model').replaceChildren(...[...models.values()].map(model => option(model.id, model.symbol)));
  await selectModel(byId('model').value);
} catch (error) {
  showNotice(error);
}

byId('online').onclick = async () => {
  const button = byId('online');
  button.disabled = true;
  byId('upload').disabled = true;
  byId('notice').hidden = false;
  setNotice(() => t('กำลังดึงราคา งบ MU และ Macro จาก FRED แล้วรัน Walk-forward อาจใช้เวลาหลายนาที…', 'Fetching MU prices, financials and FRED macro data, then running walk-forward validation. This may take several minutes…'));
  try {
    const data = await fetchJSON('/api/online/mu', {method: 'POST'});
    loaded.set('mu', {data, source: () => t('อัปเดตออนไลน์', 'Online update')});
    render();
    setNotice(() => t('อัปเดตสำเร็จ · ราคาปิดถึง ', 'Updated · Closing prices through ') + dateText(data.asOf) +
      t(' · งบสิ้นงวด ', ' · Financial period ended ') + dateText(data.sources.quarter) + t(' · Macro จาก FRED ครบ 5 ชุด', ' · All five FRED series updated'));
  } catch (error) {
    showNotice(error);
  } finally {
    button.disabled = false;
    byId('upload').disabled = false;
  }
};

const themeToggle = byId('theme-toggle');
function syncThemeToggle() {
  themeToggle.setAttribute('aria-pressed',
    String(document.documentElement.dataset.theme === 'dark'));
}
syncThemeToggle();
themeToggle.addEventListener('click', () => {
  const theme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = theme;
  try { localStorage.setItem('model411-theme', theme); } catch {}
  syncThemeToggle();
});
