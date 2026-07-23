import {
  useEffect,
  useState,
} from "react";


interface ReadinessResponse {
  status: "ok";
  service: string;
  database: "ok";
}

type CheckState =
  | { kind: "loading" }
  | {
      kind: "ready";
      payload: ReadinessResponse;
    }
  | { kind: "error" };


export default function App() {
  const [check, setCheck] = useState<CheckState>({
    kind: "loading",
  });

  useEffect(() => {
    const controller = new AbortController();

    fetch(
      "/api/v1/health/ready",
      {
        signal: controller.signal,
      },
    )
      .then((response) => {
        if (!response.ok) {
          throw new Error(
            `HTTP ${response.status}`,
          );
        }

        const payload: Promise<
          ReadinessResponse
        > = response.json();

        return payload;
      })
      .then((payload) => {
        setCheck({
          kind: "ready",
          payload,
        });
      })
      .catch((error: unknown) => {
        if (
          error instanceof DOMException
          && error.name === "AbortError"
        ) {
          return;
        }

        setCheck({
          kind: "error",
        });
      });

    return () => {
      controller.abort();
    };
  }, []);

  const isReady = check.kind === "ready";

  return (
    <main className="page">
      <section className="hero">
        <div className="brand">
          <span className="brand__mark">C2</span>
          <span>CS2Eye</span>
        </div>

        <p className="eyebrow">
          Чистая точка старта
        </p>

        <h1>
          Инфраструктура готова.
          <br />
          Продукт строим слоями.
        </h1>

        <p className="lead">
          В шаблоне нет команд, демо, импорта,
          сравнения или прогнозов. Следующая
          функция появится только вместе с
          моделью данных, API, UI и тестами.
        </p>
      </section>

      <section
        aria-label="Состояние сервисов"
        className="status-grid"
      >
        <article className="status-card">
          <div className="status-card__top">
            <span>Web UI</span>
            <span className="badge badge--ok">
              работает
            </span>
          </div>
          <strong>React + Vite</strong>
          <p>Минимальная оболочка интерфейса.</p>
        </article>

        <article className="status-card">
          <div className="status-card__top">
            <span>API</span>
            <span
              className={
                isReady
                  ? "badge badge--ok"
                  : "badge"
              }
            >
              {check.kind === "loading"
                ? "проверка"
                : isReady
                  ? "работает"
                  : "ошибка"}
            </span>
          </div>
          <strong>FastAPI</strong>
          <p>
            {isReady
              ? check.payload.service
              : "Проверка readiness endpoint."}
          </p>
        </article>

        <article className="status-card">
          <div className="status-card__top">
            <span>Database</span>
            <span
              className={
                isReady
                  ? "badge badge--ok"
                  : "badge"
              }
            >
              {isReady
                ? "работает"
                : "ожидание"}
            </span>
          </div>
          <strong>PostgreSQL + Alembic</strong>
          <p>
            {isReady
              ? "Соединение с БД установлено."
              : "Ожидается ответ API."}
          </p>
        </article>
      </section>

      <section className="next-layer">
        <span className="next-layer__index">
          01
        </span>
        <div>
          <p className="eyebrow">
            Следующий слой
          </p>
          <h2>Пока не выбран</h2>
          <p>
            Сначала формулируем один сценарий
            и критерии готовности. Затем
            реализуем его целиком.
          </p>
        </div>
      </section>
    </main>
  );
}
