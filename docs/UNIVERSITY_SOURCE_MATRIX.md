# Карта официальных источников десяти вузов

Предварительная разведка. «Ссылка найдена» не означает, что целевой документ прочитан.
Детальные снимки, ссылки и статусы: `data/source_registry.yaml` (JSON-совместимый YAML 1.2).

| Вуз | Фактически прочитано | Формат | Архив / проходные | Места | Списки | Правила / особенности | Сложность |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [МФТИ](https://pk.mipt.ru/bachelor/) | failed | unknown | unknown / unknown | unknown | unknown | Rules document not read. | high/unknown until public source is reachable |
| [НИУ ВШЭ](https://ba.hse.ru/) | http_read | HTML; linked documents not inspected | linked_not_read / linked_not_read | linked_not_read | linked_not_read | Entry page mentions: грант, олимпиад. Exact rules require document review. | medium (preliminary; deep source not validated) |
| [ИТМО](https://abit.itmo.ru/) | failed | unknown | unknown / unknown | unknown | unknown | Rules document not read. | high/unknown until public source is reachable |
| [МИФИ](https://admission.mephi.ru/) | http_read | Static HTML tables with year tabs/rowspan; linked PDF | read_2015_2025 / read_2015_2025 | read_2026 | linked_not_read | 2026 rules PDF read: campus, form, profile, funding and quota distinguish competitions; rules engine not implemented. | medium; semantics and historical group reconciliation are difficult |
| [СПбГУ](https://abiturient.spbu.ru/programs/bakalavriat/) | http_read | HTML; linked documents not inspected | linked_not_read / not_found_on_entry_page | linked_not_read | linked_not_read | Entry page mentions: олимпиад. Exact rules require document review. | medium (preliminary; deep source not validated) |
| [МГУ](https://cpk.msu.ru/) | http_read | HTML with tables | not_found_on_entry_page / linked_not_read | not_found_on_entry_page | linked_not_read | Entry page mentions: ДВИ, олимпиад. Exact rules require document review. | medium (preliminary; deep source not validated) |
| [НГУ](https://abiturient.nsu.ru/) | http_read | HTML with client templates; applicant rows not fetched | not_found_on_entry_page / not_found_on_entry_page | not_found_on_entry_page | public_list_interface_read_rows_not_collected | No rules conclusions from entry page. | medium/high; dynamic list interface, find separate admissions archive and documents |
| [МГТУ им. Баумана](https://priem.bmstu.ru/) | javascript_shell_only | JavaScript application shell; admission content not read | not_found_on_entry_page / not_found_on_entry_page | not_found_on_entry_page | not_found_on_entry_page | No rules conclusions from entry page. | high/unknown; locate public document endpoints without authorization |
| [Университет Иннополис](https://apply.innopolis.university/bachelors/) | http_read | HTML; linked documents not inspected | not_found_on_entry_page / linked_not_read | not_found_on_entry_page | not_found_on_entry_page | Entry page mentions: грант, олимпиад. Exact rules require document review. | medium (preliminary; deep source not validated) |
| [Центральный университет](https://cu.ru/) | http_read | HTML; linked documents not inspected | not_found_on_entry_page / not_found_on_entry_page | not_found_on_entry_page | not_found_on_entry_page | Entry page mentions: грант, олимпиад. Exact rules require document review. | medium (preliminary; deep source not validated) |

У остальных девяти вузов не проверялась полнота архивов, не выгружались персональные конкурсные списки и не реализованы парсеры.
Сбой robots или перенаправление на другой origin не обходились. Такие источники не объявлены прочитанными.
Состояния HTTP и содержимого относятся к сохранённому срезу, а не гарантируют доступность в будущем.
