# CPS 3740 校园自习室预约系统

这是一个使用 **Python + Flask + SQLAlchemy + MySQL** 的课程项目框架，界面支持英文和中文。为便于第一次打开，默认使用本地 SQLite 演示库；切换到 MySQL 后，业务代码不需要改动。

## 1. 在 PyCharm 中直接运行

1. 在 PyCharm 中打开克隆下来的 `campus_study_room` 目录。
2. 选择 Python 3.10 或更高版本的解释器，并在 PyCharm 终端安装依赖：

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. 右键项目根目录的 `run.py`，选择 **Run 'run'**。
4. 在浏览器打开 `http://127.0.0.1:5000/`。右上角可以切换中文。

首次运行且没有设置 `DATABASE_URL` 时，程序会在项目的 `instance/study_rooms.sqlite3` 创建 SQLite 演示库并插入示例数据。重新运行不会覆盖已有数据。SQLite 只是方便本机演示，课程最终数据库可按下一节切换至 MySQL。

演示账号仅供本地测试：

| 角色 | 邮箱 | 密码 |
| --- | --- | --- |
| 学生 | `student@example.edu` | `Student123!` |
| 管理员 | `staff@example.edu` | `Staff123!` |

用学生账号测试查找、预约、历史和取消；用管理员账号测试楼宇、房间、开放时间及统计。注册页面只创建学生账号。

## 2. 切换到 MySQL 8

本机须有可用的 MySQL 账号及其创建表的权限。不要把数据库密码发给别人或写进源代码。

### 第一步：创建空数据库

在 MySQL Workbench 登录你的 MySQL 服务，运行：

```sql
CREATE DATABASE campus_study_rooms
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

如果数据库已经存在，先确认它是此项目准备使用的数据库。程序不会删除或重建现有数据库。

### 第二步：设置数据库连接

在 PyCharm 的 **Run → Edit Configurations → Environment variables** 中，为 `run.py` 设置：

```text
DATABASE_URL=mysql+pymysql://root:YOUR_PASSWORD@127.0.0.1:3306/campus_study_rooms?charset=utf8mb4
SECRET_KEY=换成一段随机字符串
```

把 `root` 和 `YOUR_PASSWORD` 改成你自己的数据库账号和密码。请根据自己的 MySQL 服务配置账号、密码和端口。若密码含 `@`、`:`、`/` 等特殊字符，需要对密码进行 URL 编码后再放入连接字符串。

可以在本机终端生成随机密钥：

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

`.env.example` 只是配置示例，不会被程序自动读取。PyCharm 运行配置和终端的环境变量彼此独立。

### 第三步：初始化表和演示数据

在项目目录打开 PyCharm 的 PowerShell 终端，**在该终端里同样设置** `DATABASE_URL` 和 `SECRET_KEY`，然后运行：

```powershell
$env:DATABASE_URL = 'mysql+pymysql://root:YOUR_PASSWORD@127.0.0.1:3306/campus_study_rooms?charset=utf8mb4'
$env:SECRET_KEY = '换成与运行配置一致的随机字符串'
python -m flask --app run:app init-db
python -m flask --app run:app seed-demo
```

把上面的占位值替换成你自己的值。`init-db` 创建不存在的表，不会迁移或重置已有表；`seed-demo` 只在五张表都为空时添加测试数据，数据库非空时不会覆盖数据。之后运行 `run.py`，页面顶部应显示 `Database: MySQL`。

如果不需要演示账号，可跳过 `seed-demo`，并使用交互命令创建管理员：

```powershell
python -m flask --app run:app create-staff
```

命令会提示输入姓名、邮箱和密码，密码输入不回显。若使用空数据库，需由管理员先添加楼宇、房间和开放时间。

`database/schema.sql` 是从 Python 模型生成的 MySQL 建表语句，供课程作业查看；对空库可选择运行它 **或** 使用 `init-db`，不必两者都运行。实际 MySQL 连接尚需使用你自己的账号验证。

## 3. 功能与数据库结构

- 学生注册和密码登录；密码以哈希形式存储。
- 按楼宇、容量、日期和开始/结束时间搜索房间。
- 创建预约、查看自己的预约历史和取消自己的预约。
- 管理员添加楼宇、添加/编辑房间、设置每个房间每周开放时间、查看与取消预约、查看各房间预约次数及小时数。
- 预约冲突使用半开区间：已有预约的开始时间 `<` 新预约结束时间，且已有预约的结束时间 `>` 新预约开始时间时才冲突；相邻时段允许预约。
- MySQL 使用 InnoDB 事务和房间行锁，锁定房间后再次检查冲突并写入；管理员修改房间状态或开放时间、取消预约也遵循同一房间锁定协议。SQLite 本地演示使用 `BEGIN IMMEDIATE` 串行化写入。
- 五张表：`users`、`buildings`、`rooms`、`room_hours`、`reservations`。四种主要关系分别是楼宇到房间、房间到开放时间、用户到预约、房间到预约。

时间按运行服务器的本地时区解释；原型不包含邮件通知、跨时区处理或外网部署。Flask 自带服务器只用于本地课程开发；演示密码不用于真实环境。正式部署需要使用 HTTPS、独立密钥、正式 WSGI 服务和额外安全配置。

## 4. 项目目录

```text
campus_study_room/
├── run.py                  # PyCharm 运行入口
├── requirements.txt        # Python 依赖
├── .env.example            # 环境变量示例（不自动加载）
├── database/schema.sql     # MySQL 建表语句参考
├── studyroom/
│   ├── __init__.py         # 应用、配置、命令与 CSRF
│   ├── models.py           # 五张数据表
│   ├── db.py               # 数据库连接
│   ├── services.py         # 搜索与预约事务
│   ├── auth.py             # 注册、登录、退出
│   ├── views.py            # 房间与学生预约页面
│   ├── admin.py            # 管理员功能
│   ├── templates/          # HTML 页面
│   └── static/style.css    # 页面样式
└── tests/test_app.py       # 功能和并发测试
```

## 5. 运行测试

在项目根目录运行：

```powershell
python -m unittest discover -s tests -v
```

测试使用临时 SQLite 数据库，不修改你的正式数据库。当前验证覆盖注册、密码哈希、登录权限、CSRF、筛选、预约重叠、取消权限、管理员操作和双线程同时预约。
