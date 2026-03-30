COLUMN_MAP = {
    "ID задачи": "issue_id",
    "Проект": "project",
    "Теги": "tags",
    "Заголовок": "summary",
    "Заявитель": "reporter",
    "Создана": "created_at",
    "Обновлена": "updated_at",
    "Завершенная": "resolved_at",
    "Статус": "status",
    "Приоритет": "priority",
    "Функциональный заказчик": "functional_customer",
    "Ответственный (ДИТ)": "responsible_dit",
    "Согласование с ДИТ": "approval_dit",
    "Согласование с ГКУ": "approval_gku",
    "Согласование с ДКП": "approval_dkp",
    "Согласование с ДЭПиР": "approval_dep",
    "Тип документа": "doc_type",
    "Действия": "action",
    "Решение ДИТ": "decision_dit",
    "Решение ГКУ": "decision_gku",
    "Решение ДКП": "decision_dkp",
    "Решение ДЭПиР": "decision_dep",
    "StartDIT": "start_dit",
    "StartGKU": "start_gku",
    "StartDKP": "start_dkp",
    "StartDEP": "start_dep",
    "ShowAll": "show_all",
    "ShowDIT": "show_dit",
    "ShowGKU": "show_gku",
    "ShowDKP": "show_dkp",
    "ShowDEP": "show_dep",
    "Changed": "changed",
    "StatesCode": "states_code",
    "Инициатор согласования": "approval_initiator",
    "Срок согласования (ДИТ)": "deadline_dit",
    "Срок согласования (ДКП)": "deadline_dkp",
    "Срок согласования (ДЭПиР)": "deadline_dep",
    "Срок согласования (ГКУ)": "deadline_gku",
    "Срок устранения замечаний": "deadline_fix_comments",
    "Первоначальный срок рассмотрения": "initial_review_deadline",
    "Внутренний согласующий от ДЭПиР": "internal_dep_approver",
    "Согласование с \"Ценовыми справочниками, ПЦП\"": "approval_price_refs",
    "Согласование с \"АРМ Эксперта\"": "approval_arm_expert",
    "Согласование со \"Стандартизацией\"": "approval_standardization",
    "Описание": "description",
    "Голоса": "votes",
}

REQUIRED_SOURCE_COLUMNS = [
    "ID задачи",
    "Заголовок",
    "Статус",
    "Тип документа",
]

REQUIRED_TARGET_FIELDS = [
    "issue_id",
    "summary",
    "status",
    "doc_type",
]

CORE_FIELDS = [
    "issue_id",
    "project",
    "summary",
    "status",
    "priority",
    "doc_type",
    "functional_customer",
    "responsible_dit",
    "approval_initiator",
    "description",
]

DATE_TARGET_FIELDS = {
    "created_at",
    "updated_at",
    "resolved_at",
    "start_dit",
    "start_gku",
    "start_dkp",
    "start_dep",
    "deadline_dit",
    "deadline_dkp",
    "deadline_dep",
    "deadline_gku",
    "deadline_fix_comments",
    "initial_review_deadline",
}

DEDUP_SCORE_FIELDS = [
    "summary",
    "description",
    "status",
    "priority",
    "doc_type",
    "functional_customer",
    "responsible_dit",
    "approval_initiator",
    "created_at",
    "updated_at",
    "resolved_at",
    "deadline_dit",
    "deadline_gku",
    "deadline_dkp",
    "deadline_dep",
    "deadline_fix_comments",
    "initial_review_deadline",
    "approval_dit",
    "approval_gku",
    "approval_dkp",
    "approval_dep",
    "decision_dit",
    "decision_gku",
    "decision_dkp",
    "decision_dep",
    "states_code",
]

APPROVAL_TARGET_FIELDS = [
    "approval_dit",
    "approval_gku",
    "approval_dkp",
    "approval_dep",
    "approval_price_refs",
    "approval_arm_expert",
    "approval_standardization",
]

DECISION_TARGET_FIELDS = [
    "decision_dit",
    "decision_gku",
    "decision_dkp",
    "decision_dep",
]

DEADLINE_TARGET_FIELDS = [
    "deadline_dit",
    "deadline_gku",
    "deadline_dkp",
    "deadline_dep",
    "deadline_fix_comments",
    "initial_review_deadline",
]

APPROVAL_LABELS = {
    "approval_dit": "ДИТ",
    "approval_gku": "ГКУ",
    "approval_dkp": "ДКП",
    "approval_dep": "ДЭПиР",
    "approval_price_refs": "Ценовые справочники, ПЦП",
    "approval_arm_expert": "АРМ Эксперта",
    "approval_standardization": "Стандартизация",
}

DEADLINE_LABELS = {
    "deadline_dit": "Срок согласования ДИТ",
    "deadline_gku": "Срок согласования ГКУ",
    "deadline_dkp": "Срок согласования ДКП",
    "deadline_dep": "Срок согласования ДЭПиР",
    "deadline_fix_comments": "Срок устранения замечаний",
    "initial_review_deadline": "Первоначальный срок рассмотрения",
}

EMPTY_PLACEHOLDERS_BY_TARGET = {
    "action": {"Выбрать действие"},
    "doc_type": {"Не выбран"},
    "decision_dit": {"Нет решения", "Нет: решение дит"},
    "decision_gku": {"Нет решения", "Нет: решение гку"},
    "decision_dkp": {"Нет решения", "Нет: решение дкп"},
    "decision_dep": {"Нет решения", "Нет: решение дэпир"},
    "show_all": {"Нет: showall"},
    "show_dit": {"Нет: showdit"},
    "show_gku": {"Нет: showgku"},
    "show_dkp": {"Нет: showdkp"},
    "show_dep": {"Нет: showdep"},
}

SEMANTIC_BASE_FIELDS = [
    "summary",
    "description",
    "action",
]

SEMANTIC_APPROVAL_FIELDS = [
    "approval_dit",
    "approval_gku",
    "approval_dkp",
    "approval_dep",
]

SEMANTIC_DECISION_FIELDS = [
    "decision_dit",
    "decision_gku",
    "decision_dkp",
    "decision_dep",
]