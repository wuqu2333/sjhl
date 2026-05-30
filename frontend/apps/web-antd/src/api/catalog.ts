import { post } from './request';

export const catalogApi = {
  scan: (profileId = '') => post('/api/catalog/scan', { profileId })
};
