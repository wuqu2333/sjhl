declare module 'ant-design-vue' {
  import type { Plugin } from 'vue';

  const Antd: Plugin;
  export const message: {
    success(content: string): void;
    error(content: string): void;
    warning(content: string): void;
    info(content: string): void;
  };
  export default Antd;
}
