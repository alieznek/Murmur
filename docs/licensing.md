# 许可与分发

## 项目许可

Murmur 自有代码、文档、示例截图和应用图标采用 **MIT**。许可正文为根目录 [LICENSE](../LICENSE)，版权说明见 [COPYRIGHT](../COPYRIGHT)，第三方声明见 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)。

允许个人或商业使用、修改与分发，包括闭源商用；分发程序或修改版本时，保留版权声明与许可正文即可。具体条件以许可正文为准。

第三方组件、模型及许可正文不变为项目自有资产；其原许可、例外和署名继续适用。Qt 的商业许可也是上游元数据中的许可选项，保存其文字不代表本项目购买或采用了商业授权。

## 第三方组件与模型

运行依赖、原生运行库与离线模型保留各自的许可和署名，汇总见 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)。

分发完整程序包时随包携带 [LICENSE](../LICENSE)、[COPYRIGHT](../COPYRIGHT) 与 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)。

Qt / Qt for Python 与 GEOS 以动态库形式使用，允许按各自许可修改、重建和替换库，并为调试修改进行必要的逆向工程；本项目不限制这些权利。替换时须保持应用需要的 ABI、编译器运行时和依赖兼容。

## 更新依赖时

安装锁定运行依赖并更新 `requirements.lock` 后，核对新版本上游的许可、版权与署名，并同步更新 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)。项目自有代码的 MIT 许可不替代第三方的许可或署名。

对外发布安装包前，在目标机器核对实际打包内容与第三方署名。
