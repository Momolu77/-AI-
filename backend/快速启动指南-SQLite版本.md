# 快速启动指南 - SQLite 版本

## ✅ 零安装！无需数据库服务器

本系统已升级为 **SQLite + 内存缓存** 版本，无需安装 PostgreSQL 或 Redis。

---

## 🚀 快速启动（3步完成）

### 步骤1: 安装依赖

```bash
cd backend

# 创建虚拟环境（首次）
python -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# Mac/Linux:
# source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 步骤2: 配置环境变量

```bash
# 复制配置模板
copy .env.example .env

# 编辑 .env 文件，填写你的 Anthropic API Key
# ANTHROPIC_API_KEY=sk-ant-xxxxx
```

### 步骤3: 启动服务

```bash
# 启动后端（自动创建数据库）
uvicorn app.main:app --reload

# 应该看到：
# ✅ 数据库初始化完成
# INFO: Uvicorn running on http://127.0.0.1:8000
```

### 步骤4: 启动前端

```bash
# 打开新终端
cd frontend

# 安装依赖（首次）
npm install

# 启动开发服务器
npm run dev

# 应该看到：
# ➜ Local: http://localhost:5173/
```

---

## 📂 数据库文件位置

启动后，SQLite 数据库文件会自动创建在：

```
backend/
├── metacog.db          ← SQLite 数据库文件
├── metacog.db-shm      ← SQLite 临时文件
└── metacog.db-wal      ← SQLite 预写日志
```

**备份数据**: 复制 `metacog.db` 文件即可

**删除数据**: 删除 `metacog.db` 文件，重启服务会自动创建新的

---

## 🔧 常见问题

### Q1: 找不到 aiosqlite 模块？

```bash
# 确保虚拟环境已激活
pip install aiosqlite
```

### Q2: 数据库连接失败？

检查 `.env` 文件中的 `DATABASE_URL` 配置：
```
DATABASE_URL=sqlite+aiosqlite:///./metacog.db
```

### Q3: 如何查看数据库内容？

推荐使用 **DB Browser for SQLite**:
- 下载: https://sqlitebrowser.org/
- 打开 `backend/metacog.db` 文件即可

### Q4: 状态缓存会丢失吗？

是的，使用内存缓存时，服务重启后缓存会丢失。但不影响核心功能：
- ✅ 所有数据都保存在数据库中
- ✅ 状态会从数据库重新计算
- ✅ 只是计算速度稍慢（毫秒级差异）

---

## 🎓 适用场景

| 场景 | 适用性 |
|------|--------|
| **毕业答辩演示** | ✅ 完美 |
| **专利申请演示** | ✅ 完美 |
| **小班测试（3-10人）** | ✅ 完全够用 |
| **班级部署（30-50人）** | ⚠️ 可以，但需要注意并发 |
| **生产环境（100+人）** | ❌ 建议升级到 PostgreSQL |

---

## 📊 性能对比

| 数据库 | 安装 | 配置 | 并发写入 | 适用规模 |
|--------|------|------|---------|---------|
| **SQLite** | 零安装 | 零配置 | 单写 | <50人 |
| PostgreSQL | 需安装 | 需配置 | 多写 | 无限制 |

---

## 🔄 如何迁移到 PostgreSQL？

如果后续需要生产部署，只需修改 `.env` 文件：

```bash
# 1. 安装 PostgreSQL 依赖
pip install asyncpg psycopg2-binary

# 2. 修改 .env
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/metacog_db

# 3. 重启服务
# 数据表会自动创建，但旧数据需要手动迁移
```

---

## 💡 技术说明

### 已移除的依赖

- ❌ `redis` - 使用内存字典替代
- ❌ `asyncpg` - SQLite 不需要
- ❌ `psycopg2-binary` - SQLite 不需要

### 已添加的依赖

- ✅ `aiosqlite` - SQLite 异步驱动

### 修改的文件

1. `app/database.py` - 添加内存缓存函数
2. `app/redis_client.py` - 改为内存缓存客户端
3. `requirements.txt` - 移除 Redis 和 PostgreSQL 依赖
4. `.env.example` - 更新配置说明
5. `app/config.py` - 更新默认配置

---

## 📝 版本信息

- **数据库**: SQLite 3.x（Python 内置）
- **缓存**: Python 字典（内存）
- **优势**: 零安装、零配置、易备份
- **劣势**: 并发写入受限（单用户或小班无影响）

---

## 🎉 开始使用

现在可以直接启动系统，无需任何数据库安装！

```bash
# 后端
cd backend
uvicorn app.main:app --reload

# 前端
cd frontend
npm run dev
```

访问 http://localhost:5173 开始使用！
