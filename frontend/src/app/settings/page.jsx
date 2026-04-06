'use client'

import { Card, Badge } from '@/components/Card'

export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <Card>
        <h2 className="mb-4 text-base font-semibold text-gray-900">Service Endpoints</h2>
        <div className="space-y-3">
          <EndpointRow name="Kong Proxy" url="http://localhost:8800" status="healthy" />
          <EndpointRow name="Kong Admin API" url="http://localhost:8801" status="healthy" />
          <EndpointRow name="Admin Panel API" url="http://localhost:8880" status="healthy" />
          <EndpointRow name="Prometheus" url="http://localhost:9190" status="healthy" />
          <EndpointRow name="Grafana" url="http://localhost:3200" status="healthy" />
          <EndpointRow name="Cribl Stream" url="http://localhost:9421" status="healthy" />
        </div>
      </Card>

      <Card>
        <h2 className="mb-4 text-base font-semibold text-gray-900">Authentication</h2>
        <div className="space-y-3">
          <SettingRow label="OIDC Provider" value="Microsoft Entra ID" />
          <SettingRow label="Auth Methods" value="OAuth2, API Key, Basic Auth" />
          <SettingRow label="RBAC" value="Database-driven with Redis cache" />
          <SettingRow label="Session TTL" value="60 minutes" />
        </div>
      </Card>

      <Card>
        <h2 className="mb-4 text-base font-semibold text-gray-900">Infrastructure</h2>
        <div className="space-y-3">
          <SettingRow label="Database" value="PostgreSQL 16" />
          <SettingRow label="Cache" value="Redis 7" />
          <SettingRow label="Gateway" value="Kong 3.9 CE" />
          <SettingRow label="Monitoring" value="Prometheus + Grafana" />
          <SettingRow label="Log Routing" value="Cribl Stream 4.5" />
          <SettingRow label="AI Provider" value="Azure AI Foundry (Claude)" />
        </div>
      </Card>

      <Card>
        <h2 className="mb-4 text-base font-semibold text-gray-900">Quick Links</h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <QuickLink name="Kong Admin API" href="http://localhost:8801" />
          <QuickLink name="FastAPI Docs (Swagger)" href="http://localhost:8880/docs" />
          <QuickLink name="FastAPI Docs (ReDoc)" href="http://localhost:8880/redoc" />
          <QuickLink name="Prometheus" href="http://localhost:9190" />
          <QuickLink name="Grafana Dashboards" href="http://localhost:3200" />
          <QuickLink name="Cribl Stream" href="http://localhost:9421" />
        </div>
      </Card>
    </div>
  )
}

function EndpointRow({ name, url, status }) {
  return (
    <div className="flex items-center justify-between border-b border-gray-100 pb-3 last:border-0 last:pb-0">
      <div>
        <p className="text-sm font-medium text-gray-900">{name}</p>
        <a href={url} target="_blank" rel="noopener noreferrer" className="text-xs text-brand-600 hover:underline">{url}</a>
      </div>
      <Badge variant={status === 'healthy' ? 'success' : 'danger'}>{status}</Badge>
    </div>
  )
}

function SettingRow({ label, value }) {
  return (
    <div className="flex items-center justify-between border-b border-gray-100 pb-3 last:border-0 last:pb-0">
      <span className="text-sm text-gray-600">{label}</span>
      <span className="text-sm font-medium text-gray-900">{value}</span>
    </div>
  )
}

function QuickLink({ name, href }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="flex items-center gap-2 rounded-lg border border-gray-200 px-4 py-3 text-sm font-medium text-gray-700 transition-colors hover:border-brand-300 hover:bg-brand-50 hover:text-brand-700"
    >
      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 6H5.25A2.25 2.25 0 0 0 3 8.25v10.5A2.25 2.25 0 0 0 5.25 21h10.5A2.25 2.25 0 0 0 18 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25" />
      </svg>
      {name}
    </a>
  )
}
