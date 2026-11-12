# 简幻欢(simpfun.cn) 自动签到脚本

使用 Python 调用简幻欢 API 完成每日自动签到 / 领取积分，适合配合 cron 定时运行。

## 文件说明

| 文件 | 说明 |
| --- | --- |
| `checkin.py` | 主脚本：登录、签到、查询积分 |
| `config.json.example` | 配置文件示例 |
| `requirements.txt` | 依赖清单（仅 requests） |

## 环境要求

- Python 3.8+
- 依赖安装：

```bash
pip install -r requirements.txt
```

## 配置

配置来源有两种，**环境变量优先**，缺失的字段会用 `config.json` 补全。

### 方式一：环境变量（推荐用于 Docker / CI）

```bash
export SIMPFUN_USERNAME="你的用户名"
export SIMPFUN_PASSWORD="你的密码"
```

### 方式二：config.json

```bash
cp config.json.example config.json
```

编辑 `config.json`：

```json
{
  "username": "your_username",
  "password": "your_password"
}
```

> `config.json` 含明文密码，请勿提交到代码仓库。默认读取脚本同目录下的 `config.json`，
> 也可以通过 `SIMPFUN_CONFIG=/path/to/config.json` 指定其他路径。

### 可选环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `SIMPFUN_USERNAME` | 无 | 用户名 |
| `SIMPFUN_PASSWORD` | 无 | 密码 |
| `SIMPFUN_CONFIG` | 脚本同目录 `config.json` | 配置文件路径 |
| `SIMPFUN_LOG_LEVEL` | `INFO` | 日志级别，可选 `DEBUG`/`INFO`/`WARNING`/`ERROR` |

## 运行

```bash
python3 checkin.py
```

输出示例：

```text
2026-11-12 08:00:00 [INFO] 已加载配置文件: /path/config.json
2026-11-12 08:00:01 [INFO] 登录成功，账号: ab****yz
2026-11-12 08:00:01 [INFO] 开始签到（第 1/3 次）
2026-11-12 08:00:02 [INFO] 签到成功: {"code": 200, "data": {...}}
2026-11-12 08:00:02 [INFO] 用户信息: 用户名=abcdef, 积分=1234
2026-11-12 08:00:02 [INFO] 任务完成
```

判定规则：
- 登录失败 → 退出码 `1`
- 签到失败自动重试 3 次（间隔 5 秒），全部失败 → 退出码 `1`
- 签到成功或今日已签到 → 退出码 `0`

## cron 定时任务

每天 08:05 执行一次，日志追加到 `checkin.log`：

```cron
5 8 * * * cd /path/to/simpfun-checkin && /usr/bin/python3 checkin.py >> checkin.log 2>&1
```

通过环境变量传账号（避免 cron 读不到交互式 shell 的环境变量，建议直接写在 crontab 里）：

```cron
5 8 * * * cd /path/to/simpfun-checkin && SIMPFUN_USERNAME=your_username SIMPFUN_PASSWORD=your_password /usr/bin/python3 checkin.py >> checkin.log 2>&1
```

注意：
1. 使用 cron 定时运行时，必须填写 Python 的绝对路径（用 `which python3` 查看）。
2. cron 的工作目录不是项目目录；因此务必先切换（`cd`）到脚本所在的目录。
3. 修改 crontab 时使用 `crontab -e`，保存后可用 `tail -f checkin.log` 观察执行结果。

## Docker / 其他调度平台

```bash
docker run --rm -e SIMPFUN_USERNAME=xxx -e SIMPFUN_PASSWORD=yyy python:3.11 \
  sh -c "pip install -r requirements.txt && python checkin.py"
```

多数调度平台（例如青龙面板）可直接把 `checkin.py` 作为任务脚本运行，也只需配置上述环境变量。

## 常见问题

- **登录失败**：确认账号密码正确；若开启了二次验证，可能需要改用其他登录方式。
- **签到失败**：检查网络是否连通，可运行 `curl https://api.simpfun.cn`；脚本已内置 3 次重试。
- **今日已签到**：如果接口返回"已领取"类提示，就视为成功，退出码仍为 0。
