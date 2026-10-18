# 在线平台配置

在设置的“平台与模型”页选择平台，填写自己账户的凭据后保存。密钥保存在 Windows 系统凭据存储中，非敏感参数和凭据引用保存到本地设置文件。项目不加载 `.env`，不提供共享额度。

以下字段与范围对应当前客户端实现。服务开通条件、模型权限、价格和额度以官方控制台为准。

| 平台 | 配置字段 | 当前实现 |
| --- | --- | --- |
| 百度翻译 | APP ID、密钥、服务版本 | 标准版或高级版通用文本翻译 |
| 阿里云机器翻译 | AccessKey ID、AccessKey Secret、地域 | 通用版，地域选项为杭州、上海、新加坡 |
| 腾讯 TokenHub | API Key、翻译模型 | 广州入口，`hy-mt2-lite`、`hy-mt2-plus`、`hy-mt2-pro` |
| 华为 NLP | AK、SK、北京四项目 ID | 北京四文本翻译，项目 ID 为 32 位十六进制字符串 |
| 小牛通用文本 Flash | API 应用 appId、apikey | 通用文本 Flash v2 接口 |

## 账户入口

- 百度：[接口文档](https://fanyi-api.baidu.com/doc/13)、[开发者管理](https://fanyi-api.baidu.com/manage/developer)。
- 阿里云：[开通说明](https://help.aliyun.com/zh/machine-translation/getting-started/)、[控制台](https://mt.console.aliyun.com/)。
- 腾讯：[接口文档](https://cloud.tencent.com/document/product/1823/132252)、[TokenHub 控制台](https://console.cloud.tencent.com/tokenhub)。
- 华为：[文本翻译文档](https://support.huaweicloud.com/api-nlp/nlp_03_0024.html)、[NLP 控制台](https://console.huaweicloud.com/nlp/)。
- 小牛：[接口文档](https://niutrans.com/documents/contents/transapi_text_v2)、[API 应用管理](https://niutrans.com/cloud/api/list)。

## 语种选择

切换翻译平台后，源语言和目标语言列表随平台更新。点击语言选择器，可按中文名、英文名或语言代码搜索，按 Enter 确认，按 Esc 关闭。目标语言不提供“自动识别”。平台切换时保留仍可用的选择，不支持的源语言回到自动识别、目标语言回到中文。

| 平台 | 客户端可选范围 | 自动识别 |
| --- | --- | --- |
| 腾讯 TokenHub | 官方调用指南所列的 38 项，包括简繁中文、粤语、日、韩、法、德、西、俄及藏语等 | 由平台识别，省略 source |
| 百度翻译 | 34 项常用语种，包括简繁中文、粤语、日、韩、法、德、西、俄等 | 由平台识别，from=auto；部分语种需手选 |
| 阿里云通用版 | 官方列出的 16 项核心语种：中、英、日、韩、法、西、葡、意、俄、阿拉伯、土耳其、印尼、越南、泰、波兰、德 | 由平台识别，SourceLanguage=auto |
| 小牛 Flash | 38 项常用语种，包括简繁中文、粤语和少数民族语言 | 由平台识别，from=auto |
| 华为 NLP | 中文、英语 | 本地中英判断，混合文本需手选 |
| Argos 离线 | 中文、英语 | 本地中英判断 |

上述为客户端开放的范围，不等于平台全部语言或账户已开通的语言方向。阿里云繁体中文及粤语有单向限制，本版本先开放核心语种；华为官方将其他语种与服务端自动检测标记为即将下线，保留中英路径。OCR 和离线模型仍按当前资源能力工作，在线翻译新增语种不代表 OCR 新增相应识别模型。

代码映射集中在 `services/languages.py`，例如日语在百度为 `jp`、其他平台为 `ja`；繁体中文在百度和小牛为 `cht`、TokenHub 为 `zh-TR`。调整范围前核对所接入接口的官方列表，不直接使用别的平台或开源模型的代码表。

范围核对日期：2026-10-11。依据：[百度通用翻译](https://fanyi-api.baidu.com/doc_bd/21)、[阿里云通用版](https://help.aliyun.com/en/machine-translation/product-overview/general-version-of-machine-translation)、[TokenHub 调用指南](https://cloud.tencent.com/document/product/1823/132252)、[华为文本翻译](https://support.huaweicloud.com/api-nlp/nlp_03_0024.html)、[小牛 Flash 文档及其语种表](https://niutrans.com/documents/contents/transapi_text_v2)。

## 保存与验证

打开设置、切换平台和保存都不联网。主动连接验证仅向所选平台发送 `Hello.`，不发送输入框内容。保存与验证分开进行，验证成功不等于已保存草稿。

客户端按平台边界检查文本、语种及相同源目标语种，不自动拆分、截断或重试收费请求。额度不足、语言不支持或服务未开通时，修正配置后主动重试。语言代码与协议行为由本地模拟测试覆盖，实际账户是否可用需要用户主动验证。

清除某个平台凭据只影响该平台，其他配置保留。直接删除设置文件会丢失系统凭据引用；重置外观或聊天记录时应分别处理对应状态。
