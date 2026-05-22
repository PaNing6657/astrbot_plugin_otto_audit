# OTTOhub 审核助手

对接 OTTOhub 审核 API，利用多模态 AI 自动审核视频、动态、头像、封面内容。

## 工作流程

```
用户 → AI → 插件 → OTTOhub API (获取内容) → 多模态 LLM (审核) → 合规则自动通过，违规则提示人工复核
```

## 功能

- 获取待审列表（视频/动态/头像/封面）
- AI 自动审核内容，合规自动通过
- 违规内容提示人工复核，不自动驳回
- 支持 OpenAI 兼容和豆包 Ark 两种 LLM 协议

## 配置

在插件配置页填写：

| 配置项 | 说明 |
|--------|------|
| OTTOhub API 地址 | 默认 `https://api.ottohub.cn` |
| UID / 邮箱 | OTTOhub 登录账号（需审核员权限） |
| 密码 | 登录密码 |
| 审核 LLM 接口地址 | 多模态模型 API 地址 |
| 审核 LLM API Key | API 密钥 |
| 审核 LLM 模型名 | 如 `gpt-4o`、`doubao-seed-2-0-lite-260428` |
| 接口类型 | OpenAI 兼容 或 豆包 Ark |
| 自动执行通过 | 开启后合规内容自动 approve |

## 命令

```
/审核 视频/动态/头像/封面 ID     审核指定内容
/审核列表 [类型]                  查看待审列表
/审核帮助                        查看帮助
```

## LLM 工具

AI 可直接调用的工具：

- `audit_content(audit_type, target_id)` — 审核指定内容
- `audit_list(audit_type, num)` — 查看待审列表
