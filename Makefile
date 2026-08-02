# NoteLLM — one-command Docker bootstrap.
#
# 交互式安装向导（本地/生产二合一，自动生成 .env）：
#   bash install.sh
# Makefile 仅做本地开发的最小封装，等价于 install.sh --local --yes。
#
#   make up      # first run: copies .env.example to .env if missing, then builds & starts
#   make up      # later runs: just starts (uses the existing .env)
#   make down    # stop the stack
#   make logs    # follow service logs
#   make ps      # container status
#
# After `make up`, open http://localhost:5173 and log in with the superuser
# from .env (FIRST_SUPERUSER / FIRST_SUPERUSER_PASSWORD). Configure the LLM /
# embedding models in .env, or use "设置 → 模型配置" in the app with your own
# OpenAI-compatible API keys.

.PHONY: up down logs ps env

env:
	@if [ -f .env ]; then \
		echo "(.env already exists, keeping it)"; \
	else \
		cp .env.example .env; \
		echo "Created .env from .env.example — edit the credentials and provider keys, then run 'make up' again."; \
	fi

up: env
	docker compose up -d --build
	@echo ""
	@echo "NoteLLM is starting:"
	@echo "  Frontend:  http://localhost:5173"
	@echo "  API docs:  http://localhost:8000/docs"
	@echo ""
	@echo "First login uses FIRST_SUPERUSER / FIRST_SUPERUSER_PASSWORD from .env."

down:
	docker compose down

logs:
	docker compose logs -f

ps:
	docker compose ps
