# 固定评测结果

本报告由 `backend/scripts/evaluate_retrieval.py` 从合成语料生成。运行会创建并清理临时评测数据，不使用用户上传资料。

## 配置

- 运行时间（UTC）：2026-07-23T08:50:54.984398+00:00
- 代码提交：cb0ead1
- 问题数：34
- 检索：pgvector cosine distance，Top-K=5
- 分块：1,000 字符，150 字符重叠
- 嵌入模型：embedding-3（1024 维）
- 聊天模型：deepseek-v4-flash

## 自动指标

- Recall@5：100.0%
- 检索平均耗时：339 ms
- 检索 P95 耗时：894 ms
- 回答数：34
- 回答平均耗时：2904 ms
- 回答 P95 耗时：5595 ms
- 引用正确率（自动）：97.1%
- 关键词命中率（忠实度筛查）：88.2%

## 解释与人工复核

引用正确率只检查至少一条已验证引用是否来自标注的期望来源；关键词命中率不等同于回答忠实度。论文定稿前应逐题阅读答案和引用摘录，记录人工忠实度结论及异常原因。

## 逐题结果

| ID | Recall@5 | 检索 ms | 回答 ms | 引用来源匹配 | 关键词命中 |
| --- | --- | ---: | ---: | --- | --- |
| Q01 | 是 | 289 | 3489 | 是 | 是 |
| Q02 | 是 | 308 | 2426 | 是 | 是 |
| Q03 | 是 | 267 | 2397 | 是 | 是 |
| Q04 | 是 | 171 | 2746 | 是 | 否 |
| Q05 | 是 | 276 | 2294 | 是 | 是 |
| Q06 | 是 | 167 | 4536 | 是 | 是 |
| Q07 | 是 | 184 | 2109 | 是 | 是 |
| Q08 | 是 | 288 | 3044 | 是 | 是 |
| Q09 | 是 | 273 | 4017 | 是 | 否 |
| Q10 | 是 | 155 | 3210 | 是 | 是 |
| Q11 | 是 | 168 | 2737 | 是 | 是 |
| Q12 | 是 | 233 | 7037 | 是 | 是 |
| Q13 | 是 | 327 | 2654 | 是 | 是 |
| Q14 | 是 | 231 | 2198 | 是 | 是 |
| Q15 | 是 | 278 | 2383 | 是 | 是 |
| Q16 | 是 | 152 | 2654 | 是 | 是 |
| Q17 | 是 | 256 | 2256 | 是 | 是 |
| Q18 | 是 | 176 | 2625 | 是 | 是 |
| Q19 | 是 | 243 | 1976 | 是 | 是 |
| Q20 | 是 | 250 | 3330 | 是 | 是 |
| Q21 | 是 | 296 | 3285 | 是 | 是 |
| Q22 | 是 | 267 | 2490 | 是 | 是 |
| Q23 | 是 | 267 | 1735 | 是 | 是 |
| Q24 | 是 | 279 | 2526 | 是 | 是 |
| Q25 | 是 | 272 | 1702 | 是 | 是 |
| Q26 | 是 | 270 | 1876 | 是 | 是 |
| Q27 | 是 | 270 | 1868 | 是 | 是 |
| Q28 | 是 | 258 | 2295 | 是 | 是 |
| Q29 | 是 | 179 | 2625 | 是 | 是 |
| Q30 | 是 | 252 | 2235 | 是 | 是 |
| Q31 | 是 | 133 | 3545 | 是 | 是 |
| Q32 | 是 | 245 | 5595 | 否 | 否 |
| Q33 | 是 | 894 | 3255 | 是 | 是 |
| Q34 | 是 | 2954 | 3585 | 是 | 否 |

## 人工忠实度复核表

下表只包含合成语料的输出。请逐题核对回答是否仅由引用来源支持，并将“待人工复核”替换为“通过”或“未通过”，再简述异常原因。

| ID | 问题 | 期望来源 | 模型回答 | 已验证引用来源 | 人工忠实度 |
| --- | --- | --- | --- | --- | --- |
| Q01 | NoteLLM 支持哪些上传文件类型？ | rag_workflow.md | NoteLLM 支持上传 UTF-8 TXT、Markdown 和 PDF 文件。 | rag_workflow.md | 待人工复核 |
| Q02 | PDF 来源为什么可以显示页码？ | rag_workflow.md | PDF 会按页提取文本，因此引用可以显示页码。 | rag_workflow.md | 待人工复核 |
| Q03 | 文本被分块前会先经过什么步骤？ | rag_workflow.md | 提取文本 | rag_workflow.md | 待人工复核 |
| Q04 | 默认分块长度是多少？ | rag_workflow.md | 默认分块长度为1,000个字符。 | rag_workflow.md | 待人工复核 |
| Q05 | 相邻分块保留多少字符重叠？ | rag_workflow.md | 150个字符 | rag_workflow.md | 待人工复核 |
| Q06 | 哪些来源状态允许参与检索？ | rag_workflow.md | 只有状态为 ready 且已有向量的分块才可参与检索。 | rag_workflow.md | 待人工复核 |
| Q07 | 检索使用哪种距离度量？ | rag_workflow.md | 检索使用余弦距离。 | rag_workflow.md | 待人工复核 |
| Q08 | 一次问题默认返回多少个候选分块？ | rag_workflow.md | 5 | api_contract.md, rag_workflow.md | 待人工复核 |
| Q09 | 聊天模型可引用的 chunk ID 来自哪里？ | rag_workflow.md | 聊天模型可引用的 chunk ID 来自用户当前笔记本中状态为 ready 的来源，经余弦距离检索得到的前5个分块。 | rag_workflow.md | 待人工复核 |
| Q10 | 模型返回未知引用 ID 时后端如何处理？ | rag_workflow.md | 后端会移除不属于候选集的引用 ID；若没有有效引用，回答必须是“资料不足，无法根据当前笔记本中的来源可靠回答。” | rag_workflow.md | 待人工复核 |
| Q11 | 没有有效引用时系统应回复什么？ | rag_workflow.md | 资料不足，无法根据当前笔记本中的来源可靠回答。 | product_scope.md, rag_workflow.md | 待人工复核 |
| Q12 | 删除来源后哪些派生数据需要清理？ | rag_workflow.md | 删除来源时，数据库会级联删除其分块和向量，同时本地上传文件也会被删除。 | rag_workflow.md | 待人工复核 |
| Q13 | 笔记本访问控制依赖哪个字段校验？ | rag_workflow.md | owner_id | access_boundaries.md, rag_workflow.md | 待人工复核 |
| Q14 | 固定评测语料是否应包含个人资料？ | study_protocol.md | 不应包含。固定评测语料应使用合成且不含个人资料的语料。 | study_protocol.md | 待人工复核 |
| Q15 | 每轮实验至少要记录哪些模型信息？ | study_protocol.md | 每轮实验至少要记录代码提交、嵌入模型、向量维度、Top-K、运行日期和数据库镜像版本。 | study_protocol.md | 待人工复核 |
| Q16 | 为什么不应同时调整多个检索参数？ | study_protocol.md | 除非实验目标是比较配置，否则不得在同一轮中同时修改分块长度、重叠长度和检索数量，否则无法确定哪个参数变化导致了效果变化。 | study_protocol.md | 待人工复核 |
| Q17 | 评测问题包含哪三种类型？ | study_protocol.md | 事实定位、流程理解和边界条件 | study_protocol.md | 待人工复核 |
| Q18 | Recall@5 如何判定一次命中？ | study_protocol.md | 在前5个返回分块中，至少有一个分块来自期望来源，则视为一次命中。 | study_protocol.md | 待人工复核 |
| Q19 | 引用正确率在什么情况下计算？ | study_protocol.md | 引用正确率只在模型生成了回答时计算。 | study_protocol.md | 待人工复核 |
| Q20 | 什么样的引用记为正确？ | study_protocol.md | 若回答中至少一个已验证的引用来自期望来源，且引用ID在检索候选集中（即未被后端丢弃），则记为正确。 | rag_workflow.md, study_protocol.md | 待人工复核 |
| Q21 | 未知引用 ID 能否计入正确率？ | study_protocol.md | 不能 | rag_workflow.md, study_protocol.md | 待人工复核 |
| Q22 | 关键词命中率能否替代人工忠实度审核？ | study_protocol.md | 不能。关键词命中率仅是自动化的忠实度筛查信号，回答包含指定关键词不代表人工审核已经通过。 | study_protocol.md | 待人工复核 |
| Q23 | 报告中应使用哪些响应时间统计量？ | study_protocol.md | 平均值和 P95 | study_protocol.md | 待人工复核 |
| Q24 | 响应时间异常可能来自哪些外部因素？ | study_protocol.md | 网络波动、供应商限流和冷启动。 | study_protocol.md | 待人工复核 |
| Q25 | 本地数据库容器使用什么镜像？ | demo_operations.md | 本地数据库容器使用 pgvector/pgvector:pg18 镜像。 | demo_operations.md | 待人工复核 |
| Q26 | 主机连接数据库时使用什么端口？ | demo_operations.md | 5433 | demo_operations.md | 待人工复核 |
| Q27 | 数据库迁移命令应在什么目录执行？ | demo_operations.md | 应在 backend 目录执行 | demo_operations.md | 待人工复核 |
| Q28 | 当前嵌入列的维度是多少？ | demo_operations.md | 1024 | demo_operations.md | 待人工复核 |
| Q29 | 前端和 API 文档分别在哪两个地址查看？ | demo_operations.md | 前端地址：http://localhost:5173，API 文档地址：http://localhost:8000/docs。 | demo_operations.md | 待人工复核 |
| Q30 | 另一账户访问受保护笔记本应收到什么状态码？ | demo_operations.md | 404 | access_boundaries.md, demo_operations.md | 待人工复核 |
| Q31 | 演示问答前来源应显示什么状态？ | demo_operations.md | ready | demo_operations.md, rag_workflow.md | 待人工复核 |
| Q32 | 刷新工作区后应保留哪两类内容？ | demo_operations.md | 刷新工作区后应保留 conversation 和 message 两类内容。 | api_contract.md | 待人工复核 |
| Q33 | provider 未配置时密钥能否交给浏览器？ | demo_operations.md | 不能。当 provider 未配置时，系统不应把密钥交给浏览器。 | access_boundaries.md, demo_operations.md | 待人工复核 |
| Q34 | provider 未配置时系统能否编造答案？ | demo_operations.md | 不会编造答案。 | demo_operations.md | 待人工复核 |
