<template>
  <div>
    <h2 style="margin-top: 0">告警通知</h2>
    <el-card shadow="never">
      <div style="margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center">
        <el-radio-group v-model="filter" @change="load(1)">
          <el-radio-button value="unread">未读</el-radio-button>
          <el-radio-button value="read">已读</el-radio-button>
          <el-radio-button value="">全部</el-radio-button>
        </el-radio-group>
        <el-button size="small" @click="markAll">全部标记已读</el-button>
      </div>

      <el-table :data="rows" size="small" v-loading="loading">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="user_id" label="用户" width="110" />
        <el-table-column prop="rule_name" label="规则" />
        <el-table-column label="级别" width="100">
          <template #default="{ row }"><el-tag :type="sevType(row.severity)">{{ row.severity }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="channel" label="渠道" width="90" />
        <el-table-column prop="content" label="内容" min-width="220" show-overflow-tooltip />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 'unread' ? 'danger' : 'info'">{{ row.status === 'unread' ? '未读' : '已读' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="时间" width="180" />
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-button v-if="row.status === 'unread'" size="small" @click="read(row)">标记已读</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        style="margin-top: 12px"
        layout="total, prev, pager, next"
        :total="total"
        :page-size="pageSize"
        :current-page="page"
        @current-change="load"
      />
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const filter = ref('unread')
const loading = ref(false)

function sevType(s) {
  return { low: 'info', medium: 'warning', high: 'danger', critical: 'danger' }[s] || 'info'
}

async function load(p = 1) {
  loading.value = true
  page.value = p
  const params = { limit: pageSize, offset: (p - 1) * pageSize }
  if (filter.value) params.status = filter.value
  const data = await api.getNotifications(params)
  rows.value = data.items
  total.value = data.total
  loading.value = false
}

async function read(row) {
  await api.markNotificationRead(row.id)
  row.status = 'read'
  ElMessage.success('已标记已读')
}

async function markAll() {
  await api.markAllNotificationsRead()
  ElMessage.success('已全部标记已读')
  load(1)
}

onMounted(() => load(1))
</script>
