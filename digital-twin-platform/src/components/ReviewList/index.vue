<template>
  <div v-if="reviews && reviews.length" class="review-list">
    <el-divider content-position="left">扩展分析意见（仅供参考，不改变诊断结论）</el-divider>
    <el-card v-for="rv in reviews" :key="rv.name" shadow="never" class="review">
      <div slot="header">
        <b>{{ rv.label }}</b><span v-if="rv.title">：{{ rv.title }}</span>
        <el-tag v-if="rv.status !== 'done'" size="mini" type="info" class="tag">未完成</el-tag>
        <span v-else-if="rv.confidence !== undefined && rv.confidence !== null" class="muted">（把握 {{ Math.round(rv.confidence * 100) }}%）</span>
      </div>
      <div v-if="rv.status !== 'done'" class="muted">{{ rv.error }}</div>
      <template v-else>
        <p v-if="rv.summary"><b>{{ rv.summary }}</b></p>
        <p v-if="rv.details" class="details">{{ rv.details }}</p>
        <ul v-if="rv.suggestions && rv.suggestions.length">
          <li v-for="(sug, k) in rv.suggestions" :key="k">{{ sug }}</li>
        </ul>
        <div v-if="rv.references && rv.references.length" class="muted refs">依据：{{ rv.references.join('；') }}</div>
      </template>
    </el-card>
  </div>
</template>

<script>
/** 诊断扩展推理插件（如大模型智能体，见后端 diagnosis/plugins.py）的独立意见：report.reviews */
export default {
  name: 'ReviewList',
  props: { reviews: { type: Array, default: () => [] } }
}
</script>

<style scoped>
.review {
  margin-bottom: 10px;
}
.details {
  white-space: pre-wrap;
}
.muted {
  color: #909399;
}
.tag {
  margin-left: 8px;
}
.refs {
  font-size: 12px;
}
</style>
