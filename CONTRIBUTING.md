# 参与开发

本项目面向 Windows x64，使用 Python 和 PySide6。当前维护的是 `main` 上的开发版本；欢迎提交可复现的问题和范围明确的改动。

## 准备环境

从仓库根目录按 [README.md](README.md) 的快速开始安装锁定依赖。当前验证环境为 Python 3.14.7；其他版本尚未完成验证。日常开发使用 editable 安装，环境、模型和构建目录均不提交。

模型并非所有改动都需要。调整协议、配置、文档或图标，可以先运行：

```powershell
.venv\Scripts\python.exe scripts\check_ci.py
```

需要实际 OCR 或离线翻译时，再运行 `scripts/prepare_models.py` 准备模型。资源来源与许可见 [README.md](README.md) 与 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 找到负责该行为的模块

先阅读[架构说明](docs/architecture.md)。界面在 `src/screen_translator/ui/`，文本规则在 `core/`，平台与文件 I/O 在 `services/`。在线语种及各平台代码映射集中在 `services/languages.py`；新增语种前核对当前接口的官方文档，更新[平台说明](docs/providers.md)。

密钥留在 Windows 系统凭据存储；不要加入 `.env`、共享密钥或遥测。修改配置 schema、凭据引用及用户数据路径时，要说明兼容和迁移方式。

## 提交改动

1. 为问题描述复现步骤、预期和实际结果；较大的功能先讨论使用场景和边界。
2. 一次 PR 解决一个明确的问题。较大改动创建可追踪的 commit，不重写已共享的提交历史。
3. 复用受影响的现有测试；只在新行为或回归风险需要时增加测试，不写重复验证实现的测试。
4. 涉及桌面交互时，实际操作 Windows 窗口。附浅深主题、紧凑布局或 DPI 等与改动相关的检查结果，区分模拟检查与真实接口结果。
5. 更新相关文档。依赖变更同步更新锁文件与[许可说明](docs/licensing.md)。除发布任务外，不生成或提交安装包。

CI 只运行语法、文本规则、模拟平台协议、隔离配置和图标/资源路径检查；真实模型、Windows 凭据集成、快捷键及完整桌面验收留在相应改动或发布阶段。

## 许可与第三方材料

项目采用 [MIT](LICENSE)。提交贡献表示你有权按这一许可提供该贡献。引入第三方代码、图片或模型时，记录来源和版本，保留原版权及许可；不要上传来源不明的材料。第三方资产不会因为放入仓库而变为项目自有资产。

反馈与截图请遵循[隐私说明](docs/privacy.md)。安全问题按 [SECURITY.md](SECURITY.md) 处理，不在公开 Issue 粘贴密钥或私人内容。
