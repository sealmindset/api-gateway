'use client'

import { Card, Badge } from '@/components/Card'

const tiers = [
  {
    name: 'Free',
    description: 'Evaluation and development use',
    limits: { second: 1, minute: 10, hour: 500, day: 5000 },
    maxKeys: 2,
    color: 'bg-muted border-border',
    badge: 'default',
  },
  {
    name: 'Standard',
    description: 'Production workloads with moderate throughput',
    limits: { second: 5, minute: 60, hour: 5000, day: 50000 },
    maxKeys: 10,
    color: 'bg-primary/10 border-primary/20',
    badge: 'info',
  },
  {
    name: 'Premium',
    description: 'High-throughput production workloads',
    limits: { second: 20, minute: 300, hour: 25000, day: 250000 },
    maxKeys: 50,
    color: 'bg-success/10 border-success/20',
    badge: 'success',
  },
  {
    name: 'Enterprise',
    description: 'Highest throughput for strategic partners',
    limits: { second: 100, minute: 1000, hour: 100000, day: 1000000 },
    maxKeys: 'Unlimited',
    color: 'bg-accent/10 border-accent/20',
    badge: 'info',
  },
]

export default function PlansPage() {
  return (
    <div className="space-y-6">
      <p className="text-sm text-muted-foreground">
        Rate-limiting tiers applied to API consumers via Kong. These control how many requests each subscriber can make.
      </p>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-4">
        {tiers.map((tier) => (
          <div key={tier.name} className={`rounded-xl border-2 p-6 ${tier.color}`}>
            <div className="mb-4">
              <Badge variant={tier.badge}>{tier.name}</Badge>
            </div>
            <p className="mb-6 text-sm text-muted-foreground">{tier.description}</p>

            <div className="space-y-3">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Rate Limits</h4>
              <div className="space-y-2">
                {Object.entries(tier.limits).map(([window, limit]) => (
                  <div key={window} className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground capitalize">Per {window}</span>
                    <span className="font-mono font-medium text-foreground">{limit.toLocaleString()}</span>
                  </div>
                ))}
              </div>

              <div className="border-t border-border pt-3">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Max API Keys</span>
                  <span className="font-medium text-foreground">{tier.maxKeys}</span>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      <Card>
        <h2 className="mb-2 text-base font-semibold text-foreground">Rate Limiting Policy</h2>
        <p className="text-sm text-muted-foreground">
          Rate limits are enforced at the Kong gateway level using the <code className="rounded bg-muted px-1.5 py-0.5 text-xs">rate-limiting</code> plugin.
          Consumers are assigned to tiers via Kong consumer groups. In local development, limits use the <code className="rounded bg-muted px-1.5 py-0.5 text-xs">local</code> policy
          (in-memory counters). For clustered production deployments, switch to the <code className="rounded bg-muted px-1.5 py-0.5 text-xs">redis</code> policy for shared state.
        </p>
      </Card>
    </div>
  )
}
