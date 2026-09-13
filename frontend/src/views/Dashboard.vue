<template>
  <div>
    <h2 style="margin-top: 0">概览</h2>
    <el-row :gutter="16">
      <el-col :span="6" v-for="card in cards" :key="card.label">
        <el-card shadow="hover">
          <div class="stat-label">{{ card.label }}</div>
          <div class="stat-value" :style="{ color: card.color }">{{ card.value }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" style="margin-top: 16px">
      <el-col :span="12">
        <el-card shadow="hover">
          <template #header>事件类型分布</template>
          <div v-for="d in overview.event_type_dist" :key="d.event_type" class="bar-row">
            <span>{{ d.event_type }}</span>
            <el-progress :percentage="pct(d.c, maxType)" :format="() => d.c" />
          </div>
          <el-empty v-if="!overview.event_type_dist?.length" description="暂无数据" />
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="hover">
          <template #header>异常严重程度分布</template>
          <div v-for="d in overview.severity_dist" :key="d.severity" class="bar-row">
            <span>{{ d.severity }}</span>
            <el-progress :percentage="pct(d.c, maxSev)" :format="() => d.c" :color="sevColor(d.severity)" />
          </div>
          <el-empty v-if="!overview.severity_dist?.length" description="暂无数据" />
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="hover" style="margin-top: 16px">
      <template #header>最近异常事件</template>
      <el-table :data="overview.recent_anomalies || []" size="small">
        <el-table-column prop="user_id" label="用户" width="120" />
        <el-table-column prop="rule_name" label="规则" />
        <el-table-column prop="severity" label="级别" width="100">
          <template #default="{ row }"><el-tag :type="sevType(row.severity)">{{ row.severity }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="event_time" label="时间" width="200" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive } from 'vue'
import api from '../api'

const overview = reactive({ event_type_dist: [], severity_dist: [], recent_anomalies: [] })

const cards = computed(() => [
  { label: '行为日志总数', value: overview.total_logs ?? '-', color: '#409eff' },
  { label: '异常事件数', value: overview.total_anomalies ?? '-', color: '#e6a23c' },
  { label: '待处理告警', value: overview.open_alerts ?? '-', color: '#f56c6c' }
])

const maxType = computed(() => Math.max(1, ...overview.event_type_dist.map(d => d.c), 1))
const maxSev = computed(() => Math.max(1, ...overview.severity_dist.map(d => d.c), 1))

function pct(c, max) {
  return Math.round((c / Math.max(1, max)) * 100)
}

function sevColor(sev) {
  return { low: '#909399', medium: '#e6a23c', high: '#f56c6c', critical: '#c45656' }[sev] || '#909399'
}

function sevType(sev) {
  return { low: 'info', medium: 'warning', high: 'danger', critical: 'danger' }[sev] || 'info'
}

onMounted(async () => {
  const data = await api.getOverview()
  Object.assign(overview, data)
})
</script>

<style scoped>
.stat-label { color: #909399; font-size: 14px; }
.stat-value { font-size: 32px; font-weight: 600; margin-top: 8px; }
.bar-row { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.bar-row span { width: 90px; }
</style>
