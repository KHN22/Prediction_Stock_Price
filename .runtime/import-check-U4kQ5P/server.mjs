import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { readFile, writeFile, rename } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(fileURLToPath(import.meta.url));
const port = Number(process.env.PORT || 4110);
const config = {
  mu: {
    id: 'mu', symbol: 'MU', company: 'Micron Technology', exchange: 'NASDAQ',
    version: 'Capstone v5', currency: 'USD',
    updateFiles: ['mu_quarterly_update.csv'],
    files: ['mu_prices.csv', 'cleaned_macro_data.csv', 'mu_income_statement_raw.csv',
      'mu_earnings_raw.csv', 'mu_cash_flow_raw.csv', 'mu_balance_sheet_raw.csv'],
  },
};

const bundledPython = join(root, '.runtime', 'venv',
  process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const python = process.env.MODEL_PYTHON || (existsSync(bundledPython) ? bundledPython : 'python');
const dataPath = id => join(root, 'public', id + '.json');
const workingPath = id => join(root, 'data', id + '.working.json');

async function readWorking(id) {
  try { return JSON.parse(await readFile(workingPath(id), 'utf8')); }
  catch (error) {
    if (error.code !== 'ENOENT') throw error;
    return null;
  }
}

async function readBase(model) {
  return Object.fromEntries(await Promise.all(model.files.map(async name =>
    [name, await readFile(join(root, 'data', name), 'utf8')])));
}

function forecast(id, files, merge = false) {
  return new Promise((resolve, reject) => {
    const args = [join(root, 'models', 'run.py'), id];
    if (merge) args.push('--merge');
    const worker = spawn(python, args, {
      env: { ...process.env, PYTHONUTF8: '1', OMP_NUM_THREADS: '2', OPENBLAS_NUM_THREADS: '2' },
    });
    const timeout = setTimeout(() => worker.kill(), 10 * 60 * 1000);
    const output = [];
    let errors = '';
    worker.stdout.on('data', chunk => output.push(chunk));
    worker.stderr.setEncoding('utf8').on('data', chunk => { errors = (errors + chunk).slice(-5000); });
    worker.stdin.on('error', () => {});
    worker.on('error', error => {
      clearTimeout(timeout);
      reject(error);
    });
    worker.on('close', code => {
      clearTimeout(timeout);
      if (code !== 0) {
        console.error(errors);
        reject(Object.assign(new Error(code === 2 ? errors.trim().split('\n').at(-1) : 'รันโมเดลไม่สำเร็จ กรุณาตรวจสอบ Python และข้อมูล'), {
          status: code === 2 ? 422 : 500,
        }));
        return;
      }
      try { resolve(JSON.parse(Buffer.concat(output))); }
      catch (error) { reject(error); }
    });
    worker.stdin.end(JSON.stringify(files));
  });
}

async function refresh() {
  for (const model of Object.values(config)) {
    const result = await forecast(model.id, await readBase(model));
    const temporary = dataPath(model.id) + '.tmp';
    await writeFile(temporary, JSON.stringify(result));
    await rename(temporary, dataPath(model.id));
    console.log('Saved ' + model.symbol + ' forecast as of ' + result.asOf);
  }
}

const staticFiles = {
  '/': ['index.html', 'text/html'],
  '/style.css': ['style.css', 'text/css'],
  '/app.js': ['app.js', 'text/javascript'],
};
const uploadLimit = 12 * 1024 * 1024;
let busy = false;

function send(res, status, body) {
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
  res.end(JSON.stringify(body));
}

async function handle(req, res) {
  const path = new URL(req.url, 'http://localhost').pathname;
  const [, api, route, id] = path.split('/');
  if (req.method === 'GET' && Object.hasOwn(staticFiles, path)) {
    const [name, type] = staticFiles[path];
    const content = await readFile(join(root, 'public', name));
    res.writeHead(200, { 'Content-Type': type + '; charset=utf-8', 'Cache-Control': 'no-store' });
    return res.end(content);
  }
  if (req.method === 'GET' && path === '/api/models') return send(res, 200, Object.values(config));
  if (api !== 'api' || !Object.hasOwn(config, id) || path !== '/api/' + route + '/' + id) {
    return send(res, 404, { error: 'ไม่พบหน้าหรือโมเดล' });
  }
  if (req.method === 'GET' && route === 'snapshot') {
    const working = await readWorking(id);
    if (working) return send(res, 200, working.result);
    const snapshot = await readFile(dataPath(id), 'utf8');
    return send(res, 200, JSON.parse(snapshot));
  }
  const model = config[id];
  const merge = route === 'update' && Boolean(model.updateFiles);
  if (req.method !== 'POST' || (!merge && route !== 'forecast')) return send(res, 405, { error: 'คำขอนี้ใช้กับเส้นทางนี้ไม่ได้' });
  if (!/^application\/json(?:;|$)/i.test(req.headers['content-type'] || '')) {
    return send(res, 415, { error: 'ต้องส่งข้อมูลรูปแบบ JSON' });
  }
  if (busy) return send(res, 409, { error: 'ระบบกำลังประมวลผลอีกชุด กรุณารอสักครู่' });
  const chunks = [];
  let size = 0;
  for await (const chunk of req.iterator({ destroyOnReturn: false })) {
    size += chunk.length;
    if (size > uploadLimit) {
      req.resume();
      return send(res, 413, { error: 'ขนาดไฟล์รวมเกิน 12 MB' });
    }
    chunks.push(chunk);
  }
  let files;
  try { files = JSON.parse(Buffer.concat(chunks)); }
  catch { return send(res, 400, { error: 'ข้อมูลอัปโหลดไม่สมบูรณ์' }); }
  const allowed = merge ? [...model.files, ...model.updateFiles] : model.files;
  if (!files || typeof files !== 'object' || Array.isArray(files) || !Object.keys(files).length ||
      Object.entries(files).some(([name, value]) => !allowed.includes(name) || typeof value !== 'string')) {
    return send(res, 422, { error: 'ชื่อหรือเนื้อหาไฟล์ไม่ตรงกับโมเดล' });
  }
  if (busy) return send(res, 409, { error: 'ระบบกำลังประมวลผลอีกชุด กรุณารอสักครู่' });
  busy = true;
  try {
    if (!merge) return send(res, 200, await forecast(id, files));
    const base = (await readWorking(id))?.files ?? await readBase(model);
    const working = await forecast(id, { base, updates: files }, true);
    working.result.updatedAt = new Date().toISOString();
    const temporary = workingPath(id) + '.tmp';
    await writeFile(temporary, JSON.stringify(working));
    await rename(temporary, workingPath(id));
    send(res, 200, working.result);
  }
  finally { busy = false; }
}

if (process.argv.includes('--refresh')) {
  await refresh();
} else {
  const server = createServer((req, res) => handle(req, res).catch(error => {
    console.error(error.message);
    send(res, error.status || 500, { error: error.status ? error.message : 'เกิดข้อผิดพลาดในการโหลดข้อมูลหรือรันโมเดล' });
  }));
  server.listen(port, '127.0.0.1', () => console.log('Local  http://127.0.0.1:' + port));
}
