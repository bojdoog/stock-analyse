import React, { type ReactNode } from 'react';
import { Button, Result } from 'antd';

interface Props { children?: ReactNode }
interface State { error: Error | null }

/** 页面级兜底：单个页面渲染异常时保留布局与菜单，只替换内容区。 */
export default class ErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('页面渲染异常：', error, info.componentStack);
  }

  componentDidUpdate(prevProps: Props) {
    // 路由切换后自动清除错误，避免一直停留在兜底页。
    if (this.state.error && prevProps.children !== this.props.children) {
      this.setState({ error: null });
    }
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div style={{ padding: 24 }}>
        <Result
          status="error"
          title="页面渲染出错"
          subTitle={this.state.error.message || '未知错误'}
          extra={[
            <Button key="home" type="primary" onClick={() => { window.location.hash = '#/active-market'; }}>
              返回市场全景
            </Button>,
            <Button key="retry" onClick={() => this.setState({ error: null })}>重试</Button>,
          ]}
        />
      </div>
    );
  }
}
