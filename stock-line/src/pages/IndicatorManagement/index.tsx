import { queryIndicators } from '@/services/indicators';
import type { Indicator, IndicatorQuery } from '@/services/indicators';
import { ProTable } from '@ant-design/pro-components';
import type { ActionType, ProColumns } from '@ant-design/pro-components';
import { Alert, Button, Space, Tag } from 'antd';
import React, { useRef, useState } from 'react';
import IndicatorModal from './IndicatorModal';

const columns: ProColumns<Indicator>[] = [
  { title: '指标名称', dataIndex: 'name', width: 200 },
  { title: '指标代码', dataIndex: 'code', width: 130, copyable: true },
  { title: '来源', dataIndex: 'source', width: 120, hideInSearch: true },
  {
    title: '类型',
    dataIndex: 'is_default',
    width: 110,
    hideInSearch: true,
    render: (_, record) => (
      <Tag color={record.is_default ? 'cyan' : 'default'}>
        {record.is_default ? '默认指标' : '自定义指标'}
      </Tag>
    ),
  },
  { title: '指标说明', dataIndex: 'description', width: 320, ellipsis: true, hideInSearch: true },
  {
    title: '更新时间',
    dataIndex: 'updated_at',
    valueType: 'dateTime',
    width: 190,
    hideInSearch: true,
  },
];

const IndicatorManagement: React.FC = () => {
  const actionRef = useRef<ActionType>();
  const [loadError, setLoadError] = useState(false);
  const [selected, setSelected] = useState<{ indicator: Indicator; compare: boolean }>();
  const tableColumns: ProColumns<Indicator>[] = [...columns, {
    title: '操作', valueType: 'option', width: 200, fixed: 'right',
    render: (_, record) => <Space size={12}>
      <Button type="link" style={{ padding: 0 }} onClick={() => setSelected({ indicator: record, compare: false })}>查看详情</Button>
      <Button type="link" style={{ padding: 0 }} disabled={record.is_default}
        onClick={() => setSelected({ indicator: record, compare: true })}>比对基准</Button>
    </Space>,
  }];

  return (
    <div className="research-page indicator-page">
      <header className="research-heading">
        <div><div className="eyebrow">INDICATOR LIBRARY</div><h1>指标管理</h1>
          <p>沉淀研究方法，让每一个市场判断都有据可循</p></div>
        <span className="page-stamp">研究指标库</span>
      </header>
      {loadError && (
        <Alert
          type="error"
          showIcon
          message="指标列表加载失败，请稍后重试"
          action={<Button size="small" onClick={() => actionRef.current?.reload()}>重试</Button>}
          style={{ marginBottom: 16 }}
        />
      )}
      <ProTable<Indicator, IndicatorQuery>
        actionRef={actionRef}
        rowKey="id"
        headerTitle="全部指标"
        columns={tableColumns}
        tableLayout="fixed"
        search={{ labelWidth: 'auto' }}
        pagination={{ defaultPageSize: 10, showSizeChanger: true, pageSizeOptions: [10, 20, 50, 100] }}
        scroll={{ x: 1270 }}
        request={async (params) => {
          setLoadError(false);
          return queryIndicators(params);
        }}
        onRequestError={() => setLoadError(true)}
      />
      {selected && <IndicatorModal key={`${selected.indicator.id}-${selected.compare}`}
        {...selected} onClose={() => setSelected(undefined)} />}
    </div>
  );
};

export default IndicatorManagement;
