# HTTP 接口设计

## POST /api/session/start — 开始会话

- 请求：`{ user_id?: string, message: string }`（user_id 可选，默认 `default_user`）
- 响应：`{ success: true, data: { ssid: string, reply: string } }`
- 服务端创建新 session，分配 ssid，处理第一条消息，一并返回

## POST /api/chat — 继续对话

- 请求：`{ ssid: string, message: string }`
- 响应：`{ success: true, data: { reply: string } }`
- 前端带 ssid 找到已有 session 继续对话
