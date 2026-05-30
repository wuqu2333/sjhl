import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

function utf8ContentTypePlugin() {
  const patchResponse = (server: { middlewares: { use: (handler: any) => void } }) => {
    server.middlewares.use((_req: any, res: any, next: () => void) => {
      const setHeader = res.setHeader.bind(res);
      res.setHeader = (name: string, value: number | string | readonly string[]) => {
        if (name.toLowerCase() === 'content-type' && typeof value === 'string' && !/charset=/i.test(value)) {
          if (/^(text\/html|text\/javascript|application\/javascript|text\/css)(;|$)/i.test(value)) {
            value = `${value}; charset=utf-8`;
          }
        }
        return setHeader(name, value);
      };
      next();
    });
  };

  return {
    name: 'utf8-content-type',
    configureServer: patchResponse,
    configurePreviewServer: patchResponse
  };
}

export default defineConfig({
  root: 'apps/web-antd',
  plugins: [tailwindcss(), utf8ContentTypePlugin(), vue()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    allowedHosts: process.env.SJHL_ALLOWED_HOSTS?.split(',') || ['127.0.0.1', 'localhost', 'frp-pen.com', '.frp-pen.com'],
    strictPort: true,
    proxy: {
      '/api': {
        target: process.env.SJHL_BACKEND_URL?.trim() || 'http://127.0.0.1:17651',
        changeOrigin: true
      }
    }
  },
  build: {
    outDir: '../../dist',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks(id) {
          const normalizedId = id.replace(/\\/g, '/');
          if (!normalizedId.includes('/node_modules/')) {
            return undefined;
          }
          if (
            normalizedId.includes('/node_modules/vue') ||
            normalizedId.includes('/node_modules/vue-router/') ||
            normalizedId.includes('/node_modules/pinia/')
          ) {
            return 'vue-vendor';
          }
          if (
            normalizedId.includes('/node_modules/ant-design-vue/') ||
            normalizedId.includes('/node_modules/@ant-design/icons-vue/')
          ) {
            return 'antd-vendor';
          }
          if (normalizedId.includes('/node_modules/@vueuse/')) {
            return 'utility-vendor';
          }
          return 'vendor';
        }
      }
    }
  }
});
