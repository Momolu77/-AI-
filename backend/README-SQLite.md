# SQLite 版本说明

## 🎯 版本特点

本系统已升级为 **SQLite + 内存缓存** 版本：

- ✅ **零安装** - 无需安装 PostgreSQL 或 Redis
- ✅ **零配置** - 只需填写 API Key 即可运行
- ✅ **单文件数据库** - 整个数据库就是一个 `.db` 文件
- ✅ **易于备份** - 复制文件即可
- ✅ **跨平台** - Windows/Mac/Linux 通用
- ✅ **适合答辩演示** - 简单可靠

---

## 📂 文件结构

```
backend/
├── metacog.db              ← SQLite 数据库文件（运行后自动创建）
├── metacog.db-shm          ← SQLite 共享内存文件
├── metacog.db-wal          ← SQLite 预写日志
├── app/
│   ├── database.py         ← 数据库配置 + 内存缓存
│   ├── redis_client.py     ← 内存缓存客户端（模拟 Redis）
│   └── ...
├── requirements.txt        ← 依赖列表（已移除 redis/asyncpg）
└── .env                    ← 环境变量（只需填 API Key）
```

---

## 🚀 快速开始

### 1. 安装依赖

```bash
cd backend

# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

# 安装依赖（自动安装 aiosqlite）
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
# 复制配置模板
copy .env.example .env

# 编辑 .env，只需填写 API Key
# ANTHROPIC_API_KEY=sk-ant-你的密钥
```

### 3. 启动服务

```bash
# 启动后端（自动创建数据库表）
uvicorn app.main:app --reload

# 应看到：
# ✅ 数据库初始化完成
# INFO: Uvicorn running on http://127.0.0.1:8000
```

---

## 💾 数据管理

### 备份数据库

```bash
# 方法1: 直接复制文件
cp metacog.db metacog_backup.db

# 方法2: 带时间戳备份
cp metacog.db metacog_backup_$(date +%Y%m%d_%H%M%S).db
```

### 清空数据库

```bash
# 删除数据库文件
rm metacog.db metacog.db-shm metacog.db-wal

# 重启服务，会自动创建新的空数据库
uvicorn app.main:app --reload
```

### 查看数据库内容

**方法1: DB Browser for SQLite（推荐）**

1. 下载安装: https://sqlitebrowser.org/
2. 打开 `metacog.db` 文件
3. 图形化查看所有表和数据

**方法2: 命令行**

```bash
# 进入 SQLite
sqlite3 metacog.db

# 查看所有表
.tables

# 查看会话数据
SELECT * FROM sessions ORDER BY created_at DESC LIMIT 5;

# 查看日志数据
SELECT * FROM interaction_logs ORDER BY timestamp DESC LIMIT 10;

# 退出
.quit
```

### 导出数据

```bash
# 导出为 SQL 脚本
sqlite3 metacog.db .dump > backup.sql

# 导出特定表为 CSV
sqlite3 -header -csv metacog.db "SELECT * FROM sessions;" > sessions.csv
sqlite3 -header -csv metacog.db "SELECT * FROM interaction_logs;" > logs.csv
sqlite3 -header -csv metacog.db "SELECT * FROM metacog_states;" > states.csv
```

### 导入数据

```bash
# 从 SQL 脚本导入
sqlite3 metacog.db < backup.sql

# 从 CSV 导入（需要先创建表）
sqlite3 metacog.db
.mode csv
.import sessions.csv sessions
.quit
```

---

## 🔧 技术细节

### 数据库配置

**database.py**:
```python
# SQLite 连接字符串
DATABASE_URL = "sqlite+aiosqlite:///./metacog.db"

# 创建引擎（SQLite 特殊配置）
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},  # SQLite 需要此配置
)
```

### 内存缓存

**database.py**:
```python
# 全局状态缓存（字典）
_state_cache: Dict[str, dict] = {}

async def get_state_cache(session_id: str) -> Optional[dict]:
    return _state_cache.get(session_id)

async def set_state_cache(session_id: str, state: dict, ttl: int = 3600):
    _state_cache[session_id] = state
```

**redis_client.py**:
```python
# 内存缓存客户端（兼容 Redis 接口）
class MemoryCacheClient:
    async def get(self, key: str) -> Optional[str]:
        state = await get_state_cache(key)
        return json.dumps(state) if state else None
    
    async def set(self, key: str, value: str, ex: int = 3600):
        state = json.loads(value)
        await set_state_cache(key, state, ttl=ex)
```

---

## ⚠️ 注意事项

### 并发限制

**SQLite 的限制**:
- ✅ 支持多个读操作（并发读）
- ⚠️ 同时只能有一个写操作（单写）

**影响**:
- ✅ 多个用户同时查看数据 - 没问题
- ⚠️ 多个用户同时写入数据 - 会排队等待

**适用场景**:
- ✅ 单用户使用 - 完美
- ✅ 小班测试（3-10人）- 可以
- ⚠️ 班级部署（30-50人）- 勉强
- ❌ 生产环境（100+人）- 不推荐

### 缓存限制

**内存缓存的限制**:
- ⚠️ 服务重启后缓存丢失
- ⚠️ 无法跨服务器共享

**影响**:
- ✅ 核心功能不受影响（状态会从数据库重新计算）
- ⚠️ 计算速度稍慢（毫秒级差异）
- ⚠️ 无法实现分布式部署

### 数据库大小

**SQLite 理论上限**:
- 最大数据库大小: 281 TB
- 最大表数量: 无限制
- 最大行数: 2^64

**实际建议**:
- ✅ < 1 GB - 性能良好
- ⚠️ 1-10 GB - 可用，但查询变慢
- ❌ > 10 GB - 建议迁移到 PostgreSQL

---

## 🔄 如何迁移到 PostgreSQL

如果后续需要生产部署，迁移步骤：

### 1. 安装 PostgreSQL 依赖

```bash
pip install asyncpg psycopg2-binary
```

### 2. 修改 .env

```env
# 从 SQLite
DATABASE_URL=sqlite+aiosqlite:///./metacog.db

# 改为 PostgreSQL
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/metacog_db
```

### 3. 导出 SQLite 数据

```bash
# 导出为 SQL 脚本
sqlite3 metacog.db .dump > data.sql
```

### 4. 导入到 PostgreSQL

```bash
# 创建数据库
psql -U postgres
CREATE DATABASE metacog_db;
\q

# 导入数据（可能需要修改 SQL 语法）
psql -U postgres -d metacog_db < data.sql
```

### 5. 重启服务

```bash
uvicorn app.main:app --reload
```

---

## 📊 性能对比

| 指标 | SQLite | PostgreSQL |
|------|--------|-----------|
| **启动时间** | 1秒 | 5-10秒 |
| **查询速度（小数据）** | 很快 | 快 |
| **查询速度（大数据）** | 慢 | 快 |
| **并发读** | ✅ 支持 | ✅ 支持 |
| **并发写** | ❌ 单写 | ✅ 多写 |
| **内存占用** | 很低 | 中等 |
| **磁盘占用** | 很低 | 中等 |

---

## 🎓 适用场景评估

| 场景 | SQLite | PostgreSQL |
|------|--------|-----------|
| **毕业答辩** | ⭐⭐⭐⭐⭐ 完美 | ⭐⭐⭐ 过度复杂 |
| **专利演示** | ⭐⭐⭐⭐⭐ 完美 | ⭐⭐⭐ 可以 |
| **个人学习** | ⭐⭐⭐⭐⭐ 完美 | ⭐⭐⭐ 不必要 |
| **小班测试（3-10人）** | ⭐⭐⭐⭐⭐ 完美 | ⭐⭐⭐⭐ 可以 |
| **班级部署（30-50人）** | ⭐⭐⭐ 勉强 | ⭐⭐⭐⭐⭐ 推荐 |
| **生产环境（100+人）** | ⭐ 不推荐 | ⭐⭐⭐⭐⭐ 必须 |

---

## 💡 最佳实践

### 开发阶段

✅ **使用 SQLite**:
- 快速启动
- 易于调试
- 无需配置

### 答辩/演示阶段

✅ **使用 SQLite**:
- 零安装
- 易于携带
- 演示稳定

### 小规模测试

✅ **使用 SQLite**:
- 3-10 人：完美
- 10-30 人：可以
- 30-50 人：勉强

### 生产部署

⚠️ **评估后选择**:
- < 50 人：SQLite 可以
- > 50 人：必须 PostgreSQL
- 需要分布式：必须 PostgreSQL

---

## 🐛 常见问题

### Q1: 数据库文件被锁定？

**症状**: `database is locked`

**原因**: 有其他进程正在访问数据库

**解决**:
```bash
# 1. 停止所有后端服务
# 2. 删除锁文件
rm metacog.db-shm metacog.db-wal
# 3. 重启服务
```

### Q2: 内存缓存丢失？

**症状**: 服务重启后状态需要重新计算

**原因**: 内存缓存在重启后清空

**解决**: 这是正常行为，不影响功能。如果需要持久化缓存，升级到 Redis。

### Q3: 如何查看当前数据库大小？

```bash
# Windows
dir metacog.db

# Mac/Linux
ls -lh metacog.db

# 或在 SQLite 内
sqlite3 metacog.db
.dbinfo
.quit
```

### Q4: 如何优化数据库性能？

```bash
# 进入 SQLite
sqlite3 metacog.db

# 运行优化命令
VACUUM;
ANALYZE;

# 退出
.quit
```

---

## 📝 版本历史

### v2.0 (当前版本)
- ✅ 使用 SQLite 替代 PostgreSQL
- ✅ 使用内存缓存替代 Redis
- ✅ 零安装、零配置
- ✅ 更新所有文档

### v1.0 (旧版本)
- ❌ 需要安装 PostgreSQL
- ❌ 需要安装 Redis
- ❌ 配置复杂

---

## 📞 技术支持

如有问题，请查阅：

1. [快速启动.md](../快速启动.md) - 启动指南
2. [快速启动指南-SQLite版本.md](./快速启动指南-SQLite版本.md) - 详细说明
3. [演示指南.md](../演示指南.md) - 测试场景

---

**最后更新**: 2026-09-14  
**适用版本**: SQLite + 内存缓存版  
**推荐场景**: 毕设答辩、专利演示、小班测试
