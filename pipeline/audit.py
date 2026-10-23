"""Generate a deterministic coverage report without fetching sources."""
from .validate import ROOT, SCOPE, load, validate_catalog, validate_registry


def render(registry: dict, catalog: dict) -> str:
    validate_registry(registry)
    validate_catalog(catalog, registry)
    rows = catalog["records"]
    lines = [
        "# DATA_AUDIT — этап 0, подготовка", "",
        "Срез начальной разведки: 2026-10-23. Это не завершённый аудит программ.",
        "Числа приёма не извлекались. Доступность страницы не означает проверку её данных.", "",
        "В таблице ноль — число импортированных записей, а не число программ в вузе.",
        "Неизвестный объём каталога и отсутствие знаменателя обозначены «не определено».", "",
        "| Вуз | Начальный источник | Программ импортировано | С проверенным источником | Лет истории в наборе | Полнота обязательных полей | Проблемы и следующий сбор |",
        "| --- | --- | ---: | ---: | ---: | --- | --- |",
    ]
    for institution in SCOPE["institution_ids"]:
        source = next(s for s in registry["sources"] if s["institution_id"] == institution)
        found = [r for r in rows if r["institution_id"] == institution]
        programs = {r["program_id"] for r in found}
        checked_sources = {s["id"] for s in registry["sources"] if s["reliability"] == "verified" and s["parsing_status"] == "success"}
        verified = {r["program_id"] for r in found if r["verification_status"] == "verified" and r["source_id"] in checked_sources}
        years = {r["year"] for r in found}
        if found:
            count = sum(r["verification_status"] == "verified" and r[f] is not None and (not isinstance(r[f], dict) or r[f].get("status") == "verified")
                        for r in found for f in SCOPE["required_audit_fields"])
            completeness = f"{count / (len(found) * len(SCOPE['required_audit_fields'])):.1%} (только импортированные строки)"
        else:
            completeness = "не определено"
        lines.append(f"| {source['institution_name']} | [Официальная страница]({source['url']}) | {len(programs)} | {len(verified)} | {len(years)} | {completeness} | {source['notes']} |")
    lines.extend([
        "", "## Текущие выводы", "",
        f"Импортировано программ: {len({r['program_id'] for r in rows})}. Полный размер целевого каталога неизвестен.",
        "Программ, допущенных к вероятностному прогнозу: 0. Валидированных моделей: 0.",
        "Исторические ориентиры пока не загружены. Отсутствующие значения не заменены нулями.",
        "Базовый, оптимистичный и пессимистичный сценарии пока не рассчитываются.", "",
        "## Порядок этапа 1", "",
        "1. Перечислить все кампусы и программы по официальному каталогу каждого вуза.",
        "2. Обосновать включение кодом и описанием; смежные направления проверить вручную.",
        "3. Для каждой программы и конкурсной группы сверить правила, экзамены, места и категории.",
        "4. Проверить доступность 2023–2026; правила 2027 сохранять отдельно после публикации.",
        "5. Извлечь агрегаты с URL, снимком, SHA-256, годом, единицей и методикой.",
        "6. Конфликт или неуверенное извлечение отправлять на ручную проверку.",
        "7. Перегенерировать отчёт; определить пригодность данных до разработки модели.", "",
        "## Ограничение отчёта", "",
        "Процент заполнения применим только к импортированным строкам и не доказывает полноту каталога.",
        "Сейчас аудит не способен выдать разрешение на прогноз: такой критерий появится после проверки данных.",
        "Скрипт запускается офлайн: `python3 -m pipeline.audit`.", "",
    ])
    return "\n".join(lines)


if __name__ == "__main__":
    output = render(load(ROOT / "data/source_registry.json"), load(ROOT / "data/normalized/catalog.json"))
    (ROOT / "DATA_AUDIT.md").write_text(output, encoding="utf-8")
    print("DATA_AUDIT.md generated; stage 0 preparation only.")
