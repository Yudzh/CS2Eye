# Замена локального проекта и первый push

Команды ниже сохраняют каталог `.git`, поэтому история репозитория и remote
останутся на месте. Старое состояние сначала нужно зафиксировать отдельным
коммитом или веткой.

В примере:

- текущий репозиторий: `~/PycharmProjects/CS2Eye`;
- архив распакован в `~/Downloads/CS2Eye-template`;
- новая ветка: `restart/clean-foundation`.

## 1. Сохранить старый проект

```bash
cd ~/PycharmProjects/CS2Eye
git status
git add -A
git commit -m "chore: preserve draft before restart"
git push
```

Если `git status` чистый, коммит создавать не нужно.

## 2. Создать новую ветку

```bash
git switch -c restart/clean-foundation
```

## 3. Остановить старый compose

```bash
docker compose -f compose.local.yml down
```

Старые Docker volumes можно оставить как резервную копию данных черновика.
Новый шаблон ниже запускается с отдельным именем compose-проекта и получит
собственные чистые volumes.

Если резервная копия локальной БД точно не нужна, старые volumes можно удалить:

```bash
docker compose -f compose.local.yml down -v
```

`down -v` удаляет локальные данные PostgreSQL и pgAdmin. Выполнять эту команду
только если старые локальные данные больше не нужны или уже сохранены.

## 4. Заменить файлы, сохранив Git

Сначала распаковать архив. После этого выполнить:

```bash
rsync -a --delete \
  --exclude='.git/' \
  --exclude='.env' \
  --exclude='storage/' \
  --exclude='uploads/' \
  ~/Downloads/CS2Eye-template/ \
  ~/PycharmProjects/CS2Eye/
```

Важно: завершающие `/` в обеих директориях нужны. Команда заменит содержимое
рабочего дерева, но не тронет `.git`, локальный `.env`, `storage` и `uploads`.

Если `rsync` не установлен:

```bash
sudo apt install rsync
```

## 5. Подготовить окружение и проверить проект

```bash
cd ~/PycharmProjects/CS2Eye
cp -n .env.example .env
docker compose -p cs2eye-clean -f compose.local.yml config
docker compose -p cs2eye-clean -f compose.local.yml up --build
```

Проверить:

- <http://localhost:5173>
- <http://localhost:8000/docs>
- <http://localhost:8000/api/v1/health/ready>

После проверки остановить foreground-запуск сочетанием `Ctrl+C`. При
необходимости сервисы можно снова запустить в фоне:

```bash
docker compose -p cs2eye-clean -f compose.local.yml up -d
```

## 6. Закоммитить замену и отправить ветку

```bash
git status
git add -A
git commit -m "chore: restart from clean project foundation"
git push -u origin restart/clean-foundation
```

После push старая ветка остаётся черновиком, а
`restart/clean-foundation` становится чистой основой для последовательной
разработки.
