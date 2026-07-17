<template>
  <div>
    <el-button @click="handleConfig('edit')">编辑配置</el-button>
    <el-tag style="margin-left: 10px" size="mini" type="info">适配:vless vmess ss trojan hy hy2</el-tag>
    <el-dialog
      title="sing-box 配置编辑"
      :visible.sync="dialogVisible"
      width="80%"
    >
      <el-input
        v-model.lazy="config"
        type="textarea"
        rows="18"
      ></el-input>
      <span slot="footer" class="dialog-footer">
        <el-button @click="dialogVisible = false">取 消</el-button>
        <el-button type="primary" @click="handleConfig('save')">保 存</el-button>
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
      config: ''
    }
  },
  methods: {
    async handleConfig (index) {
      const { code, msg } = await GetSingBox({
        index: index === 'edit' ? 'read' : index,
        text: index === 'save' ? this.config : undefined
      })
      if (index === 'edit') {
        this.dialogVisible = true
        if (code === 200) {
          this.config = msg
        }
      }
      if (index === 'save' && code === 200) {
        this.dialogVisible = false
      }
      if (code !== 200 || index === 'save') {
        this.$message({
          type: code === 200 ? 'success' : 'warning',
          message: msg
        })
      }
    }
  }
}
</script>
