<template>
  <div>
    <h2 style="margin-top: 0">用户画像</h2>
    <el-row :gutter="16">
      <el-col :span="8">
        <el-card shadow="never">
          <template #header>用户列表</template>
          <el-table :data="profiles" size="small" highlight-current-row @current-change="selectUser" v-loading="loading">
            <el-table-column prop="user_id" label="用户" width="110" />
            <el-table-column prop="total_events" label="事件数" width="80" />
            <el-table-column prop="dominant_location" label="常用地区" />
          </el-table>
        </el-card>
      </el-col>
      <el-col :span="16">
        <el-card shadow="never" v-if="current">
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center">
              <span>画像详情：{{ current.user_id }}</span>
              <el-button size="small" type="primary" @click="goReport">查看基线报告</el-button>
            </div>
          </template>
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="总事件数">{{ current.total_events }}</el-descriptions-item>
            <el-descriptions-item label="交易次数">{{ current.transaction_count }}</el-descriptions-item>
            <el-descriptions-item label="常用设备">{{ current.dominant_device || '-' }}</el-descriptions-item>
            <el-descriptions-item label="常用地区">{{ current.dominant_location || '-' }}</el-descriptions-item>
            <el-descriptions-item label="平均交易金额">{{ current.amount_mean ?? '-' }}</el-descriptions-item>
            <el-descriptions-item label="金额标准差">{{ current.amount_std ?? '-' }}</el-descriptions-item>
            <el-descriptions-item label="首次出现">{{ current.first_seen }}</el-descriptions-item>
            <el-descriptions-item label="最近活跃">{{ current.last_seen }}</el-descriptions-item>
          </el-descriptions>

          <el-row :gutter="16" style="margin-top: 16px">
            <el-col :span="8">
              <div class="sub-title">事件类型分布</div>
              <div v-for="(c, k) in current.event_counts" :key="k" class="kv">
                <span>{{ k }}</span><b>{{ c }}</b>
              </div>
            </el-col>
            <el-col :span="8">
              <div class="sub-title">设备分布</div>
              <div v-for="(c, k) in current.devices" :key="k" class="kv">
                <span>{{ k }}</span><b>{{ c }}</b>
              </div>
            </el-col>
            <el-col :span="8">
              <div class="sub-title">地区分布</div>
              <div v-for="(c, k) in current.locations" :key="k" class="kv">
                <span>{{ k }}</span><b>{{ c }}</b>
              </div>
            </el-col>
          </el-row>

          <div class="sub-title" style="margin-top: 16px">活跃时段分布（UTC 小时）</div>
          <div class="hours">
            <el-tag v-for="(c, h) in current.active_hours" :key="h" size="small" style="margin: 2px">
              {{ h }}时: {{ c }}
            </el-tag>
          </div>
        </el-card>
        <el-empty v-else description="请选择用户" />
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'

const router = useRouter()
const profiles = ref([])
const current = ref(null)
const loading = ref(false)

function selectUser(row) {
  current.value = row
}

function goReport() {
  router.push({ path: '/reports/baseline', query: { user_id: current.value.user_id } })
}

onMounted(async () => {
  loading.value = true
  const data = await api.getProfiles()
  profiles.value = data.items || []
  loading.value = false
  if (profiles.value.length) current.value = profiles.value[0]
})
</script>

<style scoped>
.sub-title { font-weight: 600; margin-bottom: 8px; color: #303133; }
.kv { display: flex; justify-content: space-between; padding: 2px 0; color: #606266; }
.kv b { color: #409eff; }
.hours { display: flex; flex-wrap: wrap; }
</style>
