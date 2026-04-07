'use client'

import { useEffect, useState } from 'react'
import { Card, StatCard, Table, Badge, Button, EmptyState } from '@/components/Card'

export default function AIPage() {
  const [analyses, setAnalyses] = useState([])
  const [anomalies, setAnomalies] = useState([])
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState('overview')

  useEffect(() => {
    async function load() {
      try {
        const [a, an, s] = await Promise.allSettled([
          fetch('/api/ai/analyses').then((r) => r.json()),
          fetch('/api/ai/anomalies').then((r) => r.json()),
          fetch('/api/ai/stats').then((r) => r.json()),
        ])
        if (a.status === 'fulfilled') setAnalyses(Array.isArray(a.value) ? a.value : a.value.items || [])
        if (an.status === 'fulfilled') setAnomalies(Array.isArray(an.value) ? an.value : an.value.items || [])
        if (s.status === 'fulfilled') setStats(s.value)
      } catch (e) {
        console.error(e)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-32">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary/20 border-t-primary" />
      </div>
    )
  }

  const tabs = [
    { id: 'overview', label: 'Overview' },
    { id: 'anomalies', label: 'Anomaly Detection' },
    { id: 'analyses', label: 'Analysis History' },
    { id: 'config', label: 'Configuration' },
  ]

  return (
    <div className="space-y-6">
      {/* Tabs */}
      <div className="border-b border-border">
        <nav className="-mb-px flex gap-6">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`border-b-2 pb-3 text-sm font-medium transition-colors ${
                activeTab === tab.id
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:border-border hover:text-accent-foreground'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {activeTab === 'overview' && <OverviewTab stats={stats} analyses={analyses} anomalies={anomalies} />}
      {activeTab === 'anomalies' && <AnomaliesTab anomalies={anomalies} />}
      {activeTab === 'analyses' && <AnalysesTab analyses={analyses} />}
      {activeTab === 'config' && <ConfigTab />}
    </div>
  )
}

function OverviewTab({ stats, analyses, anomalies }) {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Total Analyses" value={stats?.total_analyses ?? analyses.length} sub="All time" icon={ChartIcon} />
        <StatCard label="Anomalies Detected" value={stats?.total_anomalies ?? anomalies.length} sub="All time" icon={AlertIcon} />
        <StatCard label="AI Provider" value={stats?.provider ?? 'Anthropic Foundry'} sub="Active provider" icon={BrainIcon} />
        <StatCard label="Sampling Rate" value={`${(stats?.sampling_rate ?? 0.1) * 100}%`} sub="Of total requests" icon={FilterIcon} />
      </div>

      <Card>
        <h2 className="mb-2 text-base font-semibold text-foreground">AI-Powered Intelligence Layer</h2>
        <p className="text-sm text-muted-foreground leading-relaxed">
          The AI layer uses Claude (via Azure AI Foundry) to provide real-time anomaly detection,
          intelligent rate limiting suggestions, smart routing decisions, request/response transformation,
          and automated API documentation generation. Analysis results are cached for performance
          and stored for audit trails.
        </p>
        <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-3">
          {[
            { name: 'Anomaly Detection', status: 'Active' },
            { name: 'Smart Routing', status: 'Available' },
            { name: 'Rate Limit Suggestions', status: 'Active' },
            { name: 'Request Transform', status: 'Available' },
            { name: 'Response Transform', status: 'Available' },
            { name: 'Auto Documentation', status: 'Active' },
          ].map((cap) => (
            <div key={cap.name} className="flex items-center gap-2 rounded-lg border border-border px-3 py-2">
              <span className={`h-2 w-2 rounded-full ${cap.status === 'Active' ? 'bg-success' : 'bg-warning'}`} />
              <span className="text-xs font-medium text-foreground">{cap.name}</span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}

function AnomaliesTab({ anomalies }) {
  if (anomalies.length === 0) {
    return (
      <Card>
        <EmptyState title="No anomalies detected" description="Anomalous requests will appear here when the AI detects suspicious patterns." />
      </Card>
    )
  }

  return (
    <Card className="p-0">
      <Table headers={['Time', 'Score', 'Action', 'Source IP', 'Path', 'Reason']}>
        {anomalies.map((a, i) => (
          <tr key={a.id || i} className="hover:bg-accent">
            <td className="px-4 py-3 text-xs text-muted-foreground">{a.detected_at || a.created_at || '—'}</td>
            <td className="px-4 py-3">
              <span className={`font-mono text-sm font-bold ${
                a.score >= 0.9 ? 'text-destructive' : a.score >= 0.7 ? 'text-warning-foreground' : 'text-muted-foreground'
              }`}>
                {a.score?.toFixed(2) ?? '—'}
              </span>
            </td>
            <td className="px-4 py-3">
              <Badge variant={a.action === 'block' ? 'danger' : a.action === 'header' ? 'warning' : 'default'}>
                {a.action || 'log'}
              </Badge>
            </td>
            <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{a.source_ip || '—'}</td>
            <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{a.path || '—'}</td>
            <td className="px-4 py-3 text-xs text-muted-foreground">{a.reason || '—'}</td>
          </tr>
        ))}
      </Table>
    </Card>
  )
}

function AnalysesTab({ analyses }) {
  if (analyses.length === 0) {
    return (
      <Card>
        <EmptyState title="No analyses yet" description="AI analysis results will appear here as requests are processed." />
      </Card>
    )
  }

  return (
    <Card className="p-0">
      <Table headers={['Time', 'Type', 'Model', 'Cost', 'Duration', 'Status']}>
        {analyses.map((a, i) => (
          <tr key={a.id || i} className="hover:bg-accent">
            <td className="px-4 py-3 text-xs text-muted-foreground">{a.created_at || '—'}</td>
            <td className="px-4 py-3">
              <Badge variant="info">{a.analysis_type || a.type || '—'}</Badge>
            </td>
            <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{a.model || '—'}</td>
            <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
              {a.cost ? `$${a.cost.toFixed(4)}` : '—'}
            </td>
            <td className="px-4 py-3 text-xs text-muted-foreground">
              {a.duration_ms ? `${a.duration_ms}ms` : '—'}
            </td>
            <td className="px-4 py-3">
              <Badge variant={a.status === 'success' ? 'success' : a.status === 'error' ? 'danger' : 'default'}>
                {a.status || 'completed'}
              </Badge>
            </td>
          </tr>
        ))}
      </Table>
    </Card>
  )
}

function ConfigTab() {
  return (
    <div className="space-y-6">
      <Card>
        <h2 className="mb-4 text-base font-semibold text-foreground">AI Provider Configuration</h2>
        <div className="space-y-4">
          <ConfigRow label="Provider" value="anthropic_foundry" description="Azure AI Foundry (default)" />
          <ConfigRow label="Model" value="cogdep-aifoundry-dev-eus2-claude-sonnet-4-5" description="Claude model deployment" />
          <ConfigRow label="Max Cost / Analysis" value="$0.50" description="Budget cap per individual AI call" />
          <ConfigRow label="Sampling Rate" value="10%" description="Percentage of requests analyzed" />
          <ConfigRow label="Anomaly Threshold" value="0.70" description="Score above which requests are flagged" />
          <ConfigRow label="Anomaly Action" value="header" description="block (403), header (X-Anomaly-Score), or log" />
          <ConfigRow label="Cache TTL" value="60s" description="How long AI results are cached" />
          <ConfigRow label="Fail Open" value="true" description="Allow requests if AI endpoint is unreachable" />
        </div>
      </Card>

      <Card>
        <h2 className="mb-4 text-base font-semibold text-foreground">Kong AI Plugin Settings</h2>
        <p className="text-sm text-muted-foreground">
          The <code className="rounded bg-muted px-1.5 py-0.5 text-xs">ai-gateway</code> Kong plugin
          intercepts requests during the access phase for anomaly detection and smart routing,
          and during the body_filter phase for response transformation. Configure via
          Kong Admin API or the plugin configuration in <code className="rounded bg-muted px-1.5 py-0.5 text-xs">kong.yml</code>.
        </p>
      </Card>
    </div>
  )
}

function ConfigRow({ label, value, description }) {
  return (
    <div className="flex items-start justify-between border-b border-border pb-3 last:border-0 last:pb-0">
      <div>
        <p className="text-sm font-medium text-foreground">{label}</p>
        <p className="text-xs text-muted-foreground">{description}</p>
      </div>
      <code className="rounded bg-muted px-2 py-1 text-xs font-medium text-foreground">{value}</code>
    </div>
  )
}

function ChartIcon({ className }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 0 1 3 19.875v-6.75ZM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V8.625ZM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V4.125Z" />
    </svg>
  )
}

function AlertIcon({ className }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
    </svg>
  )
}

function BrainIcon({ className }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 0 0-2.456 2.456ZM16.894 20.567 16.5 21.75l-.394-1.183a2.25 2.25 0 0 0-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 0 0 1.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 0 0 1.423 1.423l1.183.394-1.183.394a2.25 2.25 0 0 0-1.423 1.423Z" />
    </svg>
  )
}

function FilterIcon({ className }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 3c2.755 0 5.455.232 8.083.678.533.09.917.556.917 1.096v1.044a2.25 2.25 0 0 1-.659 1.591l-5.432 5.432a2.25 2.25 0 0 0-.659 1.591v2.927a2.25 2.25 0 0 1-1.244 2.013L9.75 21v-6.568a2.25 2.25 0 0 0-.659-1.591L3.659 7.409A2.25 2.25 0 0 1 3 5.818V4.774c0-.54.384-1.006.917-1.096A48.32 48.32 0 0 1 12 3Z" />
    </svg>
  )
}
