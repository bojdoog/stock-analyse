import { Alert, Button, Checkbox, DatePicker, Empty, Spin } from 'antd';
import dayjs from 'dayjs';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import KLineChart, { type KBar } from '../../components/KLineChart';
import '../HuijinHoldings/style.less';
import './style.less';

interface Pick {
  code: string;
  name?: string;
  board?: string;
  industry?: string;
  close: number;
  change_pct: number | null;
  j_value: number | null;
  volume: number | null;
}

interface PickGroup {
  date: string;
  count: number;
  j_threshold: number | null;
  boards: string[];
  created_at: string | null;
}

interface StockBasic {
  date: string;
  close: number | null;
  turnover_rate: number | null;
  pe_ttm: number | null;
  pb: number | null;
  total_mv: number | null;
  circ_mv: number | null;
  float_share: number | null;
  volume_ratio: number | null;
}

const BOARD_LABEL: Record<string, string> = { gem: '创业板', star: '科创板', bj: '北交所' };
const boardText = (boards: string[]) =>
  boards.length ? `排除${boards.map((item) => BOARD_LABEL[item] || item).join('、')}` : '全部板块';

interface JobSnapshot {
  id: string;
  kind: 'fetch' | 'b1';
  title: string;
  status: 'running' | 'done' | 'error' | 'cancelled';
  progress: number;
  elapsed: number;
  logs: string[];
  nextSince: number;
  result: { date?: string; count?: number } | null;
  wait: { left: number; total: number } | null;
  stage: '下载' | '入库' | null;
  stagePercent: number;
  stageDone: number;
  stageTotal: number;
  options: { boards?: { gem?: boolean; star?: boolean }; jThreshold?: number; date?: string } | null;
}

type JobKind = 'fetch' | 'b1';

const JOB_STATUS_TEXT: Record<JobSnapshot['status'], string> = {
  running: '运行中',
  done: '已完成',
  error: '失败',
  cancelled: '已取消',
};

const UP = '#c45e65';
const DOWN = '#238672';
const FLAT = '#7a898f';

const changeColor = (value: number | null | undefined) =>
  value == null || value === 0 ? FLAT : value > 0 ? UP : DOWN;

const formatPercent = (value: number | null | undefined) =>
  value == null ? '--' : `${value > 0 ? '+' : ''}${value.toFixed(2)}%`;

// 市值单位换算：Tushare 返回万元，这里统一显示为亿元。
const formatMoney = (value: number | null | undefined) =>
  value == null ? '—' : `${(value / 10000).toFixed(2)}亿`;

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`请求失败（${response.status}）`);
  return response.json();
}

const B1Picks: React.FC = () => {
  const [picks, setPicks] = useState<Pick[]>([]);
  const [asOf, setAsOf] = useState('');
  const [selected, setSelected] = useState('');
  const [bars, setBars] = useState<KBar[]>([]);
  const [basic, setBasic] = useState<StockBasic | null>(null);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingBars, setLoadingBars] = useState(false);
  const [error, setError] = useState('');
  const [consoleOpen, setConsoleOpen] = useState(true);
  const [consoleHeight, setConsoleHeight] = useState(240);
  const [resizing, setResizing] = useState(false);
  const [activeKind, setActiveKind] = useState<JobKind>('fetch');
  const [boardGem, setBoardGem] = useState(false);
  const [boardStar, setBoardStar] = useState(false);
  const [jThreshold, setJThreshold] = useState(15);
  const [pickDate, setPickDate] = useState('');
  const [groups, setGroups] = useState<PickGroup[]>([]);
  const [expanded, setExpanded] = useState('');
  const [jobs, setJobs] = useState<Record<JobKind, JobSnapshot | null>>({ fetch: null, b1: null });
  const [logsMap, setLogsMap] = useState<Record<JobKind, string[]>>({ fetch: [], b1: [] });
  const [followLog, setFollowLog] = useState(true);
  const logBoxRef = useRef<HTMLDivElement>(null);
  const sinceRef = useRef<Record<JobKind, number>>({ fetch: 0, b1: 0 });
  const job = jobs[activeKind];
  const logs = logsMap[activeKind];

  const loadPicks = useCallback((date?: string) => {
    setLoadingList(true);
    const query = date ? `?date=${encodeURIComponent(date)}` : '';
    return fetchJson<{ data: Pick[]; meta: { date: string } }>(`/api/b1-picks${query}`)
      .then((result) => {
        const rows = result.data || [];
        setPicks(rows);
        setAsOf(result.meta?.date || '');
        if (rows.length) setSelected((prev) => (rows.some((item) => item.code === prev) ? prev : rows[0].code));
      })
      .catch(() => setError('B1 选股结果加载失败，请确认后端已启动且个股日线已入库。'))
      .finally(() => setLoadingList(false));
  }, []);

  const loadHistory = useCallback((openDate?: string) => {
    fetchJson<{ data: PickGroup[]; date?: string }>('/api/b1-picks/history')
      .then((result) => {
        const rows = result.data || [];
        setGroups(rows);
        // 初始化日期取个股日线最新交易日，用户手动改过则保留其选择。
        if (result.date) setPickDate((prev) => prev || result.date || '');
        const target = openDate && rows.some((item) => item.date === openDate)
          ? openDate : (rows[0]?.date || '');
        setExpanded(target);
        if (target) {
          loadPicks(target);
        } else {
          setPicks([]);
          setAsOf('');
        }
      })
      .catch(() => undefined);
  }, [loadPicks]);

  const toggleGroup = useCallback((date: string) => {
    if (date === expanded) {
      setExpanded('');
      return;
    }
    setExpanded(date);
    loadPicks(date);
  }, [expanded, loadPicks]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  // 页面重新打开时：优先恢复运行中的任务，否则展示两类任务上一次的执行记录。
  useEffect(() => {
    fetchJson<{ running: JobSnapshot[]; last: Record<string, JobSnapshot> }>('/api/console/state')
      .then((result) => {
        const runningByKind: Partial<Record<JobKind, JobSnapshot>> = {};
        (result.running || []).forEach((item) => { runningByKind[item.kind] = item; });
        const nextJobs: Record<JobKind, JobSnapshot | null> = { fetch: null, b1: null };
        const nextLogs: Record<JobKind, string[]> = { fetch: [], b1: [] };
        (['fetch', 'b1'] as JobKind[]).forEach((kind) => {
          const snapshot = runningByKind[kind] || result.last?.[kind] || null;
          nextJobs[kind] = snapshot;
          nextLogs[kind] = snapshot?.logs || [];
          sinceRef.current[kind] = snapshot?.nextSince || 0;
        });
        setJobs(nextJobs);
        setLogsMap(nextLogs);
        const runningKind = (['fetch', 'b1'] as JobKind[]).find((kind) => runningByKind[kind]);
        if (runningKind) {
          setActiveKind(runningKind);
          setConsoleOpen(true);
        }
      })
      .catch(() => undefined);
  }, []);

  // 控制台任务轮询：每类任务的运行状态独立轮询，互不影响。
  useEffect(() => {
    const targets = (['fetch', 'b1'] as JobKind[])
      .map((kind) => ({ kind, id: jobs[kind]?.status === 'running' ? jobs[kind]!.id : '' }))
      .filter((item) => item.id);
    if (!targets.length) return undefined;
    const timer = window.setInterval(() => {
      targets.forEach(({ kind, id }) => {
        fetchJson<{ job: JobSnapshot }>(`/api/console/jobs/${id}?since=${sinceRef.current[kind]}`)
          .then((result) => {
            sinceRef.current[kind] = result.job.nextSince;
            setJobs((prev) => ({ ...prev, [kind]: result.job }));
            setLogsMap((prev) => ({ ...prev, [kind]: [...prev[kind], ...result.job.logs] }));
            if (result.job.status === 'done' && result.job.kind === 'b1') loadHistory(result.job.result?.date);
          })
          .catch(() => setLogsMap((prev) => ({ ...prev, [kind]: [...prev[kind], '任务状态读取失败（后端可能已重启）'] })));
      });
    }, 1000);
    return () => window.clearInterval(timer);
  }, [jobs.fetch?.id, jobs.fetch?.status, jobs.b1?.id, jobs.b1?.status, loadHistory]);

  useEffect(() => {
    if (followLog && logBoxRef.current) logBoxRef.current.scrollTop = logBoxRef.current.scrollHeight;
  }, [logs, followLog, activeKind]);

  const handleLogScroll = () => {
    const box = logBoxRef.current;
    if (!box) return;
    setFollowLog(box.scrollHeight - box.scrollTop - box.clientHeight < 24);
  };

  const scrollLogBottom = () => {
    const box = logBoxRef.current;
    if (box) box.scrollTop = box.scrollHeight;
    setFollowLog(true);
  };

  // 拖动控制台顶部横线调整日志区高度（鼠标变为上下箭头）。
  const startResize = (event: React.MouseEvent<HTMLDivElement>) => {
    event.preventDefault();
    const startY = event.clientY;
    const startHeight = consoleHeight;
    setResizing(true);
    const onMove = (moveEvent: MouseEvent) => {
      const next = startHeight + (startY - moveEvent.clientY);
      const limit = Math.max(200, window.innerHeight - 220);
      setConsoleHeight(Math.min(Math.max(next, 120), limit));
    };
    const onUp = () => {
      setResizing(false);
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  const startJob = async (kind: JobKind) => {
    const date = pickDate || groups[0]?.date || '';
    setConsoleOpen(true);
    setActiveKind(kind);
    setFollowLog(true);
    setLogsMap((prev) => ({ ...prev, [kind]: [] }));
    sinceRef.current[kind] = 0;
    const response = await fetch(`/api/console/${kind}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        options: {
          boards: { gem: boardGem, star: boardStar },
          jThreshold,
          ...(kind === 'b1' && date ? { date } : {}),
        },
      }),
    });
    const result = await response.json();
    if (!response.ok) {
      setLogsMap((prev) => ({ ...prev, [kind]: [`启动任务失败：${result.message || response.status}`] }));
      return;
    }
    setJobs((prev) => ({ ...prev, [kind]: result.job }));
    setLogsMap((prev) => ({ ...prev, [kind]: result.job.logs || [] }));
    sinceRef.current[kind] = result.job.nextSince || 0;
  };

  const cancelJob = async (kind: JobKind) => {
    const target = jobs[kind];
    if (!target || target.status !== 'running') return;
    const response = await fetch(`/api/console/jobs/${target.id}/cancel`, { method: 'POST' });
    const result = await response.json();
    if (!response.ok || !result.job) {
      setLogsMap((prev) => ({ ...prev, [kind]: [...prev[kind], `取消失败：${result.message || response.status}`] }));
      return;
    }
    const fresh = (result.job.logs || []).slice(sinceRef.current[kind]);
    sinceRef.current[kind] = result.job.nextSince || 0;
    setJobs((prev) => ({ ...prev, [kind]: result.job }));
    if (fresh.length) setLogsMap((prev) => ({ ...prev, [kind]: [...prev[kind], ...fresh] }));
  };

  useEffect(() => {
    if (!selected) return;
    setLoadingBars(true);
    fetchJson<{ data: KBar[] }>(`/api/kline/stock/${encodeURIComponent(selected)}`)
      .then((result) => setBars(result.data || []))
      .catch(() => {
        setBars([]);
        setError('该股票的日 K 数据加载失败。');
      })
      .finally(() => setLoadingBars(false));
  }, [selected]);

  // 个股每日指标：取选股日（含）之前最新一条，用于日 K 上方信息条。
  useEffect(() => {
    if (!selected) {
      setBasic(null);
      return;
    }
    const query = asOf ? `?date=${encodeURIComponent(asOf)}` : '';
    fetchJson<{ data: StockBasic | null }>(`/api/stocks/${encodeURIComponent(selected)}/basic${query}`)
      .then((result) => setBasic(result.data))
      .catch(() => setBasic(null));
  }, [selected, asOf]);

  const current = useMemo(() => picks.find((item) => item.code === selected), [picks, selected]);

  // 底部状态行：拉取数据用下载/入库进度，B1 选股用计算进度，运行结束显示任务状态。
  const stagePercent = !job
    ? 0
    : job.kind === 'fetch'
      ? Math.max(0, Math.round(job.stagePercent || 0))
      : Math.max(0, Math.round(job.progress || 0));
  const stageLabel = !job
    ? ''
    : job.status !== 'running'
      ? JOB_STATUS_TEXT[job.status]
      : job.kind === 'fetch'
        ? (job.wait && job.wait.total > 0 ? '等待中' : (job.stage === '入库' ? '入库中' : '拉取中'))
        : '筛选中';
  const stageMeta = !job
    ? ''
    : job.kind === 'fetch'
      ? (job.stage
        ? `${job.stage} ${job.stagePercent}%（${job.stageDone}/${job.stageTotal}）`
        : `${Math.round(job.progress || 0)}%`)
      : `${Math.round(job.progress || 0)}%`;

  return (
    <div className="b1-page">
      <div className="research-page hj-page b1-main">
        <section className="hj-panel hj-list-panel">
          <div className="hj-panel-title b1-panel-title">
            <strong>B1 选股</strong>
            {/* <span>{picks.length} 只 · 按代码排序 · {asOf || '--'}</span> */}
          </div>
          <Spin spinning={loadingList} tip="首次计算需要十几秒">
            {groups.length ? (
              <div className="hj-list b1-groups">
                {groups.map((group) => (
                  <div key={group.date} className="b1-group">
                    <button
                      type="button"
                      className={`b1-group-head${group.date === expanded ? ' is-open' : ''}`}
                      onClick={() => toggleGroup(group.date)}
                    >
                      <span className="b1-group-date">{group.date}</span>
                      <small>{`J＜${group.j_threshold ?? 15} · ${boardText(group.boards)} · ${group.count} 只`}</small>
                      <i className="b1-group-arrow">▾</i>
                    </button>
                    {group.date === expanded && (
                      picks.length ? (
                        <div className="b1-group-body">
                          {picks.map((item, index) => (
                            <button
                              key={item.code}
                              type="button"
                              className={`hj-row${item.code === selected ? ' hj-row-active' : ''}`}
                              onClick={() => setSelected(item.code)}
                            >
                              <span className="hj-rank">{index + 1}</span>
                              <span className="hj-name">
                                <b>{item.name || item.code}</b>
                                <small>{item.code} · {item.board}{item.industry ? ` · ${item.industry}` : ''}</small>
                              </span>
                              <span className="hj-price">
                                <b style={{ color: changeColor(item.change_pct) }}>{item.close?.toFixed(2)}</b>
                                <small style={{ color: changeColor(item.change_pct) }}>{formatPercent(item.change_pct)}</small>
                              </span>
                            </button>
                          ))}
                        </div>
                      ) : (
                        <Empty className="hj-empty" description={loadingList ? '正在计算' : '该日无股票触发 B1'} />
                      )
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <Empty className="hj-empty" description={loadingList ? '正在计算' : '暂无选股记录'} />
            )}
          </Spin>
        </section>

        <section className="hj-panel hj-chart-panel">
          <div className="hj-panel-title">
            <strong>{current ? `${current.code} ${current.name || ''} 日 K` : '日 K'}</strong>
            <span>{current
              ? [current.board, current.industry, `前复权 · 截至 ${asOf || '--'}`].filter(Boolean).join(' · ')
              : '选择左侧股票查看日 K'}
              {current && <em className="b1-chart-legend"><i />紫色虚线 = B1 选股日</em>}
            </span>
          </div>
          {basic && (
            <div className="b1-stock-info">
              <span>总市值 <b>{formatMoney(basic.total_mv)}</b></span>
              <span>流通市值 <b>{formatMoney(basic.circ_mv)}</b></span>
              <span>PE(TTM) <b>{basic.pe_ttm == null ? '—' : basic.pe_ttm < 0 ? '亏损' : basic.pe_ttm.toFixed(1)}</b></span>
              <span>换手率 <b>{basic.turnover_rate == null ? '—' : `${basic.turnover_rate.toFixed(2)}%`}</b></span>
              <em>指标日期 {basic.date}</em>
            </div>
          )}
          {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 12 }} />}
          <Spin spinning={loadingBars}>
            <KLineChart bars={bars} markDate={asOf} initialBars={125} legend ariaLabel="B1 选股日K走势图" />
          </Spin>
        </section>
      </div>

      <section className={`b1-console${consoleOpen ? ' b1-console-open' : ''}${resizing ? ' is-resizing' : ''}`}>
        {consoleOpen && (
          <div className="b1-console-resizer" role="separator" aria-orientation="horizontal"
            title="拖动调整控制台高度" onMouseDown={startResize} />
        )}
        <div className="b1-console-bar">
          <div className="b1-console-tabs">
            <button type="button"
              className={`b1-console-tab${activeKind === 'fetch' ? ' is-active' : ''}`}
              onClick={() => setActiveKind('fetch')}>拉取数据</button>
            <button type="button"
              className={`b1-console-tab${activeKind === 'b1' ? ' is-active' : ''}`}
              onClick={() => setActiveKind('b1')}>B1选股</button>
          </div>
          <span className="b1-console-status">
            {job ? `${job.title} · ${JOB_STATUS_TEXT[job.status]}` : '暂无任务记录'}
            {job?.result ? ` · ${job.result.date} 共 ${job.result.count} 只` : ''}
          </span>
          <div className="b1-console-filter">
            <Checkbox checked={boardGem} onChange={(event) => setBoardGem(event.target.checked)}>创业板</Checkbox>
            <Checkbox checked={boardStar} onChange={(event) => setBoardStar(event.target.checked)}>科创板</Checkbox>
            <span>J＜</span>
            <input className="b1-console-jinput" type="number" min={0} max={100} step={1}
              value={jThreshold}
              onChange={(event) => {
                const next = Number(event.target.value);
                setJThreshold(Number.isFinite(next) ? Math.min(100, Math.max(0, next)) : 15);
              }} />
            <DatePicker className="b1-console-date" size="small" placeholder="选股日期" allowClear
              value={pickDate || groups[0]?.date ? dayjs(pickDate || groups[0]?.date) : null}
              onChange={(value) => setPickDate(value ? value.format('YYYY-MM-DD') : '')}
              disabledDate={(current) => current && current > dayjs().endOf('day')} />
          </div>
          <span className="b1-console-spacer" />
          <Button size="small" type="primary" ghost
            loading={jobs.fetch?.status === 'running'}
            disabled={jobs.fetch?.status === 'running'}
            onClick={() => startJob('fetch')}>拉取数据</Button>
          {jobs.fetch?.status === 'running' && (
            <Button size="small" danger ghost onClick={() => cancelJob('fetch')}>取消拉取</Button>
          )}
          <Button size="small" type="primary" ghost
            loading={jobs.b1?.status === 'running'}
            disabled={jobs.b1?.status === 'running'}
            onClick={() => startJob('b1')}>B1选股</Button>
          {jobs.b1?.status === 'running' && (
            <Button size="small" danger ghost onClick={() => cancelJob('b1')}>取消选股</Button>
          )}
          {job && <span className="b1-console-elapsed">{job.elapsed}s</span>}
          <Button size="small" type="text" onClick={() => setConsoleOpen((value) => !value)}>
            {consoleOpen ? '收起 ▾' : '展开 ▴'}
          </Button>
        </div>
        <div className="b1-console-body" style={{ height: consoleOpen ? consoleHeight : 0 }}>
          <div className="b1-console-log-wrap">
            <div className="b1-console-log" ref={logBoxRef} onScroll={handleLogScroll}>
              {logs.length ? logs.join('\n') : (activeKind === 'fetch'
                ? '点击「拉取数据」更新个股日线。'
                : '点击「B1选股」重新计算选股结果。')}
            </div>
            {!followLog && logs.length > 0 && (
              <button type="button" className="b1-console-jump" title="回到最新日志" onClick={scrollLogBottom}>
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor"
                  strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 5v14M6 13l6 6 6-6" />
                </svg>
              </button>
            )}
          </div>
          {job && (
            <div className="b1-console-stage">
              <div className="b1-console-stage-bar">
                <i style={{ width: `${stagePercent}%` }} />
              </div>
              <span className="b1-console-stage-label">{stageLabel}</span>
              <span className="b1-console-stage-meta">{stageMeta}</span>
            </div>
          )}
        </div>
      </section>
    </div>
  );
};

export default B1Picks;
