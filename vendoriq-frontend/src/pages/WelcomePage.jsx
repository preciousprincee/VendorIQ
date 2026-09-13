import { Link, Navigate } from 'react-router-dom'
import { BarChart3 } from 'lucide-react'
import { useAuth } from '../context/AuthContext'

function HeroIllustration() {
  // A lightweight, self-contained illustration (no image assets) echoing the
  // "phone showing a rising profit chart" graphic from the design mockup.
  return (
    <div className="relative w-full max-w-[280px] mx-auto aspect-[4/3]">
      <div className="absolute inset-0 bg-brand-50 dark:bg-brand-500/10 rounded-[2.5rem] blur-2xl opacity-70" />
      <div className="relative card p-5 mx-auto mt-6 max-w-[220px] shadow-lg">
        <div className="flex items-center justify-between mb-3">
          <div className="w-16 h-2 rounded-full bg-navy-700" />
          <div className="w-4 h-4 rounded-full bg-brand-50 dark:bg-brand-500/20 border-2 border-brand-500" />
        </div>
        <svg viewBox="0 0 100 40" className="w-full h-14" preserveAspectRatio="none">
          <polyline points="0,32 15,26 30,28 45,14 60,18 75,6 90,10 100,2" fill="none"
            stroke="rgb(var(--c-brand-500))" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
      <div className="absolute bottom-2 left-2 card-hero px-4 py-3 shadow-md">
        <p className="text-[11px] text-white/80">Profit</p>
        <p className="text-lg font-bold font-mono">₦125,600</p>
        <p className="text-[11px] text-white/80">↗ 10%</p>
      </div>
    </div>
  )
}

export default function WelcomePage() {
  const { user } = useAuth()
  if (user) return <Navigate to="/stores" replace />

  return (
    <div className="min-h-screen bg-navy-950 flex flex-col justify-between px-6 py-10">
      <div className="flex-1 flex flex-col justify-center max-w-sm mx-auto w-full text-center">
        <div className="flex items-center gap-2.5 justify-center mb-10">
          <div className="w-9 h-9 bg-brand-500 rounded-xl flex items-center justify-center">
            <BarChart3 size={18} className="text-white" />
          </div>
          <span className="text-xl font-bold text-slate-text tracking-tight">VendorIQ</span>
        </div>

        <HeroIllustration />

        <h1 className="text-2xl font-bold text-slate-text mt-10 leading-tight">
          Know your numbers.<br /><span className="text-brand-500">Grow your business.</span>
        </h1>
        <p className="text-sm text-slate-muted mt-3 leading-relaxed">
          VendorIQ helps small businesses track sales, expenses and profit — so you always know where you stand.
        </p>
      </div>

      <div className="max-w-sm mx-auto w-full space-y-3">
        <Link to="/register" className="btn-primary w-full text-center block">Get Started</Link>
        <Link to="/login" className="btn-ghost w-full text-center block border border-navy-700">Log In</Link>
        <div className="flex items-center justify-center gap-1.5 pt-2">
          <span className="w-5 h-1.5 rounded-full bg-brand-500" />
          <span className="w-1.5 h-1.5 rounded-full bg-navy-700" />
          <span className="w-1.5 h-1.5 rounded-full bg-navy-700" />
        </div>
      </div>
    </div>
  )
}
