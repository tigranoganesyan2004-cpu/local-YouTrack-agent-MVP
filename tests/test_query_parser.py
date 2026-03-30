"""
tests/test_query_parser.py
 
Тесты для src/query_parser.py.
 
Запуск:
    python -m pytest tests/test_query_parser.py -v
 
Тесты покрывают:
  - детерминированный слой (без LLM) — все явные команды
  - LLM-слой с моком — корректный JSON, невалидный JSON, неизвестный mode
  - кэш — повторный запрос не вызывает LLM второй раз
  - граничные случаи — пустой запрос, регистр, пробелы, смешанный текст
"""
 
import sys
import os
import json
from unittest.mock import patch, MagicMock
 
import pytest
 
# Добавляем корень проекта в путь, чтобы импорты работали без установки пакета
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
 
from src.query_parser import (
    detect_intent,
    classify_intent_via_llm,
    extract_issue_id,
    parse_key_values,
    clear_intent_cache,
    VALID_MODES,
    CLASSIFICATION_PROMPT_TEMPLATE,
)
 
 
# ──────────────────────────────────────────────────────────────────────────────
# Фикстура: сброс кэша перед каждым тестом
# ──────────────────────────────────────────────────────────────────────────────
 
@pytest.fixture(autouse=True)
def reset_cache():
    clear_intent_cache()
    yield
    clear_intent_cache()
 
 
# ──────────────────────────────────────────────────────────────────────────────
# Вспомогательные функции
# ──────────────────────────────────────────────────────────────────────────────
 
class TestExtractIssueId:
    def test_latin_id(self):
        assert extract_issue_id("покажи EAIST-350") == "EAIST-350"
 
    def test_underscore_id(self):
        assert extract_issue_id("EAIST_SGL-123 это задача") == "EAIST_SGL-123"
 
    def test_no_id(self):
        assert extract_issue_id("нет ID в этом тексте") is None
 
    def test_id_alone(self):
        assert extract_issue_id("ABC-1") == "ABC-1"
 
    def test_id_at_end(self):
        assert extract_issue_id("задача номер PRJ-999") == "PRJ-999"
 
 
class TestParseKeyValues:
    def test_single_filter(self):
        result = parse_key_values(["статус=Открыта"])
        assert result == {"status": "Открыта"}
 
    def test_multiple_filters(self):
        result = parse_key_values(["приоритет=Высокий", "статус=Открыта"])
        assert result["priority"] == "Высокий"
        assert result["status"] == "Открыта"
 
    def test_unknown_field_passthrough(self):
        result = parse_key_values(["неизвестное_поле=значение"])
        assert "неизвестное_поле" in result
 
    def test_empty_value_ignored(self):
        result = parse_key_values(["статус="])
        assert "status" not in result
 
    def test_no_equals_ignored(self):
        result = parse_key_values(["просто_слово"])
        assert result == {}
 
    def test_english_aliases(self):
        result = parse_key_values(["priority=High"])
        assert result == {"priority": "High"}
 
 
# ──────────────────────────────────────────────────────────────────────────────
# Детерминированный слой detect_intent (без LLM)
# ──────────────────────────────────────────────────────────────────────────────
 
class TestDetectIntentDeterministic:
    """Эти тесты не должны вызывать LLM — проверяем с патчем для уверенности."""
 
    def _assert_no_llm(self, query: str, expected_mode: str, **expected_fields):
        with patch("src.query_parser.classify_intent_via_llm") as mock_llm:
            result = detect_intent(query)
        mock_llm.assert_not_called()
        assert result["mode"] == expected_mode
        for key, value in expected_fields.items():
            assert result.get(key) == value, f"Field {key!r}: expected {value!r}, got {result.get(key)!r}"
 
    # ── help ──────────────────────────────────────────────────────────────
 
    def test_help_russian(self):
        self._assert_no_llm("помощь", "help")
 
    def test_help_english(self):
        self._assert_no_llm("help", "help")
 
    def test_help_case_insensitive(self):
        self._assert_no_llm("ПОМОЩЬ", "help")
 
    # ── task_by_id ────────────────────────────────────────────────────────
 
    def test_id_prefix_russian(self):
        self._assert_no_llm("ид EAIST-350", "task_by_id", issue_id="EAIST-350")
 
    def test_id_prefix_english(self):
        self._assert_no_llm("id ABC-12", "task_by_id", issue_id="ABC-12")
 
    def test_show_prefix_russian(self):
        self._assert_no_llm("показать PROJ-5", "task_by_id", issue_id="PROJ-5")
 
    def test_show_prefix_english(self):
        self._assert_no_llm("show XYZ-99", "task_by_id", issue_id="XYZ-99")
 
    def test_id_in_free_text(self):
        # ID в свободном тексте (без явного префикса) — находится регуляркой
        self._assert_no_llm("расскажи про EAIST_SGL-100", "task_by_id", issue_id="EAIST_SGL-100")
 
    # ── exact_search ──────────────────────────────────────────────────────
 
    def test_exact_russian(self):
        self._assert_no_llm("точно уведомления", "exact_search", query="уведомления")
 
    def test_exact_english(self):
        self._assert_no_llm("exact notifications", "exact_search", query="notifications")
 
    # ── similar ───────────────────────────────────────────────────────────
 
    def test_similar_russian(self):
        self._assert_no_llm("похожие авторизация", "similar", query="авторизация")
 
    def test_similar_english(self):
        self._assert_no_llm("similar auth tasks", "similar", query="auth tasks")
 
    # ── analyze_new_task ──────────────────────────────────────────────────
 
    def test_analyze_russian(self):
        self._assert_no_llm("анализ новая интеграция с LDAP", "analyze_new_task")
 
    def test_proanalyze_russian(self):
        self._assert_no_llm("проанализируй задачу по уведомлениям", "analyze_new_task")
 
    # ── general_search (явный префикс) ───────────────────────────────────
 
    def test_general_russian(self):
        self._assert_no_llm("общий ошибки в модуле", "general_search", query="ошибки в модуле")
 
    def test_llm_prefix(self):
        self._assert_no_llm("llm что происходит", "general_search", query="что происходит")
 
    # ── list ──────────────────────────────────────────────────────────────
 
    def test_list_no_filters(self):
        self._assert_no_llm("список", "list")
        # filters должны быть пустым dict
 
    def test_list_with_filter(self):
        with patch("src.query_parser.classify_intent_via_llm") as mock_llm:
            result = detect_intent("список статус=Открыта")
        mock_llm.assert_not_called()
        assert result["mode"] == "list"
        assert result["filters"].get("status") == "Открыта"
 
    def test_list_multiple_filters(self):
        with patch("src.query_parser.classify_intent_via_llm") as mock_llm:
            result = detect_intent("список статус=Открыта приоритет=Высокий")
        mock_llm.assert_not_called()
        assert result["mode"] == "list"
        assert result["filters"]["status"] == "Открыта"
        assert result["filters"]["priority"] == "Высокий"
 
    # ── count ─────────────────────────────────────────────────────────────
 
    def test_count_by_status(self):
        self._assert_no_llm("количество по статус", "count", field="status")
 
    def test_count_by_priority(self):
        self._assert_no_llm("количество по приоритет", "count", field="priority")
 
    def test_count_english(self):
        self._assert_no_llm("count by status", "count", field="status")
 
    def test_count_with_filter(self):
        with patch("src.query_parser.classify_intent_via_llm") as mock_llm:
            result = detect_intent("количество по статус приоритет=Высокий")
        mock_llm.assert_not_called()
        assert result["mode"] == "count"
        assert result["field"] == "status"
        assert result["filters"].get("priority") == "Высокий"
 
    # ── deadlines ─────────────────────────────────────────────────────────
 
    def test_deadlines_default(self):
        self._assert_no_llm("сроки", "deadlines", days=14)
 
    def test_deadlines_custom_days(self):
        self._assert_no_llm("сроки days=7", "deadlines", days=7)
 
    def test_deadlines_english(self):
        self._assert_no_llm("deadlines days=30", "deadlines", days=30)
 
    def test_deadlines_russian(self):
        self._assert_no_llm("дедлайны", "deadlines")
 
    # ── граничные случаи ──────────────────────────────────────────────────
 
    def test_empty_string(self):
        with patch("src.query_parser.classify_intent_via_llm") as mock_llm:
            # Пустая строка → fallback без LLM (detect_intent возвращает рано)
            mock_llm.return_value = {"mode": "general_search", "query": ""}
            result = detect_intent("")
        assert result["mode"] == "general_search"
 
    def test_whitespace_only(self):
        with patch("src.query_parser.classify_intent_via_llm") as mock_llm:
            mock_llm.return_value = {"mode": "general_search", "query": ""}
            result = detect_intent("   ")
        assert result["mode"] == "general_search"
 
    def test_leading_whitespace_stripped(self):
        # Команда с лишними пробелами всё равно должна работать детерминированно
        self._assert_no_llm("  помощь  ", "help")
 
 
# ──────────────────────────────────────────────────────────────────────────────
# LLM-слой: classify_intent_via_llm
# ──────────────────────────────────────────────────────────────────────────────
 
def _make_llm_response(payload: dict) -> str:
    """Имитирует сырой текстовый ответ Ollama с JSON внутри."""
    return json.dumps(payload, ensure_ascii=False)
 
 
class TestClassifyIntentViaLLM:
 
    def _call_with_mock(self, text: str, llm_raw: str) -> dict:
        with patch("src.query_parser.ollama_client") as mock_client:
            mock_client.generate.return_value = llm_raw
            return classify_intent_via_llm(text)
 
    # ── корректные ответы ─────────────────────────────────────────────────
 
    def test_similar_mode(self):
        raw = _make_llm_response({"mode": "similar", "query": "авторизация", "issue_id": None, "filters": {}, "field": "status", "days": 14})
        result = self._call_with_mock("найди задачи похожие на авторизацию", raw)
        assert result["mode"] == "similar"
        assert "авторизац" in result["query"]
 
    def test_deadlines_mode(self):
        raw = _make_llm_response({"mode": "deadlines", "query": "горящие сроки", "issue_id": None, "filters": {}, "field": "status", "days": 7})
        result = self._call_with_mock("какие сроки горят на этой неделе", raw)
        assert result["mode"] == "deadlines"
        assert result["days"] == 7
 
    def test_list_with_filters(self):
        raw = _make_llm_response({
            "mode": "list",
            "query": "задачи в работе",
            "issue_id": None,
            "filters": {"status": "В работе"},
            "field": "status",
            "days": 14,
        })
        result = self._call_with_mock("покажи все задачи которые сейчас в работе", raw)
        assert result["mode"] == "list"
        assert result["filters"].get("status") == "В работе"
 
    def test_count_mode(self):
        raw = _make_llm_response({"mode": "count", "query": "статистика", "issue_id": None, "filters": {}, "field": "priority", "days": 14})
        result = self._call_with_mock("сколько задач у каждого приоритета", raw)
        assert result["mode"] == "count"
        assert result["field"] == "priority"
 
    def test_task_by_id_with_issue_id(self):
        raw = _make_llm_response({"mode": "task_by_id", "query": "", "issue_id": "PROJ-42", "filters": {}, "field": "status", "days": 14})
        result = self._call_with_mock("что за задача PROJ-42", raw)
        assert result["mode"] == "task_by_id"
        assert result["issue_id"] == "PROJ-42"
 
    def test_analyze_new_task_mode(self):
        raw = _make_llm_response({"mode": "analyze_new_task", "query": "интеграция с внешней системой", "issue_id": None, "filters": {}, "field": "status", "days": 14})
        result = self._call_with_mock("есть ли похожие задачи на мою новую задачу по интеграции", raw)
        assert result["mode"] == "analyze_new_task"
 
    # ── невалидные ответы → fallback ──────────────────────────────────────
 
    def test_invalid_json_fallback(self):
        result = self._call_with_mock("свободный запрос", "это не JSON вообще")
        assert result["mode"] == "general_search"
 
    def test_unknown_mode_fallback(self):
        raw = _make_llm_response({"mode": "unknown_mode_xyz", "query": "запрос"})
        result = self._call_with_mock("запрос", raw)
        assert result["mode"] == "general_search"
 
    def test_empty_response_fallback(self):
        result = self._call_with_mock("запрос", "")
        assert result["mode"] == "general_search"
 
    def test_json_inside_markdown_block(self):
        # Модель иногда оборачивает ответ в ```json ... ```
        raw = '```json\n{"mode":"similar","query":"уведомления","issue_id":null,"filters":{},"field":"status","days":14}\n```'
        result = self._call_with_mock("найди похожее на уведомления", raw)
        # JSON извлекается из текста — должен работать
        assert result["mode"] == "similar"
 
    def test_ollama_exception_fallback(self):
        with patch("src.query_parser.ollama_client") as mock_client:
            mock_client.generate.side_effect = ConnectionError("Ollama недоступна")
            result = classify_intent_via_llm("какой-то запрос")
        assert result["mode"] == "general_search"
        assert result["query"] == "какой-то запрос"
 
    def test_ollama_timeout_fallback(self):
        import socket
        with patch("src.query_parser.ollama_client") as mock_client:
            mock_client.generate.side_effect = TimeoutError("timeout")
            result = classify_intent_via_llm("медленный запрос")
        assert result["mode"] == "general_search"
 
    # ── нормализация полей ─────────────────────────────────────────────────
 
    def test_days_string_converted_to_int(self):
        # LLM иногда возвращает числа как строки
        raw = _make_llm_response({"mode": "deadlines", "query": "сроки", "issue_id": None, "filters": {}, "field": "status", "days": "10"})
        result = self._call_with_mock("сроки на 10 дней", raw)
        assert result["days"] == 10
        assert isinstance(result["days"], int)
 
    def test_filters_field_aliases_applied(self):
        # LLM вернула русский псевдоним поля
        raw = _make_llm_response({"mode": "list", "query": "задачи", "issue_id": None, "filters": {"статус": "Открыта"}, "field": "status", "days": 14})
        result = self._call_with_mock("задачи в статусе Открыта", raw)
        # псевдоним «статус» должен быть нормализован в «status»
        assert "status" in result["filters"]
        assert result["filters"]["status"] == "Открыта"
 
    def test_empty_issue_id_becomes_none(self):
        raw = _make_llm_response({"mode": "general_search", "query": "запрос", "issue_id": "", "filters": {}, "field": "status", "days": 14})
        result = self._call_with_mock("просто запрос", raw)
        assert result.get("issue_id") is None
 
    def test_all_valid_modes_accepted(self):
        for mode in VALID_MODES:
            raw = _make_llm_response({"mode": mode, "query": "тест", "issue_id": None, "filters": {}, "field": "status", "days": 14})
            result = self._call_with_mock(f"тест режима {mode}", raw)
            assert result["mode"] == mode, f"Mode {mode!r} not accepted"
            clear_intent_cache()
 
 
# ──────────────────────────────────────────────────────────────────────────────
# Кэш
# ──────────────────────────────────────────────────────────────────────────────
 
class TestIntentCache:
 
    def test_repeated_query_uses_cache(self):
        """Второй вызов с тем же текстом не должен обращаться к Ollama."""
        raw = _make_llm_response({"mode": "similar", "query": "уведомления", "issue_id": None, "filters": {}, "field": "status", "days": 14})
        with patch("src.query_parser.ollama_client") as mock_client:
            mock_client.generate.return_value = raw
            first = classify_intent_via_llm("найди похожие на уведомления")
            second = classify_intent_via_llm("найди похожие на уведомления")
 
        assert mock_client.generate.call_count == 1, "LLM вызвана дважды для одного запроса"
        assert first == second
 
    def test_different_queries_both_call_llm(self):
        raw = _make_llm_response({"mode": "general_search", "query": "q", "issue_id": None, "filters": {}, "field": "status", "days": 14})
        with patch("src.query_parser.ollama_client") as mock_client:
            mock_client.generate.return_value = raw
            classify_intent_via_llm("запрос один")
            classify_intent_via_llm("запрос два")
 
        assert mock_client.generate.call_count == 2
 
    def test_cache_size_limit(self):
        """При превышении лимита старые записи вытесняются."""
        from src.query_parser import _intent_cache, _CACHE_MAX_SIZE
 
        raw = _make_llm_response({"mode": "general_search", "query": "q", "issue_id": None, "filters": {}, "field": "status", "days": 14})
        with patch("src.query_parser.ollama_client") as mock_client:
            mock_client.generate.return_value = raw
            for i in range(_CACHE_MAX_SIZE + 10):
                classify_intent_via_llm(f"уникальный запрос номер {i}")
 
        assert len(_intent_cache) <= _CACHE_MAX_SIZE
 
    def test_cache_cleared_by_fixture(self):
        """Фикстура reset_cache сбрасывает кэш перед каждым тестом."""
        from src.query_parser import _intent_cache
        assert len(_intent_cache) == 0
 
    def test_fallback_result_also_cached(self):
        """Fallback-результат (при ошибке LLM) тоже кэшируется."""
        with patch("src.query_parser.ollama_client") as mock_client:
            mock_client.generate.side_effect = RuntimeError("ошибка")
            classify_intent_via_llm("запрос при ошибке")
            classify_intent_via_llm("запрос при ошибке")
 
        # generate вызвана только один раз — второй раз из кэша
        assert mock_client.generate.call_count == 1
 
 
# ──────────────────────────────────────────────────────────────────────────────
# Интеграция: detect_intent → LLM-путь
# ──────────────────────────────────────────────────────────────────────────────
 
class TestDetectIntentLLMPath:
    """Тесты для запросов, которые проходят через LLM-классификацию."""
 
    def _detect_with_mock_llm(self, text: str, llm_mode: str, **llm_extra) -> dict:
        payload = {"mode": llm_mode, "query": text, "issue_id": None, "filters": {}, "field": "status", "days": 14}
        payload.update(llm_extra)
        raw = _make_llm_response(payload)
        with patch("src.query_parser.ollama_client") as mock_client:
            mock_client.generate.return_value = raw
            return detect_intent(text)
 
    def test_free_text_similar_via_llm(self):
        result = self._detect_with_mock_llm(
            "есть ли что-то похожее на задачи по уведомлениям",
            "similar",
            query="уведомления",
        )
        assert result["mode"] == "similar"
 
    def test_free_text_deadlines_via_llm(self):
        result = self._detect_with_mock_llm(
            "у кого горят сроки на следующей неделе",
            "deadlines",
            days=7,
        )
        assert result["mode"] == "deadlines"
        assert result["days"] == 7
 
    def test_free_text_list_via_llm(self):
        result = self._detect_with_mock_llm(
            "покажи мне задачи которые сейчас в статусе ревью",
            "list",
            filters={"status": "ревью"},
        )
        assert result["mode"] == "list"
 
    def test_llm_fallback_on_garbage(self):
        with patch("src.query_parser.ollama_client") as mock_client:
            mock_client.generate.return_value = "не JSON"
            result = detect_intent("непонятный запрос без явных команд")
        assert result["mode"] == "general_search"
 
    def test_llm_fallback_on_exception(self):
        with patch("src.query_parser.ollama_client") as mock_client:
            mock_client.generate.side_effect = Exception("503")
            result = detect_intent("что-то непонятное")
        assert result["mode"] == "general_search"
 
 
# ──────────────────────────────────────────────────────────────────────────────
# Промт
# ──────────────────────────────────────────────────────────────────────────────
 
class TestClassificationPrompt:
 
    def test_prompt_contains_all_modes(self):
        """Промт должен упоминать все допустимые режимы."""
        for mode in VALID_MODES:
            assert mode in CLASSIFICATION_PROMPT_TEMPLATE, f"Mode {mode!r} not in prompt"
 
    def test_prompt_has_format_placeholder(self):
        assert "{text}" in CLASSIFICATION_PROMPT_TEMPLATE
 
    def test_prompt_reasonable_length(self):
        """Промт без подстановки должен быть компактным (~200 токенов ≈ 800 символов)."""
        template_without_placeholder = CLASSIFICATION_PROMPT_TEMPLATE.replace("{text}", "")
        assert len(template_without_placeholder) < 1500, "Промт слишком длинный"
 
    def test_prompt_renders_correctly(self):
        rendered = CLASSIFICATION_PROMPT_TEMPLATE.format(text="тестовый запрос")
        assert "тестовый запрос" in rendered
        assert "{text}" not in rendered