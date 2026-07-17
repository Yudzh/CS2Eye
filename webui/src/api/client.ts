const API_PREFIX = "/api/v1";


interface ApiErrorPayload {
  detail?: unknown;
}


export class ApiError extends Error {
  readonly status: number;

  constructor(
    message: string,
    status: number,
  ) {
    super(message);

    this.name = "ApiError";
    this.status = status;
  }
}


function detailToMessage(
  detail: unknown,
  status: number,
): string {
  if (typeof detail === "string") {
    return detail;
  }

  if (
    detail
    && typeof detail === "object"
    && "message" in detail
  ) {
    const message = (
      detail as {
        message?: unknown;
      }
    ).message;

    if (typeof message === "string") {
      return message;
    }
  }

  if (detail !== undefined) {
    try {
      return JSON.stringify(detail);
    } catch {
      // Не удалось сериализовать ошибку.
    }
  }

  return `Ошибка API: ${status}`;
}


export async function requestJson<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(
    init.headers,
  );

  headers.set(
    "Accept",
    "application/json",
  );

  if (init.body !== undefined) {
    headers.set(
      "Content-Type",
      "application/json",
    );
  }

  const response = await fetch(
    `${API_PREFIX}${path}`,
    {
      ...init,
      headers,
    },
  );

  if (!response.ok) {
    let message =
      `Ошибка API: ${response.status}`;

    try {
      const payload: ApiErrorPayload = await response.json();

      message = detailToMessage(
        payload.detail,
        response.status,
      );
    } catch {
      // Сервер вернул не JSON.
    }

    throw new ApiError(
      message,
      response.status,
    );
  }

  return await response.json() as T;
}


export function getJson<T>(
  path: string,
): Promise<T> {
  return requestJson<T>(
    path,
    {
      method: "GET",
    },
  );
}


export function postJson<T>(
  path: string,
  body: unknown,
): Promise<T> {
  return requestJson<T>(
    path,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  );
}

export function patchJson<T>(
  path: string,
  body: unknown,
): Promise<T> {
  return requestJson<T>(
    path,
    {
      method: "PATCH",
      body: JSON.stringify(body),
    },
  );
}


export function deleteJson<T>(
  path: string,
): Promise<T> {
  return requestJson<T>(
    path,
    {
      method: "DELETE",
    },
  );
}