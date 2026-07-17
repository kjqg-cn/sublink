<template>
  <div>
    <el-card class="box-card">
      <div slot="header" class="clearfix">
        <div class="brand-block">
          <strong>订阅管理</strong>
          <span>集中管理节点、生成订阅地址</span>
        </div>
        <div class="header-account">
          <span>{{ username }}</span>
          <el-button size="small" @click="handleLogout">退出</el-button>
        </div>
      </div>
      <el-tabs v-model="activeName">
        <el-tab-pane>
          <span slot="label" class="el-icon-umbrella"> 订阅管理</span>
          <el-radio v-model="radio1" label="1" border v-if="optionList.length !== 0">编辑订阅</el-radio>
          <el-radio v-model="radio1" label="2" border>创建订阅</el-radio>
          <el-radio v-model="radio1" label="3" border>订阅解析</el-radio>
          <el-radio v-model="radio1" label="4" border>全局设置</el-radio>
          <div style="margin-bottom: 10px"></div>
          <!--        编辑订阅-->
          <div v-if="radio1 === '1'">
            <div class="subscription-editor-layout">
              <aside class="subscription-list">
                <div class="subscription-list-title">订阅列表 <span>拖动排序</span></div>
                <div
                  v-for="item in optionList"
                  :key="item"
                  class="subscription-list-item"
                  :class="{ active: optionValue === item }"
                  draggable="true"
                  @click="optionValue = item"
                  @dragstart="handleSubDragStart(item)"
                  @dragover.prevent
                  @drop="handleSubDrop(item)"
                >
                  <i class="el-icon-rank"></i>
                  <span>{{ item }}</span>
                </div>
              </aside>
              <section class="subscription-editor-main">
                <template v-if="optionValue">
                <div class="subscription-heading">
                  <div>
                    <h2>{{ optionValue }}</h2>
                    <span>共 {{ NodeList.length }} 个节点</span>
                  </div>
                  <div class="subscription-actions">
                    <rename :current-name="optionValue" @handleRename="handleRename" @handleDel="handleDel"></rename>
                    <el-button @click="NewNode.dialogVisible = true" type="primary" size="mini">新增节点</el-button>
                  </div>
                </div>
                <el-dialog title="新增一个节点" :visible.sync="NewNode.dialogVisible">
                  <el-input v-model.trim="NewNode.node" type="textarea" rows="10" placeholder="节点" />
                  <div style="margin-bottom: 10px"></div>

                  <el-input v-model.trim="NewNode.remarks" placeholder="备注" @keyup.enter.native="handleNewNode" />
                  <span slot="footer" class="dialog-footer">
                    <el-button @click="NewNode.dialogVisible = false">取 消</el-button>
                    <el-button type="primary" @click="handleNewNode">确 定</el-button>
                  </span>
                </el-dialog>
                <div class="node-toolbar"><el-button icon="el-icon-edit-outline" @click="batchDialogVisible = true">批量编辑节点</el-button></div>
                <Nodelist :list="NodeList" @RefreshSub="RefreshSub" @CopySubNode="CopySubNode"></Nodelist>
              <el-dialog title="批量编辑节点" :visible.sync="batchDialogVisible" width="80%">
                <div class="batch-edit-tip">每行一个节点，节点和备注使用 | 分隔。此操作不会改变订阅列表顺序。</div>
                <el-input type="textarea" placeholder="节点多个用回车分开,每个节点最后面带上|为备注信息" v-model="optionSub" rows="20" />
                <span slot="footer" class="dialog-footer">
                  <el-button @click="batchDialogVisible = false">取 消</el-button>
                  <el-button type="primary" @click="handleSet">保存全部节点</el-button>
                </span>
              </el-dialog>
            <div class="generate-toolbar" v-if="optionSub !== ''">
              <el-tag style="margin-right: 10px">生成类型</el-tag>
              <el-select v-model="EDIT.value" placeholder="生成类型" @change="handleUrl('edit')">
                <el-option v-for="(item, index) in EDIT.option" :key="index" :value="item">
                </el-option>
              </el-select>
              <MyClash v-if="EDIT.value === 'clash'" style="margin-left: 10px"></MyClash>
              <MySurge v-if="EDIT.value === 'surge'" style="margin-left: 10px"></MySurge>
              <MySingBox v-if="EDIT.value === 'sing-box'" style="margin-left: 10px"></MySingBox>
            </div>
            <div v-if="optionSub !== ''">
              <div class="address-label"><el-tag type="success">Token 新地址</el-tag><span>新客户端请使用此地址</span></div>
              <el-input type="text" v-model="optionUrl" readonly>
                <template slot="prepend">订阅地址</template>
                <template slot="append">
                  <el-button size="small" icon="el-icon-document-copy" @click="handleCopy(optionUrl)">复制</el-button>
                  <el-button size="small" icon="iconfont icon-erweima" @click="handleOpenQr(optionUrl)">
                    二维码
                  </el-button>
                </template>
              </el-input>
              <div class="legacy-control">
                <div class="legacy-copy">
                  <strong>旧地址兼容</strong>
                  <span class="legacy-description">仅为仍在使用 Base64 地址的客户端开启</span>
                </div>
                <div class="legacy-toggle">
                  <span class="legacy-status">{{ legacyEnabled ? '已开启' : '已关闭' }}</span>
                  <el-switch
                    v-model="legacyEnabled"
                    :disabled="legacyUpdating"
                    active-color="#2e8b9d"
                    inactive-color="#c5cbd1"
                    @change="handleLegacyChange"
                  />
                </div>
              </div>
              <template v-if="legacyEnabled">
                <div class="address-label"><el-tag type="info">Base64 旧地址</el-tag><span>用于兼容已部署的旧客户端</span></div>
                <el-input type="text" v-model="legacyUrl" readonly>
                  <template slot="prepend">旧版地址</template>
                  <template slot="append"><el-button size="small" icon="el-icon-document-copy" @click="handleCopy(legacyUrl)">复制</el-button></template>
                </el-input>
              </template>
            </div>
                </template>
                <div v-else class="subscription-empty">
                  <i class="el-icon-umbrella"></i>
                  <strong>请选择订阅</strong>
                  <span>从左侧订阅列表中选择一个订阅进行管理</span>
                </div>
              </section>
            </div>
          </div>
          <!--          创建订阅-->
          <div v-if="radio1 === '2'">
            <el-input type="text" placeholder="订阅名称(支持emoji)" v-model.trim="name" maxlength="20" show-word-limit />
            <div style="margin-bottom: 10px"></div>
            <el-input type="textarea" placeholder="订阅或者节点多个用回车分开,每个节点最后面带上|为备注信息" v-model="sub" rows="10" />
            <div style="margin-bottom: 10px"></div>
            <el-button round style="position: relative;left: 50%;transform: translate(-50%)" @click="handleCreate">创建订阅
            </el-button>
          </div>
          <div v-if="radio1 === '3'">
            <MyParser></MyParser>
          </div>
          <div v-if="radio1 === '4'" @change="handleConfig">
            <el-checkbox v-model="Config.udp">udp</el-checkbox>
            <el-checkbox v-model="Config.skipCert">跳过证书</el-checkbox>
            <el-checkbox v-model="Config.emoji">emoji入口国旗</el-checkbox>
          </div>
        </el-tab-pane>

        <el-tab-pane>
          <span slot="label"><i class="el-icon-user-solid"> 账号设置</i></span>
          <USER></USER>
        </el-tab-pane>
        <el-tab-pane>
          <span slot="label"><i class="el-icon-date"> 登录记录</i></span>
          <MyAddress></MyAddress>
        </el-tab-pane>
      </el-tabs>
    </el-card>
    <!--    二维码组件-->
    <el-dialog title="二维码" :visible.sync="isQrShow" width="30%">
      <vue-qr :text="QrTest"></vue-qr>
    </el-dialog>
  </div>
</template>

<script>
import { GetSubs, CreateSub, DelSub, SetSub, RenameSub, CreateNode, SortSubs, SetSubLegacy } from '@/api/sub'
import { SetConfig, GetConfig } from '@/api/config'
import USER from '@/components/user'
import MyClash from '@/components/clash'
import MySurge from '@/components/surge'
import MySingBox from '@/components/singbox'
import MyAddress from '@/components/address'
import Nodelist from '@/components/nodelist'
import Rename from '@/components/rename'
import MyParser from '@/components/parser'
import VueQr from 'vue-qr'
export default {
  name: 'MyIndex',
  data () {
    return {
      activeName: '',
      username: '',
      name: '',
      sub: '',
      sublist: [],
      url: '',
      radio1: '2',
      list: [],
      optionValue: '',
      optionSub: '',
      optionUrl: '',
      legacyUrl: '',
      legacyEnabled: false,
      legacyUpdating: false,
      optionList: [],
      timer: null,
      dragSubName: '',
      batchDialogVisible: false,
      EDIT: {
        value: 'v2ray',
        option: ['v2ray', 'clash', 'surge', 'sing-box']
      },
      isQrShow: false,
      QrTest: '',
      ver: process.env.VUE_APP_VER,
      NodeList: [],
      NewNode: {
        dialogVisible: false,
        remarks: '',
        node: ''
      },
      Config: {
        udp: false,
        skipCert: false,
        emoji: false
      }
    }
  },
  created () {
    this.handleCurrentUser()
    this.GetSubs()
    this.GetConfig()
  },
  watch: {
    optionValue (newValue) {
      // console.log('监视' + newValue)
      // console.log(this.list)
      this.NodeList = this.list.filter(item => item.name === newValue)
      // console.log(res)
      const list = this.NodeList.map(item => item.node + (item.remarks ? '|' + item.remarks : ''))
      // console.log(list.join('\n'))
      this.optionValue = newValue
      this.optionSub = list.join('\n')
      this.legacyEnabled = this.NodeList.some(item => item.legacy_enabled)
      this.handleUrl('edit')
    }
  },
  methods: {
    handleCurrentUser () {
      const token = JSON.parse(localStorage.getItem('token'))
      if (!token) return
      const payload = token.split('.')[1]
      this.username = JSON.parse(atob(payload)).sub
    },
    handleLogout () {
      localStorage.removeItem('token')
      localStorage.removeItem('refresh')
      this.$router.push('/login')
    },
    async GetSubs () { // 获取全部订阅
      const res = await GetSubs()
      if (res.length === 0) {
        this.list = []
        this.optionList = []
        this.NodeList = []
        this.optionValue = ''
        this.optionSub = ''
        this.optionUrl = ''
        this.legacyUrl = ''
        this.legacyEnabled = false
      } else {
        this.list = res
        this.optionList = Array.from(new Set(this.list.map(item => item.name)))
        this.NodeList = this.list.filter(item => item.name === this.optionValue)
        const NodeList = this.NodeList.map(item => item.node + (item.remarks ? '|' + item.remarks : ''))
        // console.log(list.join('\n'))
        this.optionSub = NodeList.join('\n')
        this.legacyEnabled = this.NodeList.some(item => item.legacy_enabled)
      }
      this.list.length > 0 ? this.radio1 = '1' : this.radio1 = '2'
    },
    async handleCreate () {
      if (this.sub === '' || this.name === '') return false
      // await this.isSubAddress('create')
      clearTimeout(this.timer)
      this.timer = setTimeout(async () => {
        this.sublist = this.sub.split('\n')
        const { code, msg } = await CreateSub({
          name: this.name.trim(),
          node: this.sublist
        })
        this.$message({
          message: msg,
          type: code === 200 ? 'success' : 'warning'
        })
        if (code === 200) {
          await this.GetSubs() // 刷新全部节点
          this.radio1 = '1' // 切换到编辑订阅
          this.optionValue = this.name // 编辑订阅标题选择
          this.name = ''
          this.sub = ''
        }
      }, 1000)
    },
    async handleSet () { // 编辑订阅
      if (this.optionSub === '') return false
      // await this.isSubAddress('edit')
      const res = this.list.find(item => item.name === this.optionValue)
      console.log(res, res.node)
      const list = this.optionSub.split('\n')
      const { code, msg } = await SetSub({
        name: this.optionValue.trim(),
        node: res.node,
        newNode: list
      })
      this.$message({
        message: msg,
        type: code === 200 ? 'success' : 'warning'
      })
      if (code === 200) {
        this.batchDialogVisible = false
        // console.log('修改成功')
        // this.optionValue = ''
        this.GetSubs() // 刷新全部节点
        // console.log(this.NodeList)
      }
    },
    handleSubDragStart (name) {
      this.dragSubName = name
    },
    async handleSubDrop (targetName) {
      if (!this.dragSubName || this.dragSubName === targetName) return
      const names = [...this.optionList]
      const fromIndex = names.indexOf(this.dragSubName)
      const targetIndex = names.indexOf(targetName)
      names.splice(fromIndex, 1)
      names.splice(targetIndex, 0, this.dragSubName)
      const previousNames = this.optionList
      this.optionList = names
      try {
        const { code, msg } = await SortSubs(names)
        if (code !== 200) this.optionList = previousNames
        this.$message({
          type: code === 200 ? 'success' : 'warning',
          message: msg
        })
      } catch (error) {
        this.optionList = previousNames
        this.$message.warning('订阅排序保存失败，请刷新后重试')
      } finally {
        this.dragSubName = ''
      }
    },
    handleOpenUrl (url) {
      window.open(url)
    },
    handleOpenQr (url) { // 打开二维码展示
      this.isQrShow = true
      this.QrTest = url
      // window.open(url)
    },
    handleDel () {
      clearTimeout(this.timer)
      this.timer = setTimeout(() => {
        this.$confirm(`删除后无法恢复，确定删除订阅“${this.optionValue}”吗？`, '删除订阅', {
          confirmButtonText: '确认删除',
          cancelButtonText: '取消',
          type: 'warning',
          center: false,
          customClass: 'delete-sub-confirm'
        }).then(async () => {
          const { code, msg } = await DelSub(this.optionValue)
          if (code === 200) {
            this.optionList = this.optionList.filter(item => item !== this.optionValue)
            this.optionValue = '' // 更新选项值为空字符串
          }
          this.$message({
            type: code === 200 ? 'success' : 'warning',
            message: msg
          })
          if (this.optionList.length === 0) this.radio1 = '2'
        }).catch(() => {

        })
      }, 100)
    },
    handleCopy (value) {
      this.$copyText(value)
      this.$message({
        type: 'success',
        message: '复制成功'
      })
    },
    handleUrl (value) {
      if (value === 'edit') {
        const selected = this.list.find(item => item.name === this.optionValue)
        if (selected && selected.access_token) {
          this.optionUrl = location.origin + `/sub/${this.EDIT.value}/${selected.access_token}`
        } else {
          this.optionUrl = location.origin + `/sub/${this.EDIT.value}/${this.encodeLegacyName(this.optionValue)}`
        }
        this.legacyUrl = location.origin + `/sub/${this.EDIT.value}/${this.encodeLegacyName(this.optionValue)}`
      }
    },
    encodeLegacyName (name) {
      const encoder = new TextEncoder()
      const byteText = encoder.encode(name)
      return encodeURIComponent(btoa(String.fromCharCode.apply(null, byteText)))
    },
    async handleLegacyChange (enabled) {
      if (!this.optionValue) return
      const subscriptionName = this.optionValue
      const previousEnabled = !enabled
      this.legacyUpdating = true
      try {
        const { code, msg } = await SetSubLegacy(subscriptionName, enabled)
        if (code !== 200) {
          if (this.optionValue === subscriptionName) {
            this.legacyEnabled = previousEnabled
          }
        } else {
          this.list
            .filter(item => item.name === subscriptionName)
            .forEach(item => { item.legacy_enabled = enabled })
          if (this.optionValue === subscriptionName) {
            this.legacyEnabled = enabled
          }
        }
        this.$message({
          type: code === 200 ? 'success' : 'warning',
          message: msg
        })
      } catch (error) {
        if (this.optionValue === subscriptionName) {
          this.legacyEnabled = previousEnabled
        }
        this.$message.warning('旧地址兼容状态保存失败，请刷新后重试')
      } finally {
        this.legacyUpdating = false
      }
    },
    CopySubNode (text) {
      this.handleCopy(text)
    },
    RefreshSub () {
      this.GetSubs()
    },
    async handleRename (rename) {
      if (this.optionValue !== '' && rename !== '') {
        const { code, msg } = await RenameSub(this.optionValue,
          {
            newName: rename
          }
        )
        this.$message({
          message: msg,
          type: code === 200 ? 'success' : 'warning'
        })
        if (code === 200) {
          await this.GetSubs()
          this.optionValue = rename // 更新当前订阅标题
          this.handleUrl('edit')
        }
      }
    },
    async handleNewNode () {
      const { code, msg } = await CreateNode({
        name: this.optionValue,
        node: this.NewNode.node.trim(),
        remarks: this.NewNode.remarks.trim()
      })
      if (code === 200) {
        // console.log(code, msg)
        this.GetSubs()
        this.NewNode.dialogVisible = false
        this.NewNode.node = ''
        this.NewNode.remarks = ''
      }
      this.$message({
        type: code === 200 ? 'success' : 'warning',
        message: msg
      })
    },
    handleConfig () {
      clearTimeout(this.timer)
      this.timer = setTimeout(async () => {
        const { code, msg } = await SetConfig({
          udp: this.Config.udp,
          skipcert: this.Config.skipCert,
          emoji: this.Config.emoji
        })
        this.$message({
          type: code === 200 ? 'success' : 'warning',
          message: msg
        })
      }, 1000)
    },
    async GetConfig () {
      const { udp, skipcert, emoji } = await GetConfig()
      this.Config.udp = udp
      this.Config.skipCert = skipcert
      this.Config.emoji = emoji
    }
  },
  components: {
    USER,
    MyClash,
    MySurge,
    MySingBox,
    MyAddress,
    Nodelist,
    MyParser,
    Rename,
    VueQr
  }
}
</script>

<style scoped>
@import "@/assets/icon/iconfont.css";
.box-card {
  border: 0;
  border-radius: 0;
  box-shadow: none;
  height: 100vh;
  overflow: hidden;
}
.box-card ::v-deep .el-card__header {
  align-items: center;
  border-bottom: 1px solid #e1e6eb;
  display: flex;
  height: 64px;
  padding: 0 28px;
}
.brand-block {
  align-items: baseline;
  display: flex;
  gap: 14px;
}
.brand-block strong {
  color: #17202a;
  font-size: 20px;
}
.brand-block span {
  color: #7b8794;
  font-size: 13px;
}
.clearfix {
  align-items: center;
  display: flex;
  justify-content: space-between;
  width: 100%;
}
.header-account { align-items: center; display: flex; gap: 12px; }
.header-account span { color: #34495e; }
.box-card ::v-deep .el-card__body {
  padding: 0;
}
.box-card ::v-deep .el-tabs {
  display: grid;
  grid-template-columns: 232px minmax(0, 1fr);
  height: calc(100vh - 64px);
}
.box-card ::v-deep .el-tabs__header {
  background: #202b36;
  align-self: start;
  height: calc(100vh - 64px);
  margin: 0;
  overflow-y: auto;
  padding: 28px 16px;
  position: sticky;
  top: 64px;
}
.box-card ::v-deep .el-tabs__nav-wrap::after,
.box-card ::v-deep .el-tabs__active-bar {
  display: none;
}
.box-card ::v-deep .el-tabs__nav {
  display: flex;
  flex-direction: column;
  float: none;
  transform: none !important;
  width: 100%;
}
.box-card ::v-deep .el-tabs__item {
  border-radius: 4px;
  color: #d5dde5;
  height: 42px;
  line-height: 42px;
  margin-bottom: 4px;
  padding: 0 16px !important;
  text-align: left;
}
.box-card ::v-deep .el-tabs__item:hover {
  color: #fff;
}
.box-card ::v-deep .el-tabs__item.is-active {
  background: #2e8b9d;
  color: #fff;
}
.box-card ::v-deep .el-tabs__content {
  box-sizing: border-box;
  height: calc(100vh - 64px);
  min-width: 0;
  overflow-y: auto;
  padding: 24px 28px;
}
.box-card ::v-deep .el-radio.is-bordered {
  border-radius: 4px;
  margin: 0 8px 16px 0;
}
.subscription-editor-layout {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  gap: 24px;
  min-height: 0;
}
.subscription-list {
  align-self: start;
  background: #f7f9fa;
  border: 1px solid #e1e6eb;
  max-height: calc(100vh - 112px);
  overflow-y: auto;
  padding: 16px;
  position: sticky;
  top: 24px;
}
.subscription-list-title {
  color: #909399;
  font-size: 12px;
  margin-bottom: 8px;
}
.subscription-list-title span {
  float: right;
}
.subscription-list-item {
  align-items: center;
  border-radius: 4px;
  cursor: pointer;
  display: flex;
  gap: 8px;
  margin-bottom: 4px;
  overflow: hidden;
  padding: 10px 12px;
}
.subscription-list-item:hover {
  background: #f5f7fa;
}
.subscription-list-item.active {
  background: #2e8b9d;
  color: #fff;
}
.subscription-list-item span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.batch-edit-tip {
  color: #606266;
  margin-bottom: 12px;
}
.address-label {
  align-items: center;
  display: flex;
  gap: 8px;
  margin: 12px 0 6px;
}
.address-label span {
  color: #909399;
  font-size: 12px;
}
.legacy-control {
  align-items: center;
  background: #f7f9fa;
  border: 1px solid #e1e6eb;
  border-radius: 4px;
  display: flex;
  gap: 24px;
  justify-content: space-between;
  margin-top: 16px;
  padding: 14px 16px;
}
.legacy-copy {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.legacy-copy strong {
  color: #34495e;
  font-size: 14px;
}
.legacy-description {
  color: #909399;
  font-size: 12px;
}
.legacy-toggle {
  align-items: center;
  display: flex;
  flex: 0 0 auto;
  gap: 10px;
}
.legacy-status {
  color: #606266;
  font-size: 13px;
  min-width: 42px;
  text-align: right;
}
.subscription-editor-main {
  min-width: 0;
  padding-bottom: 24px;
}
.subscription-heading { align-items: center; display: flex; justify-content: space-between; margin-bottom: 20px; }
.subscription-heading h2 { color: #17202a; font-size: 22px; margin: 0 0 5px; }
.subscription-heading > div > span { color: #7b8794; font-size: 13px; }
.subscription-actions { align-items: center; display: flex; gap: 12px; }
.subscription-actions ::v-deep > div { display: flex; gap: 12px; }
.subscription-actions ::v-deep .el-button { margin-left: 0 !important; }
.node-toolbar { margin-bottom: 12px; }
.generate-toolbar { align-items: center; display: flex; margin-top: 28px; }
.subscription-empty { align-items: center; color: #909399; display: flex; flex-direction: column; gap: 10px; justify-content: center; min-height: 420px; }
.subscription-empty i { font-size: 38px; }
.subscription-empty strong { color: #606266; font-size: 16px; }
.subscription-select {
  display: none;
}
.subscription-editor-main ::v-deep .el-table {
  margin-top: 8px;
}
.subscription-editor-main ::v-deep .el-button--success,
.subscription-editor-main ::v-deep .el-button--danger,
.subscription-editor-main ::v-deep .el-button--primary {
  border-radius: 4px;
  box-shadow: none;
  font-size: 13px;
  font-weight: 500;
  height: 34px;
  padding: 0 14px;
}
.subscription-editor-main ::v-deep .el-button--success {
  background: #fff;
  border-color: #2e8b9d;
  color: #2e8b9d;
}
.subscription-editor-main ::v-deep .el-button--danger {
  background: #fff;
  border-color: #e56b6f;
  color: #c0392b;
}
.subscription-editor-main ::v-deep .el-button--primary {
  background: #2e8b9d;
  border-color: #2e8b9d;
  color: #fff;
}
.subscription-editor-main ::v-deep .el-table__fixed-right {
  box-shadow: -6px 0 10px rgba(31, 45, 61, .06);
}
@media (max-width: 768px) {
  .box-card {
    height: auto;
    min-height: 100dvh;
    overflow: visible;
  }
  .box-card ::v-deep .el-tabs {
    display: block;
    height: auto;
  }
  .box-card ::v-deep .el-tabs__header {
    height: auto;
    padding: 8px;
    position: static;
  }
  .box-card ::v-deep .el-tabs__nav {
    flex-direction: row;
  }
  .box-card ::v-deep .el-tabs__item {
    flex: 1;
    margin: 0;
    text-align: center;
  }
  .box-card ::v-deep .el-tabs__content {
    height: auto;
    overflow: visible;
    padding: 16px;
  }
  .subscription-editor-layout {
    grid-template-columns: 1fr;
  }
  .subscription-list {
    border-bottom: 1px solid #ebeef5;
    border-right: 0;
    max-height: none;
    overflow: visible;
    padding-bottom: 12px;
    padding-right: 0;
    position: static;
  }
  .legacy-control {
    align-items: flex-start;
  }
}
</style>
