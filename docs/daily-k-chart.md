# 日 K 图实现说明

日 K 图已抽成可复用组件 `KLineChart`：主图叠加指标与副图均可配置，B1 选股页只是调用方之一。本文记录组件 API、四面板布局、主图/副图样式、指标公式、悬停交互与自适应策略。改动这一块时，先读完本文，再动代码。

## 1. 相关文件

| 文件 | 作用 |
| --- | --- |
| `stock-line/src/components/KLineChart/index.tsx` | 组件本体：配置项、指标计算、`buildOption`、读数行、ECharts 生命周期 |
| `stock-line/src/components/KLineChart/style.less` | 组件样式（图表容器、读数行） |
| `stock-line/src/pages/B1Picks/index.tsx` | 调用方：取数并传入 `bars` / `markDate` |
| `stock-line/src/pages/HuijinHoldings/style.less` | `.hj-panel` 与 Spin 层 flex 基础布局（B1 页共用） |
| `flask_backend/services/data_service.py` | `get_kline_data`，按 `category + exchange + code` 查询 |
| `flask_backend/routes/api.py` | `GET /api/kline/<category>/<code>` |

数据接口返回 `{ data: [{ date, open, high, low, close, volume, amount }] }`，按日期升序，前复权。

## 1.1 组件用法

```tsx
import KLineChart from '@/components/KLineChart'; // 或相对路径

<KLineChart
  bars={bars}                       // 必填，升序日 K
  markDate={asOf}                   // 可选，画一根紫色虚线
  markLabel="B1 选股日"              // 可选，tooltip 中的标记文案
  overlays={['zx_short', 'zx_long', 'ma5', 'ma10']}  // 主图叠加，见下表
  subCharts={['volume', 'kdj', 'macd']}              // 副图，按顺序自上而下
/>
```

- `overlays` 默认 `['zx_short', 'zx_long']`；`subCharts` 默认 `['volume', 'kdj']`，只影响初始展示的副图。
- 开启 `legend` 时，图例会列出成交量、KDJ、MACD 三项，未在 `subCharts` 里的以关闭态出现，点击即可打开；关闭图例时只按 `subCharts` 渲染。
- 主图读数行会按 `overlays` 顺序自动生成色块与数值，副图读数行按当前展示的副图顺序生成，面板高度按副图数量自动分配。
- 组件自带 `flex: 1` 与 `min-height: 360px`，放在 antd `<Spin>` 内即可随面板高度自适应。

| `OverlayKind` | 含义 | 颜色 |
| --- | --- | --- |
| `zx_short` | 知行短期趋势线 | `#f08c00` |
| `zx_long` | 知行多空线 | `#3b6ea5` |
| `ma5` / `ma10` / `ma20` / `ma60` | 均线 | 金 / 绿 / 紫 / 灰 |

| `SubChartKind` | 内容 |
| --- | --- |
| `volume` | 成交量柱 |
| `kdj` | KDJ(9,3,3) 三线 |
| `macd` | MACD(12,26,9) 柱 + DIF/DEA |


## 2. 整体布局

面板数量随 `subCharts` 变化，布局在组件内按 **像素** 计算（`makeLayout`）：

- 主图顶部 `36px`（留给 HTML 读数行），底部 `24px`（日期轴），面板间距 `12px`。
- 副图高度默认可随容器高度自适应：成交量 `max(46px, 容器高×8%)`、KDJ/MACD `max(64px, 容器高×11%)`；需要固定或不同比例时用 `subHeights` 传像素覆盖（板块活跃度页即传了 `{ volume: 70, kdj: 108, macd: 108 }`）。
- 主图高度 = 容器高 − 上下留白 − 副图总高 − 间距，最小 `140px`；容器变高时主图吃掉剩余余量。

```ts
const subTotal = subCharts.reduce((sum, kind) => sum + resolved(kind), 0) + gap * subCharts.length;
const mainHeight = Math.max(140, height - top - bottom - subTotal);
```

要点：

- 左侧统一 `left: 58`，右侧 `right: 26`，所有面板纵向对齐。
- 只有最底部面板的 x 轴显示日期标签，其余 `axisLabel: { show: false }`，减少视觉噪音。
- `dataZoom` 只保留 `inside` 滚轮缩放，**没有底部拖动滑块**；初始 `start` 按“约 250 根 K 线”换算：
  ```ts
  const start = Math.max(0, Math.round(100 - 25000 / bars.length));
  ```
- 顶部 36px 是留给 HTML 读数行的空白带，不要在该区域放 ECharts 组件（原图例已移除）。

### 自适应高度（重要）

图表被 antd `<Spin>` 包裹，DOM 层级为：

```
.hj-panel.hj-chart-panel (flex column)
└─ .ant-spin-nested-loading (flex: 1)
   └─ .ant-spin-container (flex: 1)
      └─ .kline-chart-wrap (position: relative, flex: 1, min-height: 360px)
         ├─ div.kline-chart (position: absolute; inset: 0)   ← echarts 挂载点
         └─ .kline-readout-layer (absolute 覆盖层)
```

两处必须同时成立，图表才会铺满卡片：

1. CSS：`.ant-spin-nested-loading`、`.ant-spin-container` 都 `flex: 1; display: flex; flex-direction: column; min-height: 0;`，`.kline-chart` 绝对定位铺满 `.kline-chart-wrap`。
2. JS：`ResizeObserver` 量取挂载点尺寸写入 `size` state，尺寸变化时 `chart.resize()` 并用同一份尺寸重算 grid，保证读出行与面板严格对齐：

```ts
const observer = new ResizeObserver(measure);
observer.observe(host);
```

组件必须在 `size.height > 0` 之后才 `setOption`，否则首次布局未完成会画出偏小的画布。

## 3. 主图

### K 线

```ts
{
  type: 'candlestick',
  data: bars.map((bar) => [bar.open, bar.close, bar.low, bar.high]),
  itemStyle: {
    color: UP, color0: DOWN,
    borderColor: UP, borderColor0: DOWN,
    borderWidth: 1,
  },
}
```

涨跌配色为 **红涨绿跌**：`UP = #c45e65`，`DOWN = #238672`，平盘 `FLAT = #7a898f`。

### 知行短期趋势线 / 知行多空线

| 线 | 公式 | 颜色 |
| --- | --- | --- |
| 知行短期趋势线 | `EMA(EMA(C,10),10)` | `#f08c00` 橙 |
| 知行多空线 | `(MA14 + MA28 + MA57 + MA114) / 4`，任一均线不足则取 `null` | `#3b6ea5` 蓝 |

```ts
const ema = (values: number[], span: number) => {
  const k = 2 / (span + 1);
  let previous = values[0];
  return values.map((v, i) => (i === 0 ? v : (previous += k * (v - previous))));
};

const ma = (values: number[], window: number) => {
  let sum = 0;
  return values.map((value, index) => {
    sum += value;
    if (index >= window) sum -= values[index - window];
    return index >= window - 1 ? sum / window : null;
  });
};
```

两条线都是 `showSymbol: false`、`lineStyle.width: 1.5`、`connectNulls: false`，并设置 `z` 高于 K 线（3、4）。

### B1 选股日紫色虚线

只标 **一根**，位置是当前展开日期分组的选股日（`asOf`，即页面右上角「截至 xx」）：

```ts
const markMarks = markDate && dates.includes(markDate)
  ? [{ xAxis: markDate, label: { show: true } }]
  : [];

markLine: {
  silent: true,
  symbol: ['none', 'none'],
  lineStyle: { color: B1_MARK /* #8e44ad */, type: 'dashed', width: 1, opacity: 0.85 },
  data: markMarks,
}
```

不要改成“历史全部 B1 信号日”——需求明确只要选出来的当天。

## 4. 副图

### 成交量

- 柱状图，`barWidth: '60%'`；颜色跟随当根 K 线涨跌，并在颜色后加 `99` 作为透明度（`rgba` 十六进制写法）：`(bar.close >= bar.open ? UP : DOWN) + '99'`。
- y 轴隐藏刻度与网格线，只保留图形。
- 读数行显示 `量 7756.8万手`（`formatVolume`：≥1 亿显示“亿手”，≥1 万显示“万手”）。

### KDJ(9,3,3)

```ts
const rsv = ((close - lowN) / (highN - lowN + 1e-9)) * 100;
k = (2 / 3) * k + (1 / 3) * rsv;   // 首根 K/D 取 50
d = (2 / 3) * d + (1 / 3) * k;
j = 3 * k - 2 * d;
```

- `lowN` / `highN` 为最近 9 根（含当根）的最低价 / 最高价。
- 与后端 `b1_selector` 的 J 值口径一致，便于和选股结果对照。
- 颜色：K `#d9a441`、D `#3b6ea5`、J `#8e44ad`（J 与 B1 虚线同色系），线宽 1。

### MACD(12,26,9)

```ts
const fast = ema(closes, 12);
const slow = ema(closes, 26);
const dif = fast.map((v, i) => v - slow[i]);
const dea = ema(dif, 9);
const macd = dif.map((v, i) => (v - dea[i]) * 2);   // 柱 = 2×(DIF-DEA)
```

- 柱：正红负绿，带 `99` 透明度。
- DIF 橙 `#f08c00`，DEA 蓝 `#3b6ea5`。

指标序列统一由 `computeIndicators(bars)` 计算一次，绘图和读数行复用，避免两套口径。

## 5. 悬停与读数（当前设计）

### 十字线

- 顶层 `axisPointer: { type: 'cross', link: [{ xAxisIndex: 'all' }] }`，所有面板共享同一条竖线。
- 日期标签只出现在最底部 x 轴；其余轴 `axisPointer: { label: { show: false } }`。左侧价格标签保留。

### 悬浮框（只放主图信息）

- `trigger: 'axis'`，`confine: true`。
- `position` 自定义：横向跟随鼠标并左右夹紧，**纵向固定在主图顶部（`layout.main.top + 2`，默认 38）**，不再上下漂移：

```ts
position: (point, _params, _dom, _rect, size) => {
  const left = Math.min(Math.max(point[0] - size.contentSize[0] / 2, 8),
    size.viewSize[0] - size.contentSize[0] - 8);
  return [left, layout.main.top + 2];
}
```

- 内容仅：日期、开/收/高/低、涨跌、`markLabel` 标记。**成交量、KDJ、MACD、知行线都不要放回悬浮框**（副图数值由读数行承担，叠加指标由顶部读数行承担）。

### 面板顶部 HTML 读数行

ECharts 之外用一层绝对定位的 overlay，位置直接复用 `makeLayout` 的像素坐标，与 grid 严格对齐：

| 行 | 位置 | 内容 |
| --- | --- | --- |
| 主图叠加指标 | `top: 8px` | 按 `overlays` 逐个渲染色块 + 名称 + 数值 |
| 各副图 | `panel.top + 2` | 面板名 + 对应数值（成交量 / K/D/J / DIF/DEA/MACD） |

联动实现：监听 ECharts 的 `updateAxisPointer` 记录下标，鼠标移出 `globalout` 时回落到最后一根：

```ts
chart.on('updateAxisPointer', (event: any) => {
  const info = event?.axesInfo?.[0];
  if (!info) return;
  const index = typeof info.value === 'number'
    ? info.value
    : bars.findIndex((bar) => bar.date === info.value);
  if (index >= 0 && index < bars.length) setHoverIndex(index);
});
chart.on('globalout', () => setHoverIndex(null));
```

> 注意：`tooltip` 不能被删除。删掉后 `axisPointer` 不触发，十字线和悬停联动都会消失。

## 6. 配色与样式常量

| 常量 | 值 | 用途 |
| --- | --- | --- |
| `UP` | `#c45e65` | 阳线、上涨、MACD 正柱 |
| `DOWN` | `#238672` | 阴线、下跌、MACD 负柱 |
| `FLAT` | `#7a898f` | 平盘、涨跌幅为 0 |
| `B1_MARK` | `#8e44ad` | 虚线标记、KDJ 的 J |
| KDJ-K | `#d9a441` | KDJ 的 K |
| 知行/DIF | `#f08c00` | 知行短期趋势线、DIF、MA5 |
| 知行/DEA/D | `#3b6ea5` | 知行多空线、DEA、KDJ 的 D |
| MA10 / MA20 / MA60 | `#6b9e63` / `#8e44ad` / `#657780` | 均线叠加 |

坐标轴 / 文本灰阶：主 y 轴 `#7a898f`、副图刻度 `#9aa8ad`、网格线 `#eef2f3` / `#f2f5f6`、轴 `#dfe6e7`。

## 7. 常见改动指引

- **调整面板高度**：改组件里的 `SUB_HEIGHT` / `LAYOUT.gap` 即可，主图高度与读数行位置会自动重算，不要再手写百分比。
- **更换图表数据源**：保持 `data` 为升序数组；`buildOption` 依赖 `bars` 顺序计算指标与 `dataIndex`。
- **新增副图**：在 `SubChartKind`、`SUB_HEIGHT`、`SUB_LABEL` 里登记，再在 `buildOption` 的 `layout.panels.forEach` 与读数行 JSX 里各加一段；grid / 轴会按配置自动生成。
- **新增主图叠加**：在 `OverlayKind` 与 `OVERLAY_META` 里登记，`overlayData` 返回序列即可，读数行会自动出现。
- **性能**：`/api/kline/<category>/<code>` 曾因缺少 `exchange` 条件在 MySQL 上退化为全表扫描（约 5s）。查询必须带 `category + exchange + code`，前端无需额外处理。
- **图表重建**：`setOption` 依赖 `bars`、`markDate`、`overlays`、`subCharts` 与容器尺寸；`hoverIndex` 在 `bars` 变化时重置为 `null`（显示最后一根）。ECharts 实例只在挂载时创建一次，尺寸变化只 `resize` 不重建。
