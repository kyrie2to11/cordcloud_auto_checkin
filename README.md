# CordCloud Auto Login + Daily Check-in

使用 CloakBrowser (Playwright 兼容) 自动登录 CordCloud 并完成每日签到，支持 POP3 邮箱验证码 (2FA)。

## 环境要求

- Python >= 3.12
- [uv](https://github.com/astral-sh/uv) 包管理器

## 快速开始

```bash
# 1. 安装依赖
uv sync

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填入你的账号信息

# 3. 运行
uv run python main.py
```

## 配置说明

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `CORDCLOUD_EMAIL` | CordCloud 登录邮箱 | - |
| `CORDCLOUD_PASSWORD` | CordCloud 登录密码 | - |
| `POP3_HOST` | POP3 邮箱服务器地址 | `pop.example.com` |
| `POP3_PORT` | POP3 端口 | `995` |
| `POP3_USE_SSL` | 是否使用 SSL 连接 | `true` |
| `POP3_USERNAME` | POP3 用户名（默认同 CordCloud 邮箱） | - |
| `POP3_PASSWORD` | POP3 邮箱密码 | - |
| `SMTP_HOST` | SMTP 服务器地址 | `smtp.qq.com` |
| `SMTP_PORT` | SMTP 端口 | `465` |
| `SMTP_USE_SSL` | SMTP 使用 SSL | `true` |
| `SMTP_USERNAME` | SMTP 用户名（默认同 CordCloud 邮箱） | - |
| `SMTP_PASSWORD` | SMTP 授权码（QQ邮箱需开启SMTP服务获取） | - |
| `USE_PERSISTENT_CONTEXT` | 使用持久化浏览器配置 | `true` |
| `PERSISTENT_PROFILE_DIR` | 持久化配置目录 | `./cloak_profile` |

## 工作流程

1. 启动 CloakBrowser，加载持久化 Profile（保留登录状态）
2. 访问 `/user` 检查是否已登录
3. 未登录则自动填写账号密码，如触发 2FA 则通过 POP3 收取验证码
4. 登录后查找"每日签到"按钮并点击
5. 显示签到结果后退出
6. 通过 SMTP 发送签到结果邮件通知（自己发给自己）

## 邮件通知

配置 `SMTP_PASSWORD` 后，每次运行结束会自动发送签到结果到 `CORDCLOUD_EMAIL`。QQ 邮箱需先开启 SMTP 服务获取授权码：

1. 登录 QQ 邮箱 → 设置 → 账户 → POP3/SMTP 服务 → 开启
2. 将生成的授权码填入 `.env` 的 `SMTP_PASSWORD`
3. 不配置则跳过邮件发送，不影响签到流程
