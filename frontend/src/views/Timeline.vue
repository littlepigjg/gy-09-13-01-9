<template>
  <div>
    <h2 style="margin-top: 0">用户行为时间线</h2>
    <el-card shadow="never">
      <el-form :inline="true" style="margin-bottom: 8px">
        <el-form-item label="用户">
          <el-input v-model="query.user_id" placeholder="如 u1001" clearable style="width: 140px" />
        </el-form-item>
        <el-form-item label="事件类型">
          <el-select v-model="query.event_type" placeholder="全部" clearable style="width: 140px">
            <el-option label="登录" value="login" />
            <el-option label="点击" value="click" />
            <el-option label="交易" value="transaction" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="load(1)">查询</el-button>
        </el-form-item>
      </el-form>

      <el-table :data="rows" size="small" v-loading="loading">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="user_id" label="用户" width="110" />
        <el-table-column label="事件类型" width="110">
          <template #default="{ row }"><el-tag :type="typeTag(row.event_type)">{{ typeLabel(row.event_type) }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="event_time" label="时间" width="180" />
        <el-table-column prop="ip" label="IP" width="140" />
        <el-table-column prop="location" label="地区" width="100" />
        <el-table-column prop="device" label="设备" width="100" />
        <el-table-column prop="amount" label="金额" width="100" />
      </el-table>

      <el-pagination
        style="margin-top: 12px"
        layout="total, prev, pager, next"
        :total="total"
        :page-size="query.limit"
        :current-page="query.offset / query.limit + 1"
        @current-change="load"
      />
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import api from '../api'

const rows = ref([])
const total = ref(0)
const loading = ref(false)
const query = reactive({ user_id: '', event_type: '', limit: 20, offset: 0 })

function typeLabel(t) {
  return { login: '登录', click: '点击', transaction: '交易' }[t] || t
}
function typeTag(t) {
  return { login: 'primary', click: 'success', transaction: 'warning' }[t] || 'info'
}

async function load(page = 1) {
  loading.value = true
  query.offset = (page - 1) * query.limit
  const params = {
    limit: query.limit,
    offset: query.offset
  }
  if (query.user_id) params.user_id = query.user_id
  if (query.event_type) params.event_type = query.event_type
  const data = await api.getLogs(params)
  rows.value = data.items
  total.value = data.total
  loading.value = false
}

onMounted(() => load(1))
</script>
