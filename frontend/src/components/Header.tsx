import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { useApp } from '../state/AppState';
import { UiSwitch } from './common';
import { isExplore } from '../lib/routes';
import type { Page } from '../lib/routes';

const current = (on: boolean) => (on ? ('page' as const) : undefined);

export function Header({ page }: { page: Page }) {
  const { me, space, toggleSpace } = useApp();
  const [navOpen, setNavOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const dropRef = useRef<HTMLDivElement>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  // Any page change closes the mobile menu and the Explore dropdown.
  useEffect(() => { setNavOpen(false); setMenuOpen(false); }, [page]);

  // Explore menu: closes on outside click or Escape.
  useEffect(() => {
    if (!menuOpen) return;
    menuRef.current?.querySelector('a')?.focus();
    const onClick = (e: MouseEvent) => { if (!(e.target instanceof Node) || !dropRef.current?.contains(e.target)) setMenuOpen(false); };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') { setMenuOpen(false); btnRef.current?.focus(); } };
    document.addEventListener('click', onClick);
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('click', onClick); document.removeEventListener('keydown', onKey); };
  }, [menuOpen]);

  const hosted = !['127.0.0.1', 'localhost'].includes(location.hostname);
  const canUpload = !!(me?.is_admin || me?.can_upload);
  let badge: ReactNode = null;
  if (me?.name) {
    badge = <>{me.name}{me.is_admin && <span className="pill">Admin</span>}{hosted && <> <a className="small" href="/.auth/logout?post_logout_redirect_uri=/">Sign out</a></>}</>;
  } else if (me?.is_admin) {
    badge = <span className="pill">Local admin</span>;
  } else if (me && hosted) {
    badge = <a className="small" href="/.auth/login/github?post_login_redirect_uri=/">Admin sign-in</a>;
  }

  return (
    <header className="site-header">
      <div className="container header-inner">
        <a className="brand" href="#/" aria-label="Combustion Atlas home">
          <img src="/logo.svg" alt="" width="32" height="32" />
          <span>Combustion <strong>Atlas</strong></span>
        </a>
        <button className="btn small nav-toggle" type="button" aria-expanded={navOpen} aria-controls="site-nav" onClick={() => setNavOpen(o => !o)}>Menu</button>
        <nav id="site-nav" className={`site-nav${navOpen ? ' open' : ''}`} aria-label="Main">
          <a href="#/ask" aria-current={current(page === 'ask')}>Ask</a>
          <div className="nav-drop" ref={dropRef}>
            <button
              type="button" className="nav-drop-btn" ref={btnRef} aria-current={current(isExplore(page))}
              aria-expanded={menuOpen} aria-haspopup="true" aria-controls="explore-menu"
              onClick={e => { e.stopPropagation(); setMenuOpen(o => !o); }}
            >Explore <span aria-hidden="true">▾</span></button>
            <div className="nav-menu" id="explore-menu" hidden={!menuOpen} ref={menuRef} onClick={() => setMenuOpen(false)}>
              <a href="#/coverage" aria-current={current(page === 'coverage' || page === 'explore')}>Experiment coverage</a>
              <a href="#/landscape" aria-current={current(page === 'landscape')}>Evidence landscape</a>
            </div>
          </div>
          <a href="#/sources" aria-current={current(page === 'sources')}>Sources</a>
          <a href="#/upload" className="admin-only" hidden={!canUpload} aria-current={current(page === 'upload')}>Add to corpus</a>
        </nav>
        <UiSwitch id="space-toggle" className="header-space" on={space} label="Space background" text="Space" onToggle={toggleSpace} />
        <div id="user-badge" className="user-badge" aria-live="polite">{badge}</div>
      </div>
    </header>
  );
}
