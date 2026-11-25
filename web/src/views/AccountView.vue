<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage, NCard, NInput, NButton, NForm, NFormItem, NTag } from 'naive-ui'
import { setUser, currentUsername } from '@/api'
import { clearSessionState, storageRemove } from '@/utils/storage'

const router = useRouter()
const message = useMessage()

const username = ref(currentUsername())
const oldPassword = ref('')
const newUserName = ref(username.value)
const password = ref('')
const saving = ref(false)

function clearAuthAndRedirect() {
  storageRemove('local', 'token')
  storageRemove('local', 'refresh')
  clearSessionState()
  router.push('/login')
}

async function handleSave() {
  if (saving.value) return
  if (!oldPassword.value) {
    message.warning('请输入当前密码')
    return
  }
  if (!/^[A-Za-z0-9_.-]{3,32}$/.test(newUserName.value)) {
    message.warning('请输入 3-32 位字母、数字、下划线、点或连字符账号')
    return
  }
  if (!/^[\x20-\x7E]{4,64}$/.test(password.value)) {
    message.warning('请输入 4-64 位密码，可包含大小写字母、数字和符号')
    return
  }
  saving.value = true
  try {
    const { code, msg } = await setUser({
      username: username.value,
      oldPassword: oldPassword.value,
      newUserName: newUserName.value,
      password: password.value
    })
    message[code === 200 ? 'success' : 'warning'](msg)
    if (code === 200) {
      message.info('账号已修改，请重新登录')
      clearAuthAndRedirect()
    }
  } catch {
    message.error('修改失败')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="page-section">
    <p class="page-desc">
      修改管理员账号或密码前需验证当前密码；保存成功后所有历史登录令牌将自动失效。
    </p>
    <div class="account-grid">
      <n-card size="small" title="修改登录凭据">
        <n-form class="account-form" @submit.prevent="handleSave">
          <n-form-item label="当前密码">
            <n-input
              v-model:value="oldPassword"
              type="password"
              show-password-on="click"
              placeholder="请输入当前密码以确认身份"
            />
          </n-form-item>
          <n-form-item label="新账号">
            <n-input v-model:value="newUserName" placeholder="3-32 位字母、数字或 _ . -" />
          </n-form-item>
          <n-form-item label="新密码">
            <n-input
              v-model:value="password"
              type="password"
              show-password-on="click"
              placeholder="4-64 位可打印字符"
            />
          </n-form-item>
          <n-button type="primary" :loading="saving" attr-type="submit">保存修改</n-button>
        </n-form>
      </n-card>

      <n-card size="small" title="当前会话与安全说明" class="account-aside">
        <div class="info-row">
          <span class="info-label">当前登录账号</span>
          <n-tag size="small" :bordered="false" type="primary" round>{{ username || '—' }}</n-tag>
        </div>
        <ul class="security-tips">
          <li>账号支持 3～32 位字母、数字及 <code>_ . -</code> 符号。</li>
          <li>密码支持 4～64 位可打印字符，后端以 PBKDF2-SHA256 哈希存储。</li>
          <li>修改凭据后会递增令牌版本，其他设备上的旧登录态将立即失效。</li>
        </ul>
      </n-card>
    </div>
  </div>
</template>

<style scoped>
.account-grid {
  align-items: start;
  display: grid;
  gap: 20px;
  grid-template-columns: minmax(0, 1fr) 340px;
}

.account-form {
  max-width: 480px;
}

.info-row {
  align-items: center;
  border-bottom: 1px solid var(--n-border-color, #eee);
  display: flex;
  justify-content: space-between;
  margin-bottom: 14px;
  padding-bottom: 12px;
}

.info-label {
  color: var(--n-text-color-2, #555);
  font-size: 13px;
}

.security-tips {
  color: var(--n-text-color-3, #8a8f98);
  font-size: 13px;
  line-height: 1.75;
  margin: 0;
  padding-left: 18px;
}

.security-tips li + li {
  margin-top: 6px;
}

@media (max-width: 900px) {
  .account-grid {
    grid-template-columns: 1fr;
  }
}
</style>
