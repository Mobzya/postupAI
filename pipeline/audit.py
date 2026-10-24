"""Generate a deterministic coverage report without fetching sources."""
from .validate import ROOT, SCOPE, load, validate_catalog, validate_registry


def render(registry: dict, catalog: dict) -> str:
    validate_registry(registry)
    validate_catalog(catalog, registry)
    rows = catalog["records"]
    metrics_path = ROOT / 'data/normalized/mephi/metrics.json'
    mephi = load(metrics_path) if metrics_path.exists() else None
    lines = [
        "# DATA_AUDIT — этап 1A" if mephi else "# DATA_AUDIT — этап 0, подготовка", "",
        "Срез начальной разведки: 2026-10-23. Это не завершённый аудит программ.",
        "Числа МИФИ извлечены; остальные вузы пока на этапе разведки. Доступность страницы не означает проверку её данных." if mephi else "Числа приёма не извлекались. Доступность страницы не означает проверку её данных.", "",
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
        if institution == 'mephi' and mephi:
            lines.append(f"| {source['institution_name']} | [Официальная страница]({source['url']}) | {mephi['program_profiles']} профиля | {mephi['program_profiles']} строк источника; допуск кампании неполон | {len(mephi['historical_years'])} | не определено для кампании | Этап 1A: docs/MEPHI_AUDIT.md; группы истории не установлены |")
        else:
            lines.append(f"| {source['institution_name']} | [Официальная страница]({source['url']}) | {len(programs)} | {len(verified)} | {len(years)} | {completeness} | {source['notes']} |")
    lines.extend([
        "", "## Текущие выводы", "",
        f"Импортировано профилей программ МИФИ: {mephi['program_profiles'] if mephi else 0}. Полный размер целевого каталога неизвестен.",
        "Программ, допущенных к вероятностному прогнозу: 0. Валидированных моделей: 0.",
        f"Исторических строк МИФИ: {mephi['historical_rows'] if mephi else 0}. Отсутствующие значения не заменены нулями.",
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
    if mephi:
        lines.extend(['## Обновление этапа 1A','',
            'Подробности и актуальные источники: [MEPHI_AUDIT](docs/MEPHI_AUDIT.md), [матрица вузов](docs/UNIVERSITY_SOURCE_MATRIX.md).',
            'Верхняя таблица остальных вузов сохраняет исходную разведку этапа 0; свежие HTTP-статусы приведены в новой матрице.',
            'data/normalized/catalog.json — старый пустой контракт. Реальные сущности программы/направления/места/наблюдения разделены в data/normalized/mephi/.',''])
    catalog_path=ROOT/'data/normalized/catalog_v1/dataset.json'
    if catalog_path.exists():
        observed=load(catalog_path)
        profiles=sum(r['kind']=='program_profile' for r in observed['display_index'])
        tracks=sum(r['kind']=='marketing_track' for r in observed['display_index'])
        covered=sum(r['program_profiles']>0 for r in observed['coverage'])
        lines.extend(['## Каталожные наблюдения 1C','',
            f'Дополнительно извлечено {profiles} профильных записей из {covered}/10 вузов и {tracks} маркетинговых трека отдельно.',
            'Верхняя таблица отражает прежний канонический контракт; наблюдения 1C ещё не повышены до проверенных версий программ.',
            'Полнота целевого каталога неизвестна; неизвестные годы, кампусы и условия не заполнены догадками.',
            'Подробное покрытие: data/normalized/catalog_v1/coverage.json и docs/STAGE_1C_REPORT.md.',''])
    return "\n".join(lines)


if __name__ == "__main__":
    output = render(load(ROOT / "data/source_registry.json"), load(ROOT / "data/normalized/catalog.json"))
    (ROOT / "DATA_AUDIT.md").write_text(output, encoding="utf-8")
    print('DATA_AUDIT.md generated; MEPhI stage 1A facts remain unavailable for forecasting.')
