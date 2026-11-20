<template>
  <div class="login-container">
    <el-form
      ref="loginForm"
      :model="loginForm"
      :rules="loginRules"
      class="login-form"
      auto-complete="on"
      label-position="left"
    >
      <div class="title-container">
        <span class="title-mark" />
        <h3 class="title">标准试验台数字化校验系统</h3>
        <p class="subtitle">燃油泵试验数据监控与故障诊断</p>
      </div>

      <el-form-item prop="username">
        <span class="svg-container">
          <svg-icon icon-class="user" />
        </span>
        <el-input
          ref="username"
          v-model="loginForm.username"
          placeholder="用户名"
          name="username"
          type="text"
          tabindex="1"
          auto-complete="on"
        />
      </el-form-item>

      <el-form-item prop="password">
        <span class="svg-container">
          <svg-icon icon-class="password" />
        </span>
        <el-input
          :key="passwordType"
          ref="password"
          v-model="loginForm.password"
          :type="passwordType"
          placeholder="密码"
          name="password"
          tabindex="2"
          auto-complete="on"
          @keyup.enter.native="handleLogin"
        />
        <span class="show-pwd" @click="showPwd">
          <svg-icon
            :icon-class="passwordType === 'password' ? 'eye' : 'eye-open'"
          />
        </span>
      </el-form-item>

      <el-button
        :loading="loading"
        type="primary"
        style="width: 100%; margin-bottom: 30px; height: 44px; font-size: 15px"
        @click.native.prevent="handleLogin"
        >登录</el-button
      >
    </el-form>
  </div>
</template>

<script>
export default {
  name: "Login",
  data() {
    return {
      loginForm: {
        username: "",
        password: "",
      },
      loginRules: {
        username: [{ required: true, trigger: "blur", message: "请输入用户名" }],
        password: [{ required: true, trigger: "blur", message: "请输入密码" }],
      },
      loading: false,
      passwordType: "password",
      redirect: undefined,
    };
  },
  watch: {
    $route: {
      handler(route) {
        this.redirect = route.query && route.query.redirect;
      },
      immediate: true,
    },
  },
  methods: {
    showPwd() {
      this.passwordType = this.passwordType === "password" ? "" : "password";
      this.$nextTick(() => {
        this.$refs.password.focus();
      });
    },
    handleLogin() {
      this.$refs.loginForm.validate(async (valid) => {
        if (!valid) return;
        this.loading = true;
        try {
          await this.$store.dispatch("user/login", this.loginForm);
          this.$router.push({ path: this.redirect || "/" });
        } catch (e) {
          // 错误提示已由请求拦截器显示
        } finally {
          this.loading = false;
        }
      });
    },
  },
};
</script>

<style lang="scss">
/* 修复input 背景不协调 和光标变色 */
/* Detail see https://github.com/PanJiaChen/vue-element-admin/pull/927 */

$bg: #111a29;
$light_gray: #fff;
$cursor: #fff;

@supports (-webkit-mask: none) and (not (cater-color: $cursor)) {
  .login-container .el-input input {
    color: $cursor;
  }
}

/* reset element-ui css */
.login-container {
  .el-input {
    display: inline-block;
    height: 47px;
    width: 85%;

    input {
      background: transparent;
      border: 0px;
      -webkit-appearance: none;
      border-radius: 0px;
      padding: 12px 5px 12px 15px;
      color: $light_gray;
      height: 47px;
      caret-color: $cursor;

      &:-webkit-autofill {
        box-shadow: 0 0 0px 1000px $bg inset !important;
        -webkit-text-fill-color: $cursor !important;
      }
    }
  }

  .el-form-item {
    border: 1px solid rgba(120, 150, 190, 0.22);
    background: rgba(5, 10, 18, 0.45);
    border-radius: 6px;
    color: #454545;
    transition: border-color 0.2s;

    &:focus-within {
      border-color: #2f6bff;
    }
  }
}
</style>

<style lang="scss" scoped>
$dark_gray: #7d8ba0;
$light_gray: #eef3fa;

.login-container {
  min-height: 100%;
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background:
    radial-gradient(ellipse at 30% 20%, rgba(47, 107, 255, 0.18) 0%, transparent 55%),
    radial-gradient(ellipse at 80% 90%, rgba(6, 182, 212, 0.1) 0%, transparent 50%),
    #0b111c;
  overflow: hidden;

  .login-form {
    position: relative;
    width: 420px;
    max-width: calc(100% - 32px);
    padding: 40px 36px 12px;
    border-radius: 12px;
    background: rgba(17, 26, 41, 0.88);
    border: 1px solid rgba(120, 150, 190, 0.16);
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.45);
    overflow: hidden;
  }

  .svg-container {
    padding: 6px 5px 6px 15px;
    color: $dark_gray;
    vertical-align: middle;
    width: 30px;
    display: inline-block;
  }

  .title-container {
    position: relative;
    margin-bottom: 32px;

    .title-mark {
      display: block;
      width: 32px;
      height: 4px;
      border-radius: 2px;
      background: #2f6bff;
      margin-bottom: 16px;
    }

    .title {
      font-size: 22px;
      color: $light_gray;
      margin: 0 0 6px;
      font-weight: 600;
      letter-spacing: 1px;
    }

    .subtitle {
      margin: 0;
      font-size: 13px;
      color: $dark_gray;
    }
  }

  .show-pwd {
    position: absolute;
    right: 10px;
    top: 7px;
    font-size: 16px;
    color: $dark_gray;
    cursor: pointer;
    user-select: none;
  }
}
</style>
