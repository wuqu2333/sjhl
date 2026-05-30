import type { Component } from 'vue';

export interface AdminRoute {
  path: string;
  name: string;
  component: Component | (() => Promise<Component>);
  meta: {
    title: string;
    icon: string;
    order: number;
    shortTitle?: string;
  };
}
