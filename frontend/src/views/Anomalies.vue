<template>
  <div>
    <h2 style="margin-top: 0">异常事件与告警</h2>
    <el-tabs v-model="tab">
      <el-tab-pane label="异常事件" name="anomalies">
        <el-card shadow="never">
          <el-form :inline="true" style="margin-bottom: 8px">
            <el-form-item label="用户">
              <el-input v-model="q.user_id" placeholder="如 u1001" clearable style="width: 140px" @keyup.enter="loadAnomalies(1)" />
            </el-form-item>
            <el-form-item label="级别">
              <el-select v-model="q.severity" placeholder="全部" clearable style="width: 120px">
                <el-option v-for="s in sevs" :key="s" :label="s" :value="s" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="loadAnomalies(1)">查询</el-button>
            </el-form-item>
          </el-form>

          <el-table :data="anomalies" size="small" v-loading="loading">
            <el-table-column prop="id" label="ID" width="80" />
            <el-table-column prop="user_id" label="用户" width="110" />
            <el-table-column prop="rule_name" label="规则" />
            <el-table-column label="级别" width="100">
              <template #default="{ row }"><el-tag :type="sevType(row.severity)">{{ row.severity }}</el-tag></template>
            </el-table-column>
            <el-table-column label="分数" width="90">
              <template #default="{ row }">{{ row.score }}</template>
            </el-table-column>
            <el-table-column label="检测详情" min-width="240">
              <template #default="{ row }">
                <span class="detail">{{ prettyDetail(row.detail) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="event_time" label="时间" width="180" />
          </el-table>

          <el-pagination
            style="margin-top: 12px"
            layout="total, prev, pager, next"
            :total="aTotal"
            :page-size="q.limit"
            :current-page="q.offset / q.limit + 1"
            @current-change="loadAnomalies"
          />
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="告警（聚合去重）" name="alerts">
        <el-card shadow="never">
          <el-table :data="alerts" size="small" v-loading="loadingAlerts">
            <el-table-column prop="id" label="ID" width="80" />
            <el-table-column prop="user_id" label="用户" width="110" />
            <el-table-column prop="rule_name" label="规则" />
            <el-table-column label="级别" width="100">
              <template #default="{ row }"><el-tag :type="sevType(row.severity)">{{ row.severity }}</el-tag></template>
            </el-table-column>
            <el-table-column prop="anomaly_count" label="聚合数量" width="100" />
            <el-table-column prop="first_time" label="首次发生" width="180" />
            <el-table-column prop="last_time" label="最近发生" width="180" />
            <el-table-column label="状态" width="130">
              <template #default="{ row }">
                <el-tag :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="180">
              <template #default="{ row }">
                <el-button size="small" v-if="row.status === 'open'" @click="setStatus(row, 'acknowledged')">确认</el-button>
                <el-button size="small" v-if="row.status !== 'resolved'" type="success" @click="setStatus(row, 'resolved')">解决</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const tab = ref('anomalies')
const sevs = ['low', 'medium', 'high', 'critical']
const anomalies = ref([])
const alerts = ref([])
const aTotal = ref(0)
const loading = ref(false)
const loadingAlerts = ref(false)
const q = reactive({ user_id: '', severity: '', limit: 20, offset: 0 })

function sevType(s) {
  return { low: 'info', medium: 'warning', high: 'danger', critical: 'danger' }[s] || 'info'
}
function statusType(s) {
  return { open: 'danger', acknowledged: 'warning', resolved: 'success', suppressed: 'info' }[s] || 'info'
}
function statusLabel(s) {
  return { open: '待处理', acknowledged: '已确认', resolved: '已解决', suppressed: '已压制' }[s] || s
}
function prettyDetail(d) {
  if (!d) return ''
  try {
    const obj = typeof d === 'string' ? JSON.parse(d) : d
    return Object.entries(obj).map(([k, v]) => `${k}=${v}`).join(' ')
  } catch (e) {
    return d
  }
}

async function loadAnomalies(page = 1) {
  loading.value = true
  q.offset = (page - 1) * q.limit
  const params = { limit: q.limit, offset: q.offset }
  if (q.user_id) params.user_id = q.user_id
  if (q.severity) params.severity = q.severity
  const data = await api.getAnomalies(params)
  anomalies.value = data.items
  aTotal.value = data.total
  loading.value = false
}

async function loadAlerts() {
  loadingAlerts.value = true
  const data = await api.getAlerts({ limit: 100, offset: 0 })
  alerts.value = data.items
  loadingAlerts.value = false
}

async function setStatus(row, status) {
  await api.updateAlertStatus(row.id, status)
  ElMessage.success('已更新')
  loadAlerts()
}

onMounted(() => {
  loadAnomalies(1)
  loadAlerts()
})
</script>

<style scoped>
.detail { color: #909399; font-size: 12px; word-break: break-all; }
</style>
