"""
Генератор тестового JSON для агента-аналитика Agile команды разработки.
Структура: 1 тимлид + 5 разработчиков, 6 спринтов (2-недельных),
иерархические метрики с разбивкой по 10 компонентам через element.

Метрики 1-го уровня (9):
  - Velocity (с детьми)
  - РАНГ Velocity
  - Cycle Time (с детьми, включая Влияние компонентов)
  - РАНГ Cycle Time
  - Code Quality Index (с детьми)
  - РАНГ Code Quality
  - Bug Rate (с детьми)
  - Sprint Commitment Accuracy
  - PR Review Engagement (с детьми)
"""
import json
import random
from datetime import date, timedelta

random.seed(42)

# ---------- Справочники ----------
COMPONENTS = [
    "API Gateway",
    "Auth Service",
    "User Service",
    "Payment Service",
    "Notification Service",
    "Frontend Web",
    "Mobile App",
    "Admin Panel",
    "Analytics Service",
    "Data Pipeline",
]

# 6 спринтов (2-недельных), даты окончания
SPRINTS = [(date(2026, 3, 1) + timedelta(weeks=2 * i)).isoformat() for i in range(6)]

DESC = {
    "Velocity": (
        "Среднее количество доставленных story points за спринт. "
        "Сумма очков задач, переведённых в Done за спринт."
    ),
    "РАНГ Velocity": "Место разработчика по показателю Velocity в команде.",
    "Cycle Time": (
        "Время от начала работы над задачей (In Progress) до её закрытия (Done) в днях. "
        "Среднее по всем задачам разработчика за спринт."
    ),
    "РАНГ Cycle Time": "Место разработчика по показателю Cycle Time в команде.",
    "Code Quality Index": (
        "Композитный показатель качества кода: средневзвешенная оценка из покрытия "
        "тестами, процента одобренных PR, качества код-ревью и прохождения линтеров. "
        "Шкала от 0 до 100."
    ),
    "РАНГ Code Quality": "Место разработчика по показателю Code Quality Index в команде.",
    "Bug Rate": (
        "Количество багов, заведённых на код разработчика в течение спринта "
        "или сразу после релиза."
    ),
    "Sprint Commitment Accuracy": (
        "Точность планирования: отношение фактически доставленных story points "
        "к запланированным на спринт, в процентах."
    ),
    "PR Review Engagement": (
        "Композитная метрика вовлечённости в код-ревью. Учитывает количество ревью, "
        "содержательность комментариев и скорость первого ответа."
    ),
    # Дети Velocity
    "Story Points Delivered": "Сумма story points задач, закрытых в Done за спринт.",
    "Tasks Closed": "Количество задач, закрытых в Done за спринт.",
    "PRs Merged": "Количество pull request'ов, влитых в основные ветки за спринт.",
    # Дети Cycle Time
    "In Progress Time": (
        "Среднее время задачи в статусе In Progress в днях."
    ),
    "Code Review Wait Time": (
        "Среднее время ожидания PR на ревью — от готовности к ревью до первого "
        "одобрения или возврата на доработку."
    ),
    "QA Time": (
        "Среднее время прохождения задачи через тестирование — от Ready for QA до Done."
    ),
    "Влияние компонентов на Cycle Time": (
        "Вклад среднего времени работы разработчика по компоненту в среднее время "
        "работы всей команды по тому же компоненту в днях. Может быть отрицательной."
    ),
    # Дети Code Quality Index
    "Test Coverage": (
        "Процент покрытия кода unit-тестами по коммитам разработчика за спринт."
    ),
    "PR Approval Rate": (
        "Доля PR разработчика, одобренных без существенных правок, от общего числа "
        "поданных на ревью."
    ),
    "Code Review Quality": (
        "Оценка качества ревью на основе обнаруженных дефектов, глубины комментариев "
        "и точности замечаний."
    ),
    "Linter Pass Rate": (
        "Процент коммитов, прошедших автоматические проверки качества кода (линтеры, "
        "статический анализ) с первого раза."
    ),
    # Дети Bug Rate
    "Critical Bugs": (
        "Количество багов уровней Critical и Blocker, возникших по коду разработчика "
        "за спринт."
    ),
    "Minor Bugs": (
        "Количество багов уровней Minor и Trivial, возникших по коду разработчика "
        "за спринт."
    ),
    # Дети PR Review Engagement
    "PRs Reviewed": "Количество чужих PR, отревьюированных разработчиком за спринт.",
    "Substantive Comments": (
        "Количество содержательных комментариев в чужих PR "
        "(исключая 'LGTM' и косметические)."
    ),
    "Time to First Review": (
        "Среднее время от назначения разработчика ревьюером до его первого "
        "комментария или одобрения, в часах."
    ),
}

MID = {
    "Velocity": "70001001",
    "РАНГ Velocity": "70001002",
    "Cycle Time": "70001003",
    "РАНГ Cycle Time": "70001004",
    "Code Quality Index": "70001005",
    "РАНГ Code Quality": "70001006",
    "Bug Rate": "70001007",
    "Sprint Commitment Accuracy": "70001008",
    "PR Review Engagement": "70001009",
    "Story Points Delivered": "70001010",
    "Tasks Closed": "70001011",
    "PRs Merged": "70001012",
    "In Progress Time": "70001013",
    "Code Review Wait Time": "70001014",
    "QA Time": "70001015",
    "Влияние компонентов на Cycle Time": "70001016",
    "Test Coverage": "70001017",
    "PR Approval Rate": "70001018",
    "Code Review Quality": "70001019",
    "Linter Pass Rate": "70001020",
    "Critical Bugs": "70001021",
    "Minor Bugs": "70001022",
    "PRs Reviewed": "70001023",
    "Substantive Comments": "70001024",
    "Time to First Review": "70001025",
}

METRIC_TYPES = {
    "Velocity": ("прямая", "у.е."),
    "РАНГ Velocity": ("обратная", "место"),
    "Cycle Time": ("обратная", "день"),
    "РАНГ Cycle Time": ("обратная", "место"),
    "Code Quality Index": ("прямая", "%"),
    "РАНГ Code Quality": ("обратная", "место"),
    "Bug Rate": ("обратная", "штук"),
    "Sprint Commitment Accuracy": ("прямая", "%"),
    "PR Review Engagement": ("прямая", "у.е."),
    "Story Points Delivered": ("прямая", "у.е."),
    "Tasks Closed": ("прямая", "штук"),
    "PRs Merged": ("прямая", "штук"),
    "In Progress Time": ("обратная", "день"),
    "Code Review Wait Time": ("обратная", "день"),
    "QA Time": ("обратная", "день"),
    "Влияние компонентов на Cycle Time": ("обратная", "день"),
    "Test Coverage": ("прямая", "%"),
    "PR Approval Rate": ("прямая", "%"),
    "Code Review Quality": ("прямая", "%"),
    "Linter Pass Rate": ("прямая", "%"),
    "Critical Bugs": ("обратная", "штук"),
    "Minor Bugs": ("обратная", "штук"),
    "PRs Reviewed": ("прямая", "штук"),
    "Substantive Comments": ("прямая", "штук"),
    "Time to First Review": ("обратная", "час"),
}


def m(name, fact, plan, benchmark, element=None, influent=None, children=None, sprint=None):
    """Создаёт один объект метрики."""
    mtype, measure = METRIC_TYPES[name]
    obj = {
        "id": MID[name],
        "metric_name": name,
        "metric_description": DESC[name],
        "metric_type": mtype,
        "measure_type": measure,
        "date": sprint,
        "calc_period": "спринт",
        "fact": fact,
        "plan": plan,
        "benchmark": benchmark,
    }
    if influent is not None:
        obj["influent_percent"] = influent
    obj["element"] = element
    obj["child_metrics"] = children if children else []
    return obj


# ---------- ФИО ----------
FN_M = ["Дмитрий", "Артём", "Илья", "Кирилл", "Михаил", "Никита", "Матвей",
        "Роман", "Егор", "Арсений", "Александр", "Максим", "Сергей"]
FN_F = ["Анна", "Мария", "Екатерина", "Татьяна", "Юлия", "Анастасия",
        "Дарья", "Полина", "Алиса", "Виктория"]
LN_M = ["Соколов", "Лебедев", "Козлов", "Новиков", "Морозов", "Волков",
        "Соловьёв", "Зайцев", "Павлов", "Орлов", "Беляев", "Виноградов"]
MN_M = ["Александрович", "Дмитриевич", "Максимович", "Сергеевич", "Андреевич",
        "Алексеевич", "Артёмович", "Михайлович", "Романович", "Викторович"]


def random_fio(rng):
    if rng.random() < 0.7:
        return f"{rng.choice(LN_M)} {rng.choice(FN_M)} {rng.choice(MN_M)}"
    ln = rng.choice(LN_M) + "а"
    mn_m = rng.choice(MN_M)
    mn = mn_m[:-2] + "на" if mn_m.endswith("ич") else mn_m + "на"
    return f"{ln} {rng.choice(FN_F)} {mn}"


# ---------- Профили (тимлид и разработчики по грейдам) ----------
def get_profile_scaling(post):
    """Поправочные коэффициенты для значений метрик в зависимости от роли."""
    if post == "Тимлид":
        # Лид меньше кодит, больше ревьюит
        return {
            "velocity_scale": 0.5,        # меньше SP
            "review_scale": 1.8,          # больше ревью
            "quality_bonus": 5,           # стабильнее по качеству
            "bug_scale": 0.5,             # меньше багов
            "cycle_scale": 0.9,
        }
    elif post == "Senior разработчик":
        return {
            "velocity_scale": 1.15,
            "review_scale": 1.4,
            "quality_bonus": 8,
            "bug_scale": 0.6,
            "cycle_scale": 0.85,
        }
    elif post == "Middle разработчик":
        return {
            "velocity_scale": 1.0,
            "review_scale": 1.0,
            "quality_bonus": 0,
            "bug_scale": 1.0,
            "cycle_scale": 1.0,
        }
    elif post == "Junior разработчик":
        return {
            "velocity_scale": 0.65,
            "review_scale": 0.5,
            "quality_bonus": -12,
            "bug_scale": 1.6,
            "cycle_scale": 1.4,
        }
    return {"velocity_scale": 1.0, "review_scale": 1.0, "quality_bonus": 0,
            "bug_scale": 1.0, "cycle_scale": 1.0}


# ---------- Сборка метрик за один спринт ----------
def build_sprint_metrics(sprint, rng, post):
    sc = get_profile_scaling(post)
    is_lead = post == "Тимлид"

    # ----- Базовые факты на уровне человеко-спринта -----
    sp_delivered = round(rng.uniform(8, 22) * sc["velocity_scale"], 1)
    tasks_closed = max(1, int(rng.uniform(3, 13) * sc["velocity_scale"]))
    prs_merged = max(1, int(rng.uniform(5, 20) * sc["velocity_scale"]))
    # Velocity = взвешенная сумма
    velocity = round(sp_delivered, 1)

    in_progress_t = round(rng.uniform(0.7, 3.0) * sc["cycle_scale"], 2)
    cr_wait_t = round(rng.uniform(0.3, 2.0) * sc["cycle_scale"], 2)
    qa_t = round(rng.uniform(0.3, 1.6) * sc["cycle_scale"], 2)
    cycle_time = round(in_progress_t + cr_wait_t + qa_t, 2)

    test_cov = max(20.0, min(98.0, round(rng.uniform(55, 92) + sc["quality_bonus"], 1)))
    pr_appr = max(40.0, min(100.0, round(rng.uniform(70, 96) + sc["quality_bonus"] * 0.5, 1)))
    cr_quality = max(30.0, min(100.0, round(rng.uniform(60, 90) + sc["quality_bonus"], 1)))
    linter_pass = max(60.0, min(100.0, round(rng.uniform(82, 99) + sc["quality_bonus"] * 0.3, 1)))
    code_quality = round(
        test_cov * 0.30 + pr_appr * 0.20 + cr_quality * 0.25 + linter_pass * 0.25, 1
    )

    critical_bugs = max(0, int(round(rng.uniform(0, 2.5) * sc["bug_scale"])))
    minor_bugs = max(0, int(round(rng.uniform(0, 5) * sc["bug_scale"])))
    bug_rate = critical_bugs + minor_bugs

    sprint_commit = round(rng.uniform(72, 108), 1)

    prs_reviewed = int(rng.uniform(4, 18) * sc["review_scale"])
    sub_comments = int(rng.uniform(8, 40) * sc["review_scale"])
    time_first_review = round(rng.uniform(0.8, 10) / max(sc["review_scale"], 0.5), 2)
    # PR Review Engagement — условное скоринговое число
    pr_engagement = round(
        prs_reviewed * 1.0 + sub_comments * 0.3 - time_first_review * 0.2, 1
    )

    # Ранги (1-5 — среди 5 разработчиков; у лида null)
    velocity_rank = None if is_lead else rng.randint(1, 5)
    cycle_rank = None if is_lead else rng.randint(1, 5)
    quality_rank = None if is_lead else rng.randint(1, 5)

    # ----- Дети Velocity (с разбивкой по компонентам) -----
    velocity_children = []
    velocity_children.append(
        m("Story Points Delivered", sp_delivered, 14.0, 12.5,
          element=None, influent=70, sprint=sprint)
    )
    for c in COMPONENTS:
        velocity_children.append(
            m("Story Points Delivered",
              round(rng.uniform(0, 5) * sc["velocity_scale"], 1),
              None, round(rng.uniform(1.0, 2.5), 1),
              element=c, influent=70, sprint=sprint)
        )
    velocity_children.append(
        m("Tasks Closed", tasks_closed, 8, 7,
          element=None, influent=20, sprint=sprint)
    )
    for c in COMPONENTS:
        velocity_children.append(
            m("Tasks Closed", max(0, int(rng.uniform(0, 3) * sc["velocity_scale"])),
              None, round(rng.uniform(0.5, 1.5), 1),
              element=c, influent=20, sprint=sprint)
        )
    velocity_children.append(
        m("PRs Merged", prs_merged, 12, 10,
          element=None, influent=10, sprint=sprint)
    )
    for c in COMPONENTS:
        velocity_children.append(
            m("PRs Merged", max(0, int(rng.uniform(0, 4) * sc["velocity_scale"])),
              None, round(rng.uniform(0.5, 2), 1),
              element=c, influent=10, sprint=sprint)
        )

    # ----- Дети Cycle Time -----
    cycle_children = []
    cycle_children.append(
        m("In Progress Time", in_progress_t, 2.0, 2.2,
          element=None, influent=55, sprint=sprint)
    )
    for c in COMPONENTS:
        cycle_children.append(
            m("In Progress Time",
              round(rng.uniform(0.5, 4) * sc["cycle_scale"], 2),
              None, round(rng.uniform(1.8, 2.8), 2),
              element=c, influent=55, sprint=sprint)
        )
    cycle_children.append(
        m("Code Review Wait Time", cr_wait_t, 1.0, 1.3,
          element=None, influent=25, sprint=sprint)
    )
    for c in COMPONENTS:
        cycle_children.append(
            m("Code Review Wait Time",
              round(rng.uniform(0.2, 2.5) * sc["cycle_scale"], 2),
              None, round(rng.uniform(0.8, 1.6), 2),
              element=c, influent=25, sprint=sprint)
        )
    cycle_children.append(
        m("QA Time", qa_t, 0.8, 1.0,
          element=None, influent=20, sprint=sprint)
    )
    for c in COMPONENTS:
        cycle_children.append(
            m("QA Time",
              round(rng.uniform(0.2, 1.8) * sc["cycle_scale"], 2),
              None, round(rng.uniform(0.6, 1.2), 2),
              element=c, influent=20, sprint=sprint)
        )
    # «Влияние компонентов на Cycle Time» — только по компонентам, без null
    for c in COMPONENTS:
        cycle_children.append(
            m("Влияние компонентов на Cycle Time",
              round(rng.uniform(-1.5, 1.5) * sc["cycle_scale"], 2),
              0.0, 0.0,
              element=c, sprint=sprint)
        )

    # ----- Дети Code Quality Index -----
    quality_children = []
    quality_children.append(
        m("Test Coverage", test_cov, 80.0, 75.0,
          element=None, influent=30, sprint=sprint)
    )
    for c in COMPONENTS:
        quality_children.append(
            m("Test Coverage",
              max(20.0, min(99.0, round(rng.uniform(45, 95) + sc["quality_bonus"], 1))),
              80.0, round(rng.uniform(65, 85), 1),
              element=c, influent=30, sprint=sprint)
        )
    quality_children.append(
        m("PR Approval Rate", pr_appr, 90.0, 85.0,
          element=None, influent=20, sprint=sprint)
    )
    for c in COMPONENTS:
        quality_children.append(
            m("PR Approval Rate",
              max(40.0, min(100.0, round(rng.uniform(70, 98) + sc["quality_bonus"] * 0.5, 1))),
              90.0, round(rng.uniform(78, 92), 1),
              element=c, influent=20, sprint=sprint)
        )
    quality_children.append(
        m("Code Review Quality", cr_quality, 80.0, 75.0,
          element=None, influent=25, sprint=sprint)
    )
    for c in COMPONENTS:
        quality_children.append(
            m("Code Review Quality",
              max(30.0, min(100.0, round(rng.uniform(55, 90) + sc["quality_bonus"], 1))),
              80.0, round(rng.uniform(65, 85), 1),
              element=c, influent=25, sprint=sprint)
        )
    quality_children.append(
        m("Linter Pass Rate", linter_pass, 95.0, 90.0,
          element=None, influent=25, sprint=sprint)
    )
    for c in COMPONENTS:
        quality_children.append(
            m("Linter Pass Rate",
              max(60.0, min(100.0, round(rng.uniform(80, 99) + sc["quality_bonus"] * 0.3, 1))),
              95.0, round(rng.uniform(85, 95), 1),
              element=c, influent=25, sprint=sprint)
        )

    # ----- Дети Bug Rate -----
    bug_children = []
    bug_children.append(
        m("Critical Bugs", critical_bugs, 0, 1,
          element=None, influent=70, sprint=sprint)
    )
    for c in COMPONENTS:
        bug_children.append(
            m("Critical Bugs", max(0, int(round(rng.uniform(0, 1.5) * sc["bug_scale"]))),
              0, round(rng.uniform(0.1, 0.5), 1),
              element=c, influent=70, sprint=sprint)
        )
    bug_children.append(
        m("Minor Bugs", minor_bugs, 2, 3,
          element=None, influent=30, sprint=sprint)
    )
    for c in COMPONENTS:
        bug_children.append(
            m("Minor Bugs", max(0, int(round(rng.uniform(0, 3) * sc["bug_scale"]))),
              None, round(rng.uniform(0.3, 1.2), 1),
              element=c, influent=30, sprint=sprint)
        )

    # ----- Дети PR Review Engagement (без разбивки по компонентам) -----
    review_children = [
        m("PRs Reviewed", prs_reviewed, 10, 9,
          element=None, influent=40, sprint=sprint),
        m("Substantive Comments", sub_comments, 20, 18,
          element=None, influent=35, sprint=sprint),
        m("Time to First Review", time_first_review, 4.0, 5.0,
          element=None, influent=25, sprint=sprint),
    ]

    # ----- Сборка верхнего уровня -----
    metrics = [
        m("Velocity", velocity, 14.0, 12.5,
          element=None, children=velocity_children, sprint=sprint),
        m("РАНГ Velocity", velocity_rank, 3, 3, element=None, sprint=sprint),
        m("Cycle Time", cycle_time, 4.0, 4.5,
          element=None, children=cycle_children, sprint=sprint),
        m("РАНГ Cycle Time", cycle_rank, 3, 3, element=None, sprint=sprint),
        m("Code Quality Index", code_quality, 82.0, 78.0,
          element=None, children=quality_children, sprint=sprint),
        m("РАНГ Code Quality", quality_rank, 3, 3, element=None, sprint=sprint),
        m("Bug Rate", bug_rate, 2, 4,
          element=None, children=bug_children, sprint=sprint),
        m("Sprint Commitment Accuracy", sprint_commit, 95.0, 88.0,
          element=None, sprint=sprint),
        m("PR Review Engagement", pr_engagement, 18.0, 15.0,
          element=None, children=review_children, sprint=sprint),
    ]
    return metrics


def build_person(tabnum, fio, post, depart, seed):
    rng = random.Random(seed)
    person = {
        "tabnum": tabnum,
        "fio": fio,
        "post": post,
        "depart": depart,
        "metrics": [],
    }
    for s in SPRINTS:
        person["metrics"].extend(build_sprint_metrics(s, rng, post))
    return person


def main():
    depart = "Команда Платформа"

    # Тимлид
    manager = build_person(
        tabnum=2330001,
        fio="Соколов Дмитрий Александрович",
        post="Тимлид",
        depart=depart,
        seed=1001,
    )

    # 5 разработчиков с разными грейдами
    team = [
        ("Senior разработчик", 2330002, 2002),
        ("Middle разработчик", 2330003, 2003),
        ("Middle разработчик", 2330004, 2004),
        ("Middle разработчик", 2330005, 2005),
        ("Junior разработчик", 2330006, 2006),
    ]

    rng_name = random.Random(13)
    employees = []
    for post, tabnum, seed in team:
        emp = build_person(
            tabnum=tabnum,
            fio=random_fio(rng_name),
            post=post,
            depart=depart,
            seed=seed,
        )
        employees.append(emp)

    result = {"me": manager, "employees": employees}

    out_path = "/mnt/user-data/outputs/test_metrics_agile.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # Статистика
    def count_metrics(metrics_list):
        c = 0
        for mm in metrics_list:
            c += 1
            c += count_metrics(mm.get("child_metrics", []))
        return c

    total = count_metrics(manager["metrics"])
    for e in employees:
        total += count_metrics(e["metrics"])

    import os
    size_mb = os.path.getsize(out_path) / 1024 / 1024

    print(f"Готово: {out_path}")
    print(f"Размер: {size_mb:.2f} МБ")
    print(f"Команда: 1 тимлид + {len(employees)} разработчика(ов)")
    print(f"Спринтов: {len(SPRINTS)} ({SPRINTS[0]} … {SPRINTS[-1]})")
    print(f"Компонентов: {len(COMPONENTS)}")
    print(f"Метрик 1-го уровня на человеко-спринт: 9")
    print(f"Всего узлов метрик в дереве: {total}")


if __name__ == "__main__":
    main()
