"""
Генератор тестового JSON для агента-аналитика колл-центра.
Структура: 1 руководитель + 25 операторов, 6 недельных периодов,
иерархические метрики с разбивкой по 11 продуктам.
"""
import json
import random
from datetime import date, timedelta

random.seed(42)

# ---------- Справочники ----------
PRODUCTS = [
    "Банковские счета",
    "Бизнес-карта",
    "Другие банковские продукты",
    "Консультация не состоялась",
    "Кредитование",
    "Ликвидность и обязательства",
    "Небанковские продукты",
    "Переводы в рублях и валюте",
    "БанкБизнес",
    "Финмониторинг",
    "Эквайринг",
]

# 6 недельных периодов (понедельники)
WEEKS = [(date(2026, 4, 6) + timedelta(weeks=i)).isoformat() for i in range(6)]

# Описания метрик
DESC = {
    "Производительность": (
        "Основная метрика. Это сумма условных продуктов (УП), деленная на продуктивное время "
        "и нормированная на 8-часовой день. "
        "Производительность = (Кол-во звонков УП) / (Часы САП - время в Avail - время в непродуктивных режимах) * 8"
    ),
    "РАНГ Производительность": "Место сотрудника по выполнению показателя Производительность",
    "Доля переводов": (
        "Доля переведенных вызовов. Переведенные звонки весят на 50% меньше при расчёте условных продуктов."
    ),
    "AHT": (
        "Среднее время обслуживания клиента. Считается как отношение общего времени обслуживания "
        "клиентов в секундах к количеству принятых вызовов."
    ),
    "Adherence": (
        "Соблюдение расписания сотрудником (дисциплина). Если сотрудник не принимает звонки, "
        "когда должен, то теряет потенциал в количестве вызовов."
    ),
    "РАНГ AHT": "Место сотрудника по выполнению показателя AHT",
    "РАНГ Доля переводов": "Место сотрудника по выполнению показателя Доля переводов",
    "Влияние тематик на Talk&Hold": (
        "Вклад среднего времени активности сотрудника по продукту в среднее время активности всех "
        "сотрудников по продукту в секундах."
    ),
    "RING TIME": "Время поднятия трубки оператором. Среднее значение по всем звонкам.",
    "ACW TIME": (
        "Поствызывная обработка (post call) после разъединения с клиентом. Продолжается, "
        "пока оператор не поменяет статус на 'Готов', либо до 40 секунд (автозавершение)."
    ),
    "AUX PEREZVON TIME": (
        "Режим, в котором оператор совершает исходящий звонок клиенту. "
        "Производится в случае технического прерывания звонка."
    ),
    "ACD TIME": "Talk time - длительность диалога без удержаний и мьютов. Среднее по всем принятым звонкам.",
    "HOLD TIME": "Время удержания ('играет музыка'). Среднее. Мьют в эту метрику не входит.",
}

# Идентификаторы метрик
MID = {
    "Производительность": "90022908",
    "РАНГ Производительность": "90022909",
    "Доля переводов": "90022910",
    "AHT": "90022911",
    "Adherence": "90022912",
    "РАНГ AHT": "90022913",
    "РАНГ Доля переводов": "90022914",
    "Влияние тематик на Talk&Hold": "90022915",
    "RING TIME": "90022916",
    "ACW TIME": "90022917",
    "AUX PEREZVON TIME": "90022918",
    "ACD TIME": "90022919",
    "HOLD TIME": "90022920",
}

# ---------- Генератор ФИО ----------
FN_M = ["Александр", "Дмитрий", "Максим", "Сергей", "Андрей", "Алексей", "Артём",
        "Илья", "Кирилл", "Михаил", "Никита", "Матвей", "Роман", "Егор", "Арсений"]
FN_F = ["Анна", "Мария", "Елена", "Ольга", "Наталья", "Екатерина", "Татьяна",
        "Ирина", "Юлия", "Анастасия", "Светлана", "Дарья", "Виктория", "Полина", "Алиса"]
LN_M = ["Иванов", "Смирнов", "Кузнецов", "Попов", "Соколов", "Лебедев", "Козлов",
        "Новиков", "Морозов", "Петров", "Волков", "Соловьёв", "Васильев", "Зайцев", "Павлов"]
MN_M = ["Александрович", "Дмитриевич", "Максимович", "Сергеевич", "Андреевич",
        "Алексеевич", "Артёмович", "Ильич", "Кириллович", "Михайлович", "Никитич",
        "Романович", "Егорович", "Викторович", "Юрьевич"]


def random_fio(rng):
    if rng.random() < 0.55:
        return f"{rng.choice(LN_M)} {rng.choice(FN_M)} {rng.choice(MN_M)}"
    else:
        ln = rng.choice(LN_M) + "а"
        # женское отчество из мужского
        mn_m = rng.choice(MN_M)
        if mn_m.endswith("ич"):
            mn = mn_m[:-2] + "на"
        elif mn_m.endswith("ьевич"):
            mn = mn_m.replace("ьевич", "ьевна")
        else:
            mn = mn_m + "на"
        return f"{ln} {rng.choice(FN_F)} {mn}"


# ---------- Конструктор метрики ----------
def m(name, fact, plan, benchmark, element=None, influent=None, children=None, week=None):
    """Создаёт один объект метрики."""
    metric_types = {
        "Производительность": ("прямая", "у.е."),
        "РАНГ Производительность": ("обратная", "место"),
        "Доля переводов": ("обратная", "%"),
        "AHT": ("обратная", "секунда"),
        "Adherence": ("прямая", "%"),
        "РАНГ AHT": ("обратная", "место"),
        "РАНГ Доля переводов": ("обратная", "место"),
        "Влияние тематик на Talk&Hold": ("обратная", "секунда"),
        "RING TIME": ("обратная", "секунда"),
        "ACW TIME": ("обратная", "секунда"),
        "AUX PEREZVON TIME": ("обратная", "секунда"),
        "ACD TIME": ("обратная", "секунда"),
        "HOLD TIME": ("обратная", "секунда"),
    }
    mtype, measure = metric_types[name]
    obj = {
        "id": MID[name],
        "metric_name": name,
        "metric_description": DESC[name],
        "metric_type": mtype,
        "measure_type": measure,
        "date": week,
        "calc_period": "неделя",
        "fact": fact,
        "plan": plan,
        "benchmark": benchmark,
    }
    if influent is not None:
        obj["influent_percent"] = influent
    obj["element"] = element
    obj["child_metrics"] = children if children else []
    return obj


# ---------- Сборка метрик для одного периода ----------
def build_week_metrics(week, rng, is_manager=False):
    # Базовые значения для этого человеко-недели
    if is_manager:
        # У руководителя — агрегированные значения по сектору
        prod_fact = round(rng.uniform(15, 19), 2)
        prod_rank_fact = None  # у руководителя нет ранга среди операторов
        transfer_total = round(rng.uniform(10, 16), 2)
        aht_total = round(rng.uniform(310, 360), 1)
        adh_fact = round(rng.uniform(85, 92), 2)
        aht_rank_fact = None
        transfer_rank_fact = None
    else:
        prod_fact = round(rng.uniform(8, 28), 2)
        prod_rank_fact = rng.randint(1, 25)
        transfer_total = round(rng.uniform(5, 25), 2)
        aht_total = round(rng.uniform(250, 450), 1)
        adh_fact = round(rng.uniform(75, 98), 2)
        aht_rank_fact = rng.randint(1, 25)
        transfer_rank_fact = rng.randint(1, 25)

    # ----- Дочерние AHT (3-й уровень) -----
    ring_t = round(rng.uniform(2, 5), 1)
    acw_t = round(rng.uniform(15, 40), 1)
    aux_t = round(rng.uniform(5, 20), 1)
    acd_t = round(rng.uniform(150, 280), 1)
    hold_t = max(round(aht_total - ring_t - acw_t - aux_t - acd_t, 1), 30.0)

    aht_children = [
        m("RING TIME", ring_t, None, 3.2, influent=1, week=week),
        m("ACW TIME", acw_t, None, 25.5, influent=4, week=week),
        m("AUX PEREZVON TIME", aux_t, None, 10.5, influent=5, week=week),
        m("ACD TIME", acd_t, None, 210.0, influent=60, week=week),
        m("HOLD TIME", hold_t, None, 95.0, influent=30, week=week),
    ]

    # ----- 2-й уровень: дети «Производительность» -----
    prod_children = []

    # Доля переводов: общая + 11 продуктов
    prod_children.append(
        m("Доля переводов", transfer_total, 10.0, 12.5,
          element=None, influent=4, week=week)
    )
    for p in PRODUCTS:
        prod_children.append(
            m("Доля переводов",
              round(rng.uniform(3, 30), 2),
              10.0,
              round(rng.uniform(8, 18), 2),
              element=p, influent=4, week=week)
        )

    # AHT: общая (с детьми) + 11 продуктов (без детей)
    prod_children.append(
        m("AHT", aht_total, 320.0, 340.0,
          element=None, influent=90, children=aht_children, week=week)
    )
    for p in PRODUCTS:
        prod_children.append(
            m("AHT",
              round(rng.uniform(200, 500), 1),
              320.0,
              round(rng.uniform(280, 380), 1),
              element=p, influent=90, week=week)
        )

    # Adherence (только element=null)
    prod_children.append(
        m("Adherence", adh_fact, 90.0, 87.5,
          element=None, influent=6, week=week)
    )

    # РАНГ AHT и РАНГ Доля переводов (только element=null)
    prod_children.append(
        m("РАНГ AHT",
          aht_rank_fact if aht_rank_fact is not None else None,
          12, 13, element=None, week=week)
    )
    prod_children.append(
        m("РАНГ Доля переводов",
          transfer_rank_fact if transfer_rank_fact is not None else None,
          12, 13, element=None, week=week)
    )

    # Влияние тематик на Talk&Hold: только по продуктам (может быть отрицательной)
    for p in PRODUCTS:
        prod_children.append(
            m("Влияние тематик на Talk&Hold",
              round(rng.uniform(-30, 30), 2), 0.0, 0.0,
              element=p, week=week)
        )

    # ----- 1-й уровень -----
    prod_metric = m("Производительность", prod_fact, 18.0, 16.5,
                    element=None, children=prod_children, week=week)
    rank_metric = m("РАНГ Производительность",
                    prod_rank_fact, 12, 13, element=None, week=week)

    return [prod_metric, rank_metric]


# ---------- Сборка одного сотрудника ----------
def build_person(tabnum, fio, post, is_manager, seed):
    rng = random.Random(seed)
    person = {
        "tabnum": tabnum,
        "fio": fio,
        "post": post,
        "depart": "Сектор 1",
        "metrics": []
    }
    for w in WEEKS:
        person["metrics"].extend(build_week_metrics(w, rng, is_manager=is_manager))
    return person


# ---------- Главный конвейер ----------
def main():
    # Руководитель
    manager = build_person(
        tabnum=1470489,
        fio="Иванов Андрей Сергеевич",
        post="Начальник сектора",
        is_manager=True,
        seed=999,
    )

    # 25 операторов
    name_rng = random.Random(7)
    used_tabnums = {1470489}
    employees = []
    for i in range(25):
        # уникальный табельный номер
        while True:
            tn = name_rng.randint(1000000, 9999999)
            if tn not in used_tabnums:
                used_tabnums.add(tn)
                break
        emp = build_person(
            tabnum=tn,
            fio=random_fio(name_rng),
            post="Оператор",
            is_manager=False,
            seed=i * 31 + 100,
        )
        employees.append(emp)

    result = {"me": manager, "employees": employees}

    out_path = "/mnt/user-data/outputs/test_metrics.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # Стата
    def count_metrics(metrics_list):
        c = 0
        for m_ in metrics_list:
            c += 1
            c += count_metrics(m_.get("child_metrics", []))
        return c

    total_metrics = count_metrics(manager["metrics"])
    for e in employees:
        total_metrics += count_metrics(e["metrics"])

    import os
    size_mb = os.path.getsize(out_path) / 1024 / 1024

    print(f"Готово: {out_path}")
    print(f"Размер файла: {size_mb:.2f} МБ")
    print(f"Людей: 1 руководитель + {len(employees)} операторов")
    print(f"Периодов: {len(WEEKS)} ({WEEKS[0]} … {WEEKS[-1]})")
    print(f"Всего метрик в дереве: {total_metrics}")
    print(f"Продуктов: {len(PRODUCTS)}")


if __name__ == "__main__":
    main()
