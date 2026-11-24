<template>
<div>
  <el-card class="box-card">
    <div slot="header" class="clearfix">
      <span>登录后台</span>
    </div>
    <el-input v-model="username" placeholder="请输入账号"></el-input>
      <div style="padding-bottom: 5px"></div>
    <el-input
      v-model="password"
      placeholder="请输入密码"
      show-password
      @keydown.enter.native="handleLogin"
    >
    </el-input>
      <div style="padding-bottom: 5px"></div>
    <el-button type="primary" class="login" @click="handleLogin">登录</el-button>
  </el-card>
</div>
</template>

<script>
import { login } from '@/api/login'
export default {
  name: 'MyLogin',
  data () {
    return {
      username: '',
      password: '',
      timer: null
    }
  },
  beforeDestroy () {
    clearTimeout(this.timer)
  },
  methods: {
    handleLogin () {
      clearTimeout(this.timer) // 清除定时器
      this.timer = setTimeout(async () => { // 执行定时器防抖
        try {
          const { code, msg, token, refresh } = await login({
            username: this.username,
            password: this.password
          })
          this.$message({
            type: code === 200 ? 'success' : 'warning',
            message: msg
          })
          if (code === 200) {
            localStorage.setItem('token', JSON.stringify(token)) // 设置token
            localStorage.setItem('refresh', JSON.stringify(refresh)) // 设置刷新令牌
            this.$router.push('/')
          }
        } catch (error) {
          const serverMsg = error?.response?.data?.msg
          this.$message.error(serverMsg || '登录请求失败')
        }
      }, 1000)
    }
  }
}
</script>

<style scoped>
.login{
  position: relative;
  left: 50%;
  transform: translate(-50%);
}
</style>
