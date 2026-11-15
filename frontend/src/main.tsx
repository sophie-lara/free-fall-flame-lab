// Combustion Atlas public UI. Self-contained; talks only to this server's /api.
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { HashRouter } from 'react-router-dom';
import { App } from './App';
import { AppProvider } from './state/AppState';
import './styles/styles.css';
import './styles/flame-story.css';
import './styles/additions.css';

const root = document.getElementById('root');
if (root) {
  createRoot(root).render(
    <StrictMode>
      <HashRouter>
        <AppProvider>
          <App />
        </AppProvider>
      </HashRouter>
    </StrictMode>,
  );
}
