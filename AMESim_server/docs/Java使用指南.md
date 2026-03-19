# Java客户端使用指南

## 1. 环境要求

- Java 8 或更高版本
- Maven 3.x（如果使用Maven）
- Gson库（用于JSON处理）

## 2. 项目配置

### 2.1 Maven项目

在`pom.xml`中添加依赖：

```xml
<dependencies>
    <dependency>
        <groupId>com.google.code.gson</groupId>
        <artifactId>gson</artifactId>
        <version>2.10.1</version>
    </dependency>
</dependencies>
```

### 2.2 Gradle项目

在`build.gradle`中添加依赖：

```gradle
dependencies {
    implementation 'com.google.code.gson:gson:2.10.1'
}
```

### 2.3 手动添加JAR

如果不想使用构建工具，可以手动下载Gson JAR文件：
- 下载地址：https://mvnrepository.com/artifact/com.google.code.gson/gson
- 将JAR文件添加到项目的classpath中

## 3. 使用示例

### 3.1 基本使用

```java
import com.amesim.client.AMESimClient;
import com.google.gson.JsonObject;
import com.google.gson.JsonArray;

public class Example {
    public static void main(String[] args) {
        // 创建客户端实例
        AMESimClient client = new AMESimClient("http://localhost:5000");
        
        try {
            // 1. 健康检查
            JsonObject health = client.healthCheck();
            System.out.println("服务器状态: " + health);
            
            // 2. 初始化API
            JsonObject initResult = client.initAPI();
            if (!initResult.get("success").getAsBoolean()) {
                System.err.println("初始化失败: " + initResult.get("error"));
                return;
            }
            
            // 3. 打开模型
            JsonObject openResult = client.openModel("Model.ame");
            if (!openResult.get("success").getAsBoolean()) {
                System.err.println("打开模型失败: " + openResult.get("error"));
                return;
            }
            
            // 4. 运行仿真
            JsonObject runResult = client.runSimulation();
            if (!runResult.get("success").getAsBoolean()) {
                System.err.println("仿真失败: " + runResult.get("error"));
                return;
            }
            
            // 5. 获取仿真结果
            JsonObject result = client.getSimulationResults(
                "time",    // 时间变量路径
                "speed",   // 速度变量路径
                "height"   // 高度变量路径
            );
            
            if (result.get("success").getAsBoolean()) {
                JsonArray data = result.getAsJsonArray("data");
                System.out.println("共获取 " + data.size() + " 个数据点");
                
                // 遍历数据
                for (int i = 0; i < data.size(); i++) {
                    JsonObject point = data.get(i).getAsJsonObject();
                    double time = point.get("时间(s)").getAsDouble();
                    double speed = point.get("速度(m/s)").getAsDouble();
                    double height = point.get("高度(m)").getAsDouble();
                    System.out.printf("时间: %.2f, 速度: %.2f, 高度: %.2f%n", 
                        time, speed, height);
                }
            }
            
            // 6. 关闭模型
            client.closeModel();
            
            // 7. 关闭API
            client.closeAPI();
            
        } catch (Exception e) {
            System.err.println("发生错误: " + e.getMessage());
            e.printStackTrace();
        }
    }
}
```

### 3.2 参数管理示例

```java
// 获取所有参数
JsonObject params = client.getParameters();
if (params.get("success").getAsBoolean()) {
    JsonObject data = params.getAsJsonObject("data");
    JsonObject runParams = data.getAsJsonObject("runParameter");
    System.out.println("停止时间: " + runParams.get("stop_time_s"));
    System.out.println("时间间隔: " + runParams.get("interval_s"));
}

// 设置运行参数
JsonObject setResult = client.setRunParameter("stop_time_s", "20.0");
if (setResult.get("success").getAsBoolean()) {
    System.out.println("参数设置成功");
}

// 设置全局参数
client.setGlobalParameter("global_param_name", "value");

// 设置部件参数
client.setCompParameter("component/path/param", "value");
```

### 3.3 获取单个变量值

```java
// 获取指定变量的值
JsonObject variable = client.getVariable("变量路径");
if (variable.get("success").getAsBoolean()) {
    JsonObject data = variable.getAsJsonObject("data");
    JsonObject info = data.getAsJsonObject("variableInfo");
    JsonObject values = data.getAsJsonObject("variableValue");
    
    System.out.println("变量路径: " + info.get("path").getAsString());
    System.out.println("变量标题: " + info.get("title").getAsString());
    System.out.println("变量单位: " + info.get("unit").getAsString());
}
```

## 4. 错误处理

所有方法都可能抛出`Exception`，建议使用try-catch处理：

```java
try {
    JsonObject result = client.runSimulation();
    if (!result.get("success").getAsBoolean()) {
        String error = result.get("error").getAsString();
        System.err.println("操作失败: " + error);
    }
} catch (Exception e) {
    System.err.println("网络错误或其他异常: " + e.getMessage());
    e.printStackTrace();
}
```

## 5. 在Web应用中使用

### 5.1 Spring Boot示例

```java
@RestController
@RequestMapping("/api/amesim")
public class AMESimController {
    private AMESimClient client;
    
    @PostConstruct
    public void init() {
        client = new AMESimClient("http://localhost:5000");
        try {
            client.initAPI();
        } catch (Exception e) {
            e.printStackTrace();
        }
    }
    
    @PostMapping("/simulate")
    public ResponseEntity<?> runSimulation(@RequestParam String modelPath) {
        try {
            client.openModel(modelPath);
            client.runSimulation();
            JsonObject result = client.getSimulationResults("time", "speed", "height");
            return ResponseEntity.ok(result);
        } catch (Exception e) {
            return ResponseEntity.status(500)
                .body(Map.of("error", e.getMessage()));
        }
    }
}
```

### 5.2 Servlet示例

```java
@WebServlet("/simulate")
public class SimulationServlet extends HttpServlet {
    private AMESimClient client;
    
    @Override
    public void init() throws ServletException {
        client = new AMESimClient("http://localhost:5000");
        try {
            client.initAPI();
        } catch (Exception e) {
            throw new ServletException(e);
        }
    }
    
    @Override
    protected void doPost(HttpServletRequest req, HttpServletResponse resp) 
            throws ServletException, IOException {
        try {
            String modelPath = req.getParameter("modelPath");
            client.openModel(modelPath);
            client.runSimulation();
            JsonObject result = client.getSimulationResults("time", "speed", "height");
            
            resp.setContentType("application/json;charset=UTF-8");
            resp.getWriter().write(result.toString());
        } catch (Exception e) {
            resp.setStatus(500);
            resp.getWriter().write("{\"error\":\"" + e.getMessage() + "\"}");
        }
    }
}
```

## 6. 注意事项

1. **连接管理**：客户端是无状态的，每次调用都是独立的HTTP请求
2. **异常处理**：所有方法都可能抛出异常，务必进行异常处理
3. **URL编码**：变量路径中的特殊字符会自动进行URL编码
4. **响应格式**：所有响应都是JSON格式，使用Gson解析
5. **线程安全**：客户端实例不是线程安全的，多线程环境请使用多个实例或加锁

## 7. 常见问题

### Q: 如何设置超时时间？

A: 可以在`HttpURLConnection`设置超时，需要修改`AMESimClient`类：

```java
conn.setConnectTimeout(5000);  // 连接超时5秒
conn.setReadTimeout(30000);     // 读取超时30秒
```

### Q: 如何处理HTTPS？

A: 如果服务器使用HTTPS，需要配置SSL证书。可以添加SSL上下文：

```java
// 信任所有证书（仅用于开发环境）
TrustManager[] trustAllCerts = new TrustManager[]{
    new X509TrustManager() {
        public X509Certificate[] getAcceptedIssuers() { return null; }
        public void checkClientTrusted(X509Certificate[] certs, String authType) { }
        public void checkServerTrusted(X509Certificate[] certs, String authType) { }
    }
};
SSLContext sc = SSLContext.getInstance("SSL");
sc.init(null, trustAllCerts, new java.security.SecureRandom());
HttpsURLConnection.setDefaultSSLSocketFactory(sc.getSocketFactory());
```

### Q: 如何添加请求头？

A: 可以在发送请求前添加自定义请求头：

```java
conn.setRequestProperty("Authorization", "Bearer token");
conn.setRequestProperty("X-Custom-Header", "value");
```

## 8. 完整示例项目

可以参考`src/java/AMESimClient.java`中的完整实现和示例代码。

