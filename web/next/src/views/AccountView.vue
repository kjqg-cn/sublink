<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  useMessage,
  useDialog,
  NCard,
  NInput,
  NButton,
  NForm,
  NFormItem,
  NInputGroup,
  NInputGroupLabel
} from 'naive-ui'
import MD5 from 'crypto-js/md5'
import { setUser, currentUsername } from '@/api'

const router = useRouter()
const message = useMessage()
const dialog = useDialog()

const username = ref(currentUsername())
const newUserName = ref('')
const password = ref('')
const saving = ref(false)

function logout() {
  localStorage.removeItem('token')
  localStorage.removeItem('refresh')
  router.push('/login')
}

async function handleSave() {
  if (!/^\w{4,16}$/.test(newUserName.value)) {
    message.warning('请输入 4-16 位字母或数字账号')
    return
  }
  if (!/^[\x20-\x7E]{4,32}$/.test(password.value)) {
    message.warning('请输入 4-32 位密码，可包含大小写字母、数字和符号')
    return
  }
  saving.value = true
  try {
    const { code, msg } = await setUser({
      username: username.value,
      newUserName: newUserName.value,
      password: MD5(password.value).toString()
    })
    message[code === 200 ? 'success' : 'warning'](msg)
    if (code === 200) {
      message.info('账号已修改，请重新登录')
      logout()
    }
  } catch {
    message.error('修改失败')
  } finally {
    saving.value = false
  }
}

function confirmLogout() {
  dialog.warning({
    title: '注销',
    content: '此操作将注销并重新登录，是否继续？',
    positiveText: '确定',
    negativeText: '取消',
    onPositiveClick: logout
  })
}
</script>

<template>
  <n-card class="account-card" title="账号设置">
    <div class="current-user">
      当前账号：<strong>{{ username }}</strong>
      <n-button size="tiny" tertiary @click="confirmLogout">注销</n-button>
    </div>
    <n-form>
      <n-form-item label="新账号">
        <n-input-group>
          <n-input-group-label>新账号</n-input-group-label>
          <n-input v-model:value="newUserName" placeholder="4-16 位字母或数字" />
        </n-input-group>
      </n-form-item>
      <n-form-item label="新密码">
        <n-input-group>
          <n-input-group-label>新密码</n-input-group-label>
          <n-input
            v-model:value="password"
            type="password"
            show-password-on="click"
            placeholder="4-32 位"
            @keydown.enter="handleSave"
          />
        </n-input-group>
      </n-form-item>
    </n-form>
    <n-button type="primary" :loading="saving" @click="handleSave">修改</n-button>
  </n-card>
</template>

<style scoped>
.account-card {
  margin: 0 auto;
  max-width: 520px;
}

.current-user {
  align-items: center;
  display: flex;
  gap: 12px;
  margin-bottom: 18px;
}
</style>
