# Administration Guide

## Overview

Platform administrators manage user access, review API submissions, and oversee gateway operations for the API Gateway platform. This guide covers the role-based access control (RBAC) system, approval workflows, and day-to-day administrative tasks.

As an administrator, your primary responsibilities include:

- Assigning roles and permissions to users at **Access Control** (`/rbac`)
- Reviewing and approving API submissions at **API Registry** (`/api-registry`)
- Managing Kong gateway resources at **Gateway** (`/gateway`)
- Overseeing subscribers and API keys at **Subscribers** (`/subscribers`)
- Monitoring platform health through **Grafana** dashboards (`/grafana`)

---

## Two-Layer Access Control Model

The platform enforces access through two independent layers. Both layers must pass for any operation to succeed.

### Layer 1 -- Platform RBAC

Platform RBAC controls who can access admin panel features. It is managed at the **Access Control** page (`/rbac`). Permissions follow a `resource:action` format (e.g., `teams:write`, `api_registry:approve`).

Each user is assigned one or more roles. Each role bundles a set of permissions. When a user attempts an action, the platform checks whether any of their assigned roles grant the required permission.

### Layer 2 -- Team RBAC

Team RBAC controls which resources within a feature a user can touch. It is based on team membership with four levels: **owner**, **admin**, **member**, and **viewer**.

For example, a user with the `api_registry:write` platform permission can only create or edit API registrations belonging to teams they are a member of. A team viewer can see their team's APIs but cannot modify them.

### How the Two Layers Interact

A request must satisfy both layers:

1. The user's platform role must include the required permission (e.g., `api_registry:write`).
2. The user must have sufficient team membership on the resource's owning team (e.g., member or above).

**Exception:** Users with platform-level `super_admin` or `admin` roles bypass team membership checks entirely. They can manage any team's resources regardless of whether they are a member of that team.

---

## Platform Roles

Four default roles are seeded on startup. They cannot be deleted but can be edited.

### super_admin

Full system access. Includes all permissions across every resource, including role management (`roles:write`, `roles:delete`), user management, all team and API operations, and gateway write access.

### admin

Same as `super_admin` with one restriction: cannot manage roles. Specifically, `admin` lacks `roles:write` and `roles:delete`. This prevents non-super administrators from escalating privileges by creating new roles or modifying existing ones.

### operator

Designed for day-to-day operations. Operators can manage subscribers, API keys, and teams, and can submit APIs for review. However, operators **cannot approve APIs** -- they do not have the `api_registry:approve` permission. This enforces separation of duties between teams that build APIs and administrators who approve them.

### viewer

Read-only access to everything. Viewers can browse all platform pages and see data but cannot create, modify, or delete any resources.

### Custom Roles

You can create custom roles with any combination of permissions. This is useful for specialized responsibilities such as a "key manager" role that only has `api_keys:read`, `api_keys:write`, and `subscribers:read`.

---

## Managing Users and Roles

All user and role management happens at **Access Control** (`/rbac`). The page has three tabs.

### Users & Assignments Tab

This tab shows a searchable, sortable table of all platform users. Each row displays the user's name, email, role badges, and last login time.

Users are **auto-provisioned on first login** through Entra ID. When a user logs in for the first time, a user record is created automatically with **no roles assigned**. An administrator must then assign one or more roles before the user can perform any actions.

To manage a user's roles:

1. Navigate to `/rbac`.
2. Find the user in the **Users & Assignments** tab (use the search bar to filter by name).
3. Click **Manage Roles** on the user's row.
4. A panel opens showing:
   - **Current Roles** -- each assigned role displayed as a badge with a **Revoke** button.
   - **Assign Role** -- all unassigned roles displayed as clickable buttons. Click a role to assign it immediately.
5. Changes take effect on the user's next request. No logout/login is required.

The stat cards at the top of the page show total users, roles defined, total permissions, and the count of unassigned users. Monitor the unassigned users count to identify new users who need role assignments.

### Roles Tab

This tab displays role cards in a grid layout. Each card shows:

- The role name with a color-coded badge (`super_admin` in red, `admin` in yellow, `operator` in blue, `viewer` in gray)
- A description
- Permission count and user count
- Permission tags showing up to 8 permissions, with a "+N more" indicator if there are additional permissions
- **Edit** (pencil icon) and **Delete** (trash icon) buttons

To create a new role:

1. Click **+ Create Role** in the top-right corner.
2. Enter a **Role Name** (lowercase with underscores recommended, e.g., `key_manager`).
3. Enter a **Description** explaining the role's purpose.
4. Check permissions in the **Permissions** grid. Permissions are grouped by resource (subscribers, api_keys, teams, etc.), making it easy to grant all actions on a resource or select specific ones.
5. Click **Create Role**.

To edit an existing role:

1. Click the **pencil icon** on the role card.
2. The role form opens pre-populated with the current name (read-only) and permissions.
3. Adjust permissions as needed and click **Update Role**.

To delete a role:

1. Click the **trash icon** on the role card.
2. Confirm the deletion. All user assignments for that role are removed immediately.

### Audit Log Tab

This tab displays a filterable table of all RBAC activity. Each entry includes:

- **Time** -- when the event occurred
- **Action** -- color-coded badges: `access_granted` (green), `access_denied` (red), delete/revoke actions (yellow), and other actions (gray)
- **Resource** -- the resource type involved (e.g., `role`, `user`, `api_registry`)
- **Resource ID** -- the specific resource identifier
- **IP Address** -- the source IP of the request

Use the column filters to narrow down audit entries. Common investigations include filtering by `access_denied` to find users hitting permission walls, or filtering by `resource_type` to see all changes to a specific resource.

---

## Permission Reference

The following table lists every permission available in the platform, organized by resource.

| Resource | Actions | Description |
|---|---|---|
| `subscribers` | `read`, `write`, `delete` | Manage API subscriber records |
| `subscriptions` | `read`, `write`, `delete` | Manage subscriber-to-API subscriptions |
| `api_keys` | `read`, `write`, `delete` | Generate, view, and revoke API keys |
| `roles` | `read`, `write`, `delete` | View and manage platform roles |
| `users` | `read`, `write` | View and manage user accounts |
| `gateway` | `read`, `write` | View and manage Kong gateway resources |
| `audit` | `read` | View audit log entries |
| `ai` | `read`, `analyze`, `rate-limit`, `route`, `transform`, `documentation` | AI-powered features: traffic analysis, rate limit recommendations, smart routing, request/response transformation, auto-documentation |
| `teams` | `read`, `write`, `delete` | Manage teams and team membership |
| `api_registry` | `read`, `write`, `delete`, `approve` | Register APIs, manage registrations, and approve/reject submissions |

Permissions follow the format `resource:action`. For example, `api_registry:approve` grants the ability to approve or reject API submissions. The `approve` action on `api_registry` is deliberately separate from `write` to enforce separation of duties.

---

## API Review Workflow

The API review workflow ensures that all APIs exposed through the gateway meet organizational standards before they reach consumers.

### Lifecycle States

An API registration moves through these states:

```
Draft --> Pending Review --> Approved --> Active
                  |                         |
                  v                         v
              Rejected                 Deprecated --> Retired
```

### Administrator Review Process

1. **Identify pending submissions.** Navigate to **API Registry** (`/api-registry`). Use the **Pending Review** filter button or check the "Pending Review" stat card at the top. The count indicates how many APIs are awaiting review.

2. **Review the submission.** For each pending API, verify the following:
   - **Upstream URL** -- Is the backend service reachable and correct? Ensure it uses HTTPS where required.
   - **Gateway Path** -- Does the proposed path conflict with existing routes? Check for overlapping paths in the table.
   - **Auth Type** -- Is the selected authentication method (API Key, OAuth 2.0, JWT, None) appropriate for this API's sensitivity level?
   - **Rate Limits** -- Are the per-second, per-minute, and per-hour limits reasonable? Defaults are 5/s, 100/m, 3000/h.
   - **Team ownership** -- Is the correct team listed as the owner?

3. **Take action.** On the API's row, click one of:
   - **Approve** -- Moves the API to "Approved" status, ready for activation.
   - **Reject** -- A prompt appears asking for a rejection reason. Enter clear notes explaining what needs to change. The submitting team will see these notes.

4. **Activate the API.** After approval, an **Activate** button appears on the API's row. Clicking it provisions the API in Kong. Activation creates the following Kong resources:
   - A **Kong service** pointing to the upstream URL
   - A **Kong route** mapped to the gateway path
   - A **rate-limiting plugin** configured with the specified limits
   - An **auth plugin** matching the selected auth type (key-auth, oauth2, jwt, or none)
   - A **prometheus plugin** for metrics collection

5. **Post-activation management.** If issues are discovered after activation:
   - **Deprecate** -- The API remains functional but is flagged as deprecated. Consumers are signaled to migrate away. Use this when a replacement API is available or planned.
   - **Retire** -- Removes the API's Kong resources (service, route, plugins). The registration record remains for audit purposes. Only deprecated APIs can be retired.

---

## Kong Gateway Management

Direct gateway management is available at **Gateway** (`/gateway`). This page provides visibility into and control over Kong's resources.

### Viewing Resources

The gateway page shows:

- **Services** -- Backend services registered in Kong, including their URL, protocol, and status
- **Routes** -- Path-to-service mappings with their methods and hosts
- **Plugins** -- Active plugins across services (rate-limiting, auth, prometheus, etc.)
- **Consumers** -- Kong consumers that correspond to your platform subscribers

### Managing Plugins

Administrators with `gateway:write` permission can:

- Create new plugins on specific services or globally
- Update plugin configurations (e.g., adjusting rate limit values)
- Delete plugins that are no longer needed

### Managing Consumers

While consumers are typically created automatically through the subscriber workflow, you can also create them manually through the gateway page when needed for special cases.

### Health Monitoring

The gateway page displays Kong's health status and database connectivity. Check this page if you suspect gateway issues before investigating deeper in Grafana.

---

## Subscriber and Key Management

Manage subscribers at **Subscribers** (`/subscribers`).

### Creating Subscribers

1. Navigate to `/subscribers`.
2. Click **+ Create Subscriber**.
3. Fill in the subscriber details (name, contact information, associated team).
4. Save the subscriber record.

### Generating API Keys

1. Open a subscriber's detail view.
2. Click **Generate Key**.
3. The key is created and synced to a Kong consumer automatically.
4. Copy and securely share the key with the subscriber. The full key is only shown once.

### Rotating Keys

Key rotation revokes the old key and creates a new one with the same configuration:

1. Open the subscriber's key list.
2. Click **Rotate** on the key to be replaced.
3. Confirm the rotation. The old key is immediately invalidated.
4. Distribute the new key to the subscriber.

### Rate Limit Overrides

To set custom rate limits for a specific subscriber (overriding the API's default limits):

1. Open the subscriber's detail view.
2. Locate the rate limit override section.
3. Enter custom per-second, per-minute, and per-hour values.
4. Save. The override is applied in Kong immediately.

---

## Monitoring and Alerting

### Grafana Dashboards

Grafana is available at `/grafana` and includes pre-configured dashboards:

| Dashboard | What It Shows |
|---|---|
| **Gateway Overview** | Request volume, latency percentiles, error rates, and upstream response times across all services |
| **Auth** | Authentication success/failure rates by method (key-auth, OAuth, JWT), top denied consumers |
| **Rate Limiting** | Rate limit hit counts by service and consumer, near-limit warnings |
| **Infrastructure** | Kong node CPU/memory, database connections, PostgreSQL performance |
| **AI** | AI feature usage: analysis requests, routing decisions, transformation counts |
| **Security** | ZAP scan results, vulnerability trends, TLS certificate expiry status |

### Prometheus Alerts

Prometheus fires alerts to AlertManager based on predefined rules. Key alerts to monitor:

| Alert | Severity | What It Means |
|---|---|---|
| `KongHighErrorRate` | Warning/Critical | The percentage of 5xx responses has exceeded the threshold. Investigate upstream service health. |
| `KongAuthFailureSpike` | Warning | A sudden increase in authentication failures, which may indicate credential stuffing or misconfigured consumers. |
| `ZAPCriticalVulnerability` | Critical | An automated ZAP security scan has found a critical vulnerability. Review the security dashboard immediately. |

Configure AlertManager notification channels (email, Slack, PagerDuty) in the alertmanager configuration file to ensure the right people are notified.

---

## Entra ID App Registration Setup

The platform uses Microsoft Entra ID (Azure AD) for single sign-on. Follow these steps to configure the app registration.

### 1. Create the App Registration

1. Sign in to the [Azure AD portal](https://portal.azure.com/#view/Microsoft_AAD_IAM/ActiveDirectoryMenuBlade/~/RegisteredApps).
2. Click **New registration**.
3. Enter a name (e.g., "API Gateway Portal").
4. Under **Supported account types**, select the option appropriate for your organization (typically "Accounts in this organizational directory only").
5. Click **Register**.

### 2. Configure the Redirect URI

1. In the app registration, go to **Authentication**.
2. Click **Add a platform** and select **Web**.
3. Set the redirect URI to:
   ```
   https://<portal-host>/auth/callback
   ```
   Replace `<portal-host>` with your portal's hostname (e.g., `gateway.yourcompany.com`).
4. Save.

### 3. Note the IDs

From the app registration's **Overview** page, copy:

- **Application (client) ID**
- **Directory (tenant) ID**

### 4. Create a Client Secret

1. Go to **Certificates & secrets**.
2. Click **New client secret**.
3. Enter a description and select an expiration period.
4. Click **Add** and immediately copy the secret value. It is only shown once.

### 5. Set Environment Variables

Configure the following environment variables in your deployment:

```
ENTRA_TENANT_ID=<your-tenant-id>
ENTRA_CLIENT_ID=<your-client-id>
ENTRA_CLIENT_SECRET=<your-client-secret>
```

### 6. Required Scopes

The platform requests the following scopes during authentication:

- `openid` -- Required for OpenID Connect sign-in
- `email` -- Provides the user's email address
- `profile` -- Provides the user's display name

No additional API permissions need to be configured in the app registration unless your organization requires admin consent for these basic scopes.

### Secret Rotation

Client secrets expire based on the period selected during creation. Set a calendar reminder to rotate the secret before expiration:

1. Create a new client secret in the Azure portal.
2. Update the `ENTRA_CLIENT_SECRET` environment variable in your deployment.
3. Restart the portal service.
4. Verify login works, then delete the old secret from Azure.
