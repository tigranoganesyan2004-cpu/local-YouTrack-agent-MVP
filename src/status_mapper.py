from src.utils import safe_str


# Базовая карта сырых статусов YouTrack -> внутренняя рабочая группа.
# Эти группы выбраны специально под ваш контур согласования:
# approved                - согласовано / завершено успешно
# review                  - находится на согласовании / рассмотрении
# rework                  - возвращено с замечаниями / требует доработки
# rejected_or_cancelled   - отказано или процесс отменен
# not_started             - согласование еще не запущено
# other                   - все, что пока не покрыто правилами
STATUS_TO_WORKFLOW = {
    "Согласовано": "approved",
    "Согласовано с замеч.": "approved",
    "Направлено на согл.": "review",
    "Выданы замечания": "rework",
    "Отказано": "rejected_or_cancelled",
    "Согл. отменено": "rejected_or_cancelled",
    "Согл. не инициировано": "not_started",
}


def normalize_raw_status(raw_status: str) -> str:
    """
    Возвращает очищенный сырой статус без логического преобразования.

    Это нужно, чтобы:
    - хранить исходное значение как пришло из выгрузки;
    - сравнивать статусы без лишних пробелов;
    - использовать raw_status дальше в диагностике и отчетах.
    """
    return safe_str(raw_status).strip()


def normalize_status(raw_status: str) -> str:
    """
    Возвращает внутреннюю рабочую группу статуса.

    Пока функция называется normalize_status, чтобы не ломать
    существующий код Stage 1, где уже используется status_group.
    По смыслу это именно workflow_group.
    """
    status = normalize_raw_status(raw_status)
    return STATUS_TO_WORKFLOW.get(status, "other")


def is_final_status_group(status_group: str) -> bool:
    """
    Финальные группы процесса:
    - approved
    - rejected_or_cancelled

    Это пригодится дальше на Stage 2:
    - для аналитики завершенных процессов;
    - для синка / отчетов;
    - для фильтрации "что уже завершено".
    """
    return safe_str(status_group) in {"approved", "rejected_or_cancelled"}