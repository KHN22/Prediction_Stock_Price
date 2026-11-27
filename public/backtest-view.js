import {backtestPoints, selectBacktest, evaluateBacktest} from './backtest.js';

const node = (tag, text, className) => {
  const element = document.createElement(tag);
  if (text != null) element.textContent = text;
  if (className) element.className = className;
  return element;
};
const element = id => document.getElementById(id);

export function renderBacktest(data, row, {t, format, dateText, visible, nonoverlap, onSample, onInspect}) {
  const root = element('backtest-evidence');
  root.hidden = !visible;
  const all = backtestPoints(data, row), points = selectBacktest(all, nonoverlap);
  const model = evaluateBacktest(points), baseline = evaluateBacktest(points, true);
  const intervals = data.model === 'amzn';
  element('backtest-sample').value = nonoverlap ? 'separated' : 'daily';
  element('backtest-sample').onchange = event => onSample(event.target.value === 'separated');
  const pct = value => value == null ? '—' : (100 * value).toFixed(1) + '%';
  const number = value => value == null ? '—' : value.toFixed(4);
  const description = (nonoverlap
    ? t('เลือกจากจุดแรก แล้วเว้นให้วันออกคำพยากรณ์ไม่อยู่ก่อนวันครบกำหนดของจุดก่อนหน้า ผลขึ้นกับจุดเริ่มต้น และตลาดยังอาจสัมพันธ์กัน', 'Starts at the first origin, then selects origins at or after the previous target. Results depend on the starting point; market dependence can remain.')
    : t('ใช้ทุกวันออกคำพยากรณ์ หน้าต่างอนาคตทับซ้อนกัน จำนวนจุดจึงไม่ใช่จำนวนการทดสอบอิสระ', 'Uses every forecast origin. Future windows overlap, so observations are not independent trials.'));
  element('backtest-sample-note').textContent = `${points.length} / ${all.length} ` + t('จุด · ', 'observations · ') + description;
  element('backtest-protocol').textContent = intervals
    ? t('RMSE ความผันผวนด้านบนใช้ CV เพื่อเลือกโมเดล ส่วนตารางนี้คำนวณราคาค่ากลางและกรอบจาก Holdout บนวันเดียวกันทั้งสองวิธี Holdout นี้ถูกดูระหว่างพัฒนาแล้ว จึงยังไม่ใช่หลักฐานจากอนาคตที่ไม่เคยเห็น', 'The volatility RMSE above uses CV for selection. This table evaluates median prices and intervals on identical Holdout dates for both methods. This Holdout was inspected during development; it is not untouched future evidence.')
    : t('ตารางนี้ประเมินผลตอบแทนและราคาบนชุดทดสอบเดียวกับกราฟ วิธีอ้างอิงของมุมมองหลักล็อก Momentum 21 วัน ส่วนช่องอื่นเลือกวิธีอ้างอิงด้วย RMSE บน test ย้อนหลัง', 'This table evaluates returns and prices on the chart’s test set. The primary view fixes 21-day momentum; other views retrospectively choose the benchmark using test RMSE.');
  const rows = element('backtest-score-rows');
  rows.replaceChildren();
  const headers = element('backtest-score-head');
  headers.replaceChildren(...[
    t('เกณฑ์วัด', 'Measure'), t('โมเดล', 'Model'),
    intervals ? t('กรอบคงสเกล', 'Constant-scale intervals') : row.best_baseline,
    t('อ่านผลอย่างไร', 'How to read'),
  ].map(value => node('th', value)));
  const add = (label, modelValue, baseValue, hint) => {
    const tr = node('tr');
    tr.append(node('th', label), node('td', modelValue), node('td', baseValue), node('td', hint));
    rows.append(tr);
  };
  add(t('จำนวนจุด', 'Observations'), String(model?.n ?? 0), String(baseline?.n ?? 0), t('วันเป้าหมายชุดเดียวกัน', 'Identical target dates'));
  if (model) {
    add('RMSE · log return', number(model.rmse), number(baseline.rmse), t('ความผิดพลาดค่ากลาง · ต่ำกว่าดีกว่า', 'Median error · lower is better'));
    add(t('MAE ของราคา', 'Price MAE'), format(model.maeUSD), format(baseline.maeUSD), t('ขนาดความผิดพลาดเฉลี่ยต่อหุ้น · ต่ำกว่าดีกว่า', 'Mean absolute error per share · lower is better'));
    add(t('ทายทิศทางถูก', 'Directional accuracy'), pct(model.direction), pct(baseline.direction), t('วัดจากราคาวันออกพยากรณ์ ไม่ใช่ทิศทางเส้นรายวัน', 'Compared with the origin close, not daily line movements'));
    if (intervals) {
      for (const level of [80, 95]) {
        const coverage = metrics => metrics['coverage' + level] == null ? '—' : pct(metrics['coverage' + level]) + ` (${metrics['hits' + level]}/${metrics.n})`;
        add(`Coverage ${level}%`, coverage(model), coverage(baseline), t(`ควรใกล้ ${level}% ไม่ใช่ยิ่งสูงยิ่งดี`, `Should be near ${level}%; higher is not always better`));
        add(t(`ความกว้างกรอบ ${level}%`, `${level}% interval width`),
          model['width' + level] == null ? '—' : model['width' + level].toFixed(1) + '%',
          baseline['width' + level] == null ? '—' : baseline['width' + level].toFixed(1) + '%',
          t('เฉลี่ยเทียบราคาวันออกพยากรณ์ · ดูคู่กับ coverage', 'Mean width / origin close · assess with coverage'));
        add(`Interval score ${level}%`, number(model['score' + level]), number(baseline['score' + level]), t('หน่วย log return · ลงโทษกรอบกว้างและการหลุดกรอบ · ต่ำกว่าดีกว่า', 'Log-return units · penalizes width and misses · lower is better'));
      }
    }
  }
  const commentary = [];
  if (!model) commentary.push(t('ไม่มีจุดที่ประเมินได้ในตัวเลือกนี้', 'No eligible observations for this selection.'));
  else {
    if (intervals && model.coverage80 != null) {
      commentary.push(t('กรอบ 80% ครอบคลุมจริง ', 'Actual coverage of the 80% interval: ') + pct(model.coverage80) +
        t(' เป้าหมายคือ 80% ต้องดูความกว้างและ interval score ประกอบก่อนสรุปว่าดี', '; target 80%. Inspect width and interval score before judging quality.'));
      if (baseline.score80 != null) commentary.push(model.score80 < baseline.score80
        ? t('Interval score 80% ต่ำกว่าวิธีอ้างอิงในชุดนี้', 'The 80% interval score is lower than the benchmark on this sample.')
        : t('Interval score 80% ยังไม่ต่ำกว่าวิธีอ้างอิงในชุดนี้', 'The 80% interval score is not lower than the benchmark on this sample.'));
      else commentary.push(t('ผลเก่าไม่มีกรอบของวิธีอ้างอิง ให้คำนวณใหม่เพื่อเปรียบเทียบคะแนนช่วงราคา', 'Legacy output lacks benchmark intervals. Recalculate to compare interval scores.'));
    }
    if (model.upRate != null) commentary.push(t('ช่วงที่ขึ้นจริงมี ', 'Actual positive-return windows: ') + pct(model.upRate) + t(' ของชุดนี้ จึงต้องอ่านความแม่นทิศทางคู่กับสัดส่วนดังกล่าว', '; interpret directional accuracy alongside that rate.'));
    if (points.length < 30) commentary.push(t('ตัวอย่างน้อยกว่า 30 จุด ผลยังไวต่อช่วงตลาดและจุดเริ่มต้น', 'Fewer than 30 observations; results are sensitive to market period and starting point.'));
  }
  element('backtest-verdict').textContent = commentary.join(' ');
  const slider = element('backtest-case');
  slider.min = 0;
  slider.max = Math.max(points.length - 1, 0);
  slider.disabled = !points.length;
  slider.value = slider.max;
  function inspect(index) {
    const point = points[index];
    const details = element('backtest-case-values');
    details.replaceChildren();
    if (!point) return;
    slider.value = index;
    element('backtest-case-label').textContent = t('คำพยากรณ์ตัวอย่าง ', 'Example forecast ') + `${index + 1} / ${points.length}`;
    const pair = (label, value) => {
      const div = node('div');
      div.append(node('span', label), node('strong', value));
      details.append(div);
    };
    pair(t('วันออกพยากรณ์', 'Origin date'), point.originDate ? dateText(point.originDate) : '—');
    pair(t('วันครบกำหนด', 'Target date'), dateText(point.targetDate));
    pair(t('ราคาวันออกพยากรณ์', 'Origin close'), point.originClose == null ? '—' : format(point.originClose));
    pair(t('ราคาจริงเมื่อครบกำหนด', 'Realized target close'), format(point.actual));
    pair(t('ค่ากลางจาก Backtest', 'Backtest median'), format(point.predicted));
    if (point.intervals) {
      const [lo95, hi95, lo80, hi80] = point.intervals;
      pair(t('กรอบ 80% จาก Backtest', 'Backtest 80% interval'), `${format(lo80)} – ${format(hi80)}`);
      pair(t('กรอบ 95% จาก Backtest', 'Backtest 95% interval'), `${format(lo95)} – ${format(hi95)}`);
      pair(t('ผลเทียบกรอบ', 'Interval outcome'), point.actual >= lo80 && point.actual <= hi80
        ? t('อยู่ในกรอบ 80%', 'Inside 80% interval')
        : point.actual >= lo95 && point.actual <= hi95 ? t('หลุด 80% แต่ยังอยู่ใน 95%', 'Outside 80%, inside 95%') : t('หลุดกรอบ 95%', 'Outside 95% interval'));
    }
  }
  slider.oninput = () => { const index = Number(slider.value); inspect(index); onInspect?.(index); };
  inspect(points.length - 1);
  return {points, inspect};
}

export function renderDecision(data, row, {t, format}) {
  const amzn = data.model === 'amzn', explanation = row.explanation;
  element('model-evaluation-note').textContent = amzn
    ? t('CV คือช่วงประเมินเพื่อเลือกโมเดลความผันผวนและค่าปรับ ส่วนกราฟกับตาราง Backtest ใช้ Holdout ราคาปลายช่วง ความแม่นทิศทางในแถบสรุปด้านบนใช้ CV ที่เว้นทุก h วัน จึงมีจำนวนจุดต่างจากกราฟ ปฏิทินงบอาจมีวันประมาณการ และ Holdout เคยถูกดูระหว่างพัฒนาแล้ว', 'CV is the evaluation period used to select the volatility model and tuning settings. The Backtest chart and table use terminal Holdout prices. Directional accuracy in the upper summary uses CV origins spaced h sessions apart, so its count differs from the chart. Earnings dates may be estimated, and the Holdout was inspected during development.')
    : t('มุมมองหลัก MU ใช้ Random Forest กับราคาและ Macro ระยะ 63 วันซื้อขาย เทียบ Momentum 21 วัน การแบ่งตามเวลาตัดแถวฝึกที่เป้าหมายล้ำเข้าช่วงประเมิน ผลรายวันมีเป้าหมายซ้อนทับกัน Macro ใช้ lag ตามสมมติฐานและอาจมีการแก้ไขข้อมูลย้อนหลัง', 'The primary MU view uses Random Forest with price and macro inputs over 63 sessions, benchmarked against 21-day momentum. Temporal splits purge training targets crossing into evaluation. Daily targets overlap. Macro availability uses assumed lags and historical data may be revised.');

  element('decision-title').textContent = amzn ? t('โมเดลกำหนดค่ากลางและกรอบอย่างไร?', 'How are the median and range determined?') : t('ฐานราคาและ ML สร้างผลคาดการณ์อย่างไร?', 'How do the baseline and ML form the forecast?');
  element('decision-process').textContent = amzn
    ? t('1 · CV เลือกวิธีพยากรณ์ความผันผวน  2 · ค่าเฉลี่ยผลตอบแทนในอดีตที่ผ่านการลดน้ำหนักกำหนดศูนย์กลาง  3 · ความผันผวนปรับสเกลกรอบ  4 · Quantile ของข้อผิดพลาดที่ทราบผลแล้วปรับขอบกรอบและค่ามัธยฐาน', '1 · CV selects a volatility model. 2 · Shrunk historical mean return sets the center. 3 · Volatility scales the range. 4 · Quantiles of realized errors set interval bounds and adjust the median.')
    : t('1 · สร้างฐานจากค่าเฉลี่ย 63 วันของ log return 21 วัน  2 · โมเดลเรียนรู้ส่วนต่างจากฐาน  3 · ใช้น้ำหนัก ML ที่เลือกจาก validation  4 · รวมเป็นผลตอบแทนและแปลงเป็นราคา', '1 · Build a baseline from the 63-day mean of 21-day log returns. 2 · Learn a residual. 3 · Apply the validation-selected ML weight. 4 · Combine and convert to a price.');
  const values = element('decision-values');
  values.replaceChildren();
  const pair = (label, value) => {
    const div = node('div'); div.append(node('span', label), node('strong', value)); values.append(div);
  };
  pair(t('โมเดลที่เลือก', 'Selected model'), row.best_model);
  if (amzn && row.intervals) {
    pair(t('ความผันผวนรายวันคาดการณ์', 'Forecast daily volatility'), (100 * row.intervals.expDailyVol).toFixed(2) + '%');
    pair(t('ตัวลดน้ำหนักศูนย์กลาง', 'Center shrinkage'), row.intervals.shrink.toFixed(2));
    pair(t('มีวันงบในช่วงพยากรณ์', 'Earnings event within horizon'), row.intervals.earningsInWindow ? t('มี · ตามปฏิทินที่นำเข้า', 'Yes · based on imported calendar') : t('ไม่มีในปฏิทินที่นำเข้า', 'None in imported calendar'));
  } else {
    pair(t('น้ำหนัก ML', 'ML weight'), (row.blend_weight ?? 1).toFixed(3));
    if (explanation) {
      pair(t('ผลตอบแทนจากฐาน', 'Baseline return'), (100 * explanation.baseReturn).toFixed(2) + '%');
      pair(t('ส่วนเพิ่มจาก ML', 'ML increment'), explanation.mlIncrementPp.toFixed(2) + t(' จุดเปอร์เซ็นต์', ' percentage points'));
    }
  }
  const direction = row.directionProbability;
  if (amzn && direction?.version === 2) {
    const pct = value => (100 * value).toFixed(1) + '%';
    const horizon = row.sessions;
    pair(t(`โอกาสปิดสูงขึ้นใน ${horizon} วันซื้อขาย`, `Probability of a higher close after ${horizon} sessions`), pct(direction.up));
    pair(t('โอกาสปิดเท่าเดิมหรือต่ำลง', 'Probability of a flat or lower close'), pct(1 - direction.up));
    pair(t('วิธีประเมินทิศทาง', 'Direction estimate'), direction.method === 'rangeBlend'
      ? t('เฉลี่ยโอกาสจากกรอบราคากับอัตราขึ้นย้อนหลัง อย่างละครึ่ง', 'Equal blend of range-implied probability and historical up rate')
      : t('อัตราขึ้นย้อนหลัง', 'Historical up rate'));
    pair(t('โอกาสขึ้นจากกรอบราคา / อัตราขึ้นย้อนหลัง', 'Range-implied probability / historical up rate'), pct(direction.rangeUp) + ' / ' + pct(direction.historicalRate));
    for (const [label, scores] of [['CV', direction.cv], ['Holdout', direction.holdout]]) {
      if (scores) pair(label + t(' · Brier วิธีผสม / อัตราย้อนหลัง (ต่ำดีกว่า)', ' · Brier, blend / historical (lower is better)'),
        scores.candidate.toFixed(4) + ' / ' + scores.baseline.toFixed(4) + ' · n=' + scores.n);
    }
    pair(t('อ่านผลทดสอบ', 'Reading the scores'), t('แต่ละวันเริ่มต้นมีช่วงพยากรณ์ซ้อนกัน ใช้ปี Holdout ประกอบการเลือกวิธีสำหรับเว็บ', 'Forecast windows overlap. The holdout year informed the choice of method for this release.'));
  } else if (amzn && direction) {
    const pct = value => (100 * value).toFixed(1) + '%';
    pair(t('โอกาสปิดสูงกว่าวันตั้งต้นใน 63 วันซื้อขาย', 'Probability of a higher close after 63 sessions'), pct(direction.up));
    pair(t('โอกาสปิดเท่าเดิมหรือต่ำกว่า', 'Probability of an equal or lower close'), pct(1 - direction.up));
    pair(t('อัตราขึ้นย้อนหลัง ณ วันพยากรณ์', 'Historical up rate at forecast origin'), pct(direction.historicalRate));
    pair(t('วิธีพยากรณ์ทิศทางที่เลือกจาก CV', 'Direction method selected on CV'), direction.method === 'logistic'
      ? t('โลจิสติกเฉลี่ยกับอัตราขึ้นย้อนหลัง', 'Logistic probability averaged with historical rate')
      : t('อัตราขึ้นย้อนหลัง', 'Historical up rate'));
    const names = {momentum: t('ผลตอบแทน 21 วัน', '21-session return'), volatility: t('ความผันผวน 21 วัน', '21-session volatility'),
      earnings: t('กำไรผิดจากคาดครั้งล่าสุด', 'Latest earnings surprise'), vix: 'VIX'};
    for (const [key, effect] of Object.entries(direction.effects).sort((a,b) => Math.abs(b[1]) - Math.abs(a[1]))) {
      pair(names[key] + t(' · ผลต่อ log-odds ก่อนเฉลี่ยกับฐาน', ' · log-odds effect before blending'), effect.toFixed(3));
    }
    for (const [label, scores] of [['CV', direction.cv], ['Holdout', direction.holdout]]) {
      if (scores) pair(label + t(' · Brier ยิ่งต่ำยิ่งดี (โลจิสติกผสม / ฐาน)', ' · Brier, lower is better (blend / base)'),
        scores.candidate.toFixed(4) + ' / ' + scores.baseline.toFixed(4) + ' · n=' + scores.n + t(' วันเริ่มต้นที่ช่วงทับซ้อนกัน', ' overlapping origins'));
    }
  }
  const factors = element('decision-factors'); factors.replaceChildren();
  element('decision-factor-unit').textContent = amzn
    ? t('ความไวของความผันผวนคาดการณ์เทียบกรณีอ้างอิง (%)', 'Forecast volatility sensitivity vs. reference (%)')
    : t('ความไวของราคาคาดการณ์เทียบกรณีอ้างอิง (%)', 'Forecast price sensitivity vs. reference (%)');
  element('decision-components').textContent = explanation?.components
    ? t('ค่าสัมประสิทธิ์โมเดลย่อย: ', 'Component coefficients: ') + explanation.components.map(c => `${c.model} ${c.coefficient.toFixed(3)}`).join(' · ') +
      t(' · เป็นตัวคูณในสมการ ไม่ใช่สัดส่วนความสำคัญรวม 100%', ' · Multipliers in the model equation, not importance shares summing to 100%.')
    : '';
  const labels = {
    price: t('ราคาและความผันผวนย้อนหลัง', 'Historical price and volatility'),
    macro: t('เศรษฐกิจมหภาค', 'Macroeconomic indicators'),
    financials: t('งบการเงิน', 'Financial statements'),
    vix: t('VIX', 'VIX'),
    earnings: t('ปฏิทินงบ', 'Earnings calendar'),
  };
  if (explanation?.factors?.length) {
    const maximum = Math.max(...explanation.factors.map(f => Math.abs(f.impactPct)), 1e-12);
    explanation.factors.forEach(factor => {
      const item = node('li');
      const head = node('div', null, 'factor-heading');
      head.append(node('span', labels[factor.group] || factor.group), node('strong', `${factor.impactPct >= 0 ? '+' : ''}${factor.impactPct.toFixed(2)}%`));
      const track = node('div', null, 'factor-track'); const bar = node('span');
      bar.style.width = `${100 * Math.abs(factor.impactPct) / maximum}%`;
      track.append(bar); item.append(head, track); factors.append(item);
    });
  }
  const zeroWeight = !amzn && row.blend_weight === 0;
  let interpretation = !explanation
    ? t('ผลที่บันทึกนี้ยังไม่มีการวัดความไวรายกลุ่ม กดคำนวณใหม่เพื่อดูอันดับจากโมเดลจริง จึงยังระบุไม่ได้ว่ากลุ่มใดส่งผลมากที่สุด', 'This saved result has no group sensitivity. Recalculate to obtain a measured ranking; the strongest group cannot yet be identified.')
    : zeroWeight ? t('รอบนี้น้ำหนัก ML เป็นศูนย์ ผลทั้งหมดมาจากฐาน จึงไม่ควรให้เครดิต Macro หรืองบว่าเป็นตัวผลักคำพยากรณ์', 'ML weight is zero: the forecast comes entirely from the baseline. Macro or financial features should not be credited as drivers.')
    : t('เรียงตามขนาดความไวของคำพยากรณ์ล่าสุด: เปลี่ยนข้อมูลทีละกลุ่มเป็นค่ามัธยฐานในชุดฝึก แล้วเปรียบเทียบกับค่าจริงโดยตรึงโมเดลไว้ เครื่องหมายบวกหมายถึงข้อมูลปัจจุบันทำให้', 'Ranked by latest-forecast sensitivity: replace one group with its training median and compare with the actual input, holding the fitted model fixed. A positive value means the current inputs make the') +
      (amzn ? t('ความผันผวนคาดการณ์สูงกว่ากรณีอ้างอิง ไม่ได้แปลว่าราคาจะขึ้น', ' forecast volatility higher than the reference; it does not mean price will rise.') : t('ราคาคาดการณ์สูงกว่ากรณีอ้างอิง', ' forecast price higher than the reference.'));
  if (explanation?.gjrHeldFixed) interpretation += t(' การวัดนี้ตรึงส่วน GJR ไว้ จึงยังไม่จัดอันดับปัจจัยภายใน GJR', ' The GJR component is held fixed; its internal drivers are not ranked.');
  if (explanation && !amzn) interpretation += t(' ความไวรายกลุ่มวัดเฉพาะส่วน ML โดยตรึงฐานไว้ ผลจากฐานแสดงแยกด้านบน', ' Group sensitivity measures only the ML component, holding the baseline fixed; the baseline effect is shown separately above.');
  if (explanation?.factors?.length && !zeroWeight) interpretation += t(' ค่ารายกลุ่มบวกกันไม่ได้ ไม่ใช่เปอร์เซ็นต์ความสำคัญรวม 100% และไม่ยืนยันเหตุและผลของราคาตลาด', ' Group effects are not additive, do not sum to 100% importance, and do not establish market causality.');
  element('decision-interpretation').textContent = interpretation;
  element('decision-reading').textContent = amzn
    ? t('ใช้กรอบประเมินขนาดการแกว่งของราคาปิดเมื่อครบกำหนด ไม่ใช่จุดสูงสุด/ต่ำสุดระหว่างทาง ตรวจ coverage พร้อมความกว้างและ interval score เทียบวิธีอ้างอิงก่อนให้น้ำหนักกับคำพยากรณ์ กรอบกว้างบอกว่ามีความไม่แน่นอนมาก ค่ากลางสูงขึ้นเพียงอย่างเดียวไม่ได้ยืนยันโอกาสทำกำไร', 'Use the range to assess uncertainty in the terminal close, not the path’s maximum/minimum. Check coverage, width and interval score against the benchmark before relying on a forecast. A wide range indicates uncertainty; a higher median alone does not establish profitability.')
    : t('อ่านค่ากลางคู่กับ RMSE และทิศทางบนชุดทดสอบ ตรวจว่าชนะวิธีอ้างอิงหรือไม่ และดูน้ำหนัก ML ก่อนอธิบายบทบาทของ Macro หรืองบ ผลตอบแทนคาดการณ์สูงเพียงอย่างเดียวไม่ได้แสดงว่าทดสอบย้อนหลังได้ดี', 'Read the point forecast with test RMSE and directional accuracy. Check benchmark performance and ML weight before attributing the result to macro or financial data. A high forecast return alone does not indicate good backtest performance.');
}
