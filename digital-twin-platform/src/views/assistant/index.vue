<template>
  <div class="assistant">
    <el-card class="files-card" shadow="never">
      <div slot="header">数据文件分析</div>
      <el-input v-model="dataPath" size="small" placeholder="数据目录，如 D:\试验数据" @keyup.enter.native="loadFiles">
        <el-button slot="append" icon="el-icon-search" @click="loadFiles">列出文件</el-button>
      </el-input>
      <div class="file-list">
        <el-empty v-if="!files.length" description="输入数据目录后列出文件" :image-size="80" />
        <div v-for="file in files" :key="file" class="file-item">
          <span class="file-name" :title="file">{{ file }}</span>
          <el-button size="mini" type="primary" plain :disabled="busy" @click="analyze(file)">分析</el-button>
        </div>
      </div>
      <p class="hint">支持 TDMS、Excel、TXT 文件。分析会按窗口逐段调用大模型，耗时取决于文件大小。</p>
    </el-card>

    <el-card class="chat-card" shadow="never" :body-style="{ display: 'flex', flexDirection: 'column', height: '100%' }">
      <div slot="header" class="chat-header">
        <span>智能助手</span>
        <el-button size="mini" :disabled="busy" @click="newSession">新会话</el-button>
      </div>
      <div ref="messages" class="messages">
        <div v-if="!messages.length" class="welcome">我是试验台故障诊断助手，可以回答运维排障问题，也可以分析左侧的数据文件。</div>
        <div v-for="msg in messages" :key="msg.id" :class="['message', msg.role]">
          <!-- 内容先经 renderMarkdown 转义，再作为 HTML 显示 -->
          <div class="bubble" v-html="render(msg.text)" />
        </div>
        <div v-if="busy" class="message assistant"><div class="bubble">{{ progress || '思考中...' }}</div></div>
      </div>
      <div class="input-row">
        <el-input
          v-model="question"
          type="textarea"
          :rows="2"
          resize="none"
          placeholder="输入问题，Ctrl+Enter 发送"
          @keyup.ctrl.enter.native="ask"
        />
        <el-button v-if="busy" type="danger" @click="cancel">停止</el-button>
        <el-button v-else type="primary" :disabled="!question.trim()" @click="ask">发送</el-button>
      </div>
    </el-card>
  </div>
</template>

<script>
import { analyzeFile, chat } from '@/api/ai'
import { listFiles } from '@/api/files'
import { renderMarkdown } from '@/utils/markdown'

let messageId = 0
const newSessionId = () => `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`

export default {
  name: 'Assistant',
  data() {
    return {
      dataPath: '',
      files: [],
      messages: [],
      question: '',
      busy: false,
      progress: '',
      sessionId: newSessionId()
    }
  },
  beforeDestroy() {
    this.cancel()
  },
  methods: {
    render: renderMarkdown,
    push(role, text) {
      this.messages.push({ id: ++messageId, role, text })
      this.$nextTick(() => {
        const box = this.$refs.messages
        if (box) box.scrollTop = box.scrollHeight
      })
    },
    newSession() {
      this.messages = []
      this.sessionId = newSessionId()
    },
    async loadFiles() {
      if (!this.dataPath.trim()) return
      try {
        this.files = (await listFiles(this.dataPath.trim())).files
      } catch (e) {
        this.files = []
      }
    },
    cancel() {
      if (this.abortController) this.abortController.abort()
    },
    // 统一处理流式事件；返回 Promise，结束或出错时 resolve
    async run(start) {
      this.busy = true
      this.progress = ''
      this.abortController = new AbortController()
      try {
        await start(this.abortController.signal, event => {
          if (event.event === 'error') this.push('assistant', `**出错了：** ${event.message}`)
          else this.onEvent(event)
        })
      } catch (e) {
        if (e.name !== 'AbortError') this.push('assistant', `**请求失败：** ${e.message}`)
      } finally {
        this.busy = false
        this.progress = ''
        this.abortController = null
      }
    },
    onEvent(event) {
      if (event.event === 'start') {
        this.progress = `共 ${event.windows} 个分析窗口，开始分析...`
      } else if (event.event === 'window') {
        this.progress = `正在分析第 ${event.index}/${event.total} 个窗口...`
        this.push('assistant', `**窗口 ${event.index}（样本 ${event.start}–${event.end}）**\n${event.analysis}`)
      } else if (event.event === 'summary') {
        this.push('assistant', `### 总体评估\n${event.text}`)
      } else if (event.event === 'answer') {
        this.push('assistant', event.text)
      }
    },
    analyze(fileName) {
      this.push('user', `分析文件：${fileName}`)
      return this.run((signal, onEvent) =>
        analyzeFile({ path: this.dataPath.trim(), fileName, sessionId: this.sessionId }, onEvent, signal))
    },
    ask() {
      const question = this.question.trim()
      if (!question || this.busy) return
      this.question = ''
      this.push('user', question)
      return this.run((signal, onEvent) => chat(question, this.sessionId, onEvent, signal))
    }
  }
}
</script>

<style lang="scss" scoped>
.assistant {
  display: flex;
  gap: 20px;
  padding: 20px;
  height: 100%;
  box-sizing: border-box;
}
.files-card {
  width: 340px;
  flex-shrink: 0;
  overflow-y: auto;
}
.file-list {
  margin-top: 12px;
}
.file-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 0;
  border-bottom: 1px solid #f0f0f0;
}
.file-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-right: 8px;
  font-size: 13px;
}
.hint {
  color: #999;
  font-size: 12px;
}
.chat-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.chat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.messages {
  flex: 1;
  overflow-y: auto;
  padding-bottom: 12px;
  min-height: 0;
}
.welcome {
  color: #999;
  text-align: center;
  margin-top: 40px;
}
.message {
  display: flex;
  margin: 10px 0;
  &.user {
    justify-content: flex-end;
    .bubble {
      background: #409eff;
      color: #fff;
    }
  }
}
.bubble {
  max-width: 80%;
  padding: 8px 12px;
  border-radius: 8px;
  background: #f4f6f8;
  line-height: 1.6;
  word-break: break-word;
  ::v-deep p {
    margin: 4px 0;
  }
  ::v-deep pre {
    background: #2d2d2d;
    color: #eee;
    padding: 8px;
    border-radius: 4px;
    overflow-x: auto;
  }
}
.input-row {
  display: flex;
  gap: 10px;
  align-items: flex-end;
}
</style>
