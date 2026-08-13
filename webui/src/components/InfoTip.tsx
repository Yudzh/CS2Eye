import type { ReactNode } from "react";

export function InfoTip({ text }: { text: string }) {
  return <span className="info-tip" tabIndex={0} aria-label={`Пояснение: ${text}`}>
    <span aria-hidden="true">!</span><span className="info-tip__content" role="tooltip">{text}</span>
  </span>;
}

export function Term({ children, tip }: { children: ReactNode; tip: string }) {
  return <span className="term-with-tip">{children}<InfoTip text={tip}/></span>;
}
