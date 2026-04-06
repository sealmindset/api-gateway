'use client'

import { usePathname } from 'next/navigation'

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
    <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-gray-200 bg-white/80 px-8 backdrop-blur">
      <h1 className="text-lg font-semibold text-gray-900">{title}</h1>
      <div className="flex items-center gap-4">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-medium text-green-800">
          <span className="h-1.5 w-1.5 rounded-full bg-green-500" />
          Healthy
        </span>
        <div className="h-8 w-8 rounded-full bg-brand-600 text-center text-sm font-semibold leading-8 text-white">
          A
        </div>
      </div>
    </header>
  )
}
