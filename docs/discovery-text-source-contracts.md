# 本轮三有界text scope source contracts（实施前提案）

仅从现存官方捕获回放，不改每日执行目录/routine；最迟12:50（北京时间）交首轮。

## DeepSeek
原厂pricing article的 Model Details 独立完整MODEL表 -> 脚注 -> Deduction Rules -> article关闭 -> HTML关闭。
必须显式原厂BASE URL、非空唯一合法MODEL单元、逐列MODEL VERSION对应、完整标签。目录页工具/语音表不作为text模型。
脚注须完整匹配“Use <code>当前ID</code> as model name; legacy names <code>别名</code> ... still accepted ... corresponding models retired ... served by 版本”的关系；target必须对应MODEL列及VERSION列。别名调用保留active_accepted_alias，退役仅指底层旧实体，无精确T。未来合法ID列保留；未知结构/脚注/重复/截断失败关门，不按固定两款硬编码。

## 腾讯混元
仅官方1823/130051目录现存正文，以语言模型及多模态理解模型两节覆盖text/图文理解输出；不能只看第一张表。
逐表明示model调用参数，逐行合法非空ID；Hy/混元显示品牌与hy/hunyuan调用ID须双重一致，不按TokenHub页面托管就当原厂。已知第三方品牌的记录另列TokenHub reseller；未知归属失败关门。
页面全目录heading/表终止、能力说明与HTML闭合齐；未知新section/表、遗漏类型、截断失败关门。未来合法Hy ID保留。其他模态原始记录保持，不扩监控scope。

## Anthropic
All models到Using Models API章节完整表逐行；有链接实体必须各有原生Claude API表ID，不用detail slug猜。
无链接retired实体仅凭生命周期明确display/API-ID关系桥接；单实体notice可唯一桥接；多实体notice不得猜一一对应，不以字符串大小写/标点变换猜ID。
先实现notice桥与严格目录终止证明；遇到Opus4/Sonnet4共有notice仅明示组关系则保留pending，Anthropic整体不证全。没有直接桥证据不额外搜索或冒充完整。

## 主动反例
非法输入类型、HTML/Markdown表缺行/字段/列、文末截断、未知heading、新合法ID、native/第三方错配、别名路由文本变化、孤立/多义notice、缺detail/缺原厂API列。既存body只读，回放不是fresh；作者complete不是独审通过。

## 本次实现与保留边界

- DeepSeek与腾讯text完整证明从结构/表/原厂身份/终止条件动态推导，不使用固定模型数或固定型号白名单。表内未知未来合法ID可进入；未知格式/品牌/未审section失败关门。
- 腾讯同时覆盖语言模型和多模态理解模型（不是只看第一张表），其他模态旧raw observations保留并标text_scope_member=false，不新增监控scope。
- Anthropic只实现单实体Claude API退休notice显式桥；当前Opus4.1得直接证据，Opus4/Sonnet4共有notice仍不能提供一一display/API-ID桥。完整目录终止proof未据此放行；所有Anthropic完整性flags保持未通过。
- 新回放必须标replay，不把历史混元成功body替代当前fresh超时；本轮不发新厂商请求。作者scope计数不等于独立审核。
- 每日执行目录repo保持已审e731d0d原样。开发只在独立worktree。远端PR新head与每日pin分别报告；每日pin须增量独审后经负责人更新，本次未改routine，未自动更新每日执行代码。
