<template>
  <div>
  <div class="node-table">
    <div class="node-table-row node-table-header"><div>节点</div><div>备注</div><div>操作</div></div>
    <div class="node-table-row" v-for="item in list" :key="item.id">
      <div class="node-cell" :title="item.node">{{ item.node }}</div>
      <div class="node-cell" :title="item.remarks">{{ item.remarks }}</div>
      <div class="node-actions">
        <el-button @click="handleEditPop(item)" type="text" size="small">编辑</el-button>
        <el-button @click="handleCopy(item)" type="text" size="small">复制</el-button>
        <el-button @click="handleDel(item)" type="text" size="small">删除</el-button>
      </div>
    </div>
  </div>
  <el-dialog
    title="单个节点编辑"
    :visible.sync="dialogVisible"
  >
    <el-input
      v-model.trim="Edit.node"
      type="textarea"
      rows="10"
      placeholder="节点"
    />
    <div style="margin-bottom: 10px"></div>

    <el-input
      v-model.trim="Edit.remarks"
      placeholder="备注"
      @keyup.enter.native="handleEdit"
    />
    <span slot="footer" class="dialog-footer">
    <el-button @click="dialogVisible = false">取 消</el-button>
    <el-button type="primary" @click="handleEdit">确 定</el-button>
  </span>
  </el-dialog>
  </div>
</template>

<script>
import { DelSubNode, SetNode } from '@/api/sub'
export default {
  name: 'NodeList',
  data () {
    return {
      dialogVisible: false,
      Edit: {
        id: 0,
        remarks: '',
        node: ''
      }
    }
  },
  props: {
    list: Array
  },
  created () {
    // console.log(this.list)
  },
  methods: {
    handleCopy ({ node }) {
      this.$emit('CopySubNode', node)
    },
    handleDel ({ id, node, remarks }) {
      console.log(id)
      const nodeLabel = remarks && remarks !== '无备注' ? remarks : node.slice(0, 40)
      this.$confirm(`删除后无法恢复，确定删除节点“${nodeLabel}”吗？`, '删除节点', {
        confirmButtonText: '确认删除',
        cancelButtonText: '取消',
        type: 'warning',
        center: false,
        customClass: 'delete-sub-confirm'
      }).then(async () => {
        const { code, msg } = await DelSubNode(id)
        if (code === 200) {
          this.$emit('RefreshSub')
        }
        this.$message({
          type: code === 200 ? 'success' : 'warning',
          message: msg
        })
      }).catch(() => {

      })
    },
    handleEditPop ({ id, node, remarks }) {
      this.Edit.id = id
      this.Edit.node = node
      this.Edit.remarks = remarks
      this.dialogVisible = true
    },
    async handleEdit () {
      const { code, msg } = await SetNode({
        id: this.Edit.id,
        node: this.Edit.node.trim(),
        remarks: this.Edit.remarks.trim()
      })
      if (code === 200) {
        // console.log(code, msg)
        this.$emit('RefreshSub')
        this.dialogVisible = false
      }
      this.$message({
        type: code === 200 ? 'success' : 'warning',
        message: msg
      })
    }

  }
}
</script>

<style scoped>
.node-table { border: 1px solid #e1e6eb; max-height: clamp(220px, 40vh, 430px); overflow-y: auto; width: 100%; }
.node-table-row { align-items: center; border-top: 1px solid #edf0f2; display: grid; grid-template-columns: 5fr 3.5fr 1.5fr; min-height: 48px; }
.node-table-row:first-child { border-top: 0; }
.node-table-row > div { min-width: 0; padding: 12px 18px; }
.node-table-header { background: #f7f9fa; color: #65727e; font-size: 12px; min-height: 42px; position: sticky; top: 0; z-index: 1; }
.node-cell { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.node-actions { white-space: nowrap; }
@media (max-width: 900px) { .node-table-row { grid-template-columns: minmax(260px,5fr) minmax(160px,3.5fr) 150px; } .node-table { overflow-x: auto; } }
</style>
