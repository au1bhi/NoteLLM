# 部署与检查记录

项目以 Docker Compose 提供 PostgreSQL 服务，向量扩展由 pgvector 镜像提供。应用在启动前需要应用 Alembic 迁移；迁移版本比应用代码旧时，不应把数据库视为可用。开发环境可单独启动 FastAPI 和 Vite，生产演示应使用同一份非敏感配置模板。

代码检查包含 Ruff、mypy、ty、pytest 和前端生产构建。单元测试必须使用假 provider，不能在 CI 或日常测试中消耗外部模型额度。真实 provider 的冒烟评测应只针对固定合成语料，并在完成后清除临时用户与上传文件。

若 PostgreSQL 提示 collation version mismatch，应在维护窗口按数据库提示重建相关对象并刷新 collation 版本。该维护问题与 pgvector 维度不匹配不同：后者会阻止向量写入，必须先使模型返回维度与迁移定义一致。
