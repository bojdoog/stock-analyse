export default [
  {
    path: '/',
    redirect: '/active-market',
  },
  {
    name: '市场全景',
    path: '/active-market',
    component: './ActiveMarket',
  },
  {
    name: '板块活跃度',
    path: '/sector-activity',
    component: './SectorActivity',
  },
  {
    name: 'B1选股',
    path: '/b1-picks',
    component: './B1Picks',
  },
  {
    name: '国家队持仓',
    path: '/huijin-holdings',
    component: './HuijinHoldings',
  },
  {
    name: '指标管理',
    path: '/indicators',
    component: './IndicatorManagement',
  },
];
