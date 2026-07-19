<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage, NCard, NInput, NButton, NForm, NFormItem, NIcon } from 'naive-ui'
import MD5 from 'crypto-js/md5'
import { login } from '@/api'
import { themeMode, toggleTheme } from '@/theme'

const router = useRouter()
const message = useMessage()

const username = ref('')
const password = ref('')
const loading = ref(false)

async function handleLogin() {
  if (!username.value || !password.value) {
    message.warning('请输入账号和密码')
    return
  }
  loading.value = true
  try {
    const { code, msg, token, refresh } = await login({
      username: username.value,
      password: MD5(password.value).toString()
    })
    message[code === 200 ? 'success' : 'warning'](msg)
    if (code === 200 && token) {
      localStorage.setItem('token', JSON.stringify(token))
      localStorage.setItem('refresh', JSON.stringify(refresh))
      router.push('/')
    }
  } catch {
    message.error('登录请求失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <div class="theme-toggle">
      <n-button quaternary circle @click="toggleTheme">
        <template #icon>
          <n-icon>
            <svg viewBox="0 0 24 24" width="18" height="18">
              <path
                v-if="themeMode === 'light'"
                fill="currentColor"
                d="M12 7a5 5 0 100 10 5 5 0 000-10zM2 13h2a1 1 0 000-2H2a1 1 0 000 2zm18 0h2a1 1 0 000-2h-2a1 1 0 000 2zM11 2v2a1 1 0 002 0V2a1 1 0 00-2 0zm0 18v2a1 1 0 002 0v-2a1 1 0 00-2 0zM5.99 4.58a1 1 0 00-1.41 1.41l1.06 1.06a1 1 0 001.41-1.41L5.99 4.58zm12.37 12.37a1 1 0 00-1.41 1.41l1.06 1.06a1 1 0 001.41-1.41l-1.06-1.06zm1.06-10.96a1 1 0 00-1.41-1.41l-1.06 1.06a1 1 0 001.41 1.41l1.06-1.06zM7.05 18.36a1 1 0 00-1.41-1.41l-1.06 1.06a1 1 0 001.41 1.41l1.06-1.06z"
              />
              <path
                v-else
                fill="currentColor"
                d="M12.3 2.03a1 1 0 00-1.07 1.42A7 7 0 1120.55 12.7a1 1 0 00-1.42-1.07A9 9 0 1012.3 2.03z"
              />
            </svg>
          </n-icon>
        </template>
      </n-button>
    </div>

    <n-card class="login-card" :bordered="false">
      <div class="brand">
        <div class="brand-logo">S</div>
        <div class="brand-text">
          <h1>Sublink</h1>
          <p>订阅管理后台</p>
        </div>
      </div>

      <n-form @submit.prevent="handleLogin">
        <n-form-item label="账号">
          <n-input v-model:value="username" placeholder="请输入账号" size="large" />
        </n-form-item>
        <n-form-item label="密码">
          <n-input
            v-model:value="password"
            type="password"
            show-password-on="click"
            placeholder="请输入密码"
            size="large"
          />
        </n-form-item>
        <n-button
          type="primary"
          size="large"
          block
          :loading="loading"
          attr-type="submit"
        >
          登录
        </n-button>
      </n-form>
    </n-card>
  </div>
</template>

<style scoped>
.login-page {
  align-items: center;
  display: flex;
  justify-content: center;
  min-height: 100vh;
  padding: 24px;
  position: relative;
  background: radial-gradient(circle at 20% 20%, rgba(99, 102, 241, 0.18), transparent 40%),
    radial-gradient(circle at 80% 70%, rgba(16, 185, 129, 0.16), transparent 42%);
}

.theme-toggle {
  position: absolute;
  right: 20px;
  top: 20px;
}

.login-card {
  border-radius: 18px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.12);
  max-width: 380px;
  width: 100%;
}

.brand {
  align-items: center;
  display: flex;
  gap: 14px;
  margin-bottom: 26px;
}

.brand-logo {
  align-items: center;
  background: linear-gradient(135deg, #6366f1, #22d3ee);
  border-radius: 14px;
  color: #fff;
  display: flex;
  font-size: 24px;
  font-weight: 700;
  height: 48px;
  justify-content: center;
  width: 48px;
}

.brand-text h1 {
  font-size: 22px;
  line-height: 1.1;
  margin: 0;
}

.brand-text p {
  color: var(--n-text-color-3, #8a8f98);
  font-size: 13px;
  margin: 4px 0 0;
}
</style>
