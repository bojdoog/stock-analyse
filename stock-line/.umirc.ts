import { defineConfig } from '@umijs/max';
import routes from './config/routes';

export default defineConfig({
  antd: {},
  access: {},
  model: {},
  initialState: {},
  request: {},
  layout: {
    title: '投资科学',
  },
  routes,
  npmClient: 'npm',
  history: { type: 'hash' },
  utoopack: {},
  proxy: {
    '/api/': {
      target: 'http://localhost:5000',
      changeOrigin: true,
    },
  },
});
