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
    name: '指标管理',
    path: '/indicators',
    component: './IndicatorManagement',
  },
];
