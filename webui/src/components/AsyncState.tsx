interface ErrorStateProps {
  message: string;
  onRetry?: () => void;
}


export function LoadingState({
  message = "Загрузка...",
}: {
  message?: string;
}) {
  return (
    <div
      className="state-card"
      role="status"
    >
      <span
        className="spinner"
        aria-hidden="true"
      />

      <span>{message}</span>
    </div>
  );
}


export function ErrorState({
  message,
  onRetry,
}: ErrorStateProps) {
  return (
    <div
      className="state-card state-card--error"
      role="alert"
    >
      <div>
        <strong>
          Не удалось загрузить данные
        </strong>

        <p>{message}</p>
      </div>

      {onRetry ? (
        <button
          className="button button--secondary"
          onClick={onRetry}
          type="button"
        >
          Повторить
        </button>
      ) : null}
    </div>
  );
}


export function EmptyState({
  message,
}: {
  message: string;
}) {
  return (
    <div className="state-card state-card--empty">
      {message}
    </div>
  );
}