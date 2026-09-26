// Regression: close-only data must render a primary line, even without API metadata.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function loadTs(relativePath, dependencies, globals = {}) {
  const filename = path.join(__dirname, '..', relativePath);
  const code = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.React, esModuleInterop: true },
  }).outputText;
  const module = { exports: {} };
  vm.runInNewContext(code, { module, exports: module.exports, require: name => {
    if (!(name in dependencies)) throw new Error(`Unexpected dependency: ${name}`);
    return dependencies[name];
  }, console, ...globals }, { filename });
  return module.exports;
}

const display = loadTs('src/pages/ActiveMarket/utils/indicatorDisplay.ts', {});
let option;
let refIndex = 0;
const effects = [];
const react = {
  createElement: () => null,
  useRef: initial => ({ current: refIndex++ === 0 ? {} : initial }),
  useEffect: effect => effects.push(effect),
};
const handlers = {};
const canvasHandlers = {};
let convertedIndex = 30;
const chart = { dispose() {}, on(name, handler) { handlers[name] = handler; }, resize() {},
  getZr() { return { on(name, handler) { canvasHandlers[name] = handler; }, off() {} }; },
  containPixel(finder, point) { assert.equal(finder.gridIndex, 0); return point[1] >= 0 && point[1] <= 500; },
  convertFromPixel(finder) { assert.equal(finder.xAxisIndex, 0); return convertedIndex; },
  getOption() { return option; }, setOption(value) { option = value; } };
const Component = loadTs('src/pages/ActiveMarket/components/KLineChart.tsx', {
  react,
  echarts: { init: () => chart, connect() {} },
  '../utils/indicatorDisplay': display,
}, { window: { addEventListener() {}, removeEventListener() {} } }).default;

function render(data, props = {}) {
  option = undefined;
  refIndex = 0;
  effects.length = 0;
  Component({ data, showZones: false, ...props });
  for (const effect of effects) effect();
  return option;
}

const closeOnly = Array.from({ length: 65 }, (_, i) => ({
  date: `day-${i}`, close: 100 + i, open: null, high: null, low: null, volume: null, amount: null,
}));
for (const data of [closeOnly, closeOnly.map(row => ({ date: row.date, close: row.close })),
  closeOnly.map(row => ({ ...row, open: NaN, high: NaN, low: NaN, volume: NaN }))]) {
  const result = render(data);
  assert.equal(result.series[0].type, 'line');
  assert.equal(result.series[0].name, '\u6536\u76d8\u4f30\u7b97\u503c');
  assert.equal(result.series[0].data.length, 65);
  assert.equal(result.series[0].data[0], 100);
  assert.equal(result.series[0].data[64], 164);
  assert.equal(result.series.some(series => series.type === 'candlestick' || series.type === 'bar'), false);
  assert.equal(result.legend.selected[result.series[0].name], true);
}
const ohlc = closeOnly.map(row => ({ ...row, open: row.close - 1, high: row.close + 2, low: row.close - 2, volume: 500 }));
assert.equal(render(ohlc).series[0].type, 'candlestick');
assert.equal(render(ohlc).series.some(series => series.type === 'bar'), true);
assert.equal(render(ohlc, { seriesType: 'line', mainSeriesName: 'ETF' }).series[0].name, 'ETF');
assert.equal(render(ohlc, { seriesType: 'line', mainSeriesName: 'ETF' }).series[0].type, 'line');
console.log('PASS: close-only primary line, null/missing/NaN fields, candlestick and ETF modes');

const dated = Array.from({ length: 100 }, (_, i) => ({ ...ohlc[0],
  date: new Date(Date.UTC(2026, 0, i + 1)).toISOString().slice(0, 10),
}));
const dateWindowRef = { current: null };
render(dated, { dateWindowRef });
assert.equal(dateWindowRef.current.start, dated[89].date);
// Simulate zooming out, then unmount/remount with a shorter indicator history.
option.dataZoom[0] = { startValue: 20, endValue: 80 };
handlers.dataZoom();
assert.equal(dateWindowRef.current.start, dated[20].date);
assert.equal(dateWindowRef.current.end, dated[80].date);
let restored = render(dated.slice(10), { dateWindowRef });
assert.equal(restored.xAxis[0].data[restored.dataZoom[0].startValue], dated[20].date);
assert.equal(restored.xAxis[0].data[restored.dataZoom[0].endValue], dated[80].date);
restored = render(dated.slice(50, 70), { dateWindowRef });
assert.equal(restored.dataZoom[0].startValue, 0);
assert.equal(restored.dataZoom[0].endValue, 19);
restored = render(dated, { dateWindowRef });
assert.equal(restored.dataZoom[0].startValue, 20);
assert.equal(restored.dataZoom[0].endValue, 80);
// The linked upper chart restores the same dates without a visible slider.
restored = render(dated, { dateWindowRef, showVolume: false, showDataZoom: false });
assert.equal(restored.dataZoom[0].startValue, 20);
assert.equal(restored.dataZoom[0].endValue, 80);
option.dataZoom[0] = { start: 0, end: 100 };
handlers.dataZoom();
assert.equal(dateWindowRef.current.start, dated[0].date);
assert.equal(dateWindowRef.current.end, dated[99].date);
console.log('PASS: date window survives remounts, different histories, clipping, linked charts and zoom events');
const openedDates = [];
render(dated, { onDayDoubleClick: day => openedDates.push(day), maxDate: dated[80].date });
for (const offsetY of [1, 200, 499]) canvasHandlers.dblclick({ offsetX: 300, offsetY });
assert.deepEqual(openedDates, [dated[30].date, dated[30].date, dated[30].date]);
canvasHandlers.dblclick({ offsetX: 300, offsetY: 600 });
convertedIndex = 99999;
canvasHandlers.dblclick({ offsetX: 300, offsetY: 200 });
convertedIndex = NaN;
canvasHandlers.dblclick({ offsetX: 300, offsetY: 200 });
assert.equal(openedDates.length, 3);
convertedIndex = 60;
canvasHandlers.dblclick({ offsetX: 300, offsetY: 200 });
assert.equal(openedDates[3], dated[60].date);
render(dated);
assert.doesNotThrow(() => canvasHandlers.dblclick({ offsetX: 300, offsetY: 200 }));
console.log('PASS: canvas double-click accepts all main-grid heights, maps the current axis date, and ignores outside/invalid coordinates');
