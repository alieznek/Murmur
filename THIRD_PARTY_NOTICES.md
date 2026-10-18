# 第三方声明

Murmur 自有代码、文档与图标采用 MIT。以下第三方组件、模型、版权和许可保持独立；本文件不重新授权它们。

许可与分发说明见 `docs/licensing.md`，在完整程序包中对应 `guides/licensing.md`。

| 组件 | 许可与来源 |
| --- | --- |
| MiniSBD 0.9.5 | GNU AGPLv3；LibreTranslate/MiniSBD。部分代码修改自 Stanford Stanza，保留包内 Apache-2.0 声明 |
| PySide6 / Shiboken6 6.11.2 | 上游声明 LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only；Qt 和其他第三方部分各自保留声明 |
| RapidOCR 3.9.2、SentencePiece 0.2.2、FlatBuffers 25.12.19 | Apache-2.0；保留版本对应的声明或 wheel 版权头 |
| CTranslate2 4.8.2、ONNX Runtime 1.30.0 | MIT；ONNX Runtime 另含 ThirdPartyNotices |
| NumPy、Pillow、OpenCV 与其余运行依赖 | 多种许可，随各自 wheel 保留 LICENSE / COPYING / NOTICE 声明 |
| Click、Rich、markdown-it-py、mdurl、Pygments、psutil、setuptools | 随冻结 EXE 一并分发的额外模块，保留各包及其随附组件的原始声明 |
| Shapely 随附的 GEOS 3.13.1 | LGPLv2.1；以动态库形式分发 |
| CTranslate2 随附的 Intel OpenMP 2025.3.0 | 按 Intel EULA 及其第三方声明使用；不能沿用 CTranslate2 主包的 MIT 标签 |
| Mesa 11.2.2 / LLVM 3.6.2、oneDNN 3.1.1 | 随 Qt/Python 原生运行环境提供；保留上游许可与署名 |
| certifi、tqdm | 涉及 MPL-2.0，保留许可及已安装源文件；certifi 证书 PEM 保持可读形式 |

## 关键许可正文

- [LGPL-3.0-only](LICENSES/LGPL-3.0-only.txt)：Qt / PySide6
- [LGPL v2.1（GEOS）](LICENSES/LICENSE_GEOS.txt)：GEOS / Shapely
- [AGPL-3.0](LICENSES/AGPL-3.0.txt)：MiniSBD
- [Apache-2.0](LICENSES/Apache-2.0.txt)：RapidOCR、FlatBuffers 等

## 模型与署名

当前两份 Argos 1.9 中英模型包中的 README 明示其原始 OPUS 模型采用 CC-BY 4.0。保留以下署名与原说明：

Jörg Tiedemann and Santhosh Thottingal. “OPUS-MT — Building open translation services for the World.” Proceedings of the 22nd Annual Conference of the European Association for Machine Translation (EAMT), 2020, Lisbon, Portugal.

模型由 Argos 发布为 `.argosmodel`，应用使用其中的 CTranslate2 模型和 SentencePiece 文件；模型权重由上游准备，Murmur 未进一步修改。包内原始 README 随模型包保留。不能用 Argos 软件/索引的 MIT/CC0 许可替代这些模型包自己的许可。

MiniSBD 的英语及简体中文 ONNX 分句模型来自其 v0.0.1 模型 release。MiniSBD 声明 AGPLv3，并说明模型由 Stanford Stanza tokenizer 转换为 ONNX、量化而来。Stanford NLP 的英语、简体中文模型卡声明 Apache-2.0。保留 MiniSBD README、AGPL 正文、Stanford Stanza 版权声明与来源；Murmur 复制这些 ONNX 文件，不修改其权重。包内未使用的 Stanza 资源如随 Argos 包保留，也保留同一上游署名。

RapidOCR 的三个 ONNX 模型使用 ModelScope 的 `v3.9.2` 修订；该修订模型卡声明 Apache License 2.0。模型卡、具体文件名、来源和哈希均保留，权重未经应用修改。

第三方训练数据、商标及署名不能视为本项目自有资产。

## 构建工具与源码材料

开发/构建依赖与运行依赖分开；实际进入冻结包的额外模块也纳入声明收集。PyInstaller 官方打包例外允许分发生成的应用而无需附其许可证或致谢；该例外不重新授权应用的依赖。Inno Setup 的原声明位于 `scripts/packaging/languages/INNO-LICENSE.txt`。

Argos Translate 软件采用上游 MIT 许可，保留其声明以说明模型集成来源；当前应用不通过该 Python 包运行推理，它不是 `requirements.lock` 中的运行依赖。

发布完整程序包时同时提供本项目源码（`source-materials.zip`）与第三方组件的许可说明；Qt / Qt for Python 与 GEOS 以动态库形式使用。公开分发前检查实际打包内容与第三方署名。
