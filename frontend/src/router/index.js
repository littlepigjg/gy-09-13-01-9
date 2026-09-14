import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from '../views/Dashboard.vue'
import Timeline from '../views/Timeline.vue'
import Anomalies from '../views/Anomalies.vue'
import Rules from '../views/Rules.vue'
import Profiles from '../views/Profiles.vue'
import BaselineReport from '../views/BaselineReport.vue'
import Notifications from '../views/Notifications.vue'

const routes = [
  { path: '/', redirect: '/dashboard' },
  { path: '/dashboard', name: 'dashboard', component: Dashboard, meta: { title: '概览' } },
  { path: '/timeline', name: 'timeline', component: Timeline, meta: { title: '行为时间线' } },
  { path: '/anomalies', name: 'anomalies', component: Anomalies, meta: { title: '异常事件' } },
  { path: '/rules', name: 'rules', component: Rules, meta: { title: '规则配置' } },
  { path: '/profiles', name: 'profiles', component: Profiles, meta: { title: '用户画像' } },
  { path: '/reports/baseline', name: 'baseline-report', component: BaselineReport, meta: { title: '基线报告' } },
  { path: '/notifications', name: 'notifications', component: Notifications, meta: { title: '通知' } }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
