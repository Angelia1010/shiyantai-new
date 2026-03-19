package com.amesim.client;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import com.google.gson.Gson;
import com.google.gson.JsonObject;
import com.google.gson.JsonArray;

/**
 * AMESim服务Java客户端
 * 
 * 使用示例：
 * <pre>
 * AMESimClient client = new AMESimClient("http://localhost:5000");
 * client.initAPI();
 * client.openModel("Model.ame");
 * client.runSimulation();
 * JsonObject result = client.getSimulationResults("time", "speed", "height");
 * </pre>
 */
public class AMESimClient {
    private String baseUrl;
    private String apiBase;
    private Gson gson;
    
    /**
     * 构造函数
     * @param baseUrl 服务器基础URL，例如 "http://localhost:5000"
     */
    public AMESimClient(String baseUrl) {
        this.baseUrl = baseUrl;
        this.apiBase = baseUrl + "/api";
        this.gson = new Gson();
    }
    
    /**
     * 发送GET请求
     */
    private JsonObject sendGetRequest(String endpoint) throws Exception {
        URL url = new URL(apiBase + endpoint);
        HttpURLConnection conn = (HttpURLConnection) url.openConnection();
        conn.setRequestMethod("GET");
        conn.setRequestProperty("Accept", "application/json");
        
        int responseCode = conn.getResponseCode();
        if (responseCode >= 400) {
            BufferedReader errorReader = new BufferedReader(
                new InputStreamReader(conn.getErrorStream(), StandardCharsets.UTF_8)
            );
            StringBuilder errorResponse = new StringBuilder();
            String line;
            while ((line = errorReader.readLine()) != null) {
                errorResponse.append(line);
            }
            errorReader.close();
            throw new Exception("HTTP Error " + responseCode + ": " + errorResponse.toString());
        }
        
        BufferedReader in = new BufferedReader(
            new InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8)
        );
        String inputLine;
        StringBuilder response = new StringBuilder();
        while ((inputLine = in.readLine()) != null) {
            response.append(inputLine);
        }
        in.close();
        
        return gson.fromJson(response.toString(), JsonObject.class);
    }
    
    /**
     * 发送POST请求
     */
    private JsonObject sendPostRequest(String endpoint, JsonObject data) throws Exception {
        URL url = new URL(apiBase + endpoint);
        HttpURLConnection conn = (HttpURLConnection) url.openConnection();
        conn.setRequestMethod("POST");
        conn.setRequestProperty("Content-Type", "application/json");
        conn.setRequestProperty("Accept", "application/json");
        conn.setDoOutput(true);
        
        if (data != null) {
            try (OutputStream os = conn.getOutputStream()) {
                byte[] input = data.toString().getBytes(StandardCharsets.UTF_8);
                os.write(input, 0, input.length);
            }
        }
        
        int responseCode = conn.getResponseCode();
        if (responseCode >= 400) {
            BufferedReader errorReader = new BufferedReader(
                new InputStreamReader(conn.getErrorStream(), StandardCharsets.UTF_8)
            );
            StringBuilder errorResponse = new StringBuilder();
            String line;
            while ((line = errorReader.readLine()) != null) {
                errorResponse.append(line);
            }
            errorReader.close();
            throw new Exception("HTTP Error " + responseCode + ": " + errorResponse.toString());
        }
        
        BufferedReader in = new BufferedReader(
            new InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8)
        );
        String inputLine;
        StringBuilder response = new StringBuilder();
        while ((inputLine = in.readLine()) != null) {
            response.append(inputLine);
        }
        in.close();
        
        return gson.fromJson(response.toString(), JsonObject.class);
    }
    
    /**
     * 发送PUT请求
     */
    private JsonObject sendPutRequest(String endpoint, JsonObject data) throws Exception {
        URL url = new URL(apiBase + endpoint);
        HttpURLConnection conn = (HttpURLConnection) url.openConnection();
        conn.setRequestMethod("PUT");
        conn.setRequestProperty("Content-Type", "application/json");
        conn.setRequestProperty("Accept", "application/json");
        conn.setDoOutput(true);
        
        if (data != null) {
            try (OutputStream os = conn.getOutputStream()) {
                byte[] input = data.toString().getBytes(StandardCharsets.UTF_8);
                os.write(input, 0, input.length);
            }
        }
        
        int responseCode = conn.getResponseCode();
        if (responseCode >= 400) {
            BufferedReader errorReader = new BufferedReader(
                new InputStreamReader(conn.getErrorStream(), StandardCharsets.UTF_8)
            );
            StringBuilder errorResponse = new StringBuilder();
            String line;
            while ((line = errorReader.readLine()) != null) {
                errorResponse.append(line);
            }
            errorReader.close();
            throw new Exception("HTTP Error " + responseCode + ": " + errorResponse.toString());
        }
        
        BufferedReader in = new BufferedReader(
            new InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8)
        );
        String inputLine;
        StringBuilder response = new StringBuilder();
        while ((inputLine = in.readLine()) != null) {
            response.append(inputLine);
        }
        in.close();
        
        return gson.fromJson(response.toString(), JsonObject.class);
    }
    
    /**
     * 健康检查
     * @return 响应JSON对象
     */
    public JsonObject healthCheck() throws Exception {
        return sendGetRequest("/health");
    }
    
    /**
     * 初始化API
     * @return 响应JSON对象
     */
    public JsonObject initAPI() throws Exception {
        return sendPostRequest("/init", null);
    }
    
    /**
     * 打开模型文件
     * @param filePath 模型文件路径
     * @return 响应JSON对象
     */
    public JsonObject openModel(String filePath) throws Exception {
        JsonObject data = new JsonObject();
        data.addProperty("filePath", filePath);
        return sendPostRequest("/model/open", data);
    }
    
    /**
     * 关闭模型
     * @return 响应JSON对象
     */
    public JsonObject closeModel() throws Exception {
        return sendPostRequest("/model/close", null);
    }
    
    /**
     * 获取所有参数
     * @return 响应JSON对象
     */
    public JsonObject getParameters() throws Exception {
        return sendGetRequest("/model/parameters");
    }
    
    /**
     * 设置运行参数
     * @param parameter 参数名
     * @param value 参数值
     * @return 响应JSON对象
     */
    public JsonObject setRunParameter(String parameter, String value) throws Exception {
        JsonObject data = new JsonObject();
        data.addProperty("parameter", parameter);
        data.addProperty("value", value);
        return sendPutRequest("/model/parameters/run", data);
    }
    
    /**
     * 设置全局参数
     * @param parameter 参数名
     * @param value 参数值
     * @return 响应JSON对象
     */
    public JsonObject setGlobalParameter(String parameter, String value) throws Exception {
        JsonObject data = new JsonObject();
        data.addProperty("parameter", parameter);
        data.addProperty("value", value);
        return sendPutRequest("/model/parameters/global", data);
    }
    
    /**
     * 设置部件参数
     * @param parameter 参数名
     * @param value 参数值
     * @return 响应JSON对象
     */
    public JsonObject setCompParameter(String parameter, String value) throws Exception {
        JsonObject data = new JsonObject();
        data.addProperty("parameter", parameter);
        data.addProperty("value", value);
        return sendPutRequest("/model/parameters/component", data);
    }
    
    /**
     * 运行仿真
     * @return 响应JSON对象
     */
    public JsonObject runSimulation() throws Exception {
        return sendPostRequest("/simulation/run", null);
    }
    
    /**
     * 获取变量值
     * @param variablePath 变量路径
     * @return 响应JSON对象
     */
    public JsonObject getVariable(String variablePath) throws Exception {
        String encodedPath = java.net.URLEncoder.encode(variablePath, StandardCharsets.UTF_8.toString());
        return sendGetRequest("/simulation/variable?path=" + encodedPath);
    }
    
    /**
     * 获取仿真结果（时间、速度、高度）
     * @param timePath 时间变量路径
     * @param speedPath 速度变量路径
     * @param heightPath 高度变量路径
     * @return 响应JSON对象，包含data字段，data是数组格式
     */
    public JsonObject getSimulationResults(String timePath, String speedPath, String heightPath) throws Exception {
        String encodedTimePath = java.net.URLEncoder.encode(timePath, StandardCharsets.UTF_8.toString());
        String encodedSpeedPath = java.net.URLEncoder.encode(speedPath, StandardCharsets.UTF_8.toString());
        String encodedHeightPath = java.net.URLEncoder.encode(heightPath, StandardCharsets.UTF_8.toString());
        
        String endpoint = String.format("/simulation/results?timePath=%s&speedPath=%s&heightPath=%s",
            encodedTimePath, encodedSpeedPath, encodedHeightPath);
        return sendGetRequest(endpoint);
    }
    
    /**
     * 关闭API
     * @return 响应JSON对象
     */
    public JsonObject closeAPI() throws Exception {
        return sendPostRequest("/close", null);
    }
    
    /**
     * 使用示例
     */
    public static void main(String[] args) {
        AMESimClient client = new AMESimClient("http://localhost:5000");
        
        try {
            // 健康检查
            System.out.println("健康检查: " + client.healthCheck());
            
            // 初始化API
            System.out.println("初始化API: " + client.initAPI());
            
            // 打开模型
            System.out.println("打开模型: " + client.openModel("Model.ame"));
            
            // 运行仿真
            System.out.println("运行仿真: " + client.runSimulation());
            
            // 获取仿真结果（需要替换为实际的变量路径）
            String timePath = "time";      // 替换为实际的时间变量路径
            String speedPath = "speed";    // 替换为实际的速度变量路径
            String heightPath = "height";  // 替换为实际的高度变量路径
            
            JsonObject result = client.getSimulationResults(timePath, speedPath, heightPath);
            System.out.println("仿真结果: " + result);
            
            // 如果成功，打印数据
            if (result.has("success") && result.get("success").getAsBoolean()) {
                JsonArray dataArray = result.getAsJsonArray("data");
                if (dataArray != null && dataArray.size() > 0) {
                    System.out.println("共获取 " + dataArray.size() + " 个数据点");
                    System.out.println("第一个数据点: " + dataArray.get(0));
                }
            }
            
            // 关闭模型
            System.out.println("关闭模型: " + client.closeModel());
            
            // 关闭API
            System.out.println("关闭API: " + client.closeAPI());
            
        } catch (Exception e) {
            System.err.println("错误: " + e.getMessage());
            e.printStackTrace();
        }
    }
}

