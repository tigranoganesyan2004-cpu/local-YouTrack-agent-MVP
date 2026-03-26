from src.bootstrap import bootstrap_project
from src.data_prepare import save_prepared_tasks, has_prepared_tasks
from src.vector_store import rebuild_index, has_ready_index
from src.history_store import init_history_db, get_last_history
from src.agent import run_agent
from src.answer_builder import pretty_print_response

def print_menu():
    print("\n" + "=" * 88)
    print("ЛОКАЛЬНЫЙ YOUTRACK AGENT MVP")
    print("=" * 88)

    prepared = has_prepared_tasks()
    index_ready = has_ready_index()

    print(f"Статус: данные={'OK' if prepared else 'НЕТ'} | индекс={'OK' if index_ready else 'НЕТ'}")
    print("-" * 88)

    print("1. Подготовить данные из выгрузки")
    print("2. Пересобрать индекс")
    print("3. Запустить чат")
    print("4. Показать историю")
    print("5. Показать подсказку по командам")
    print("6. Показать статус системы")
    print("0. Выход")
    print("=" * 88)

def print_help():
    print("""
Доступные команды:

  help                                         - показать эту справку

  id EAIST_SGL-350                             - найти задачу по ID
  show EAIST_SGL-350                           - показать полную карточку задачи

  exact <текст>                                - детерминированный поиск без LLM
  similar <текст>                              - найти похожие задачи
  похожие <текст>

  анализ <новая постановка>                    - проанализировать новую задачу через аналоги
  analyze <новая постановка>

  rag <свободный запрос>                       - retrieval + LLM по найденным задачам
  general <свободный запрос>                   - общий поиск с LLM
  общий <свободный запрос>

  list [поле=значение]                         - фильтр по полям
  список [поле=значение]

  пример:
    list status=Согласовано
    list workflow_group=review
    list priority=Высокий

  count by <поле> [поле=значение]              - подсчёт задач
  количество по <поле> [поле=значение]

  пример:
    count by status
    count by workflow_group
    количество по doc_type status=Согласовано

  deadlines [days=N]                           - задачи с истекающими сроками
  сроки [days=N]

  пример:
    deadlines days=14

Можно писать и свободно, например:
  Покажи задачу EAIST_SGL-350
  Найди похожие задачи по уведомлениям
  Какие дедлайны горят в ближайшие 10 дней

Рекомендуемый порядок запуска Stage 1:
  1 -> подготовить данные
  2 -> пересобрать индекс
  3 -> запускать чат
""")

def print_system_status():
    """
    Показывает текущее состояние системы:
    - подготовлены ли данные
    - собран ли индекс
    """
    prepared = has_prepared_tasks()
    index_ready = has_ready_index()

    print("Статус системы:")
    print(f" - Подготовленные данные: {'да' if prepared else 'нет'}")
    print(f" - Индекс поиска: {'да' if index_ready else 'нет'}")


def can_rebuild_index() -> bool:
    """
    Индекс можно собирать только если уже есть prepared tasks.
    """
    return has_prepared_tasks()


def can_run_chat() -> tuple[bool, str]:
    """
    Чат можно запускать только если:
    - prepared data готовы
    - индекс собран
    """
    if not has_prepared_tasks():
        return False, "Сначала выполни шаг 1: подготовь данные из выгрузки."

    if not has_ready_index():
        return False, "Сначала выполни шаг 2: пересобери индекс."

    return True, ""

def run_chat():
    """
    Запускает интерактивный чат только если система готова:
    - данные подготовлены
    - индекс собран
    """
    ready, message = can_run_chat()
    if not ready:
        print(f"\nЧат недоступен: {message}\n")
        return

    print("\nЧат запущен. Для выхода: exit\n")

    while True:
        text = input("Вопрос: ").strip()

        if text.lower() in {"exit", "quit", "выход"}:
            print("Чат завершен.")
            break

        if not text:
            print("Пустой запрос. Попробуй еще раз.\n")
            continue

        if text.lower() == "help":
            print_help()
            continue

        try:
            response = run_agent(text)
            print("\nОтвет агента:")
            print("-" * 88)
            print(pretty_print_response(response))
            print("-" * 88 + "\n")
        except Exception as e:
            print(f"Ошибка: {e}\n")

def show_history():
    rows = get_last_history(limit=10)
    if not rows:
        print("История пока пуста.")
        return
    print("\nПоследние записи истории:\n")
    for row in rows:
        created_at, query_mode, query_text, answer_text, found_issue_ids = row
        print("=" * 88)
        print("Время:", created_at)
        print("Режим:", query_mode)
        print("Вопрос:", query_text)
        print("Найденные задачи:", found_issue_ids)
        print("Ответ:")
        print(answer_text[:800] + ("..." if len(answer_text) > 800 else ""))
        print("=" * 88)


def main():
    bootstrap_project()
    init_history_db()

    while True:
        print_menu()
        choice = input("Выбери действие: ").strip()

        try:
            if choice == "1":
                tasks, report = save_prepared_tasks()
                print(f"Готово. Подготовлено задач: {len(tasks)}")
                print("Краткий отчет:")
                for line in report:
                    print(" -", line)

            elif choice == "2":
                if not can_rebuild_index():
                    print("Нельзя пересобрать индекс: сначала выполни шаг 1 (подготовка данных).")
                    continue

                report = rebuild_index()
                print("Индекс пересобран.")
                print("Краткий отчет по индексации:")
                print(f" - Всего задач: {report['tasks_total']}")
                print(f" - Успешно проиндексировано: {report['indexed_total']}")
                print(f" - Пропущено пустых semantic_text: {report['skipped_empty_semantic_text']}")
                print(f" - Пропущено из-за плохих векторов: {report['skipped_bad_vector']}")
                print(f" - Ошибок эмбеддинга: {report['embedding_errors']}")
                print(f" - Размерность embedding: {report['embedding_dim']}")

            elif choice == "3":
                run_chat()

            elif choice == "4":
                show_history()

            elif choice == "5":
                print_help()

            elif choice == "6":
                print_system_status()

            elif choice == "0":
                print("Выход.")
                break

            else:
                print("Неизвестная команда.")

        except Exception as e:
            # Одна ошибка в меню не должна завершать всю программу.
            print(f"Ошибка выполнения действия: {e}")

if __name__ == "__main__":
    main()
