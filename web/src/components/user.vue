<template>
<div>
  <div style="display: flex;justify-content: center">
  <span>{{username}}</span>
  <span style="margin-left: 10px">
    <el-button size="mini" @click="ifOutUser">注销</el-button>
  </span>
  </div>
  <div style="margin-bottom: 10px"></div>
  <el-input
    type="password"
    show-password
    v-model="oldPassword"
    placeholder="请输入当前密码"
  >
    <template slot="prepend">当前密码</template>
  </el-input>
  <div style="margin-bottom: 10px"></div>
  <el-input
    type="text"
    v-model="newUserName"
    placeholder="新账号（3-32 位字母、数字或 _ . -）"
  >
    <template slot="prepend">新账号</template>
  </el-input>
  <div style="margin-bottom: 10px"></div>
  <el-input
    type="password"
    show-password
    v-model="password"
    placeholder="新密码（4-64 位）"
    @keydown.enter.native="handleSetUser"
  >
    <template slot="prepend">新密码</template>
  </el-input>
  <div style="margin-bottom: 10px"></div>
  <el-button round style="position: relative;left: 50%;transform: translate(-50%)" @click="handleSetUser">修改</el-button>
  <div style="margin-bottom: 10px"></div>
</div>
</template>

<script>
import { SetUser } from '@/api/user'
import { decodeJwtPayload, readStoredToken } from '@/utils/request'
export default {
  name: 'MyUser',
  data () {
    return {
      username: '',
      oldPassword: '',
      newUserName: '',
      password: '',
      timer: null
    }
  },
  created () {
    this.handleUser()
  },
  beforeDestroy () {
    clearTimeout(this.timer)
  },
  methods: {
    handleUser () {
      const token = readStoredToken('token')
      if (token) {
        const decoded = decodeJwtPayload(token)
        this.username = (decoded && decoded.sub) || ''
        if (!this.newUserName) {
          this.newUserName = this.username
        }
      }
    },
    handleSetUser () {
      if (!this.oldPassword) {
        this.$message({
          type: 'warning',
          message: '请输入当前密码'
        })
        return false
      }
      if (!/^[A-Za-z0-9_.-]{3,32}$/.test(this.newUserName)) {
        this.$message({
          type: 'warning',
          message: '请输入 3-32 位字母、数字、下划线、点或连字符账号'
        })
        return false
      }
      if (!/^[\x20-\x7E]{4,64}$/.test(this.password)) {
        this.$message({
          type: 'warning',
          message: '请输入 4-64 位密码，可以包含大小写字母、数字和符号'
        })
        return false
      }
      clearTimeout(this.timer)
      this.timer = setTimeout(async () => {
        try {
          const { code, msg } = await SetUser({
            username: this.username,
            oldPassword: this.oldPassword,
            newUserName: this.newUserName,
            password: this.password
          })
          this.$message({
            type: code === 200 ? 'success' : 'warning',
            message: msg
          })
          if (code === 200) {
            this.handleOutUser()
          }
        } catch (error) {
          this.$message.error('修改失败')
        }
      }, 300)
    },
    handleOutUser () { // 注销用户
      localStorage.removeItem('token')
      localStorage.removeItem('refresh')
      location.reload()
    },
    ifOutUser () {
      this.$confirm('此操作将注销重新登录, 是否继续?', '提示', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
        center: true
      }).then(() => {
        this.handleOutUser()
      }).catch(() => {

      })
    }
  }
}
</script>

<style scoped>

</style>
