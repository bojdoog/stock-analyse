import React from 'react';
import { AimOutlined, BankOutlined, ExperimentOutlined, FireOutlined, GlobalOutlined, LineChartOutlined } from '@ant-design/icons';
import ErrorBoundary from './components/ErrorBoundary';

// 左侧菜单图标：按路由指定语义图标，未登记的沿用折线图。
const MENU_ICONS: Record<string, typeof LineChartOutlined> = {
  '/active-market': GlobalOutlined,
  '/sector-activity': FireOutlined,
  '/b1-picks': AimOutlined,
  '/huijin-holdings': BankOutlined,
  '/indicators': ExperimentOutlined,
};

export async function getInitialState(): Promise<{ name: string }> {
  return { name: '研究工作台' };
}

export const antd = { theme: {
  token: {
    colorPrimary: '#167d8d', colorInfo: '#167d8d', colorText: '#22343b',
    colorTextSecondary: '#7a898f', colorBgLayout: '#f3f5f5', colorBorder: '#dfe6e7',
    borderRadius: 8, controlHeight: 36,
    fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif',
  },
} };

export const layout = () => ({
  title: '投资科学',
  logo: React.createElement('span', { className: 'brand-mark' }, React.createElement(LineChartOutlined)),
  layout: 'side', siderWidth: 224, fixedSiderbar: true,
  rightContentRender: false,
  // 页面渲染异常时由 ErrorBoundary 兜底，保留侧边栏与页面框架。
  childrenRender: (children: React.ReactNode) => React.createElement(ErrorBoundary, null, children),
  menu: { locale: false },
  menuDataRender: (items: any[]) => items.map(item => ({ ...item,
    icon: React.createElement(MENU_ICONS[item.path] ?? LineChartOutlined),
  })),
  menuFooterRender: (props: { collapsed?: boolean }) => props?.collapsed ? null : React.createElement('div', { className: 'workspace-footer' },
    React.createElement('span', { className: 'workspace-monogram' }, 'IS'),
    React.createElement('div', null, React.createElement('strong', null, '投研工作空间'), React.createElement('small', null, 'INVESTMENT SCIENCE'))),
  token: {
    sider: { colorMenuBackground: '#142b32', colorTextMenu: '#97adb3', colorTextMenuSelected: '#efffff',
      colorTextMenuActive: '#ffffff', colorBgMenuItemSelected: '#24454e', colorBgMenuItemHover: '#1d3b44', colorTextMenuTitle: '#ffffff' },
    pageContainer: { paddingInlinePageContainerContent: 0, paddingBlockPageContainerContent: 0 },
  },
});
