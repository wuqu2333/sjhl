import { createApp } from 'vue';
import Alert from 'ant-design-vue/es/alert';
import Button from 'ant-design-vue/es/button';
import Card from 'ant-design-vue/es/card';
import Checkbox from 'ant-design-vue/es/checkbox';
import Descriptions from 'ant-design-vue/es/descriptions';
import Drawer from 'ant-design-vue/es/drawer';
import Empty from 'ant-design-vue/es/empty';
import Form from 'ant-design-vue/es/form';
import Input from 'ant-design-vue/es/input';
import InputNumber from 'ant-design-vue/es/input-number';
import Layout from 'ant-design-vue/es/layout';
import List from 'ant-design-vue/es/list';
import Menu from 'ant-design-vue/es/menu';
import Modal from 'ant-design-vue/es/modal';
import Progress from 'ant-design-vue/es/progress';
import Select from 'ant-design-vue/es/select';
import Space from 'ant-design-vue/es/space';
import Spin from 'ant-design-vue/es/spin';
import Switch from 'ant-design-vue/es/switch';
import Table from 'ant-design-vue/es/table';
import Tabs from 'ant-design-vue/es/tabs';
import Tag from 'ant-design-vue/es/tag';
import Upload from 'ant-design-vue/es/upload';
import { createPinia } from 'pinia';
import 'ant-design-vue/dist/reset.css';
import './style.css';
import App from './App.vue';
import { router } from './router';

const app = createApp(App);
app.use(createPinia());
[
  Alert,
  Button,
  Card,
  Checkbox,
  Descriptions,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  Layout,
  List,
  Menu,
  Modal,
  Progress,
  Select,
  Space,
  Spin,
  Switch,
  Table,
  Tabs,
  Tag,
  Upload
].forEach((component) => {
  app.use(component);
});
app.use(router);
app.mount('#app');
