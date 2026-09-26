import React from 'react';
import { LineChartOutlined, ExperimentOutlined } from '@ant-design/icons';

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
  menu: { locale: false },
  menuDataRender: (items: any[]) => items.map(item => ({ ...item,
    icon: React.createElement(item.path === '/indicators' ? ExperimentOutlined : LineChartOutlined),
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
