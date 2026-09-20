import { request } from '@umijs/max';
import type { KLineData } from '@/pages/ActiveMarket/utils/backtest';

export interface Indicator {
  id: number;
  code: string;
  name: string;
  source: string;
  description: string;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface IndicatorQuery {
  current?: number;
  pageSize?: number;
  name?: string;
  code?: string;
}

interface IndicatorListResponse {
  code: number;
  message: string;
  success: boolean;
  data: Indicator[];
  total: number;
}

export async function queryIndicators(params: IndicatorQuery) {
  const result = await request<IndicatorListResponse>('/api/indicators', {
    method: 'GET',
    params,
    skipErrorHandler: true,
  });
  if (result.code !== 0 || !result.success) {
    throw new Error(result.message || '指标列表加载失败');
  }
  return result;
}

export async function queryIndicatorData(id: number): Promise<KLineData[]> {
  const result = await request<{ code: number; message: string; data: KLineData[] }>(
    `/api/indicators/${id}/data`, { method: 'GET', skipErrorHandler: true },
  );
  if (result.code !== 0) throw new Error(result.message || '指标行情加载失败');
  return result.data;
}
