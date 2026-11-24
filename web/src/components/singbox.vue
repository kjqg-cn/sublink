<template>
  <div>
    <el-button @click="handleConfig('edit')">编辑配置</el-button>
    <el-tag style="margin-left: 10px" size="mini" type="info">适配:vless vmess ss trojan hy hy2</el-tag>
    <el-dialog
      title="sing-box 配置编辑"
      :visible.sync="dialogVisible"
      width="80%"
    >
      <p class="singbox-tip">
        默认按 sing-box 1.14+ 语法输出（无 download_detour 弃用警告）；sing-box 1.12～1.13 旧版客户端可在订阅地址后追加 ?legacy=1 或 ?version=1.12。
      </p>
      <div v-if="loadFailed" class="load-error-banner">
        <span>{{ loadError }}</span>
        <el-button size="mini" type="danger" plain :disabled="loading" @click="handleConfig('edit')">重新加载</el-button>
      </div>
      <el-input
        v-model="config"
        type="textarea"
        :readonly="loading || saving || loadFailed"
        rows="18"
      ></el-input>
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
import { GetSingBox } from '@/api/nodetype'

export default {
  name: 'MySingBox',
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
          const { code, msg } = await GetSingBox({ index: 'read' })
          if (code === 200 && typeof msg === 'string') {
            this.config = msg
          } else {
            const detail = typeof msg === 'string' && msg.trim() ? msg.trim() : '读取配置失败'
            this.loadFailed = true
            this.loadError = `${detail}，已禁用保存以防覆盖原有配置`
            this.$message({ type: 'warning', message: detail })
          }
        } catch (error) {
          this.loadFailed = true
          this.loadError = '读取配置失败，已禁用保存以防覆盖原有配置'
          this.$message.error('读取配置失败')
        } finally {
          this.loading = false
        }
        return
      }
      if (index === 'save') {
        if (this.loading || this.saving || this.loadFailed) return
        this.saving = true
        try {
          const { code, msg } = await GetSingBox({
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
          this.$message.error('保存配置失败')
        } finally {
          this.saving = false
        }
      }
    }
  }
}
</script>

<style scoped>
.singbox-tip {
  color: #606266;
  font-size: 13px;
  margin: 0 0 10px;
}
.load-error-banner {
  align-items: center;
  background: #fef0f0;
  border: 1px solid #fbc4c4;
  border-radius: 4px;
  color: #f56c6c;
  display: flex;
  justify-content: space-between;
  margin-bottom: 10px;
  padding: 8px 12px;
}
</style>
