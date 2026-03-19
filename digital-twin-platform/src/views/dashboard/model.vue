<template>
  <div class="app-container">
    <div class="x-frame">
      <div
        v-if="showLoading"
        class="loading-outer"
        id="loading"
      >
          <div class="loading-inner one"></div>
          <div class="loading-inner two"></div>
          <div class="loading-inner three"></div>
      </div>
      <iframe
        id="x_iframe_ref"
        src="./model/pump.html"
        style="width: 100%;height: 100%"
        frameborder="no"
        border="0"
        marginwidth="0"
        marginheight="0"
        scrolling="no"
        allowtransparency="yes"
      />
    </div>
  </div>
</template>

<script>
export default {
  data() {
    return {
      form: {
        name: '',
        region: '',
        date1: '',
        date2: '',
        delivery: false,
        type: [],
        resource: '',
        desc: ''
      },
      showLoading: true,
    }
  },
  created() {
      window.addEventListener('message',this.iframeEventListener);
      window.hideLoading = () => {
        this.showLoading = false;
      }
  },
  methods: {
    onSubmit() {
      this.$message('submit!')
    },
    onCancel() {
      this.$message({
        message: 'cancel!',
        type: 'warning'
      })
    },
  }
}
</script>

<style scoped>
.app-container {
  width: 100%;
  height: calc(100vh - 50px);
  background-color: #000;
}
.x-frame {
    width: 100%;
    height: 100%;
    position: absolute;
    top: 0;
    left: 0;
    z-index: 0;
    overflow: hidden;
}
</style>

