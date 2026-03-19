<template>
  <div>
    <!-- 悬浮的小机器人头像 -->
    <div
      id="ai-avatar"
      @click="toggleChatbox"
      :class="{ active: isChatboxVisible }"
    >
      <img src="/model/img/robot.png" alt="AI Robot" />
    </div>
    <div v-if="isChatboxVisible" class="chat-container">
      <el-card class="chat-box">
        <div class="messages">
          <div
            v-for="(message, index) in messages"
            :key="index"
            :class="['message', message.sender]"
          >
            <span>{{ message.text }}</span>
          </div>
        </div>
        <el-input
          v-model="newMessage"
          placeholder="Type your message..."
          @keyup.enter="sendMessage"
          class="input-box"
        >
          <template #append>
            <el-button @click="sendMessage" type="primary">Send</el-button>
          </template>
        </el-input>
      </el-card>
    </div>
  </div>
</template>

<script>
export default {
  data() {
    return {
      messages: [
        { text: "Hello! How can I help you today?", sender: "ai" },
        { text: "I have a question about my order.", sender: "user" },
        {
          text: "Sure, I can help with that. What is your order number?",
          sender: "ai",
        },
      ],
      newMessage: "",
      isChatboxVisible: false,
    };
  },
  methods: {
    toggleChatbox() {
      this.isChatboxVisible = !this.isChatboxVisible;
    },
    sendMessage() {
      if (this.newMessage.trim() !== "") {
        this.messages.push({ text: this.newMessage, sender: "user" });
        this.newMessage = "";
        // Simulate a response from the AI
        setTimeout(() => {
          this.messages.push({
            text: "This is a response from the AI.",
            sender: "ai",
          });
        }, 1000);
      }
    },
  },
};
</script>

<style scoped>
#ai-avatar {
  position: fixed;
  bottom: 20px;
  left: 20px;
  width: 60px;
  height: 60px;
  border-radius: 50%;
  background-color: #ff6347;
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
}

#ai-avatar.active {
  transform: scale(1.2); /* 放大效果 */
}

.chat-container {
  position: fixed;
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100vh;
  background-color: #f5f5f5;
  z-index: 100;
}

.chat-box {
  width: 400px;
  max-height: 600px;
  flex: 1 0 auto;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.messages {
  flex: 1;
  overflow-y: auto;
  padding: 10px;
}

.message {
  margin: 5px 0;
  padding: 10px;
  border-radius: 5px;
}

.message.user {
  background-color: #d1e7dd;
  align-self: flex-end;
}

.message.ai {
  background-color: #f8d7da;
  align-self: flex-start;
}

.input-box {
  margin-top: 10px;
}
</style>
