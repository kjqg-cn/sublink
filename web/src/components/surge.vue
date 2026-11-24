<template>
<div>
  <el-button @click="handleConfig('edit')">编辑规则</el-button>
  <el-tag style="margin-left: 10px" size="mini" type="info">适配:ss vmess trojan hy2</el-tag>
  <el-dialog
    title="surge规则编辑(所有订阅共用一个规则)"
    :visible.sync="dialogVisible"
    width="80%"
  >
    <span>建议复制出来修改后再替换上去，大模板直接编辑可能有卡顿</span>
    <p>[Proxy Group] 下写上 auto 会插入本订阅所有节点名称列表</p>
    <div v-if="loadFailed" class="load-error-banner">
      <span>{{ loadError }}</span>
      <el-button size="mini" type="danger" plain :disabled="loading" @click="handleConfig('edit')">重新加载</el-button>
    </div>
    <div style="margin-bottom: 10px"></div>
    <span>
      <el-input
        v-model="config"
        type="textarea"
        :readonly="loading || saving || loadFailed"
        rows="12"
      ></el-input>
    </span>
    <span slot="footer" class="dialog-footer">
      <el-button @click="dialogVisible = false">取 消</el-button>
      <el-button
        type="primary"
        :loading="saving"
        :disabled="loading || saving || loadFailed"
        @click="handleConfig('save')"
      >保 存</el-button>
    </span>
  </el-dialog>
</div>
</template>

<script>
import { GetSurge } from '@/api/nodetype'
export default {
  name: 'MySurge',
  data () {
    return {
      dialogVisible: false,
      config: '',
      loading: false,
      saving: false,
      loadFailed: false,
      loadError: ''
    }
  },
  methods: {
    async handleConfig (index) {
      if (index === 'edit') {
        this.dialogVisible = true
        this.loading = true
        this.loadFailed = false
        this.loadError = ''
        this.config = ''
        try {
          const { code, msg } = await GetSurge({ index: 'read' })
          if (code === 200 && typeof msg === 'string') {
            this.config = msg
          } else {
            const detail = typeof msg === 'string' && msg.trim() ? msg.trim() : '读取规则失败'
            this.loadFailed = true
            this.loadError = `${detail}，已禁用保存以防覆盖原有规则`
            this.$message({ type: 'warning', message: detail })
          }
        } catch (error) {
          this.loadFailed = true
          this.loadError = '读取规则失败，已禁用保存以防覆盖原有规则'
          this.$message.error('读取规则失败')
        } finally {
          this.loading = false
        }
        return
      }
      if (index === 'save') {
        if (this.loading || this.saving || this.loadFailed) return
        this.saving = true
        try {
          const { code, msg } = await GetSurge({
            index: 'save',
            text: this.config
          })
          this.$message({
            type: code === 200 ? 'success' : 'warning',
            message: msg || (code === 200 ? '保存成功' : '保存失败')
          })
          if (code === 200) {
            this.dialogVisible = false
          }
        } catch (error) {
          this.$message.error('保存规则失败')
        } finally {
          this.saving = false
        }
      }
    }
  }
}
</script>

<style scoped>
.load-error-banner {
  align-items: center;
  background: #fef0f0;
  border: 1px solid #fbc4c4;
  border-radius: 4px;
  color: #f56c6c;
  display: flex;
  justify-content: space-between;
  margin-top: 8px;
  padding: 8px 12px;
}
</style>
