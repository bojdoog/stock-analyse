export interface BacktestZone {
  start_idx: number;
  end_idx: number;
  start_date: string;
  end_date: string;
  type: 'bull' | 'bear';
}

export interface BacktestHolding {
  name: string;
  weight: number;
  day_change?: number;
  holding_return: number;
  industry_name?: string; // 板块名称（仅用于资金流入排名）
}

export interface BacktestTrade {
  type: 'bull' | 'bear';
  start_date: string;
  end_date: string;
  year: number;
  return: number;
  amv_return: number;
  holdings: BacktestHolding[];
}

export interface BacktestYearResult {
  year: number;
  start_nav: number;
  end_nav: number;
  annual_return: number;
  bull_return?: number;
  bear_return?: number;
}

export interface BacktestNavPoint {
  date: string;
  nav: number;
}

export interface BenchmarkReturn {
  name: string;
  etfCode: string;
  totalReturn: number;
  annualReturns: { year: number; return: number }[];
}

export interface BacktestResult {
  zones: BacktestZone[];
  trades: BacktestTrade[];
  yearResults: BacktestYearResult[];
  totalReturn: number;
  finalNav: number;
  navSeries: BacktestNavPoint[];
  benchmarkReturns: BenchmarkReturn[];
}

export interface KLineData {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  amount: number;
}

export interface ExtraSeries {
  name: string;
  id: string;
  data: KLineData[];
}

/** 板块资金流向数据 */
export interface MoneyflowData {
  date: string;
  industry_name: string;
  pct_change: number;
  close: number;
  net_inflow: number;
  net_amount_rate: number;
  super_large_inflow: number;
  large_inflow: number;
  rank: number;
  etf_code: string;
  etf_name: string;
}

/** ETF名称到板块名称的映射（反向查询） */
const ETF_TO_INDUSTRY: Record<string, string[]> = {
  游戏ETF: ['游戏'],
  软件ETF: [
    '互联网服务',
    '软件开发',
    '算力概念',
    '数据要素',
    '云计算',
    '区块链',
    '数字货币',
    '网络安全',
  ],
  证券ETF: ['证券'],
  白酒ETF: ['酿酒行业'],
  新能源ETF: [
    '电池',
    '风电设备',
    '固态电池',
    '钠离子电池',
    '锂电池',
    '储能',
    '氢能源',
    '充电桩',
  ],
  半导体ETF: [
    '半导体',
    '半导体概念',
    '芯片概念',
    '汽车芯片',
    '存储芯片',
    '国产芯片',
  ],
  银行ETF: ['银行'],
  光伏ETF: ['光伏设备'],
  通信ETF: ['通信设备', '物联网', '5G概念', '光通信模块', 'CPO概念'],
  医药ETF: ['医药商业', '医疗器械', '化学制药', '中药'],
  创新药ETF: ['医疗服务', '生物制品'],
  传媒ETF: ['文化传媒'],
  军工ETF: [
    '航天航空',
    '船舶制造',
    '大飞机',
    '军民融合',
    '航母概念',
    '国产航母',
    '军工',
    '无人机',
  ],
  有色ETF: ['能源金属', '小金属', '贵金属', '有色金属'],
  煤炭ETF: ['煤炭行业'],
  沪深300ETF: ['石油行业', '水泥建材', '房地产', '工程建设', '装修装饰'],
  消费ETF: [
    '家电行业',
    '旅游酒店',
    '食品饮料',
    '商业百货',
    '农牧饲渔',
    '猪肉概念',
    '鸡肉概念',
  ],
  创业板人工智能ETF: ['创业板人工智能', '人工智能', 'ChatGPT概念', 'AIGC概念'],
  机器人ETF: ['机器人', '人形机器人'],
  电网设备ETF: [
    '电网设备',
    '电力行业',
    '公用事业',
    '燃气',
    '特高压',
    '智能电网',
    '虚拟电厂',
    '核能核电',
    '超导概念',
  ],
  新能源车ETF: [
    '汽车整车',
    '汽车零部件',
    '新能源车',
    '无人驾驶',
    '特斯拉',
    '比亚迪概念',
  ],
  卫星ETF: ['北斗导航', '航天概念'],
  高端装备ETF: ['工业母机', '高端装备', '海工装备', '海洋经济'],
  科创半导体设备ETF: ['EDA概念', '光刻机', '中芯概念'],
};

export type RankingMethod =
  | 'etf_gain'
  | 'ths_moneyflow'
  | 'ths_concept'
  | 'dc_moneyflow';

export interface StrategyParams {
  bullStartSingleDay: number;
  bullStartTwoDay: number;
  bullEndSingleDay: number;
  bullEndUseMA10: boolean;
  /** 买入比例，单位为百分比，如 30 表示 30% */
  weights: number[];
  bearStartYear: number;
  startYear: number;
  endYear: number;
  /** 多头区间买入排名方式：etf_gain=ETF涨幅排名, ths_moneyflow=同花顺板块流入, ths_concept=同花顺概念流入, dc_moneyflow=东财板块流入 */
  rankingMethod: RankingMethod;
}

export const DEFAULT_STRATEGY_PARAMS: StrategyParams = {
  bullStartSingleDay: 4,
  bullStartTwoDay: 4,
  bullEndSingleDay: -2.3,
  bullEndUseMA10: true,
  weights: [30, 30, 20, 10, 10],
  bearStartYear: 2024,
  startYear: 2019,
  endYear: new Date().getFullYear(),
  rankingMethod: 'etf_gain',
};

export type OptimalMethod = 'equal' | 'return' | 'growth' | 'sharpe';

function normalizeWeights(weights: number[]): number[] {
  const rounded = weights.map((w) => Math.round(w));
  const sum = rounded.reduce((a, b) => a + b, 0);
  if (sum === 0) return [20, 20, 20, 20, 20];
  if (sum === 100) return rounded;
  const diff = 100 - sum;
  const maxIdx = rounded.indexOf(Math.max(...rounded));
  rounded[maxIdx] += diff;
  return rounded;
}

export function calculateOptimalWeights(
  result: BacktestResult,
  method: OptimalMethod,
): number[] {
  const bullTrades = result.trades.filter((t) => t.type === 'bull');
  if (bullTrades.length === 0) return [20, 20, 20, 20, 20];

  if (method === 'equal') {
    return [20, 20, 20, 20, 20];
  }

  // Extract returns by rank (0-4)
  const rankReturns: number[][] = [[], [], [], [], []];
  bullTrades.forEach((t) => {
    t.holdings.forEach((h, idx) => {
      if (idx < 5) {
        rankReturns[idx].push(h.holding_return);
      }
    });
  });

  if (method === 'return') {
    const avgReturns = rankReturns.map((returns) =>
      returns.length === 0
        ? 0
        : returns.reduce((a, b) => a + b, 0) / returns.length,
    );
    const minReturn = Math.min(...avgReturns);
    const adjusted = avgReturns.map((r) =>
      Math.max(r - Math.min(0, minReturn), 0),
    );
    const total = adjusted.reduce((a, b) => a + b, 0);
    if (total === 0) return [20, 20, 20, 20, 20];
    return normalizeWeights(adjusted.map((r) => (r / total) * 100));
  }

  // Grid search for growth / sharpe
  const step = 5;
  const n = 5;
  let bestWeights = [20, 20, 20, 20, 20];
  let bestValue = -Infinity;

  const evaluate = (weights: number[]) => {
    const portfolioReturns = bullTrades.map((t) => {
      let pr = 0;
      for (let i = 0; i < n; i++) {
        const h = t.holdings[i];
        if (h) {
          pr += (weights[i] / 100) * h.holding_return;
        }
      }
      return pr;
    });

    if (method === 'growth') {
      return portfolioReturns.reduce((a, b) => a * Math.max(1 + b, 0.0001), 1);
    }

    const mean =
      portfolioReturns.reduce((a, b) => a + b, 0) / portfolioReturns.length;
    const std = Math.sqrt(
      portfolioReturns.reduce((a, b) => a + Math.pow(b - mean, 2), 0) /
        portfolioReturns.length,
    );
    return std === 0 ? mean : mean / std;
  };

  const generate = (idx: number, remaining: number, current: number[]) => {
    if (idx === n - 1) {
      current.push(remaining);
      const value = evaluate(current);
      if (value > bestValue) {
        bestValue = value;
        bestWeights = [...current];
      }
      current.pop();
      return;
    }
    for (let w = 0; w <= remaining; w += step) {
      current.push(w);
      generate(idx + 1, remaining - w, current);
      current.pop();
    }
  };

  generate(0, 100, []);
  return bestWeights;
}

const BANK_ETF_NAME = '银行ETF';

function calculateMA(data: KLineData[], dayCount: number): (number | null)[] {
  const result: (number | null)[] = [];
  for (let i = 0; i < data.length; i++) {
    if (i < dayCount - 1) {
      result.push(null);
      continue;
    }
    let sum = 0;
    for (let j = 0; j < dayCount; j++) {
      sum += data[i - j].close;
    }
    result.push(sum / dayCount);
  }
  return result;
}

export function identifyZones(
  data: KLineData[],
  params: StrategyParams = DEFAULT_STRATEGY_PARAMS,
): BacktestZone[] {
  const ma10 = calculateMA(data, 10);

  const bullZones: { start: number; end: number }[] = [];
  let isBullZone = false;
  let lastBullMarkIndex = -1;
  let currentBullStart = -1;

  for (let i = 0; i < data.length; i++) {
    const item = data[i];
    let change = 0;
    if (i > 0) {
      const prev = data[i - 1];
      change = ((item.close - prev.close) / prev.close) * 100;
    }

    let bullStart = false;
    let twoDayBull = false;

    if (change > params.bullStartSingleDay) {
      bullStart = true;
    } else if (change > 0 && i > 1) {
      const prev = data[i - 1];
      const prevPrev = data[i - 2];
      const prevChange = ((prev.close - prevPrev.close) / prevPrev.close) * 100;
      if (prevChange > 0 && change + prevChange > params.bullStartTwoDay) {
        bullStart = true;
        twoDayBull = true;
      }
    }

    if (bullStart && !isBullZone) {
      if (twoDayBull && i - 1 > lastBullMarkIndex) {
        lastBullMarkIndex = i - 1;
      }
      lastBullMarkIndex = i;
      isBullZone = true;
      currentBullStart = i;
      continue;
    }

    if (isBullZone) {
      const ma10Value = ma10[i];
      const breakMA10 =
        params.bullEndUseMA10 && ma10Value !== null && item.close < ma10Value;
      if (change < params.bullEndSingleDay || breakMA10) {
        isBullZone = false;
        bullZones.push({ start: currentBullStart, end: i });
        currentBullStart = -1;
      }
    }
  }

  if (isBullZone && currentBullStart >= 0) {
    bullZones.push({ start: currentBullStart, end: data.length - 1 });
  }

  const bearZones: { start: number; end: number }[] = [];
  let currentBearStart = -1;
  for (let i = 0; i < data.length; i++) {
    const inBull = bullZones.some((z) => i >= z.start && i <= z.end);
    if (!inBull) {
      if (currentBearStart === -1) {
        currentBearStart = i;
      }
    } else {
      if (currentBearStart !== -1) {
        bearZones.push({ start: currentBearStart, end: i - 1 });
        currentBearStart = -1;
      }
    }
  }
  if (currentBearStart !== -1) {
    bearZones.push({ start: currentBearStart, end: data.length - 1 });
  }

  const zones: BacktestZone[] = [];
  bullZones.forEach((z) => {
    zones.push({
      start_idx: z.start,
      end_idx: z.end,
      start_date: data[z.start].date,
      end_date: data[z.end].date,
      type: 'bull',
    });
  });
  bearZones.forEach((z) => {
    zones.push({
      start_idx: z.start,
      end_idx: z.end,
      start_date: data[z.start].date,
      end_date: data[z.end].date,
      type: 'bear',
    });
  });

  zones.sort((a, b) => a.start_idx - b.start_idx);
  return zones;
}

function getClose(df: KLineData[], date: string): number | null {
  const item = df.find((d) => d.date === date);
  return item ? item.close : null;
}

function getPrevDate(amv: KLineData[], date: string): string | null {
  const idx = amv.findIndex((d) => d.date === date);
  if (idx <= 0) return null;
  return amv[idx - 1].date;
}

/** 根据ETF名称获取对应板块在指定日期的资金流向排名 */
function getMoneyflowRank(
  etfName: string,
  date: string,
  moneyflowMap: Map<string, MoneyflowData[]>,
): number | null {
  const industries = ETF_TO_INDUSTRY[etfName];
  if (!industries || industries.length === 0) return null;

  const dateData = moneyflowMap.get(date);
  if (!dateData) return null;

  // 找到该ETF对应的所有板块中净流入最高的排名
  let bestRank: number | null = null;
  for (const industry of industries) {
    const item = dateData.find((d) => d.industry_name === industry);
    if (item && item.rank > 0) {
      if (bestRank === null || item.rank < bestRank) {
        bestRank = item.rank;
      }
    }
  }
  return bestRank;
}

/** 根据ETF名称获取对应板块在指定日期的净流入和板块名 */
function getMoneyflowInflow(
  etfName: string,
  date: string,
  moneyflowMap: Map<string, MoneyflowData[]>,
): { inflow: number; industryName: string } | null {
  const industries = ETF_TO_INDUSTRY[etfName];
  if (!industries || industries.length === 0) return null;

  const dateData = moneyflowMap.get(date);
  if (!dateData) return null;

  // 找到该ETF对应的所有板块中净流入最高的值
  let maxInflow: number | null = null;
  let bestIndustry = '';
  for (const industry of industries) {
    const item = dateData.find((d) => d.industry_name === industry);
    if (item && item.net_inflow !== undefined && !isNaN(item.net_inflow)) {
      if (maxInflow === null || item.net_inflow > maxInflow) {
        maxInflow = item.net_inflow;
        bestIndustry = industry;
      }
    }
  }
  if (maxInflow === null) return null;
  return { inflow: maxInflow, industryName: bestIndustry };
}

/** 根据ETF名称获取指定日期同花顺概念资金流向中该ETF相关概念的净流入和概念名 */
function getConceptInflow(
  etfName: string,
  date: string,
  conceptMap: Map<string, MoneyflowData[]>,
): { inflow: number; industryName: string } | null {
  const dateData = conceptMap.get(date);
  if (!dateData) return null;

  // 找到该ETF对应的所有概念中净流入最高的值（CSV 中已包含 etf_name 映射）
  let maxInflow: number | null = null;
  let bestConcept = '';
  for (const item of dateData) {
    if (item.etf_name !== etfName) continue;
    if (item.net_inflow !== undefined && !isNaN(item.net_inflow)) {
      if (maxInflow === null || item.net_inflow > maxInflow) {
        maxInflow = item.net_inflow;
        bestConcept = item.industry_name;
      }
    }
  }
  if (maxInflow === null) return null;
  return { inflow: maxInflow, industryName: bestConcept };
}

export function runBacktest(
  amvData: KLineData[],
  etfData: ExtraSeries[],
  params: StrategyParams = DEFAULT_STRATEGY_PARAMS,
  moneyflowData?: MoneyflowData[],
  conceptMoneyflowData?: MoneyflowData[],
  indMoneyflowData?: MoneyflowData[],
): BacktestResult {
  const { startYear, endYear, weights, bearStartYear, rankingMethod } = params;

  // 过滤到指定年份区间
  const filteredAMV = amvData.filter((d) => {
    const year = parseInt(d.date.split('-')[0], 10);
    return year >= startYear && year <= endYear;
  });

  const zones = identifyZones(filteredAMV, params);
  const etfMap = new Map<string, KLineData[]>();
  etfData.forEach((s) => {
    if (!s.id.startsWith('sh')) {
      etfMap.set(s.name, s.data);
    }
  });

  // 构建资金流向数据映射
  const moneyflowMap = new Map<string, MoneyflowData[]>();
  if (moneyflowData && moneyflowData.length > 0) {
    moneyflowData.forEach((item) => {
      const dateKey = item.date.replace(/-/g, '');
      if (!moneyflowMap.has(dateKey)) {
        moneyflowMap.set(dateKey, []);
      }
      moneyflowMap.get(dateKey)!.push(item);
    });
  }

  // 构建概念资金流向数据映射
  const conceptMoneyflowMap = new Map<string, MoneyflowData[]>();
  if (conceptMoneyflowData && conceptMoneyflowData.length > 0) {
    conceptMoneyflowData.forEach((item) => {
      const dateKey = item.date.replace(/-/g, '');
      if (!conceptMoneyflowMap.has(dateKey)) {
        conceptMoneyflowMap.set(dateKey, []);
      }
      conceptMoneyflowMap.get(dateKey)!.push(item);
    });
  }

  // 构建同花顺行业资金流向数据映射
  const indMoneyflowMap = new Map<string, MoneyflowData[]>();
  if (indMoneyflowData && indMoneyflowData.length > 0) {
    indMoneyflowData.forEach((item) => {
      const dateKey = item.date.replace(/-/g, '');
      if (!indMoneyflowMap.has(dateKey)) {
        indMoneyflowMap.set(dateKey, []);
      }
      indMoneyflowMap.get(dateKey)!.push(item);
    });
  }

  const trades: BacktestTrade[] = [];

  zones.forEach((zone) => {
    const startDate = zone.start_date;
    const endDate = zone.end_date;

    if (zone.type === 'bull') {
      const prevDate = getPrevDate(filteredAMV, startDate);
      if (!prevDate) return;

      let topN: { name: string; day_change: number }[] = [];

      if (rankingMethod === 'ths_moneyflow' && indMoneyflowMap.size > 0) {
        // 使用同花顺行业流入量排名
        const inflows: {
          name: string;
          day_change: number;
          inflow: number;
          industry_name: string;
        }[] = [];
        const dateKey = startDate.replace(/-/g, '');
        etfMap.forEach((data, name) => {
          if (name === BANK_ETF_NAME) return;
          const result = getConceptInflow(name, dateKey, indMoneyflowMap);
          if (result !== null) {
            inflows.push({
              name,
              day_change: result.inflow,
              inflow: result.inflow,
              industry_name: result.industryName,
            });
          }
        });

        topN = inflows
          .filter((g) => !isNaN(g.inflow))
          .sort((a, b) => b.inflow - a.inflow)
          .slice(0, weights.length)
          .map(({ name, day_change, industry_name }) => ({
            name,
            day_change,
            industry_name,
          }));
      } else if (rankingMethod === 'dc_moneyflow' && moneyflowMap.size > 0) {
        // 使用东财板块流入量排名
        const inflows: {
          name: string;
          day_change: number;
          inflow: number;
          industry_name: string;
        }[] = [];
        const dateKey = startDate.replace(/-/g, '');
        etfMap.forEach((data, name) => {
          if (name === BANK_ETF_NAME) return;
          // 获取该ETF在多头启动日的资金流向（使用startDate查询）
          const result = getMoneyflowInflow(name, dateKey, moneyflowMap);
          if (result !== null) {
            inflows.push({
              name,
              day_change: result.inflow,
              inflow: result.inflow,
              industry_name: result.industryName,
            });
          }
        });

        topN = inflows
          .filter((g) => !isNaN(g.inflow))
          .sort((a, b) => b.inflow - a.inflow)
          .slice(0, weights.length)
          .map(({ name, day_change, industry_name }) => ({
            name,
            day_change,
            industry_name,
          }));
      } else if (
        rankingMethod === 'ths_concept' &&
        conceptMoneyflowMap.size > 0
      ) {
        // 使用同花顺概念流入量排名
        const inflows: {
          name: string;
          day_change: number;
          inflow: number;
          industry_name: string;
        }[] = [];
        const dateKey = startDate.replace(/-/g, '');
        etfMap.forEach((data, name) => {
          if (name === BANK_ETF_NAME) return;
          const result = getConceptInflow(name, dateKey, conceptMoneyflowMap);
          if (result !== null) {
            inflows.push({
              name,
              day_change: result.inflow,
              inflow: result.inflow,
              industry_name: result.industryName,
            });
          }
        });

        topN = inflows
          .filter((g) => !isNaN(g.inflow))
          .sort((a, b) => b.inflow - a.inflow)
          .slice(0, weights.length)
          .map(({ name, day_change, industry_name }) => ({
            name,
            day_change,
            industry_name,
          }));
      } else {
        // 使用ETF涨幅排名（原有逻辑）
        const gains: { name: string; day_change: number }[] = [];
        etfMap.forEach((data, name) => {
          if (name === BANK_ETF_NAME) return;
          const prevClose = getClose(data, prevDate);
          const startClose = getClose(data, startDate);
          if (prevClose === null || startClose === null || prevClose === 0)
            return;
          const dayChange = ((startClose - prevClose) / prevClose) * 100;
          gains.push({ name, day_change: dayChange });
        });

        topN = gains
          .filter((g) => !isNaN(g.day_change))
          .sort((a, b) => b.day_change - a.day_change)
          .slice(0, weights.length);
      }

      // 构建持仓：如果 topN 中的 ETF 缺少 start/end 价格数据，用候选池中的下一个补上
      // 先把所有候选收集起来，过滤有完整价格数据的
      const rankedCandidates = topN.map((item) => ({
        item,
      }));

      // 补充候选：对于资金流向排名方式，如果 topN 中因缺少价格数据被跳过，从原候选池补
      const backupCandidates: {
        item: { name: string; day_change: number; industry_name?: string };
      }[] = [];
      if (rankingMethod !== 'etf_gain') {
        const allCandidates = ((): {
          name: string;
          day_change: number;
          industry_name?: string;
        }[] => {
          const dateKey = startDate.replace(/-/g, '');
          if (rankingMethod === 'ths_moneyflow' && indMoneyflowMap.size > 0) {
            const list: {
              name: string;
              day_change: number;
              industry_name?: string;
            }[] = [];
            etfMap.forEach((_data, name) => {
              if (name === BANK_ETF_NAME) return;
              const r = getConceptInflow(name, dateKey, indMoneyflowMap);
              if (r !== null)
                list.push({
                  name,
                  day_change: r.inflow,
                  industry_name: r.industryName,
                });
            });
            return list.sort((a, b) => b.day_change - a.day_change);
          } else if (
            rankingMethod === 'dc_moneyflow' &&
            moneyflowMap.size > 0
          ) {
            const list: {
              name: string;
              day_change: number;
              industry_name?: string;
            }[] = [];
            etfMap.forEach((_data, name) => {
              if (name === BANK_ETF_NAME) return;
              const r = getMoneyflowInflow(name, dateKey, moneyflowMap);
              if (r !== null)
                list.push({
                  name,
                  day_change: r.inflow,
                  industry_name: r.industryName,
                });
            });
            return list.sort((a, b) => b.day_change - a.day_change);
          } else if (
            rankingMethod === 'ths_concept' &&
            conceptMoneyflowMap.size > 0
          ) {
            const list: {
              name: string;
              day_change: number;
              industry_name?: string;
            }[] = [];
            etfMap.forEach((_data, name) => {
              if (name === BANK_ETF_NAME) return;
              const r = getConceptInflow(name, dateKey, conceptMoneyflowMap);
              if (r !== null)
                list.push({
                  name,
                  day_change: r.inflow,
                  industry_name: r.industryName,
                });
            });
            return list.sort((a, b) => b.day_change - a.day_change);
          }
          return [];
        })();
        const topNames = new Set(topN.map((t) => t.name));
        for (const c of allCandidates) {
          if (topNames.has(c.name)) continue;
          backupCandidates.push({ item: c });
        }
      }

      let totalReturn = 0;
      const holdings: BacktestHolding[] = [];

      const getSectorClose = (
        industryName: string,
        date: string,
        map: Map<string, MoneyflowData[]>,
      ): number | null => {
        const dateKey = date.replace(/-/g, '');
        const list = map.get(dateKey);
        if (!list) return null;
        const item = list.find((d) => d.industry_name === industryName);
        if (
          !item ||
          item.close === undefined ||
          isNaN(item.close) ||
          item.close === 0
        )
          return null;
        return item.close;
      };

      const tryAddHolding = (
        item: { name: string; day_change: number; industry_name?: string },
        weightPct: number,
      ) => {
        let startClose: number | null = null;
        let endClose: number | null = null;
        let useSectorPrice = false;

        const data = etfMap.get(item.name);
        if (data) {
          startClose = getClose(data, startDate);
          endClose = getClose(data, endDate);
        }

        // 如果ETF数据缺失，尝试用板块指数收盘价
        if (
          (startClose === null || endClose === null || startClose === 0) &&
          item.industry_name
        ) {
          let map: Map<string, MoneyflowData[]> | null = null;
          if (rankingMethod === 'dc_moneyflow') map = moneyflowMap;
          else if (rankingMethod === 'ths_concept') map = conceptMoneyflowMap;
          else if (rankingMethod === 'ths_moneyflow') map = indMoneyflowMap;

          if (map && map.size > 0) {
            const sectorStart = getSectorClose(
              item.industry_name,
              startDate,
              map,
            );
            const sectorEnd = getSectorClose(item.industry_name, endDate, map);
            if (
              sectorStart !== null &&
              sectorEnd !== null &&
              sectorStart !== 0
            ) {
              startClose = sectorStart;
              endClose = sectorEnd;
              useSectorPrice = true;
            }
          }
        }

        if (startClose === null || endClose === null || startClose === 0)
          return false;

        const holdingReturn = endClose / startClose - 1;
        const weight = weightPct / 100;
        totalReturn += weight * holdingReturn;
        holdings.push({
          name: item.name,
          weight,
          day_change: item.day_change,
          holding_return: holdingReturn,
          industry_name: item.industry_name,
        });
        return true;
      };

      // 先按排名顺序尝试，权重按实际持仓位置分配
      for (const c of rankedCandidates) {
        if (holdings.length >= weights.length) break;
        const weightPct = weights[holdings.length] ?? 0;
        tryAddHolding(c.item, weightPct);
      }

      // 如果持仓不够，从替补池补
      if (holdings.length < weights.length && backupCandidates.length > 0) {
        const prevDate = getPrevDate(filteredAMV, startDate);
        for (const bc of backupCandidates) {
          if (holdings.length >= weights.length) break;
          const data = etfMap.get(bc.item.name);
          if (!data) continue;
          // 计算ETF启动日涨幅作为兜底 day_change
          if (prevDate) {
            const prevClose = getClose(data, prevDate);
            const startClose = getClose(data, startDate);
            if (prevClose !== null && startClose !== null && prevClose !== 0) {
              bc.item.day_change = ((startClose - prevClose) / prevClose) * 100;
            }
          }
          const weightPct = weights[holdings.length] ?? 0;
          tryAddHolding(bc.item, weightPct);
        }
      }

      // 如果还是不够，用 etf_gain 排名兜底
      if (holdings.length < weights.length) {
        const prevDate = getPrevDate(filteredAMV, startDate);
        const fallbackGains: { name: string; day_change: number }[] = [];
        etfMap.forEach((data, name) => {
          if (name === BANK_ETF_NAME) return;
          if (holdings.some((h) => h.name === name)) return;
          const prevClose = prevDate ? getClose(data, prevDate) : null;
          const startClose = getClose(data, startDate);
          if (prevClose === null || startClose === null || prevClose === 0)
            return;
          fallbackGains.push({
            name,
            day_change: ((startClose - prevClose) / prevClose) * 100,
          });
        });
        fallbackGains
          .filter((g) => !isNaN(g.day_change))
          .sort((a, b) => b.day_change - a.day_change)
          .forEach((g) => {
            if (holdings.length >= weights.length) return;
            const weightPct = weights[holdings.length] ?? 0;
            tryAddHolding(g, weightPct);
          });
      }

      const amvStartClose = getClose(filteredAMV, startDate);
      const amvEndClose = getClose(filteredAMV, endDate);
      const amvReturn =
        amvStartClose !== null && amvEndClose !== null && amvStartClose !== 0
          ? amvEndClose / amvStartClose - 1
          : 0;

      trades.push({
        type: 'bull',
        start_date: startDate,
        end_date: endDate,
        year: parseInt(startDate.split('-')[0], 10),
        return: totalReturn,
        amv_return: amvReturn,
        holdings,
      });
    } else {
      // 从指定年份开始，空头区间才买入银行 ETF
      const zoneStartYear = parseInt(startDate.split('-')[0], 10);
      if (zoneStartYear < bearStartYear) return;

      const data = etfMap.get(BANK_ETF_NAME);
      if (!data) return;
      const startClose = getClose(data, startDate);
      const endClose = getClose(data, endDate);
      if (startClose === null || endClose === null || startClose === 0) return;
      const holdingReturn = endClose / startClose - 1;

      const amvStartClose = getClose(filteredAMV, startDate);
      const amvEndClose = getClose(filteredAMV, endDate);
      const amvReturn =
        amvStartClose !== null && amvEndClose !== null && amvStartClose !== 0
          ? amvEndClose / amvStartClose - 1
          : 0;

      trades.push({
        type: 'bear',
        start_date: startDate,
        end_date: endDate,
        year: zoneStartYear,
        return: holdingReturn,
        amv_return: amvReturn,
        holdings: [
          { name: BANK_ETF_NAME, weight: 1, holding_return: holdingReturn },
        ],
      });
    }
  });

  const tradesSorted = [...trades].sort((a, b) =>
    a.start_date.localeCompare(b.start_date),
  );
  const yearNav = new Map<number, number>();
  let currentNav = 1;

  tradesSorted.forEach((t) => {
    if (!yearNav.has(t.year)) {
      yearNav.set(t.year, currentNav);
    }
    yearNav.set(t.year, yearNav.get(t.year)! * (1 + t.return));
    currentNav = yearNav.get(t.year)!;
  });

  const maxYear = Math.max(startYear, endYear, ...yearNav.keys());
  const yearResults: BacktestYearResult[] = [];
  let prevYearEndNav = 1;

  // 计算每年多头/空头区间收益率
  const bullYearNav = new Map<number, number>();
  const bearYearNav = new Map<number, number>();
  trades.forEach((t) => {
    const y = t.year;
    if (t.type === 'bull') {
      bullYearNav.set(y, (bullYearNav.get(y) ?? 1) * (1 + t.return));
    } else {
      bearYearNav.set(y, (bearYearNav.get(y) ?? 1) * (1 + t.return));
    }
  });

  for (let y = startYear; y <= maxYear; y++) {
    const endNav = yearNav.has(y) ? yearNav.get(y)! : prevYearEndNav;
    const annualReturn = endNav / prevYearEndNav - 1;
    const bullNav = bullYearNav.get(y);
    const bearNav = bearYearNav.get(y);
    yearResults.push({
      year: y,
      start_nav: parseFloat(prevYearEndNav.toFixed(4)),
      end_nav: parseFloat(endNav.toFixed(4)),
      annual_return: parseFloat((annualReturn * 100).toFixed(2)),
      bull_return:
        bullNav !== undefined
          ? parseFloat(((bullNav - 1) * 100).toFixed(2))
          : undefined,
      bear_return:
        bearNav !== undefined
          ? parseFloat(((bearNav - 1) * 100).toFixed(2))
          : undefined,
    });
    prevYearEndNav = endNav;
  }

  const finalNav =
    yearResults.length > 0 ? yearResults[yearResults.length - 1].end_nav : 1;
  const totalReturn = finalNav - 1;

  // 计算每日净值序列
  const navSeries: BacktestNavPoint[] = [];
  let nav = 1;

  const tradeByZone = new Map<string, BacktestTrade>();
  trades.forEach((t) => {
    tradeByZone.set(`${t.start_date}_${t.end_date}`, t);
  });

  const dateToTrade = new Map<string, BacktestTrade>();
  zones.forEach((zone) => {
    const trade = tradeByZone.get(`${zone.start_date}_${zone.end_date}`);
    if (!trade) return;
    for (
      let i = zone.start_idx;
      i <= zone.end_idx && i < filteredAMV.length;
      i++
    ) {
      dateToTrade.set(filteredAMV[i].date, trade);
    }
  });

  const holdingDataMap = new Map<string, Map<string, Map<string, KLineData>>>();
  trades.forEach((t) => {
    const holdingMap = new Map<string, Map<string, KLineData>>();
    t.holdings.forEach((h) => {
      const data = etfMap.get(h.name);
      if (data) {
        const dateMap = new Map<string, KLineData>();
        data.forEach((d) => dateMap.set(d.date, d));
        holdingMap.set(h.name, dateMap);
      }
    });
    holdingDataMap.set(`${t.start_date}_${t.end_date}`, holdingMap);
  });

  // 找到所有 ETF 和 AMV 的最晚日期，以及最后一个区间的结束日期，取最大者
  let lastDate = filteredAMV[filteredAMV.length - 1]?.date || '';
  zones.forEach((z) => {
    if (z.end_date > lastDate) lastDate = z.end_date;
  });
  etfData.forEach((s) => {
    if (s.data.length > 0) {
      const d = s.data[s.data.length - 1].date;
      if (d > lastDate) lastDate = d;
    }
  });

  // 生成从 filteredAMV 第一天到最后日期的所有日期序列
  const allDates: string[] = [];
  const dateSet = new Set<string>();
  filteredAMV.forEach((d) => dateSet.add(d.date));
  etfData.forEach((s) => s.data.forEach((d) => dateSet.add(d.date)));
  Array.from(dateSet)
    .filter((d) => d >= (filteredAMV[0]?.date || '') && d <= lastDate)
    .sort()
    .forEach((d) => allDates.push(d));

  const dateToPrevDate = new Map<string, string>();
  for (let i = 1; i < allDates.length; i++) {
    dateToPrevDate.set(allDates[i], allDates[i - 1]);
  }

  for (let i = 0; i < allDates.length; i++) {
    const date = allDates[i];
    if (i === 0) {
      navSeries.push({ date, nav });
      continue;
    }
    const prevDate = allDates[i - 1];
    const trade = dateToTrade.get(date);
    const prevTrade = dateToTrade.get(prevDate);

    if (trade && trade === prevTrade) {
      const holdingMap = holdingDataMap.get(
        `${trade.start_date}_${trade.end_date}`,
      );
      if (holdingMap) {
        let dailyReturn = 0;
        trade.holdings.forEach((h) => {
          const dateMap = holdingMap.get(h.name);
          if (!dateMap) return;
          const prevClose = dateMap.get(prevDate)?.close;
          const curClose = dateMap.get(date)?.close;
          if (prevClose && curClose && prevClose !== 0) {
            dailyReturn += h.weight * (curClose / prevClose - 1);
          }
        });
        nav = nav * (1 + dailyReturn);
      }
    }
    navSeries.push({ date, nav: parseFloat(nav.toFixed(6)) });
  }

  // 计算基准 ETF（上证50、沪深300、中证2000）在多头区间的买入持有收益
  const bullZonesOnly = zones.filter((z) => z.type === 'bull');
  const benchmarkETFs: { name: string; code: string }[] = [
    { name: '上证50ETF', code: '510050' },
    { name: '沪深300ETF', code: '510300' },
    { name: '中证2000ETF', code: '563300' },
  ];
  const benchmarkReturns: BenchmarkReturn[] = benchmarkETFs.map((b) => {
    const data = etfMap.get(b.name);
    let totalReturn = 0;
    let hasAnyTrade = false;
    const yearReturns = new Map<number, number[]>();

    bullZonesOnly.forEach((zone) => {
      const startClose = data ? getClose(data, zone.start_date) : null;
      const endClose = data ? getClose(data, zone.end_date) : null;
      if (startClose !== null && endClose !== null && startClose !== 0) {
        const r = endClose / startClose - 1;
        totalReturn = (1 + totalReturn) * (1 + r) - 1;
        hasAnyTrade = true;
        const y = parseInt(zone.start_date.split('-')[0], 10);
        if (!yearReturns.has(y)) yearReturns.set(y, []);
        yearReturns.get(y)!.push(r);
      }
    });

    const annualReturns: { year: number; return: number }[] = [];
    if (hasAnyTrade) {
      const sortedYears = [...yearReturns.keys()].sort();
      sortedYears.forEach((y) => {
        const returns = yearReturns.get(y)!;
        const annual = returns.reduce((a, b) => (1 + a) * (1 + b) - 1, 0);
        annualReturns.push({
          year: y,
          return: parseFloat((annual * 100).toFixed(2)),
        });
      });
    }

    return {
      name: b.name,
      etfCode: b.code,
      totalReturn: parseFloat(totalReturn.toFixed(4)),
      annualReturns,
    };
  });

  return {
    zones,
    trades,
    yearResults,
    totalReturn,
    finalNav,
    navSeries,
    benchmarkReturns,
  };
}
