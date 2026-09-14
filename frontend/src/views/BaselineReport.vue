<template>
  <div>
    <h2 style="margin-top: 0">用户行为基线报告</h2>
    <el-row :gutter="16">
      <el-col :span="8">
        <el-card shadow="never">
          <template #header>选择用户</template>
          <el-form :inline="true" style="margin-bottom: 8px" @submit.prevent>
            <el-form-item>
              <el-input v-model="inputUser" placeholder="输入用户ID，如 u1001" clearable style="width: 170px" @keyup.enter="generate(inputUser)" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :disabled="!inputUser" @click="generate(inputUser)">生成报告</el-button>
            </el-form-item>
          </el-form>
          <el-table :data="users" size="small" highlight-current-row @current-change="selectUser" v-loading="loadingUsers">
            <el-table-column prop="user_id" label="用户" width="110" />
            <el-table-column prop="total_events" label="事件数" width="80" />
            <el-table-column prop="dominant_location" label="常用地区" />
          </el-table>
        </el-card>
      </el-col>

      <el-col :span="16">
        <template v-if="report">
          <el-card shadow="never" style="margin-bottom: 16px" v-loading="loadingReport">
            <template #header>
              <div class="report-header">
                <span>基线报告：{{ report.user_id }}</span>
                <span class="meta">生成于 {{ report.generated_at }}（UTC）· 偏离统计窗口：近 {{ report.recent_days }} 天</span>
              </div>
            </template>
            <el-descriptions :column="3" border size="small">
              <el-descriptions-item label="数据充分度">
                <el-tag :type="suffType(report.data_sufficiency.level)">{{ suffLabel(report.data_sufficiency.level) }}</el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="行为事件总量">{{ report.data_sufficiency.total_events }}</el-descriptions-item>
              <el-descriptions-item label="登录 / 交易次数">
                {{ report.data_sufficiency.login_count }} / {{ report.data_sufficiency.transaction_count }}
              </el-descriptions-item>
            </el-descriptions>
            <el-alert
              v-for="(n, i) in report.data_sufficiency.notes" :key="i"
              :title="n" type="warning" :closable="false" show-icon style="margin-top: 8px"
            />
          </el-card>

          <el-card shadow="never" style="margin-bottom: 16px">
            <template #header>行为基线（与用户画像同源）</template>
            <template v-if="report.baseline">
              <el-descriptions :column="2" border size="small">
                <el-descriptions-item label="常用活跃时段">{{ topHoursText }}</el-descriptions-item>
                <el-descriptions-item label="常用设备">{{ report.baseline.dominant_device || '-' }}</el-descriptions-item>
                <el-descriptions-item label="常用登录地点">{{ report.baseline.dominant_location || '-' }}</el-descriptions-item>
                <el-descriptions-item label="首次 / 最近活跃">
                  {{ report.baseline.first_seen || '-' }} / {{ report.baseline.last_seen || '-' }}
                </el-descriptions-item>
                <el-descriptions-item label="平均交易金额">{{ report.baseline.amount_mean ?? '-' }}</el-descriptions-item>
                <el-descriptions-item label="交易金额常规区间">
                  <span v-if="report.baseline.amount_normal_range">
                    {{ report.baseline.amount_normal_range[0] }} ~ {{ report.baseline.amount_normal_range[1] }} 元
                  </span>
                  <span v-else>-</span>
                </el-descriptions-item>
              </el-descriptions>

              <el-row :gutter="16" style="margin-top: 16px">
                <el-col :span="8">
                  <div class="sub-title">活跃时段分布</div>
                  <div v-for="(c, p) in report.baseline.active_periods" :key="p" class="kv">
                    <span>{{ p }}</span><b>{{ c }}</b>
                  </div>
                </el-col>
                <el-col :span="8">
                  <div class="sub-title">设备分布</div>
                  <div v-for="(c, k) in report.baseline.devices" :key="k" class="kv">
                    <span>{{ k }}</span><b>{{ c }}</b>
                  </div>
                  <div v-if="!hasKeys(report.baseline.devices)" class="kv"><span>暂无</span></div>
                </el-col>
                <el-col :span="8">
                  <div class="sub-title">地区分布</div>
                  <div v-for="(c, k) in report.baseline.locations" :key="k" class="kv">
                    <span>{{ k }}</span><b>{{ c }}</b>
                  </div>
                  <div v-if="!hasKeys(report.baseline.locations)" class="kv"><span>暂无</span></div>
                </el-col>
              </el-row>

              <div class="sub-title" style="margin-top: 16px">活跃小时分布（UTC）</div>
              <div class="hours">
                <el-tag v-for="(c, h) in report.baseline.active_hours" :key="h" size="small" style="margin: 2px">
                  {{ h }}时: {{ c }}
                </el-tag>
              </div>
            </template>
            <el-empty v-else description="暂无行为数据，基线暂未建立" />
          </el-card>

          <el-card shadow="never" style="margin-bottom: 16px">
            <template #header>偏离判定口径（与检测规则一致）</template>
            <el-row :gutter="12">
              <el-col :span="8">
                <div class="crit">
                  <div class="crit-title">深夜登录</div>
                  <div class="crit-body">{{ report.criteria.late_night_login.description }}</div>
                </div>
              </el-col>
              <el-col :span="8">
                <div class="crit">
                  <div class="crit-title">异地登录</div>
                  <div class="crit-body">{{ report.criteria.remote_login.description }}</div>
                </div>
              </el-col>
              <el-col :span="8">
                <div class="crit">
                  <div class="crit-title">大额交易</div>
                  <div class="crit-body">{{ report.criteria.amount_anomaly.description }}</div>
                </div>
              </el-col>
            </el-row>
          </el-card>

          <el-card shadow="never">
            <template #header>
              近期偏离基线的行为（近 {{ report.recent_days }} 天，共 {{ report.deviations.total }} 条）
            </template>
            <div style="margin-bottom: 12px">
              <el-tag
                v-for="(label, t) in typeLabels" :key="t"
                :type="devTagType(t)" style="margin-right: 8px"
              >{{ label }} {{ report.deviations.by_type[t] || 0 }}</el-tag>
            </div>
            <el-table v-if="report.deviations.items.length" :data="report.deviations.items" size="small">
              <el-table-column prop="event_time" label="时间" width="170" />
              <el-table-column label="偏离类型" width="110">
                <template #default="{ row }">
                  <el-tag :type="devTagType(row.type)">{{ row.type_label }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="级别" width="90">
                <template #default="{ row }">
                  <el-tag :type="sevType(row.severity)">{{ row.severity }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="summary" label="偏离说明" min-width="240" />
              <el-table-column prop="rule_name" label="判定规则" width="110" />
            </el-table>
            <el-alert v-else type="success" :closable="false" show-icon
              title="近期未发现偏离基线的行为" />
          </el-card>
        </template>
        <el-empty v-else description="请选择或输入用户生成基线报告" />
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '../api'

const route = useRoute()
const users = ref([])
const inputUser = ref('')
const report = ref(null)
const loadingUsers = ref(false)
const loadingReport = ref(false)

const typeLabels = {
  late_night_login: '深夜登录',
  remote_login: '异地登录',
  amount_anomaly: '大额交易'
}

const topHoursText = computed(() => {
  const hours = report.value?.baseline?.top_active_hours || []
  return hours.length ? hours.map(h => `${h} 时`).join('、') + '（UTC）' : '-'
})

function devTagType(t) {
  return { late_night_login: 'warning', remote_login: 'danger', amount_anomaly: 'danger' }[t] || 'info'
}
function sevType(s) {
  return { low: 'info', medium: 'warning', high: 'danger', critical: 'danger' }[s] || 'info'
}
function suffType(l) {
  return { sufficient: 'success', limited: 'warning', none: 'info' }[l] || 'info'
}
function suffLabel(l) {
  return { sufficient: '数据充分', limited: '数据有限，基线仅供参考', none: '暂无数据' }[l] || l
}
function hasKeys(obj) {
  return obj && Object.keys(obj).length > 0
}

function selectUser(row) {
  if (row) generate(row.user_id)
}

async function generate(userId) {
  if (!userId) return
  loadingReport.value = true
  try {
    report.value = await api.getBaselineReport(userId, { recent_days: 7 })
  } catch (e) {
    ElMessage.error('生成基线报告失败')
  } finally {
    loadingReport.value = false
  }
}

onMounted(async () => {
  loadingUsers.value = true
  try {
    const data = await api.getProfiles()
    users.value = data.items || []
  } finally {
    loadingUsers.value = false
  }
  const q = route.query.user_id
  if (q) {
    inputUser.value = q
    generate(q)
  } else if (users.value.length) {
    generate(users.value[0].user_id)
  }
})
</script>

<style scoped>
.report-header { display: flex; justify-content: space-between; align-items: center; }
.report-header .meta { font-size: 12px; color: #909399; font-weight: normal; }
.sub-title { font-weight: 600; margin-bottom: 8px; color: #303133; }
.kv { display: flex; justify-content: space-between; padding: 2px 0; color: #606266; }
.kv b { color: #409eff; }
.hours { display: flex; flex-wrap: wrap; }
.crit { border: 1px solid #ebeef5; border-radius: 4px; padding: 10px; height: 100%; }
.crit-title { font-weight: 600; margin-bottom: 6px; color: #303133; }
.crit-body { font-size: 12px; color: #606266; line-height: 1.6; }
</style>
