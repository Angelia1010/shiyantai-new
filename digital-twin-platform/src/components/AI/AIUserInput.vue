<template>
  <div class="input-container">
    <el-input
      type="textarea"
      placeholder="给AI发送消息..."
      v-model="userInput"
      show-word-limit
      resize="none"
      :autosize="{ minRows: 2, maxRows: 6 }"
    >
    </el-input>

    <div style="display: flex; justify-content: space-between">
      <div style="display: flex; justify-content: flex-start">
        <el-button round size="small" class="el-icon-help" disabled
          >深度思考</el-button
        >
        <el-button size="small" round class="el-icon-eleme" disabled
          >联网搜索</el-button
        >
      </div>
      <div style="display: flex; justify-content: flex-end">
        <el-button
          circle
          style="
            padding: 4px;
            font-size: 24px;
            width: 38px;
            height: 38px;
            background-color: #409eff; /* 蓝色背景 */
            border: none;
            display: flex;
            align-items: center;
            justify-content: center;
          "
        >
          <i
            class="el-icon-arrow-up"
            style="color: white; /* 白色箭头 */ font-size: 18px"
          ></i>
        </el-button>
        <el-button
          type="primary"
          icon="el-icon-top"
          circle
          style="padding: 4px; font-size: 24px; width: 38px; height: 38px"
          @click="sendUserInput"
          :disabled="userInput.length === 0"
        >
        </el-button>
      </div>
    </div>
  </div>
</template>
<script>
export default {
  data() {
    return {
      userInput: "",
    };
  },
  onmounted() {},
  computed: {},
  methods: {
    sendUserInput() {
      this.$emit("send-user-input", this.userInput);
      this.userInput = "";
    },
  },
};
</script>

<style scoped>
.input-container {
  background-color: #f3f4f6;
  padding: 10px;
  border-radius: 10px;
  width: 100%;
}

::v-deep .el-textarea__inner {
  border: none;
  background-color: transparent;
  outline: none;
}
</style>
