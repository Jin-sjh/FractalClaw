# Todo待办事项应用

一个使用 **React** + **FastAPI** + **SQLite** 构建的全栈待办事项管理应用。

## 📋 项目概述

这是一个功能完整的Todo应用，支持以下特性：
- ✅ 创建新的待办事项
- ✅ 查看所有待办事项列表
- ✅ 编辑待办事项内容
- ✅ 删除待办事项
- ✅ 标记待办事项为已完成/未完成
- ✅ 实时统计待办事项状态

## 🏗️ 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 前端 | React 18 | 用户界面框架 |
| 后端 | FastAPI | Python Web框架 |
| 数据库 | SQLite | 轻量级关系型数据库 |
| HTTP客户端 | Axios | 前端API请求 |

## 📁 项目结构

```
todo-app/
├── backend/                # 后端目录
│   ├── main.py            # FastAPI应用主文件
│   ├── requirements.txt   # Python依赖
│   └── todos.db          # SQLite数据库文件（运行后自动生成）
├── frontend/              # 前端目录
│   ├── public/
│   │   └── index.html    # HTML模板
│   ├── src/
│   │   ├── App.js        # 主应用组件
│   │   ├── App.css       # 样式文件
│   │   ├── index.js      # React入口文件
│   │   └── services/
│   │       └── api.js    # API服务层
│   └── package.json      # 前端依赖配置
├── README.md              # 项目说明文档
├── start.bat              # Windows启动脚本
└── start.sh               # Linux/Mac启动脚本
```

## 🚀 快速开始

### 前置要求

- **Python 3.8+**
- **Node.js 14+** 和 **npm**
- **Git**（可选）

### 方式一：使用启动脚本（推荐）

#### Windows系统：
```bash
start.bat
```

#### Linux/Mac系统：
```bash
chmod +x start.sh
./start.sh
```

### 方式二：手动启动

#### 1. 启动后端服务

```bash
# 进入后端目录
cd backend

# 创建虚拟环境（推荐）
python -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 启动FastAPI服务器
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

后端服务将在 http://localhost:8000 启动

#### 2. 启动前端服务

```bash
# 打开新的终端窗口，进入前端目录
cd frontend

# 安装依赖
npm install

# 启动React开发服务器
npm start
```

前端应用将在 http://localhost:3000 启动

## 📚 API文档

FastAPI自动生成交互式API文档：
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### API端点

| 方法 | 端点 | 描述 |
|------|------|------|
| GET | `/todos` | 获取所有待办事项 |
| POST | `/todos` | 创建新的待办事项 |
| GET | `/todos/{id}` | 获取指定ID的待办事项 |
| PUT | `/todos/{id}` | 更新指定ID的待办事项 |
| DELETE | `/todos/{id}` | 删除指定ID的待办事项 |

### 请求/响应示例

#### 创建待办事项

**请求:**
```http
POST /todos
Content-Type: application/json

{
    "title": "学习React",
    "description": "完成React基础教程",
    "completed": false
}
```

**响应:**
```json
{
    "id": 1,
    "title": "学习React",
    "description": "完成React基础教程",
    "completed": false,
    "created_at": "2024-01-01T12:00:00",
    "updated_at": "2024-01-01T12:00:00"
}
```

#### 更新待办事项

**请求:**
```http
PUT /todos/1
Content-Type: application/json

{
    "completed": true
}
```

**响应:**
```json
{
    "id": 1,
    "title": "学习React",
    "description": "完成React基础教程",
    "completed": true,
    "created_at": "2024-01-01T12:00:00",
    "updated_at": "2024-01-01T12:30:00"
}
```

## 🎨 前端功能

### 界面特性
- 📱 响应式设计，支持移动端
- 🎯 直观的用户界面
- ✨ 平滑的动画效果
- 🎨 现代化的UI设计

### 操作说明
1. **添加待办事项**: 在顶部表单输入标题和描述，点击"添加待办事项"
2. **完成待办事项**: 点击待办事项前的复选框标记为已完成
3. **编辑待办事项**: 点击"编辑"按钮修改待办事项内容
4. **删除待办事项**: 点击"删除"按钮删除待办事项

## 🔧 配置说明

### 后端配置

在 `backend/main.py` 中可以修改以下配置：

```python
# CORS配置
allow_origins=["http://localhost:3000"]  # 允许的前端域名

# 服务器配置
uvicorn.run(app, host="0.0.0.0", port=8000)  # 服务器地址和端口
```

### 前端配置

在 `frontend/package.json` 中配置代理：

```json
{
    "proxy": "http://localhost:8000"
}
```

## 🐛 常见问题

### 1. 端口被占用
如果端口8000或3000被占用，可以修改启动命令：
```bash
# 后端使用其他端口
uvicorn main:app --reload --port 8001

# 前端使用其他端口
PORT=3001 npm start
```

### 2. 数据库问题
如果数据库出现问题，可以删除 `backend/todos.db` 文件，重启后端服务会自动重新创建。

### 3. 依赖安装失败
确保Python和Node.js版本符合要求，并尝试使用国内镜像源：
```bash
# Python镜像
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# npm镜像
npm install --registry=https://registry.npmmirror.com
```

## 📝 开发说明

### 后端开发
- 使用FastAPI框架，支持异步请求处理
- SQLite数据库，无需额外安装数据库服务
- 自动生成API文档

### 前端开发
- 使用React函数组件和Hooks
- Axios处理HTTP请求
- CSS模块化样式

## 📄 许可证

本项目采用 MIT 许可证。

## 👥 贡献

欢迎提交Issue和Pull Request！

---

**享受使用Todo应用！** 🎉
