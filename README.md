# Редактор расписания и UTB2

- **manual-scheduler** — редактор (FastAPI + Vue), общий аккаунт, совместная работа.
- **UTB2** — студенческий сайт. Получает расписание по кнопке «Опубликовать».

## Сервер: новая установка

Нужны Docker Engine с Compose v2, Git и Python 3. Домены должны указывать на сервер;
порты 80 и 443 должны быть свободны и доступны. Caddy автоматически выдаёт HTTPS-сертификаты.

```bash
git clone https://github.com/ahmetovdotcom/utb-schedule.git ~/utb-schedule
cd ~/utb-schedule
./deploy.sh init
```

В `manual-scheduler/deploy/.env` задайте `STUDENT_DOMAIN` и `EDITOR_DOMAIN`.
По умолчанию: `okak.asia` и `app.okak.asia`. Затем:

```bash
./deploy.sh up server
./deploy.sh user admin server
```

Последняя команда создаёт общий аккаунт; пароль вводится скрыто.
Если Docker требует sudo, добавьте `sudo` перед `./deploy.sh`.
Секреты публикации генерируются автоматически и остаются на сервере.

## Если сервер уже работает со старым редактором

Не начинайте с пустой базы. Сохраните резервные копии, перенесите базу
`manual-scheduler/backend/schedule.db` и импортируйте её **до первого запуска**
нового редактора. Исходная PostgreSQL студентов и её пароль сохраняются.

Подробная последовательность: [инструкция перехода](manual-scheduler/deploy/README.md).
Перед переходом скопируйте прежний `~/okak/timetable-system/deploy/.env` в
`manual-scheduler/deploy/.env` нового проекта. Старый том `staff_data` остаётся
нетронутым; редактор использует отдельный `manual_data`. Имя Compose-проекта
по умолчанию `okak` сохраняет существующую PostgreSQL студентов.

## Обновление и обслуживание

```bash
./deploy.sh backup server
git pull --ff-only
./deploy.sh up server
./deploy.sh status server
./deploy.sh logs server
```

Данные сохраняются в Docker volumes между обновлениями. `down` их не удаляет.
Не запускайте `docker compose down -v` на рабочем сервере.

Для локальной Docker-проверки замените `server` на `local`: UTB2 на
http://localhost:8080, редактор на http://localhost:8081.

`./deploy.sh package` создаёт архив исходников в `manual-scheduler/deploy/releases`.
Пароли, `.env`, рабочие базы, резервные копии и зависимости в архив и Git не входят.
База с расписанием переносится отдельно защищённым SSH/SCP-соединением.
