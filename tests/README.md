# 测试模块

## 目录结构

- `unit/` - 快速单元测试，默认回归入口。
- `integration/` - 本地集成测试，不依赖真实外部模型服务。
- `e2e/` - 端到端和外部服务测试；OpenAI/Langfuse 类测试默认跳过，设置 `RUN_EXTERNAL_TESTS=true` 后运行。

## 运行测试

推荐使用仓库根目录的 Makefile:

```bash
make test
make test-integration
make test-e2e
make test-all
```

## 测试配置

外部服务测试使用 `config/test.env` 中的配置，并需要显式开启:

```bash
RUN_EXTERNAL_TESTS=true make test-e2e
```
