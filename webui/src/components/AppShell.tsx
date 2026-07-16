import type {
  PropsWithChildren,
} from "react";

import {
  NavLink,
} from "react-router-dom";


export function AppShell({
  children,
}: PropsWithChildren) {
  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="topbar__inner">
          <NavLink
            className="brand"
            to="/teams"
          >
            <span className="brand__mark">
              C2
            </span>

            <span>
              <strong>CS2Eye</strong>

              <small>
                Betting Analytics
              </small>
            </span>
          </NavLink>

          <nav
            className="main-nav"
            aria-label="Основная навигация"
          >
            <NavLink
              className={({ isActive }) =>
                `main-nav__link${
                  isActive
                    ? " main-nav__link--active"
                    : ""
                }`
              }
              to="/teams"
            >
              Команды
            </NavLink>

            <NavLink
              className={({ isActive }) =>
                `main-nav__link${
                  isActive
                    ? " main-nav__link--active"
                    : ""
                }`
              }
              to="/compare"
            >
              Сравнение команд
            </NavLink>
            <NavLink
              className={({ isActive }) =>
                `main-nav__link${
                  isActive
                    ? " main-nav__link--active"
                    : ""
                }`
              }
              to="/admin/teams/import"
            >
              Администрирование
            </NavLink>
          </nav>
        </div>
      </header>

      <main className="page-container">
        {children}
      </main>
    </div>
  );
}