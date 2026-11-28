# Golden evaluation set — ai-agent-corp-docs

Корпус: `internal/corpus-samples/` (именованные `.txt` + raw docx / hashed mirrors).  
Режим по умолчанию: `regs_only` (корпоративные регламенты; ТК/Конституция — out of domain → `refuse`).

**Как прогонять:** для каждого кейса задать `question`, зафиксировать фактический исход в полях лога внизу кейса, сравнить со `scenario` / `expected_*`.

**Offline (CI):** `pytest tests/application/test_golden_set.py` — моки, без сети.

**Online (локально, scenario runner → live LLM/embeddings/Qdrant; без записи в Qdrant/Postgres):**

```bash
cd server
# .env с живым стеком; корпус уже ingest в коллекцию
python scripts/run_golden_scenarios.py
```

Сценарии: `scenarios/golden-set.yaml`. Лог для вставки обратно: **`artifacts/golden-run.log`**
(блоки `GOLDEN LOG` → поля `log (paste back)` ниже).

**Баланс:** 17 кейсов — answer 8 · clarify 3 · escalate 3 · refuse 3.

---

## GS-01 · answer · DBRCT пресейл 3 р.д.

- **id:** `GS-01`
- **scenario:** `answer`
- **question:** За сколько рабочих дней необходимо инициировать заявку на пресейл ДБРЦТ?
- **expected_behavior:** Короткий ответ: не менее чем за 3 рабочих дня до подачи предложения Заказчику.
- **expected_doc:** Проектная деятельность ДБРЦТ (Департамента бизнес-решений и цифровой трансформации)
- **locator:** п. 1.5
- **quote_snippet:** «Заявка должна быть инициирована не менее чем за 3 рабочих дня до подачи предложения Заказчику.»
- **notes / traps:** lead-time WHEN; не проигрывать Presale IB 3.4/6.9 (wait/timeout «3 рабочих дня» / дисквалификация) — prefer initiation clause п.1.5 даже при score~0.33; риск `paraphrase_required` если 1.5 отфильтрован topical_floor.
- **log (paste back):**
  - status:
  - summary/answer:
  - citations (doc, locator, score):
  - escalation reason:

---

## GS-01b · answer · DBRCT пресейл 3 р.д. (near-dup «в ДБРЦТ»)

- **id:** `GS-01b`
- **scenario:** `answer`
- **question:** За сколько рабочих дней необходимо инициировать заявку на пресейл в ДБРЦТ?
- **expected_behavior:** Тот же ground truth, что GS-01 — не менее чем за 3 рабочих дня (п. 1.5).
- **expected_doc:** Проектная деятельность ДБРЦТ (Департамента бизнес-решений и цифровой трансформации)
- **locator:** п. 1.5
- **quote_snippet:** «Заявка должна быть инициирована не менее чем за 3 рабочих дня до подачи предложения Заказчику.»
- **notes / traps:** единственное отличие от GS-01 — предлог «в» перед ДБРЦТ. Live: hybrid/rerank уводил в Presale IB 3.4/6.9 (wait/timeout), 1.5 почти не в top → `paraphrase_required` / grounded=false. Fix: lead-time synonym expand + deterministic blend (boost initiation, demote wait, org-title ДБРЦТ); grounding escalate если в пуле только wait/timeout.
- **log (paste back):**
  - status:
  - summary/answer:
  - citations (doc, locator, score):
  - escalation reason:

---

## GS-02 · answer · кто подписывает договоры на закупку

- **id:** `GS-02`
- **scenario:** `answer`
- **question:** Кто подписывает договоры на закупку?
- **expected_behavior:** Ответ про юридические лица Компании (не ФИО / не роль сотрудника / не АМ+ДС).
- **expected_doc:** Пресейловая деятельность Дирекции ИБ
- **locator:** п. 9.5
- **quote_snippet:** «Все субподрядные договоры по ИБ проектам, кроме перепродажи вендорских сервисов, заключаются от юридических лиц Компании.»
- **notes / traps:** в 9.5 нет «закупку»/«подписывает» → hybrid+LLM rerank часто не кладёт 9.5 в top-5 (DBRCT 8.7/17.6, сроки подписания, 20.7) → paraphrase_required. Fix: synonym expand + deterministic purchase-WHO blend (skip LLM rerank); grounding prefer agency over DS/AM.
- **log (paste back):**
  - status:
  - summary/answer:
  - citations (doc, locator, score):
  - escalation reason:

---

## GS-03 · answer · WHEN RP Q1 (лексика близка к п. 2.7)

- **id:** `GS-03`
- **scenario:** `answer`
- **question:** В течение какого срока Координатор департамента назначает РП при наличии полного Расчёта проекта?
- **expected_behavior:** В течение 1 рабочего дня (при полной информации / по итоговому Расчёту проекта).
- **expected_doc:** Проектная деятельность Дирекции ИБ
- **locator:** п. 2.7
- **quote_snippet:** «Если предоставлена полная информация, Координатор департамента назначает РП в соответствии с итоговым Расчётом проекта в течение 1 рабочего дня.»
- **notes / traps:** near-dup к GS-04; токены вопроса почти дословно в 2.7 → обычно высокий lexical overlap. Не путать с Тех дирекцией п. 9.1 («Срок назначения Руководителя проекта – 1 рабочий день») без Координатора.
- **log (paste back):**
  - status:
  - summary/answer:
  - citations (doc, locator, score):
  - escalation reason:

---

## GS-04 · answer · WHEN RP Q2 (near-duplicate, морфология)

- **id:** `GS-04`
- **scenario:** `answer`
- **question:** За сколько назначается РП в Дирекции ИБ при предоставлении полной информации?
- **expected_behavior:** Тот же ground truth, что GS-03: в течение 1 рабочего дня (Координатор / полная информация).
- **expected_doc:** Проектная деятельность Дирекции ИБ
- **locator:** п. 2.7
- **quote_snippet:** «Если предоставлена полная информация, Координатор департамента назначает РП в соответствии с итоговым Расчётом проекта в течение 1 рабочего дня.»
- **notes / traps:** исторический fail: Jaccard с 2.7 ≈ 0 (`назначается`/`предоставлении` vs `назначает`/`предоставлена`) → demote правильного чанка; сосед без дедлайна → `paraphrase_required`. Ожидание после фиксов: **answer**, не escalate. `strip_regulation_noise` не должен съедать «1» у «1 рабочего дня».
- **log (paste back):**
  - status:
  - summary/answer:
  - citations (doc, locator, score):
  - escalation reason:

---

## GS-05 · answer · отчётность по проекту — РП

- **id:** `GS-05`
- **scenario:** `answer`
- **question:** Кто отвечает за организацию отчётности по проекту?
- **expected_behavior:** Руководитель проекта (РП).
- **expected_doc:** Организация проектной деятельности *(Тех дирекция)* **или** Проектная деятельность ДБРЦТ — оба содержат норму
- **locator:** п. 18.1 (Тех) / п. 15.1 (ДБРЦТ)
- **quote_snippet:** «За организацию отчетности по проекту отвечает Руководитель проекта.» / «За организацию отчётности по проекту отвечает РП.»
- **notes / traps:** роль+тема → `looks_role_topic_specific` должен override timid `underspecified` (не clarify). Допустима цитата из любого релевантного докa с той же нормой; плохо — ответ «координатор» из демо-фикстур.
- **log (paste back):**
  - status:
  - summary/answer:
  - citations (doc, locator, score):
  - escalation reason:

---

## GS-06 · answer · ПА принимает заявку за 1 р.д.

- **id:** `GS-06`
- **scenario:** `answer`
- **question:** За какой срок Пресейл-архитектор обязан принять заявку в работу после назначения?
- **expected_behavior:** В течение 1 рабочего дня с момента назначения.
- **expected_doc:** Пресейловая деятельность Дирекции ИБ
- **locator:** п. 5.1
- **quote_snippet:** «ПА обязан принять заявку в работу в течение 1 рабочего дня с момента назначения.»
- **notes / traps:** много соседних «1 рабочий день» (6.6, 6.7, 7.8…) — WHEN-extract должен привязаться к принятию заявки ПА, не к ответу SS/РМ.
- **log (paste back):**
  - status:
  - summary/answer:
  - citations (doc, locator, score):
  - escalation reason:

---

## GS-07 · answer · ДБРЦТ — создание проекта после договора

- **id:** `GS-07`
- **scenario:** `answer`
- **question:** За сколько РП создаёт проект в системе управления проектами после подписания договора в ДБРЦТ?
- **expected_behavior:** В течение 1 рабочего дня (с учётом исключения п. 8.4 — ГП + согласование Директора).
- **expected_doc:** Проектная деятельность ДБРЦТ
- **locator:** п. 10.1
- **quote_snippet:** «…РП создаёт проект в системе управления проектами в течение 1 рабочего дня.»
- **notes / traps:** lexical overlap с п. 10.2 (смета — **3** рабочих дня); не подменять срок сметы сроком проекта.
- **log (paste back):**
  - status:
  - summary/answer:
  - citations (doc, locator, score):
  - escalation reason:

---

## GS-08 · clarify · underspec — «кто отвечает за организацию»

- **id:** `GS-08`
- **scenario:** `clarify`
- **question:** Кто отвечает за организацию?
- **expected_behavior:** Уточняющий вопрос (нет темы: отчётность / риски / изменения / …). Не answer и не escalate на первом ходе.
- **expected_doc:** —
- **locator:** —
- **quote_snippet:** —
- **notes / traps:** без topic `looks_role_topic_specific` = false; если LLM timid → `underspecified` → clarify. Ложный pass: override в specific и ground по случайному «организац*».
- **log (paste back):**
  - status:
  - summary/answer:
  - citations (doc, locator, score):
  - escalation reason:

---

## GS-09 · clarify · ambiguous — «кто подписывает договоры»

- **id:** `GS-09`
- **scenario:** `clarify`
- **question:** Кто подписывает договоры?
- **expected_behavior:** Уточнение scope (закупка/субподряд ИБ vs подряд/иное). Не отвечать п. 9.5 без уточнения.
- **expected_doc:** —
- **locator:** —
- **quote_snippet:** —
- **notes / traps:** эталон ambiguous в classify-промпте; после уточнения «на закупку» → как GS-02. Риск: prefer_specific по слову «договор*» без «на закупку».
- **log (paste back):**
  - status:
  - summary/answer:
  - citations (doc, locator, score):
  - escalation reason:

---

## GS-10 · clarify · underspec — срок пресейла без подразделения

- **id:** `GS-10`
- **scenario:** `clarify`
- **question:** Какой срок на пресейл?
- **expected_behavior:** Уточнить подразделение / тип оценки (ДБРЦТ точная vs бюджетная; ИБ SLA ПА; и т.д.). Не усреднять разные сроки.
- **expected_doc:** —
- **locator:** —
- **quote_snippet:** —
- **notes / traps:** в корпусе несколько разных SLA; self-consistency / multi-doc → clarify или escalate, но **не** выдуманный единый срок. Ожидание golden: **clarify** (недостаточно scope).
- **log (paste back):**
  - status:
  - summary/answer:
  - citations (doc, locator, score):
  - escalation reason:

---

## GS-11 · escalate · пороговая маржинальность (нет % в корпусе)

- **id:** `GS-11`
- **scenario:** `escalate`
- **question:** Какой точный процент пороговой маржинальности установлен в Дирекции ИБ?
- **expected_behavior:** Эскалация в службу качества (`irrelevant_citations` / insufficient). **Не** отвечать чужим чанком про согласование Директора / бюджета.
- **expected_doc:** — *(в Пресейловой ИБ п. 14.3–14.4 есть слово «маржинальность», но нет числового порога)*
- **locator:** —
- **quote_snippet:** —
- **notes / traps:** классический weak-hit false answer: hybrid scores ~0.3–0.5 при lex≈0; до фикса grounding парафразировал top-hit. Регресс: `test_weak_hit_escalate.py`. Короткие titled orphans ухудшают пул.
- **log (paste back):**
  - status:
  - summary/answer:
  - citations (doc, locator, score):
  - escalation reason:

---

## GS-12 · escalate · целевая маржа без цифры (paraphrase trap)

- **id:** `GS-12`
- **scenario:** `escalate`
- **question:** Чему равна целевая маржинальность услуг по регламенту Дирекции ИБ?
- **expected_behavior:** Escalate — п. 14.4 отсылает к «внутреннему регламенту контроля маржинальности сделок», число не задано.
- **expected_doc:** —
- **locator:** —
- **quote_snippet:** — *(ложный якорь: «Если итоговая маржинальность услуг не достигает целевой…» — без величины)*
- **notes / traps:** высокий lexical overlap со словом «маржинальность» при отсутствии ответа → нельзя `enforce_short_paraphrase` с этого чанка; ожидание `irrelevant_citations` или `paraphrase_required` → escalate.
- **log (paste back):**
  - status:
  - summary/answer:
  - citations (doc, locator, score):
  - escalation reason:

---

## GS-13 · escalate · SLA поиска подрядчика ДБРЦТ (норма отсылает, цифры нет)

- **id:** `GS-13`
- **scenario:** `escalate`
- **question:** Какой точный SLA в рабочих днях на поиск и согласование подрядчика при оценке в ДБРЦТ?
- **expected_behavior:** Escalate — п. 1.7 говорит «учитывать SLA», но не задаёт число дней.
- **expected_doc:** —
- **locator:** —
- **quote_snippet:** — *(ложный якорь п. 1.7: «необходимо дополнительно учитывать SLA на поиск и согласование подрядчика»)*
- **notes / traps:** retrieve найдёт 1.5/1.6 с числами 3/5 → риск ложного WHEN-answer; grounding должен отвергнуть нерелевантный дедлайн.
- **log (paste back):**
  - status:
  - summary/answer:
  - citations (doc, locator, score):
  - escalation reason:

---

## GS-14 · refuse · off-topic погода

- **id:** `GS-14`
- **scenario:** `refuse`
- **question:** Какая сегодня погода в Москве?
- **expected_behavior:** Вежливый отказ вне домена. **Без** тикета quality / без escalate.
- **expected_doc:** —
- **locator:** —
- **quote_snippet:** —
- **notes / traps:** `is_off_topic` → refuse до retrieve; если ушло в escalate — регресс топологии (refuse ≠ escalate).
- **log (paste back):**
  - status:
  - summary/answer:
  - citations (doc, locator, score):
  - escalation reason:

---

## GS-15 · refuse · кулинарный out-of-regs

- **id:** `GS-15`
- **scenario:** `refuse`
- **question:** Как приготовить борщ?
- **expected_behavior:** Отказ: вопрос не про корпоративные регламенты.
- **expected_doc:** —
- **locator:** —
- **quote_snippet:** —
- **notes / traps:** chitchat / out of domain; не искать «процесс» в корпусе.
- **log (paste back):**
  - status:
  - summary/answer:
  - citations (doc, locator, score):
  - escalation reason:

---

## GS-16 · refuse · Конституция при regs_only

- **id:** `GS-16`
- **scenario:** `refuse`
- **question:** Что говорит Конституция РФ о свободе слова?
- **expected_behavior:** Отказ: Конституция не в `ALLOWED_TOPICS` → `off_topic` / refuse. Не answer junk из корпоративных регламентов.
- **expected_doc:** —
- **locator:** —
- **quote_snippet:** —
- **notes / traps:** dual-mode `regs_only` снят; gate = **ALLOWED_TOPICS**. Без «Конституция РФ» в allowlist — refuse до retrieve. Если ingest + ALLOWED_TOPICS включает Конституцию — кейс не как refuse.
- **log (paste back):**
  - status:
  - summary/answer:
  - citations (doc, locator, score):
  - escalation reason:

---

## Сводка

| id | scenario | короткий фокус |
|---|---|---|
| GS-01 | answer | ДБРЦТ пресейл ≥ 3 р.д. |
| GS-01b | answer | ДБРЦТ пресейл «в ДБРЦТ» near-dup |
| GS-02 | answer | закупка → юр. лица, п. 9.5 |
| GS-03 | answer | WHEN RP Q1 (Координатор / Расчёт) |
| GS-04 | answer | WHEN RP Q2 near-dup |
| GS-05 | answer | отчётность → РП |
| GS-06 | answer | ПА принять заявку 1 р.д. |
| GS-07 | answer | ДБРЦТ создать проект 1 р.д. |
| GS-08 | clarify | «кто отвечает за организацию» |
| GS-09 | clarify | «кто подписывает договоры» |
| GS-10 | clarify | «срок на пресейл» без scope |
| GS-11 | escalate | % пороговой маржи |
| GS-12 | escalate | «целевая маржа» без цифры |
| GS-13 | escalate | SLA подрядчика ДБРЦТ без числа |
| GS-14 | refuse | погода |
| GS-15 | refuse | борщ |
| GS-16 | refuse | Конституция (regs_only) |

**Замечания по корпусу:** файл `Проектная деятельность Дирекции ИБ.txt` в samples по содержимому = «Организация проектной деятельности» (Тех); полный текст с п. 2.7 Координатора — в hashed `___________________________________571f.txt` (заголовок «Проектная деятельность Дирекции ИБ»). При ingest ориентироваться на title внутри документа, не на имя файла.
