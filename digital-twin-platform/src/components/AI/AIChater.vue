<template>
  <div>
    <!-- 悬浮的小机器人头像 -->
    <div
      id="ai-avatar"
      @click="toggleChatbox"
      :class="{ active: isChatboxVisible }"
    >
      <img src="/model/img/robot1.png" alt="AI Robot" />
    </div>

    <!-- AI 对话框 -->
    <div
      v-if="isChatboxVisible"
      id="chat-container"
      :class="{
        'nonempty-chat-container': messages.length > 0,
        'empty-chat-container': messages.length === 0,
      }"
    >
      <div
        v-if="messages.length === 0"
        style="
          display: flex;
          flex-direction: row;
          align-items: center;
          gap: 10px;
          padding: 20px;
        "
      >
        <img class="robot-head" src="/model/img/robot1.png" />
        <h3>我是专属AI助理，很高兴见到你！</h3>
      </div>
      <div
        class="messages"
        ref="messagesContainer"
        style="
          display: flex;
          flex-direction: column;
          flex-grow: 1 0 auto;
          overflow-y: auto;
          gap: 10px;
          width: 100%;
          padding-left: 80px;
          padding-right: 80px;
          padding-top: 20px;
          padding-bottom: 20px;
        "
      >
        <div
          style="
            display: flex;
            flex-direction: column;
            gap: 10px;
            align-items: center;
          "
        >
          <div
            style="
              display: flex;
              flex-direction: column;
              gap: 10px;
              width: 100%;
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
                <div v-html="message.text" style="padding-top: 7px"></div>
              </div>
            </div>
            <div v-if="true" class="message">
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
          </div>

          <div
            v-if="messages.length > 0"
            style="
              display: flex;
              flex-direction: row;
              justify-content: center;
              align-items: center;
              gap: 10px;
              padding: 5px;
              background-color: #dbeafe;
              color: #4d6bfe;
              width: 140px;
              border-radius: 10px;
              cursor: pointer;
              font-size: 14px;
              margin-top: 40px;
              margin-bottom: 20px;
            "
            @click="newChat"
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 18 18"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path
                d="M5.856 17.121a.979.979 0 0 1-.327-.06.839.839 0 0 1-.283-.177.739.739 0 0 1-.187-.255.724.724 0 0 1-.07-.303l-.02-1.609a4.663 4.663 0 0 1-1.446-.455 4.252 4.252 0 0 1-.637-.401c-.199-.146-.385-.31-.553-.492a4.442 4.442 0 0 1-.45-.577 4.303 4.303 0 0 1-.327-.637 3.823 3.823 0 0 1-.206-.686 3.729 3.729 0 0 1-.064-.704V6.478c0-.261.025-.516.077-.771a4.43 4.43 0 0 1 .244-.747 4.062 4.062 0 0 1 .932-1.28c.2-.183.418-.347.65-.493.23-.145.482-.267.739-.364a4.21 4.21 0 0 1 .81-.225c.27-.054.553-.078.835-.078H8.55c.103 0 .2.018.29.054a.7.7 0 0 1 .411.376.667.667 0 0 1-.161.766.736.736 0 0 1-.25.151.764.764 0 0 1-.29.055H5.573c-.186 0-.366.012-.54.049-.18.03-.353.079-.52.145-.167.061-.328.14-.482.237-.148.091-.29.2-.418.316a2.897 2.897 0 0 0-.347.388c-.097.14-.187.286-.257.444a2.473 2.473 0 0 0-.206.977v4.287c0 .17.013.333.051.503a2.549 2.549 0 0 0 .772 1.33 2.721 2.721 0 0 0 .913.559c.167.066.347.115.527.152.18.03.36.048.546.048a.904.904 0 0 1 .61.23.848.848 0 0 1 .194.262.84.84 0 0 1 .07.303l.007.99 1.915-1.293a2.877 2.877 0 0 1 1.64-.492h2.372c.186 0 .366-.018.54-.048.18-.03.353-.08.52-.146.168-.067.329-.146.483-.237.148-.091.29-.2.418-.316.128-.121.244-.249.347-.388a2.8 2.8 0 0 0 .257-.444 2.47 2.47 0 0 0 .206-.977V8.585a.646.646 0 0 1 .225-.492.679.679 0 0 1 .244-.152.814.814 0 0 1 .585 0c.09.03.174.085.244.152a.657.657 0 0 1 .225.492V10.8c0 .261-.032.516-.083.771a4.192 4.192 0 0 1-.245.74c-.109.244-.244.468-.398.687a3.735 3.735 0 0 1-.534.6c-.2.183-.418.347-.65.493a4.134 4.134 0 0 1-.738.364 4.7 4.7 0 0 1-.81.225c-.27.054-.553.079-.836.079h-1.877c-.604 0-1.144.164-1.633.491l-2.54 1.713a.913.913 0 0 1-.514.157z"
                fill="currentColor"
              ></path>
              <path
                d="M15.866 4.125h-4.174c-.41 0-.741.313-.741.7 0 .387.332.7.741.7h4.174c.41 0 .742-.313.742-.7 0-.387-.332-.7-.742-.7z"
                fill="currentColor"
              ></path>
              <path
                d="M14.537 2.932c0-.396-.34-.717-.759-.717s-.758.32-.758.717v3.786c0 .396.34.717.758.717.42 0 .76-.321.76-.717V2.932z"
                fill="currentColor"
              ></path>
            </svg>
            开启新对话
          </div>
        </div>
      </div>

      <div
        class="input-container"
        style="flex-direction: column; width: 100%; max-width: 600px"
      >
        <textarea
          ref="textarea"
          rows="2"
          v-model="userInput"
          @keyup.enter="sendMessage"
          placeholder="给 AI 发送消息..."
          class="input-box"
          @input="autoResize"
        />
        <div style="display: flex; justify-content: space-between">
          <div style="flex: 1 1 auto"></div>
          <div style="flex: 0 0 auto">
            <div
              :class="dsIconStyle"
              style="
                width: 32px;
                height: 32px;
                border-radius: 16px;
                display: flex;
                justify-content: center;
                align-items: center;
              "
              @click="sendMessage"
            >
              <div
                style="
                  font-size: 16px;
                  width: 16px;
                  height: 16px;
                  display: flex;
                  justify-content: center;
                  align-items: center;
                "
              >
                <svg
                  width="14"
                  height="16"
                  viewBox="0 0 14 16"
                  fill="none"
                  xmlns="http://www.w3.org/2000/svg"
                >
                  <path
                    fill-rule="evenodd"
                    clip-rule="evenodd"
                    d="M7 16c-.595 0-1.077-.462-1.077-1.032V1.032C5.923.462 6.405 0 7 0s1.077.462 1.077 1.032v13.936C8.077 15.538 7.595 16 7 16z"
                    fill="currentColor"
                  ></path>
                  <path
                    fill-rule="evenodd"
                    clip-rule="evenodd"
                    d="M.315 7.44a1.002 1.002 0 0 1 0-1.46L6.238.302a1.11 1.11 0 0 1 1.523 0c.421.403.421 1.057 0 1.46L1.838 7.44a1.11 1.11 0 0 1-1.523 0z"
                    fill="currentColor"
                  ></path>
                  <path
                    fill-rule="evenodd"
                    clip-rule="evenodd"
                    d="M13.685 7.44a1.11 1.11 0 0 1-1.523 0L6.238 1.762a1.002 1.002 0 0 1 0-1.46 1.11 1.11 0 0 1 1.523 0l5.924 5.678c.42.403.42 1.056 0 1.46z"
                    fill="currentColor"
                  ></path>
                </svg>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import axios from "axios";
import { chat, chatStream } from "@/api/home";
import { simpleMarkdownToHtml } from "@/utils/markdown";

export default {
  data() {
    return {
      userInput: "",
      messages: [],
      apiKey: "your-openai-api-key", // 请替换为你的 API 密钥
      isChatboxVisible: false, // 控制对话框是否可见
      sessionId: this.generateUniqueId(), // 初始化 sessionId
      loading: false, // Add loading state
      loadingDots: "", // Add state for loading dots
    };
  },
  onmounted() {
    this.autoResize();
  },
  computed: {
    isInputEmpty() {
      return this.userInput.trim() === "";
    },
    dsIconStyle() {
      // return "send-button-active";
      return this.isInputEmpty ? "send-button-inactive" : "send-button-active";
      // return "send-button-inactive";
    },
  },
  methods: {
    generateUniqueId() {
      return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    },
    toggleChatbox() {
      this.isChatboxVisible = !this.isChatboxVisible;
    },
    startLoadingDots() {
      console.log("startLoadingDots", this.loadingDotsInterval);
      if (this.loadingDotsInterval) {
        console.log(
          "loadingDotsInterval already exists, no need to create a new one."
        );
        return;
      }
      this.loadingDotsInterval = setInterval(() => {
        this.loadingDots =
          this.loadingDots.length < 6 ? this.loadingDots + "." : "";
        console.log("loadingDots", this.loadingDots);
      }, 200);
    },

    stopLoadingDots() {
      console.log("stopLoadingDots", this.loadingDotsInterval);
      clearInterval(this.loadingDotsInterval);
      this.loadingDotsInterval = null;
      this.loadingDots = "";
    },

    async sendMessage() {
      if (this.isInputEmpty) return;

      this.loading = true; // Show loading indicator
      this.startLoadingDots(); // Start dots animation

      // Add user message
      this.messages.push({
        id: this.generateUniqueId(),
        sender: "user",
        text: this.userInput,
      });
      const userMessage = this.userInput;
      this.userInput = "";

      const aiMessage = {
        id: this.generateUniqueId(),
        sender: "ai",
        text: "",
      };
      this.messages.push(aiMessage);
      try {
        await chatStream(userMessage, this.sessionId, (chunk) => {
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
        console.error("Error initializing chat stream:", error);
        aiMessage.text = "Sorry, there was an error.";
      } finally {
        this.loading = false; // Hide loading indicator
        this.stopLoadingDots(); // Stop dots animation
      }
    },
    autoResize() {
      const textarea = this.$refs.textarea; // 获取 textarea 元素
      textarea.style.height = "auto"; // 重置高度
      textarea.style.height = Math.min(textarea.scrollHeight, 150) + "px"; // 设置高度，不超过最大高度
    },
    newChat() {
      console.log("new chat");
      this.messages = [];
      this.sessionId = this.generateUniqueId(); // 刷新 sessionId
    },
    scrollHeight() {
      this.$nextTick(() => {
        const messagesContainer = this.$refs.messagesContainer;
        if (messagesContainer) {
          messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }
      });
    },
  },
  watch: {
    messages() {
      this.scrollHeight(); // Scroll to the bottom when messages change
    },
  },
};
</script>

<style scoped>
#ai-avatar {
  position: fixed;
  bottom: 20px;
  right: 20px;
  width: 60px;
  height: 60px;
  border-radius: 50%;
  background-color: transparent;
  display: flex;
  justify-content: center;
  align-items: center;
  cursor: pointer;
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
  transition: transform 0.3s ease;
  z-index: 100;
}

#ai-avatar img {
  width: 40px;
  height: 40px;
  background-color: transparent;
}

#ai-avatar.active {
  transform: scale(1.2); /* 放大效果 */
}

#chat-container {
  position: fixed;
  top: 50%; /* 将顶部定位到窗口的 50% */
  left: 50%; /* 将左侧定位到窗口的 50% */
  transform: translate(-50%, -50%); /* 通过 transform 将元素自身居中 */
  width: 800px;
  border: 1px solid #ccc;
  border-radius: 10px;
  background: white;
  height: 700px;
  display: flex;
  flex-direction: column;
  align-items: center;
  z-index: 100;
  /* padding: 40px 40px 40px 40px; */
  scrollbar-color: #d3d3d3 transparent; /* Light border color */
}

.nonempty-chat-container {
  justify-content: space-between;
}

.empty-chat-container {
  justify-content: center;
}

.input-box {
  /*no border*/
  border: none;
  /*透明背景*/
  background-color: transparent;
  /*no outline*/
  outline: none;
  /*no resize*/
  resize: none;
  /* overflow: hidden; */
}

.message {
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  /* opacity: 0; */
  /* animation: fadeIn 0.3s ease forwards; */
}

.input-container {
  display: flex;
  /*gray background*/
  background-color: #f3f4f6;
  padding: 10px;
  /*radius 10px*/
  border-radius: 10px;
  max-width: 800px;
  margin: 20px;
}

input {
  border: 1px solid #ccc;
  border-radius: 5px;
}

button {
  border: 1px solid #ccc;
  border-radius: 5px;
  background-color: #007bff;
  color: white;
  cursor: pointer;
  transition: background-color 0.3s ease;
}

button:disabled {
  background-color: #ccc;
  cursor: not-allowed;
}

button:hover:enabled {
  background-color: #0056b3;
}

.ai {
  background-color: transparent;
  align-self: flex-start;
  font-size: 16px;
}

.user {
  background-color: #f0f0f0;
  align-self: flex-end;
  padding: 8px 20px;
  border-radius: 14px;
  background-color: #eff6ff;
  font-size: 16px;
}

/* .message-content {
  border-radius: 15px;
  max-width: 98%;
  word-wrap: break-word;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
} */

.send-button-active {
  background-color: #007bff;
  color: white;
  border: none;
  cursor: pointer;
}

.send-button-inactive {
  background-color: #ccc;
  color: white;
  border: none;
  border-radius: 5px;
  padding: 5px 10px;
  cursor: not-allowed;
}

.robot-head {
  width: 32px;
  height: 32px;
  border-radius: 50%;
}
</style>
