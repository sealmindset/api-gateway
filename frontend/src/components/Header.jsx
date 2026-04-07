'use client'

import { usePathname } from 'next/navigation'
import { ModeToggle } from '@/components/mode-toggle'

const titles = [
  ['/dashboard', 'Dashboard'],
  ['/subscribers', 'Subscribers'],
  ['/api-keys', 'API Keys'],
  ['/plans', 'Rate Limit Tiers'],
  ['/ai/prompts', 'Prompt Management'],
  ['/ai', 'AI Analysis'],
  ['/gateway', 'Gateway Services'],
  ['/settings', 'Settings'],
]

export default function Header() {
  const pathname = usePathname()
  const title = titles.find(([k]) => pathname?.startsWith(k))?.[1] || 'Dashboard'

  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border bg-background px-4">
      <h1 className="text-lg font-semibold text-foreground">{title}</h1>
      <div className="flex-1" />
      <div className="flex items-center gap-3">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-success/10 px-2.5 py-0.5 text-xs font-medium text-success">
          <span className="h-1.5 w-1.5 rounded-full bg-success" />
          Healthy
        </span>
        <ModeToggle />
        <div className="h-8 w-8 rounded-full bg-primary text-center text-sm font-semibold leading-8 text-primary-foreground">
          A
        </div>
      </div>
    </header>
  )
}
