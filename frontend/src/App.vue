<template>
  <el-container class="app-container">
    <el-aside width="220px" class="aside">
      <div class="logo">用户行为审计系统</div>
      <el-menu :default-active="activeMenu" router class="menu">
        <el-menu-item index="/dashboard">概览</el-menu-item>
        <el-menu-item index="/timeline">行为时间线</el-menu-item>
        <el-menu-item index="/anomalies">异常事件</el-menu-item>
        <el-menu-item index="/rules">规则配置</el-menu-item>
        <el-menu-item index="/profiles">用户画像</el-menu-item>
        <el-menu-item index="/reports/baseline">基线报告</el-menu-item>
        <el-menu-item index="/notifications">通知</el-menu-item>
      </el-menu>
    </el-aside>
    <el-main class="main">
      <router-view />
    </el-main>
  </el-container>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const activeMenu = computed(() => route.path)
</script>

<style>
* { box-sizing: border-box; }
body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f7fa; }
.app-container { height: 100vh; }
.aside { background: #1f2d3d; color: #fff; }
.logo { height: 60px; line-height: 60px; text-align: center; font-weight: 600; font-size: 16px; color: #fff; }
.menu { border-right: none; background: #1f2d3d; }
.menu .el-menu-item { color: #c0c4cc; }
.menu .el-menu-item.is-active { color: #fff; background: #409eff; }
.main { padding: 20px; overflow: auto; }
</style>
