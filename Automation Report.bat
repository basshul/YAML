@echo off
:: 한글 깨짐 방지 (UTF-8 언어팩 로드)
chcp 65001 >nul

:: 날짜 변수 설정 (YYYY-MM-DD 형식)
set TODAY=%date:~0,4%-%date:~5,2%-%date:~8,2%

claude -p "첨부한 qa_report.json 을 읽고, GME QA 자동화 진행 데일리 리포트를 마크다운으로 작성해줘. 1) 맨 위에 오늘 새로 완료된 케이스와 '검토 필요' 항목을 배치하고, 2) 전체 커버리지(완전/부분/미커버)와 어제 대비 변경분을 요약해줘. 3) 특히 전날 어떤 부분에 대한 작업이 있었는지 기술하고, 작업 중 발생한 기술적 문제와 그 문제를 어떻게 해결했는지(Troubleshooting) 상세히 포함해줘. 단, 단순 정보 부족으로 인해 발생한 이슈는 제외하고 실제 자동화 구현 및 환경 상의 문제와 해결책 위주로 서술해줘. 마지막으로 ClickUp 문서 document_id 2kzmx95r-78 의 페이지 2kzmx95r-38 하위에 '%TODAY% 데일리 리포트' 제목으로 새 페이지를 만들어 올려줘." ^
  --append-system-prompt "리포트는 한국어로 작성하되, 표(Table)와 불릿 기호(*)를 적극 활용하여 가독성을 높이고 기술적 트러블슈팅 과정은 상세하게 기술하고, 요약버전도 작성해줘." ^
  --permission-mode dontAsk ^
  --allowedTools "Read" "mcp__clickup" ^
  --allowedTools "Read" "mcp__claude_ai_ClickUp__clickup_create_document_page" "mcp__claude_ai_ClickUp__clickup_list_document_pages"

echo.
echo 작업이 완료되었습니다.
pause