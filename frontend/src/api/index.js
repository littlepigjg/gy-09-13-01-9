import axios from 'axios'

const http = axios.create({
  baseURL: '/api',
  timeout: 10000
})

http.interceptors.response.use(
  (res) => res.data,
  (err) => Promise.reject(err)
)

export default {
  // 概览
  getOverview: () => http.get('/stats/overview'),
  // 时间线
  getLogs: (params) => http.get('/logs', { params }),
  ingest: (event) => http.post('/logs/ingest', event),
  ingestBatch: (events) => http.post('/logs/ingest/batch', events),
  // 异常
  getAnomalies: (params) => http.get('/anomalies', { params }),
  // 告警
  getAlerts: (params) => http.get('/alerts', { params }),
  updateAlertStatus: (id, status) => http.patch(`/alerts/${id}/status`, { status }),
  // 规则
  getRules: () => http.get('/rules'),
  createRule: (rule) => http.post('/rules', rule),
  updateRule: (id, rule) => http.put(`/rules/${id}`, rule),
  deleteRule: (id) => http.delete(`/rules/${id}`),
  // 用户画像
  getProfiles: () => http.get('/profiles'),
  getProfile: (userId) => http.get(`/profiles/${userId}`),
  // 基线报告
  getBaselineReport: (userId, params) => http.get(`/reports/baseline/${userId}`, { params }),
  // 通知
  getNotifications: (params) => http.get('/notifications', { params }),
  markNotificationRead: (id) => http.patch(`/notifications/${id}/read`),
  markAllNotificationsRead: () => http.patch('/notifications/read-all'),
  // 聚合统计
  getUserStats: () => http.get('/stats/users'),
  getRuleStats: () => http.get('/stats/rules')
}
