export default [
  {
    path: '/',
    redirect: '/active-market',
  },
  {
    name: '活跃市值(默认)',
    path: '/active-market',
    component: './ActiveMarket',
  },
  {
    name: '指标管理',
    path: '/indicators',
    component: './IndicatorManagement',
  },
];
