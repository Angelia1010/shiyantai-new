<template>
  <div class="app-container">
    <el-form :model="dynamicValidateForm" ref="dynamicValidateForm" label-width="110px" class="demo-dynamic">
      <el-form-item v-for="(domain, index) in dynamicValidateForm.address" :label="'配置地址（' + (+index + 1) + '）'"
        :key="domain.key" :prop="'address.' + index + '.value'">
        <el-input v-model="domain.value"></el-input><el-button @click.prevent="removeDomain(domain)">删除</el-button>
      </el-form-item>
      <el-form-item>
        <el-button @click="addDomain">新增配置</el-button>
        <el-button @click="resetForm('dynamicValidateForm')">重置</el-button>
        <el-button type="primary" @click="submitForm('dynamicValidateForm')">开始监测</el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<script>
export default {
  data() {
    return {
      dynamicValidateForm: {
        address: [{
          value: ''
        }],
      }
    };
  },
  methods: {
    submitForm(formName) {
      this.$refs[formName].validate((valid) => {
        console.log(this.dynamicValidateForm)
        if (valid) {
          this.$message.success('同步成功');
        } else {
          console.log('error submit!!');
          return false;
        }
      });
    },
    resetForm(formName) {
      this.$refs[formName].resetFields();
    },
    removeDomain(item) {
      if (this.dynamicValidateForm.address.length <= 1) {
        this.$message({
          message: '配置地址至少保留一个!',
          type: 'warning'
        })
        return;
      }
      var index = this.dynamicValidateForm.address.indexOf(item)
      if (index !== -1) {
        this.dynamicValidateForm.address.splice(index, 1)
      }
    },
    addDomain() {
      this.dynamicValidateForm.address.push({
        value: '',
        key: Date.now()
      });
    }
  }
}
</script>

<style scoped>
.app-container {
  margin-top: 20px;
}

.el-input {
  width: 220px;
}

.el-input+.el-button {
  margin-left: 10px;
}
</style>
