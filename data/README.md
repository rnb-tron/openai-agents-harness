# 数据目录

本目录用于存储应用运行时产生的数据文件。

## 目录结构

```
data/
├── logs/          # 应用日志文件
│   ├── default.log
│   └── default.log.2026-05-19
└── .gitkeep       # 保持目录结构
```

## 说明

- **logs/**: 应用运行时日志,会自动按日期轮转
- 此目录已被 `.gitignore` 忽略,不会被提交到 Git

## 配置

日志目录可通过环境变量 `MATRIX_APPLOGS_DIR` 自定义:

```bash
export MATRIX_APPLOGS_DIR=/path/to/logs
```

默认值: `data/logs/`
