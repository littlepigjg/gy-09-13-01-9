<template>
  <div>
    <h2 style="margin-top: 0">审计规则配置</h2>
    <el-card shadow="never">
      <div style="margin-bottom: 12px">
        <el-button type="primary" @click="openCreate">新增规则</el-button>
      </div>
      <el-table :data="rules" size="small" v-loading="loading">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="name" label="名称" width="150" />
        <el-table-column label="类型" width="160">
          <template #default="{ row }"><el-tag>{{ typeLabel(row.rule_type) }}</el-tag></template>
        </el-table-column>
        <el-table-column label="适用事件" width="120">
          <template #default="{ row }">{{ row.event_type || '全部' }}</template>
        </el-table-column>
        <el-table-column label="级别" width="100">
          <template #default="{ row }"><el-tag :type="sevType(row.severity)">{{ row.severity }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="description" label="说明" min-width="200" show-overflow-tooltip />
        <el-table-column label="参数" min-width="220">
          <template #default="{ row }">
            <span class="params">{{ JSON.stringify(row.params) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="启用" width="80">
          <template #default="{ row }">
            <el-switch :model-value="row.enabled" @change="(v) => toggle(row, v)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150">
          <template #default="{ row }">
            <el-button size="small" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialog.visible" :title="dialog.id ? '编辑规则' : '新增规则'" width="560px">
      <el-form :model="form" label-width="90px">
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="类型">
          <el-select v-model="form.rule_type" style="width: 100%">
            <el-option v-for="t in ruleTypes" :key="t.value" :label="t.label" :value="t.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="适用事件">
          <el-select v-model="form.event_type" placeholder="全部事件" clearable style="width: 100%">
            <el-option label="登录" value="login" />
            <el-option label="点击" value="click" />
            <el-option label="交易" value="transaction" />
          </el-select>
        </el-form-item>
        <el-form-item label="级别">
          <el-select v-model="form.severity" style="width: 100%">
            <el-option v-for="s in sevs" :key="s" :label="s" :value="s" />
          </el-select>
        </el-form-item>
        <el-form-item label="说明"><el-input v-model="form.description" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="参数(JSON)">
          <el-input v-model="form.paramsText" type="textarea" :rows="6" placeholder='{"window_seconds": 60, "threshold": 10}' />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog.visible = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'

const rules = ref([])
const loading = ref(false)
const sevs = ['low', 'medium', 'high', 'critical']
const ruleTypes = [
  { label: '深夜登录', value: 'late_night_login' },
  { label: '异地登录', value: 'remote_login' },
  { label: '高频操作', value: 'high_frequency' },
  { label: '历史基线偏差', value: 'baseline_deviation' },
  { label: '单笔金额异常', value: 'amount_anomaly' },
  { label: '设备更换', value: 'device_change' },
  { label: '多地快速登录', value: 'rapid_login' }
]
const dialog = reactive({ visible: false, id: null })
const form = reactive({ name: '', rule_type: 'high_frequency', event_type: '', severity: 'medium', description: '', paramsText: '{}' })

function typeLabel(t) {
  const m = ruleTypes.find(x => x.value === t)
  return m ? m.label : t
}
function sevType(s) {
  return { low: 'info', medium: 'warning', high: 'danger', critical: 'danger' }[s] || 'info'
}

async function load() {
  loading.value = true
  const data = await api.getRules()
  rules.value = data.items
  loading.value = false
}

function openCreate() {
  dialog.id = null
  Object.assign(form, { name: '', rule_type: 'high_frequency', event_type: '', severity: 'medium', description: '', paramsText: '{}' })
  dialog.visible = true
}

function openEdit(row) {
  dialog.id = row.id
  Object.assign(form, {
    name: row.name,
    rule_type: row.rule_type,
    event_type: row.event_type || '',
    severity: row.severity,
    description: row.description || '',
    paramsText: JSON.stringify(row.params, null, 2)
  })
  dialog.visible = true
}

async function save() {
  let params
  try {
    params = JSON.parse(form.paramsText || '{}')
  } catch (e) {
    ElMessage.error('参数不是合法 JSON')
    return
  }
  const payload = {
    name: form.name,
    rule_type: form.rule_type,
    event_type: form.event_type || null,
    severity: form.severity,
    description: form.description,
    params
  }
  if (dialog.id) {
    await api.updateRule(dialog.id, payload)
  } else {
    await api.createRule(payload)
  }
  ElMessage.success('已保存')
  dialog.visible = false
  load()
}

async function toggle(row, v) {
  await api.updateRule(row.id, { enabled: v })
  row.enabled = v
}

async function remove(row) {
  await ElMessageBox.confirm(`确定删除规则「${row.name}」？`, '提示', { type: 'warning' })
  await api.deleteRule(row.id)
  ElMessage.success('已删除')
  load()
}

onMounted(load)
</script>

<style scoped>
.params { color: #909399; font-size: 12px; word-break: break-all; }
</style>
