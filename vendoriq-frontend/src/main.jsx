import React from 'react'
import ReactDOM from 'react-dom/client'
import * as Sentry from '@sentry/react'
import App from './App.jsx'
import { ThemeProvider } from './context/ThemeContext'
import { InstallProvider } from './context/InstallContext'
import { initSentry } from './lib/sentry'
import './index.css'

initSentry()

function ErrorFallback() {
  return (
    <div className="min-h-screen flex items-center justify-center p-6 text-center">
      <div>
        <p className="text-lg font-semibold text-slate-text mb-2">Something went wrong</p>
        <p className="text-sm text-slate-dim mb-4">The error's been reported. Try reloading the page.</p>
        <button onClick={() => window.location.reload()} className="btn-primary">Reload</button>
      </div>
    </div>
  )
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <Sentry.ErrorBoundary fallback={<ErrorFallback />}>
      <ThemeProvider>
        <InstallProvider>
          <App />
        </InstallProvider>
      </ThemeProvider>
    </Sentry.ErrorBoundary>
  </React.StrictMode>,
)
