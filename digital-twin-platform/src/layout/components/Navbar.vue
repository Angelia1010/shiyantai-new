<template>
  <div class="navbar">
    <hamburger
      :is-active="sidebar.opened"
      class="hamburger-container"
      @toggleClick="toggleSideBar"
    />

    <breadcrumb class="breadcrumb-container" />

    <div class="right-menu">
      <el-dropdown class="avatar-container" trigger="click">
        <div class="avatar-wrapper">
          <i class="el-icon-user-solid user-avatar" />
          <span class="user-name">{{ name }}</span>
          <i class="el-icon-caret-bottom" />
        </div>
        <el-dropdown-menu slot="dropdown" class="user-dropdown">
          <router-link to="/">
            <el-dropdown-item>工作台</el-dropdown-item>
          </router-link>
          <el-dropdown-item divided @click.native="logout">
            <span style="display: block">退出登录</span>
          </el-dropdown-item>
        </el-dropdown-menu>
      </el-dropdown>
    </div>
  </div>
</template>

<script>
import { mapGetters } from "vuex";
import Breadcrumb from "@/components/Breadcrumb";
import Hamburger from "@/components/Hamburger";

export default {
  components: {
    Breadcrumb,
    Hamburger,
  },
  computed: {
    ...mapGetters(["sidebar", "name"]),
  },
  methods: {
    toggleSideBar() {
      this.$store.dispatch("app/toggleSideBar");
    },
    logout() {
      this.$store.dispatch("user/logout");
      this.$router.push(`/login?redirect=${encodeURIComponent(this.$route.fullPath)}`);
    },
  },
};
</script>

<style lang="scss" scoped>
.navbar {
  height: 50px;
  overflow: hidden;
  position: relative;
  background: #0b1626;
  border-bottom: 1px solid rgba(56, 189, 248, 0.14);
  color: #c7d2e0;

  .hamburger-container {
    line-height: 46px;
    height: 100%;
    float: left;
    cursor: pointer;
    transition: background 0.3s;
    -webkit-tap-highlight-color: transparent;

    &:hover {
      background: rgba(255, 255, 255, 0.05);
    }
  }

  ::v-deep .hamburger {
    fill: #c7d2e0;
  }

  ::v-deep .el-breadcrumb__inner,
  ::v-deep .el-breadcrumb__inner a {
    color: #c7d2e0;
  }

  .breadcrumb-container {
    float: left;
  }

  .right-menu {
    float: right;
    height: 100%;
    line-height: 50px;

    &:focus {
      outline: none;
    }

    .avatar-container {
      margin-right: 20px;
      height: 100%;

      .avatar-wrapper {
        display: flex;
        align-items: center;
        gap: 6px;
        height: 50px;
        cursor: pointer;

        .user-avatar {
          font-size: 18px;
          color: #38bdf8;
        }

        .user-name {
          color: #eef3fa;
          font-size: 14px;
          line-height: 1;
        }

        .el-icon-caret-bottom {
          font-size: 12px;
          color: #7891ad;
        }
      }
    }
  }
}
</style>
