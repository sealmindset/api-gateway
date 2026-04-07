import { cn } from '@/lib/utils'

export function Card({ className, children }) {
  return (
    <div className={cn('rounded-xl border border-border bg-card p-5 text-card-foreground shadow-sm transition-shadow hover:shadow-md', className)}>
      {children}
    </div>
  )
}

export function StatCard({ label, value, sub, trend, icon: Icon }) {
  return (
    <Card>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm font-medium text-muted-foreground">{label}</p>
          <p className="mt-1 text-2xl font-bold text-foreground">{value}</p>
          {sub && <p className="mt-1 text-xs text-muted-foreground">{sub}</p>}
        </div>
        {Icon && (
          <div className="rounded-lg bg-primary/10 p-2.5">
            <Icon className="h-5 w-5 text-primary" />
          </div>
        )}
      </div>
      {trend !== undefined && (
        <p className={cn('mt-3 text-xs font-medium', trend >= 0 ? 'text-success' : 'text-destructive')}>
          {trend >= 0 ? '+' : ''}{trend}% from last hour
        </p>
      )}
    </Card>
  )
}

export function Badge({ children, variant = 'default', className }) {
  const styles = {
    default: 'bg-secondary text-secondary-foreground',
    success: 'bg-success/15 text-success',
    warning: 'bg-warning/15 text-warning-foreground',
    danger: 'bg-destructive/15 text-destructive',
    destructive: 'bg-destructive/15 text-destructive',
    info: 'bg-primary/15 text-primary',
    primary: 'bg-primary/15 text-primary',
  }
  return (
    <span className={cn('inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium', styles[variant], className)}>
      {children}
    </span>
  )
}

export function Table({ headers, children }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-border">
            {headers.map((h) => (
              <th key={h} className="whitespace-nowrap px-4 py-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border">{children}</tbody>
      </table>
    </div>
  )
}

export function EmptyState({ title, description }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="mb-3 rounded-full bg-muted p-4">
        <svg className="h-8 w-8 text-muted-foreground" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 7.5l-.625 10.632a2.25 2.25 0 01-2.247 2.118H6.622a2.25 2.25 0 01-2.247-2.118L3.75 7.5m6 4.125l2.25 2.25m0 0l2.25 2.25M12 13.875l2.25-2.25M12 13.875l-2.25 2.25M3.375 7.5h17.25c.621 0 1.125-.504 1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125z" />
        </svg>
      </div>
      <h3 className="text-sm font-semibold text-foreground">{title}</h3>
      <p className="mt-1 text-sm text-muted-foreground">{description}</p>
    </div>
  )
}

export function Button({ children, variant = 'primary', size = 'md', className, ...props }) {
  const base = 'inline-flex items-center justify-center rounded-lg font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed'
  const variants = {
    primary: 'bg-primary text-primary-foreground hover:bg-primary/90',
    secondary: 'border border-input bg-background text-foreground hover:bg-accent hover:text-accent-foreground',
    danger: 'bg-destructive text-destructive-foreground hover:bg-destructive/90',
  }
  const sizes = {
    sm: 'px-3 py-1.5 text-xs',
    md: 'px-4 py-2 text-sm',
    lg: 'px-5 py-2.5 text-sm',
  }
  return (
    <button className={cn(base, variants[variant], sizes[size], className)} {...props}>
      {children}
    </button>
  )
}
