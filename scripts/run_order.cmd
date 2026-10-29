@echo off
cd /d "C:\Users\Administrator\.zcode\workspace\9af7e246-9f04-46ee-9ce9-cb285b2aad54\luckin-auto"
python -X utf8 scripts\mcp_order.py >> logs\scheduled_run.log 2>&1
