<template>
<div>
  <el-button
    type="success"
    size="mini"
    style="margin-left: 10px"
    @click="handleOpen"
    round
  >修改订阅名称
  </el-button>
  <el-button
    type="danger"
    size="mini"
    style="margin-left: 10px"
    @click="handleDel"
    round
  >删除订阅
  </el-button>
  <el-dialog
    title="新订阅名称"
    :visible.sync="dialogVisible"
    width="480px"
    >
    <el-input
      v-model.trim="rename"
      ref="inp"
      @keyup.enter.native="handleRename"
    />
    <div slot="footer" class="dialog-footer">
      <el-button @click="handleCancel">取消</el-button>
      <el-button type="primary" @click="handleRename">确定</el-button>
    </div>
  </el-dialog>
</div>
</template>

<script>
export default {
  name: 'ReName',
  props: {
    currentName: {
      type: String,
      default: ''
    }
  },
  data () {
    return {
      dialogVisible: false,
      rename: ''
    }
  },
  methods: {
    handleOpen () {
      this.rename = this.currentName
      this.dialogVisible = true
      this.$nextTick(() => {
        // console.log(this.$refs.inp)
        this.$refs.inp.focus()
      })
    },
    handleRename () {
      if (!this.rename || this.rename === this.currentName) {
        this.dialogVisible = false
        return
      }
      this.$emit('handleRename', this.rename)
      this.dialogVisible = false
      this.rename = ''
    },
    handleCancel () {
      this.dialogVisible = false
      this.rename = ''
    },
    handleDel () {
      this.$emit('handleDel')
    }
  }
}
</script>

<style scoped>
.dialog-footer {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
}
</style>
