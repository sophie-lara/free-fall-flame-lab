import { useEffect, useRef } from 'react';
import { Route, Routes, useLocation } from 'react-router-dom';
import { Header } from './components/Header';
import { Toast } from './components/common';
import { useApp } from './state/AppState';
import { pageOf, pageTitle } from './lib/routes';
import { Home } from './pages/Home';
import { Ask } from './pages/ask/Ask';
import { CoveragePage } from './pages/coverage/CoveragePage';
import { LandscapePage } from './pages/landscape/LandscapePage';
import { Sources } from './pages/Sources';
import { Upload } from './pages/Upload';

export function App() {
  const location = useLocation();
  const page = pageOf(location.pathname);
  const { me, space, toastState } = useApp();
  const mainRef = useRef<HTMLElement>(null);
  const lastPath = useRef(location.pathname);

  // The space photo backdrop (and its dark theme) applies to every page when on.
  useEffect(() => {
    document.body.dataset.route = page;
    document.body.dataset.space = space ? 'on' : 'off';
    document.title = pageTitle(page);
  }, [page, space]);

  // On navigation: focus the main region and start at the top.
  useEffect(() => {
    if (lastPath.current === location.pathname) return;
    lastPath.current = location.pathname;
    mainRef.current?.focus({ preventScroll: true });
    window.scrollTo(0, 0);
  }, [location.pathname]);

  return (
    <>
      <a className="skip-link" href="#main" onClick={e => { e.preventDefault(); mainRef.current?.focus(); }}>Skip to content</a>
      <Header page={page} />
      <main id="main" tabIndex={-1} className="container" ref={mainRef}>
        {!me ? <p className="loading">Loading…</p> : (
          <Routes>
            <Route path="/ask/*" element={<Ask />} />
            <Route path="/explore/*" element={<CoveragePage />} />
            <Route path="/coverage/*" element={<CoveragePage />} />
            <Route path="/landscape/*" element={<LandscapePage />} />
            <Route path="/sources/*" element={<Sources />} />
            <Route path="/upload/*" element={<Upload />} />
            <Route path="*" element={<Home />} />
          </Routes>
        )}
      </main>
      {space ? (
        <footer className="container site-credit">
          <p className="photo-credit">Background: orbital sunrise over the Pacific Ocean, photographed from the International Space Station on Aug. 6, 2024. Image: NASA (iss071e439624).</p>
        </footer>
      ) : null}
      <Toast message={toastState.message} visible={toastState.visible} />
    </>
  );
}
