const TimeModule = {
    getTime() {
        try {
            var myDate = new Date();
            var myYear = myDate.getFullYear(); //获取完整的年份(4位,1970-????)
            var myMonth = myDate.getMonth() + 1; //获取当前月份(0-11,0代表1月)
            var myToday = myDate.getDate(); //获取当前日(1-31)
            var myDay = myDate.getDay(); //获取当前星期X(0-6,0代表星期天)
            var myHour = myDate.getHours(); //获取当前小时数(0-23)
            var myMinute = myDate.getMinutes(); //获取当前分钟数(0-59)
            var mySecond = myDate.getSeconds(); //获取当前秒数(0-59)
            var week = ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六'];
            var nowTime;

            nowTime = myYear + '-' + this.fillZero(myMonth) + '-' + this.fillZero(myToday) + '&nbsp;&nbsp;' + this.fillZero(myHour) + ':' + this.fillZero(myMinute) + ':' + this.fillZero(mySecond) + '&nbsp;&nbsp;' + week[myDay] + '&nbsp;&nbsp;';
            document.getElementById('time').innerHTML = nowTime;
        } catch (error) {
            // console.error('Error getting time:', error);
        }
    },
    fillZero(str) {
        return str < 10 ? '0' + str : str;
    }
};

setInterval(() => {
    TimeModule.getTime()
}, 1000);

export default TimeModule;