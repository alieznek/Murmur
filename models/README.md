# 本地模型

本目录是应用的运行资源位置，模型文件不进入 Git。

- `ocr/`：三个 RapidOCR ONNX 模型。
- `argos/`：中英 Argos 模型、MiniSBD 和完整性清单。

先在仓库根目录安装环境和项目，再运行 `.venv\Scripts\python.exe scripts\prepare_models.py`。准备阶段可以联网，正常运行期间不下载。

删除模型目录后须重新准备。
