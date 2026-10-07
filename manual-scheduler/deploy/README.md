# manual-scheduler + UTB2

Составление расписания — `manual-scheduler`, просмотр студентами — `UTB2`.
`timetable-system` в этом стеке не запускается. Имена сервисов `staff-api` и
`staff-web` сохранены для совместимости адресов, но собираются из manual-scheduler.
Базы раздельные: `manual_data` (SQLite) и прежний `student_data` (PostgreSQL).
Старый том `staff_data` не удаляется и не используется.

## Переход с существующей установки

1. Сохраните резервную копию PostgreSQL до обновления контейнеров:

   ```bash
   mkdir -p backups
   chmod 700 backups
   (umask 077; docker exec okak-student-db-1 pg_dump -U okak -d okak -Fc > backups/students-before-manual.dump)
   ```

   Если COMPOSE_PROJECT_NAME отличается от `okak`, используйте соответствующее имя контейнера.
   Сохраните также старую SQLite и `.env`. Не удаляйте тома и не меняйте пароль PostgreSQL.

2. Скопируйте `~/okak/timetable-system/deploy/.env` из прежнего проекта в
   `~/utb-schedule/manual-scheduler/deploy/.env` нового проекта.
   Все следующие команды выполняются в `manual-scheduler/deploy`.

3. Перенесите **manual-scheduler/backend/schedule.db** с ноутбука на сервер
   согласованной SQLite-копией (при остановленном API либо через sqlite backup).
   Это база с расставленными занятиями и общим аккаунтом. Импортируйте её до первого запуска:

   ```bash
   ./deploy.sh import-manual /absolute/path/schedule.db server
   ```

   Перед импортом остановите старый staff-api, если он ещё работает:
   `docker stop okak-staff-api-1` (студенческий сайт продолжает работать). Затем
   выполните команду импорта выше.

   Импорт разрешён только в пустой том manual_data. Старую timetable.db эта команда
   отклоняет. Уже существующую manual-базу нельзя заменять заново: в ней хранятся
   идентификатор источника и версии публикаций. После импорта сохраняется общий логин/пароль.

4. Проверьте `STUDENT_DOMAIN` и `EDITOR_DOMAIN` в `.env` (по умолчанию
   okak.asia и app.okak.asia), затем:

   ```bash
   ./deploy.sh up server
   ```

   Одновременно обновляются обе стороны. Студенты продолжают видеть старую публикацию
   до первого нажатия «Опубликовать» в manual-scheduler. Старый POST /api/v1/publication
   возвращает 410 и больше не меняет расписание. Новый канал /api/v1/manual-publication
   доступен только между API в приватной Docker-сети с Bearer-ключом.

5. Откройте app.okak.asia, проверьте расписание и нажмите «Опубликовать».
   Первая успешная публикация заменяет старое расписание и привязывает UTB2 к этой
   manual-базе. Совпадающие названия групп сохраняют прежние ID. Отсутствующие группы
   и пары удаляются из опубликованной версии. Далее ID групп сохраняются при переименовании.

## Новая установка / локальная проверка

```bash
./deploy.sh init
./deploy.sh up local
./deploy.sh user admin local
```

Пароль вводится скрыто. Студенты: http://localhost:8080, редактор: http://localhost:8081.
Локальный student API: http://127.0.0.1:8001 (только loopback). Для server-режима
порты API наружу не открываются; cookie Secure включён, HTTPS обеспечивает Caddy.
`init` не генерирует секреты при обнаружении старых томов: восстановите исходный `.env`.

`./deploy.sh backup server` сохраняет manual.sqlite, students.dump и секреты deploy.env
в приватном каталоге backups. `./deploy.sh package` упаковывает только два новых проекта
без баз, зависимостей, паролей и .env. `down` сохраняет данные; не используйте `down -v`.
