"""
tests/test_query_parser.py

Тесты для src/query_parser.py.

Запуск:
    python -m pytest tests/test_query_parser.py -v

Покрывают:
  - extract_issue_id
  - parse_key_values (включая current_approval_stage alias)
  - detect_intent — детерминированный слой (list, count, deadlines, task_by_id, ...)
  - Регрессии: multiword customer, dotted responsible codes, current_approval_stage e2e
"""

import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.query_parser import (
    detect_intent,
    extract_issue_id,
    parse_key_values,
)


# ──────────────────────────────────────────────────────────────────────────────
# extract_issue_id
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


# ──────────────────────────────────────────────────────────────────────────────
# parse_key_values
# ──────────────────────────────────────────────────────────────────────────────

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

    def test_current_approval_stage_alias(self):
        result = parse_key_values(["current_approval_stage=ДИТ"])
        assert result == {"current_approval_stage": "ДИТ"}

    def test_current_approval_stage_russian_alias(self):
        result = parse_key_values(["стадия=ДИТ"])
        assert result == {"current_approval_stage": "ДИТ"}

    def test_responsible_with_dot_kv(self):
        """Dotted responsible code via key=value must be preserved intact."""
        result = parse_key_values(["responsible=SEA.1"])
        assert result == {"responsible_dit": "SEA.1"}

    def test_responsible_with_dot_kv_ru(self):
        result = parse_key_values(["ответственный=SEA.1"])
        assert result == {"responsible_dit": "SEA.1"}


# ──────────────────────────────────────────────────────────────────────────────
# detect_intent — детерминированный слой
# ──────────────────────────────────────────────────────────────────────────────

class TestDetectIntentDeterministic:

    # ── help ──────────────────────────────────────────────────────────────

    def test_help_russian(self):
        assert detect_intent("помощь")["mode"] == "help"

    def test_help_english(self):
        assert detect_intent("help")["mode"] == "help"

    def test_help_case_insensitive(self):
        assert detect_intent("ПОМОЩЬ")["mode"] == "help"

    # ── task_by_id ────────────────────────────────────────────────────────

    def test_id_prefix_russian(self):
        r = detect_intent("ид EAIST-350")
        assert r["mode"] == "task_by_id"
        assert r["issue_id"] == "EAIST-350"

    def test_id_prefix_english(self):
        r = detect_intent("id ABC-12")
        assert r["mode"] == "task_by_id"
        assert r["issue_id"] == "ABC-12"

    def test_show_prefix_russian(self):
        r = detect_intent("показать PROJ-5")
        assert r["mode"] == "task_by_id"
        assert r["issue_id"] == "PROJ-5"

    def test_id_in_free_text(self):
        r = detect_intent("расскажи про EAIST_SGL-100")
        assert r["mode"] == "task_by_id"
        assert r["issue_id"] == "EAIST_SGL-100"

    # ── exact_search ──────────────────────────────────────────────────────

    def test_exact_russian(self):
        r = detect_intent("точно уведомления")
        assert r["mode"] == "exact_search"
        assert r["query"] == "уведомления"

    def test_exact_english(self):
        r = detect_intent("exact notifications")
        assert r["mode"] == "exact_search"
        assert r["query"] == "notifications"

    # ── similar ───────────────────────────────────────────────────────────

    def test_similar_russian(self):
        r = detect_intent("похожие авторизация")
        assert r["mode"] == "similar"
        assert r["query"] == "авторизация"

    def test_similar_english(self):
        r = detect_intent("similar auth tasks")
        assert r["mode"] == "similar"
        assert r["query"] == "auth tasks"

    # ── analyze_new_task ──────────────────────────────────────────────────

    def test_analyze_russian(self):
        r = detect_intent("анализ новая интеграция с LDAP")
        assert r["mode"] == "analyze_new_task"

    def test_proanalyze_russian(self):
        r = detect_intent("проанализируй задачу по уведомлениям")
        assert r["mode"] == "analyze_new_task"

    # ── general_search (explicit prefix) ──────────────────────────────────

    def test_general_russian(self):
        r = detect_intent("общий ошибки в модуле")
        assert r["mode"] == "general_search"
        assert r["query"] == "ошибки в модуле"

    def test_llm_prefix(self):
        r = detect_intent("llm что происходит")
        assert r["mode"] == "general_search"
        assert r["query"] == "что происходит"

    # ── list ──────────────────────────────────────────────────────────────

    def test_list_no_filters(self):
        r = detect_intent("список")
        assert r["mode"] == "list"

    def test_list_with_kv_filter(self):
        r = detect_intent("список статус=Открыта")
        assert r["mode"] == "list"
        assert r["filters"].get("status") == "Открыта"

    def test_list_multiple_kv_filters(self):
        r = detect_intent("список статус=Открыта приоритет=Высокий")
        assert r["mode"] == "list"
        assert r["filters"]["status"] == "Открыта"
        assert r["filters"]["priority"] == "Высокий"

    # ── count ─────────────────────────────────────────────────────────────

    def test_count_by_status(self):
        r = detect_intent("количество по статус")
        assert r["mode"] == "count"
        assert r["field"] == "status"

    def test_count_by_priority(self):
        r = detect_intent("количество по приоритет")
        assert r["mode"] == "count"
        assert r["field"] == "priority"

    def test_count_english(self):
        r = detect_intent("count by status")
        assert r["mode"] == "count"
        assert r["field"] == "status"

    def test_count_with_filter(self):
        r = detect_intent("количество по статус приоритет=Высокий")
        assert r["mode"] == "count"
        assert r["field"] == "status"
        assert r["filters"].get("priority") == "Высокий"

    # ── deadlines ─────────────────────────────────────────────────────────

    def test_deadlines_default(self):
        r = detect_intent("сроки")
        assert r["mode"] == "deadlines"
        assert r["days"] == 14

    def test_deadlines_custom_days(self):
        r = detect_intent("сроки days=7")
        assert r["mode"] == "deadlines"
        assert r["days"] == 7

    def test_deadlines_english(self):
        r = detect_intent("deadlines days=30")
        assert r["mode"] == "deadlines"
        assert r["days"] == 30

    def test_deadlines_russian(self):
        r = detect_intent("дедлайны")
        assert r["mode"] == "deadlines"

    # ── edge cases ────────────────────────────────────────────────────────

    def test_empty_string_returns_mode(self):
        r = detect_intent("")
        assert "mode" in r

    def test_leading_whitespace_stripped(self):
        r = detect_intent("  помощь  ")
        assert r["mode"] == "help"


# ──────────────────────────────────────────────────────────────────────────────
# Regression: multiword customer values
# ──────────────────────────────────────────────────────────────────────────────

class TestMultiwordCustomer:
    """Regression tests: customer values that span multiple words."""

    def test_single_word_customer_natural(self):
        r = detect_intent("задачи заказчик ДЗМ")
        # Queries mentioning "заказчик" correctly route to by_customer mode.
        assert r["mode"] in {"list", "by_customer"}
        assert r["filters"].get("functional_customer") == "ДЗМ"

    def test_two_word_customer_natural(self):
        r = detect_intent("задачи заказчик Городской ИТ-центр")
        assert r["mode"] in {"list", "by_customer"}
        customer = r["filters"].get("functional_customer", "")
        assert "Городской" in customer
        assert "ИТ-центр" in customer

    def test_quoted_double_customer_natural(self):
        r = detect_intent('список заказчик "Комитет цифрового управления"')
        assert r["mode"] in {"list", "by_customer"}
        assert r["filters"].get("functional_customer") == "Комитет цифрового управления"

    def test_quoted_single_customer_natural(self):
        r = detect_intent("список заказчик 'ДГИТ'")
        assert r["mode"] in {"list", "by_customer"}
        assert r["filters"].get("functional_customer") == "ДГИТ"

    def test_customer_kv_multiword_quoted(self):
        r = detect_intent('список functional_customer="Комитет ИТ"')
        assert r["mode"] in {"list", "by_customer"}
        assert r["filters"].get("functional_customer") == "Комитет ИТ"

    def test_customer_via_genitive(self):
        r = detect_intent("задачи заказчика ДЗМ")
        assert r["mode"] in {"list", "by_customer"}
        assert r["filters"].get("functional_customer") == "ДЗМ"


# ──────────────────────────────────────────────────────────────────────────────
# Regression: dotted responsible codes (SEA.1, SAA.2, etc.)
# ──────────────────────────────────────────────────────────────────────────────

class TestDottedResponsibleCodes:
    """Regression tests: responsible codes containing dots like SEA.1."""

    def test_dotted_code_kv(self):
        r = detect_intent("список responsible=SEA.1")
        # Queries with responsible filter correctly route to by_responsible mode.
        assert r["mode"] in {"list", "by_responsible"}
        assert r["filters"].get("responsible_dit") == "SEA.1"

    def test_dotted_code_natural_language(self):
        r = detect_intent("задачи ответственный SEA.1")
        assert r["mode"] in {"list", "by_responsible"}
        assert r["filters"].get("responsible_dit") == "SEA.1"

    def test_dotted_code_natural_responsible_dit(self):
        r = detect_intent("что у ответственного SAA.2")
        filters = r.get("filters", {})
        assert filters.get("responsible_dit") == "SAA.2"

    def test_dotted_code_latin_u_prefix(self):
        """Shorthand 'у CODE' should capture dotted code."""
        r = detect_intent("что у SEA.1")
        filters = r.get("filters", {})
        assert filters.get("responsible_dit") == "SEA.1"

    def test_plain_code_still_works(self):
        r = detect_intent("список responsible=SAA")
        assert r["filters"].get("responsible_dit") == "SAA"

    def test_dotted_with_deep_code(self):
        r = detect_intent("список responsible=SEA.10")
        assert r["filters"].get("responsible_dit") == "SEA.10"


# ──────────────────────────────────────────────────────────────────────────────
# Regression: current_approval_stage end-to-end
# ──────────────────────────────────────────────────────────────────────────────

class TestCurrentApprovalStage:
    """Regression tests: current_approval_stage parsed and present in filters."""

    def test_kv_english_key(self):
        r = detect_intent("список current_approval_stage=ДИТ")
        assert r["mode"] == "list"
        assert r["filters"].get("current_approval_stage") == "ДИТ"

    def test_kv_russian_alias_stadia(self):
        r = detect_intent("список стадия=ДКП")
        assert r["mode"] == "list"
        assert r["filters"].get("current_approval_stage") == "ДКП"

    def test_kv_russian_alias_stadii(self):
        r = detect_intent("список стадии=ДКП")
        assert r["mode"] == "list"
        assert r["filters"].get("current_approval_stage") == "ДКП"

    def test_count_by_stage(self):
        r = detect_intent("количество по стадиям")
        assert r["mode"] == "count"
        assert r["field"] == "current_approval_stage"

    def test_current_approval_stage_in_filter_dict(self):
        """After parsing, current_approval_stage must be inside filters dict."""
        r = detect_intent("список current_approval_stage=ДИТ")
        assert "current_approval_stage" in r.get("filters", {}), (
            "current_approval_stage must be inside 'filters' dict, not top-level"
        )

    def test_stage_combined_with_other_filter(self):
        r = detect_intent("список стадия=ДИТ приоритет=Высокий")
        assert r["filters"].get("current_approval_stage") == "ДИТ"
        assert r["filters"].get("priority") == "Высокий"


class TestQuickActionTemplates:
    """Regression tests for fixed quick-action templates used in Precise Mode UI."""

    def test_quick_action_task_by_id(self):
        r = detect_intent("\u041f\u043e\u043a\u0430\u0436\u0438 \u0437\u0430\u0434\u0430\u0447\u0443 EAIST_SGL-350")
        assert r["mode"] == "task_by_id"
        assert r["issue_id"] == "EAIST_SGL-350"

    def test_quick_action_approvals(self):
        r = detect_intent("\u0427\u0442\u043e \u0436\u0434\u0451\u0442 \u0441\u043e\u0433\u043b\u0430\u0441\u043e\u0432\u0430\u043d\u0438\u044f \u043e\u0442 \u0414\u0418\u0422?")
        assert r["mode"] == "approval_status"
        assert r.get("department") == "dit"

    def test_quick_action_overdue(self):
        r = detect_intent("\u041a\u0430\u043a\u0438\u0435 \u0437\u0430\u0434\u0430\u0447\u0438 \u043f\u0440\u043e\u0441\u0440\u043e\u0447\u0435\u043d\u044b?")
        assert r["mode"] == "overdue"

    def test_quick_action_deadlines(self):
        r = detect_intent("\u041a\u0430\u043a\u0438\u0435 \u0441\u0440\u043e\u043a\u0438 \u0441\u043e\u0433\u043b\u0430\u0441\u043e\u0432\u0430\u043d\u0438\u044f \u0438\u0441\u0442\u0435\u043a\u0430\u044e\u0442 \u0432 \u0431\u043b\u0438\u0436\u0430\u0439\u0448\u0438\u0435 7 \u0434\u043d\u0435\u0439?")
        assert r["mode"] == "deadlines"
        assert r["days"] == 7

    def test_quick_action_stats(self):
        r = detect_intent("\u0421\u0442\u0430\u0442\u0438\u0441\u0442\u0438\u043a\u0430 \u043f\u043e \u0441\u0442\u0430\u0442\u0443\u0441\u0430\u043c")
        assert r["mode"] == "stats"
        assert r["field"] == "status"

    def test_quick_action_by_customer(self):
        r = detect_intent(
            "\u0417\u0430\u0434\u0430\u0447\u0438 \u043f\u043e \u0437\u0430\u043a\u0430\u0437\u0447\u0438\u043a\u0443 "
            "\u0413\u041a\u0423 functional_customer=\"\u0413\u041a\u0423\""
        )
        assert r["mode"] == "by_customer"
        assert r.get("filters", {}).get("functional_customer") == "\u0413\u041a\u0423"

    def test_quick_action_by_responsible(self):
        r = detect_intent("\u0417\u0430\u0434\u0430\u0447\u0438 \u0433\u0434\u0435 \u043e\u0442\u0432\u0435\u0442\u0441\u0442\u0432\u0435\u043d\u043d\u044b\u0439 SAA_1")
        assert r["mode"] == "by_responsible"
        assert r.get("filters", {}).get("responsible_dit") == "SAA_1"
