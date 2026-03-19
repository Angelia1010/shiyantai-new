<template>
  <div style="height: 100%; margin: 0 auto; /* 水平居中 */">
    <div
      v-if="messages.length == 0"
      style="
        display: flex;
        flex-direction: column;
        justify-content: flex-start;
        align-items: center;
        height: 100%;
        padding: 20px;
        gap: 10px;
      "
    >
      <div
        v-if="messages.length === 0"
        style="display: flex; flex-direction: row; align-items: center"
      >
        <img class="robot-head" src="/model/img/robot1.png" />
        <h3>我是专属AI助理，很高兴见到你！</h3>
      </div>
      <AIUserInput @send-user-input="sendMessage" style="width: 800px" />

      <el-tabs
        v-model="activeName"
        @tab-click="handleClick"
        style="width: 800px; margin: 20px 0px"
      >
        <el-tab-pane label="智能诊断" name="diagnose">
          <el-input
            v-model="workspace"
            placeholder="请输入工作台路径"
            @input="handlePathChange"
            style="margin: 20px 0px"
          ></el-input>
          <el-empty
            v-if="fileList.length === 0"
            description="输入工作台路径，选择文件进行诊断"
          ></el-empty>
          <div id="fileContainer">
            <el-card
              v-for="(filename, index) in fileList"
              :key="index"
              shadow="hover"
              class="custom-card"
            >
              <div class="filename">{{ filename }}</div>
              <el-button
                class="diagnose-button"
                @click="diagnoseFile(filename)"
              >
                点我诊断
              </el-button>
            </el-card>
          </div>
        </el-tab-pane>
        <el-tab-pane label="更多功能" name="tab1">更多功能敬请期待</el-tab-pane>
        <el-tab-pane label="敬请期待" name="tab2">更多功能敬请期待</el-tab-pane>
      </el-tabs>
    </div>

    <div
      v-if="messages.length > 0"
      style="
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        align-items: center;
        height: 100%;
        padding: 20px;
      "
    >
      <div
        id="message-container"
        ref="messagesContainer"
        style="
          display: flex;
          flex-direction: column;
          gap: 10px;
          width: 100%;
          overflow-y: auto !important;
          scrollbar-color: #d3d3d3 transparent;
          flex-grow: 1;
          padding-right: 260px;
          padding-top: 20px;
          padding-bottom: 20px;
          padding-left: 260px;
        "
      >
        <div v-for="message in messages" :key="message.id" class="message">
          <div
            v-if="message.sender === 'user'"
            class="message-content user"
            v-html="message.text"
          ></div>
          <div
            v-else
            class="message-content ai"
            style="
              display: flex;
              flex-direction: row;
              justify-content: space-between;
              gap: 10px;
            "
          >
            <img class="robot-head" src="/model/img/robot1.png" />
            <div
              v-html="message.text"
              style="padding-top: 7px; flex: 1; word-break: break-word"
            ></div>
          </div>
        </div>
        <div v-if="loading" class="message">
          <div
            class="message-content ai"
            style="
              display: flex;
              flex-direction: row;
              justify-content: space-between;
              gap: 10px;
            "
          >
            <img
              class="robot-head"
              src="/model/img/robot1.png"
              style="visibility: hidden"
            />

            <div
              v-html="loadingDots"
              style="padding-top: 7px; flex: 1; word-break: break-word"
            ></div>
          </div>
        </div>
        <button
          class="el-icon-chat-square"
          @click="newChat"
          style="
            align-self: center;
            width: 140px;
            border: none;
            padding: 10px;
            background-color: #dbeafe;
            color: #409eff;
            border-radius: 10px;
            cursor: pointer;
            margin-top: 20px;
            margin-bottom: 20px;
          "
        >
          开启新对话
        </button>
      </div>
      <AIUserInput @send-user-input="sendMessage" style="width: 800px" />
    </div>
  </div>
</template>

<script>
import axios from "axios";
import { chatStream, chatStreamWithTmdsFile } from "@/api/home";
import AIUserInput from "./AIUserInput.vue";
import { readExcelApi, fileListAPI, storeReport } from "@/api/home";
import { simpleMarkdownToHtml } from "@/utils/markdown"; // 假设你有一个函数来处理 Markdown 转换
export default {
  components: {
    AIUserInput,
  },
  data() {
    return {
      messages: [],
      apiKey: "your-openai-api-key", // 请替换为你的 API 密钥
      isChatboxVisible: false, // 控制对话框是否可见
      expendMenu: true,
      history: ["对话1", "对话2", "对话3"],
      activeName: "diagnose",
      workspace: "",
      fileList: "",
      filename: "",
      sessionId: this.generateUniqueId(), // Initialize sessionId
      loading: false, // Add loading state
      loadingDots: "", // Add state for loading dots
    };
  },
  onmounted() {},
  computed: {},
  methods: {
    generateUniqueId() {
      return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    },
    async sendMessage(userInput) {
      if (!userInput) return;

      this.loading = true; // Show loading indicator
      this.startLoadingDots(); // Start dots animation

      // 添加用户消息
      this.messages.push({
        id: this.generateUniqueId(),
        sender: "user",
        text: userInput,
      });

      const aiMessage = {
        id: this.generateUniqueId(),
        sender: "ai",
        text: "",
      };
      this.messages.push(aiMessage);

      try {
        await chatStream(userInput, this.sessionId, (chunk) => {
          console.log("Received chunk:", chunk);
          //check if chunk contains </think> tag
          if (chunk.includes("</think>")) {
            //remove </think> tag and context before from chunk
            const startIndex = chunk.indexOf("</think>") + "</think>".length;
            const processedChunk = chunk.substring(startIndex, chunk.length);
            aiMessage.text += simpleMarkdownToHtml(processedChunk);
          } else {
            aiMessage.text += simpleMarkdownToHtml(chunk);
          }
          aiMessage.text = aiMessage.text.replace(/^(<br\s*\/?>)+/g, "");
          this.scrollHeight(); // Scroll to the bottom after updating
        });
      } catch (error) {
        console.error("Error fetching chat response:", error);
        aiMessage.text = "Sorry, there was an error.";
      } finally {
        this.loading = false; // Hide loading indicator
        this.stopLoadingDots(); // Stop dots animation
      }

      // 保证显示最新消息
      this.$nextTick(() => {
        const messagesContainer = this.$refs.messagesContainer;
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
      });
    },

    newChat() {
      console.log("new chat");
      this.messages = [];
      this.sessionId = this.generateUniqueId(); // Reset sessionId for a new chat
    },

    handleTabChange(tab, event) {
      console.log(tab, event);
    },

    handlePathChange(path) {
      fileListAPI(path).then(
        (response) => {
          console.log(response);
          this.fileList = response.files || [];
        },
        (error) => {
          console.log(error);
          this.fileList = [];
        }
      );
    },

    async diagnoseFile(filename) {
      this.loading = true; // Show loading indicator
      this.startLoadingDots(); // Start dots animation

      const aiMessage = {
        id: this.generateUniqueId(),
        sender: "ai",
        text: "",
      };
      this.messages.push(aiMessage);

      try {
        await chatStreamWithTmdsFile(
          this.sessionId,
          `${this.workspace}/${filename}`,
          (chunk) => {
            console.log("Received chunk:", chunk);
            //check if chunk contains </think> tag
            if (chunk.includes("</think>")) {
              //remove </think> tag and context before from chunk
              const startIndex = chunk.indexOf("</think>") + "</think>".length;
              const processedChunk = chunk.substring(startIndex, chunk.length);
              aiMessage.text += simpleMarkdownToHtml(processedChunk);
            } else {
              aiMessage.text += simpleMarkdownToHtml(chunk);
            }
            aiMessage.text = aiMessage.text.replace(/^(<br\s*\/?>)+/g, "");
            this.scrollHeight(); // Scroll to the bottom after updating
          }
        );
      } catch (error) {
        console.error("Error fetching diagnosis response:", error);
        aiMessage.text = "Sorry, there was an error.";
      } finally {
        this.loading = false; // Hide loading indicator
        this.stopLoadingDots(); // Stop dots animation
      }
    },
    scrollHeight() {
      this.$nextTick(() => {
        const messagesContainer = this.$refs.messagesContainer;
        if (messagesContainer) {
          messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }
      });
    },
    startLoadingDots() {
      if (this.loadingDotsInterval) return;
      this.loadingDotsInterval = setInterval(() => {
        this.loadingDots =
          this.loadingDots.length < 6 ? this.loadingDots + "." : "";
      }, 200);
    },

    stopLoadingDots() {
      clearInterval(this.loadingDotsInterval);
      this.loadingDotsInterval = null;
      this.loadingDots = "";
    },
  },

  watch: {
    messages() {
      this.scrollHeight();
    },
  },
};
</script>

<style scoped>
::v-deep .el-tabs__nav-wrap::after {
  width: 0px;
}

::v-deep .el-card__body {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 800px;
  padding: 5px 10px;
}

.menu-button {
  font-size: 28px;
}

.ai {
  background-color: transparent;
  align-self: flex-start;
  font-size: 16px;
  width: 100%;
  word-wrap: break-word;
  overflow-wrap: break-word;
}

.user {
  align-self: flex-end;
  padding: 8px 20px;
  border-radius: 14px;
  background-color: #eff6ff;
  font-size: 16px;
  max-width: 100%;
  word-wrap: break-word;
  overflow-wrap: break-word;
}

.robot-head {
  width: 32px;
  height: 32px;
  border-radius: 50%;
}

.message {
  display: flex;
  flex-direction: column;
  width: 100%;
}

.message-content {
  max-width: 100%;
  word-break: break-word;
}

#message-container::-webkit-scrollbar {
  width: 8px; /* Width of the scrollbar */
}

#message-container::-webkit-scrollbar-track {
  background: transparent; /* Transparent track */
}

#message-container::-webkit-scrollbar-thumb {
  background-color: transparent; /* Light gray with transparency */
  border: 1px solid #d3d3d3; /* Very light border */
  border-radius: 10px; /* Rounded edges */
}

#fileContainer {
  display: flex;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px; /* 网格项之间的间距 */
  overflow-y: auto;
  max-height: 450px;
}

.filename {
  white-space: nowrap; /* 禁止换行 */
  overflow: hidden; /* 隐藏超出部分 */
  text-overflow: ellipsis; /* 超出部分用省略号表示 */
  max-width: 100%; /* 确保文本不会超出卡片宽度 */
}

.diagnose-button {
  border: none;
  color: #409eff;
  cursor: pointer;
}

.loading-dots {
  font-size: 16px;
  color: #409eff;
  text-align: left;
  margin-top: 10px;
}
</style>
