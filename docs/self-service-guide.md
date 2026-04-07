# API Gateway Self-Service Guide

Welcome to the API Gateway platform. This guide walks you through the complete lifecycle of registering, submitting, and managing your APIs -- from first draft to live traffic. Everything described here is done through the admin UI. No tickets, no waiting on other teams. You drive the process.

---

## Overview

The API Gateway platform gives every team the tools to expose their services through a centralized, managed gateway powered by Kong. The workflow is straightforward:

1. Create your team in the portal.
2. Register your API with its upstream details, auth, and rate limits.
3. Submit it for review by a platform admin.
4. Once approved and activated, your API is live and routable through the gateway.

All of this happens at the **API Registry** page (`/api-registry`). You can manage teams at `/teams`, subscribers at `/subscribers`, and API keys at `/api-keys`.

---

## Step 1: Create Your Team

Navigate to `/teams` in the admin UI.

### Creating the team

1. Click **"+ Create Team"** in the upper right.
2. Fill in the form:
   - **Team Name** -- A human-readable name for your team (e.g., "Weather Services Team").
   - **Slug** -- Auto-generated from the team name as a lowercase, hyphenated identifier (e.g., `weather-services-team`). You can override it if needed.
   - **Contact Email** -- The team inbox or point-of-contact email for platform notifications.
   - **Description** -- A brief summary of what your team owns or is responsible for.
3. Click **Save**. You are automatically assigned as the **owner** of the new team.

### Adding team members

1. On the `/teams` page, click your team's name to open the detail view.
2. Click **"+ Add Member"**.
3. Enter the person's **user ID** and select their **role**:

| Role     | What they can do                                                       |
|----------|------------------------------------------------------------------------|
| **Owner**  | Full control over the team, including deleting it. Can do everything an admin can do. |
| **Admin**  | Edit team details, manage members, and manage all of the team's APIs.  |
| **Member** | Create and edit APIs, submit them for review.                          |
| **Viewer** | Read-only access to team details and APIs.                             |

Roles are hierarchical: Owner > Admin > Member > Viewer. Assign the least privilege that makes sense for each person.

---

## Step 2: Register an API

Navigate to `/api-registry` in the admin UI.

1. Click **"+ Register API"**.
2. Fill in the registration form:

| Field               | Description                                                                                     | Example                                      |
|---------------------|-------------------------------------------------------------------------------------------------|----------------------------------------------|
| **API Name**        | A human-readable name for the API.                                                              | Weather Forecast API                         |
| **Slug**            | A URL-safe identifier, auto-generated from the name.                                            | `weather-forecast-api`                       |
| **Team**            | Select the team that owns this API. You must be a member of the team.                           | Weather Services Team                        |
| **Description**     | What does this API do? Keep it concise but informative.                                         | Returns 7-day forecasts by ZIP code.         |
| **Upstream URL**    | The internal URL where the actual service is running.                                           | `https://internal-service.company.com/v1`    |
| **Protocol**        | The protocol used to communicate with the upstream. Options: HTTP, HTTPS, gRPC, gRPCs.         | HTTPS                                        |
| **Gateway Path**    | The public path through Kong. Defaults to `/api/{slug}`.                                        | `/api/weather`                               |
| **API Type**        | The style of API. Options: REST, GraphQL, gRPC, WebSocket.                                      | REST                                         |
| **Auth Type**       | How consumers authenticate. Options: API Key (default), OAuth 2.0, JWT, None.                   | API Key                                      |
| **Version**         | The version of this API.                                                                        | `v1`                                         |
| **Health Check Path** | An endpoint the platform will poll to monitor availability. Defaults to `/health`.            | `/health`                                    |
| **Rate Limits**     | Throttle limits per consumer: requests per second, per minute, and per hour.                    | 10/s, 200/min, 5000/hr                       |
| **Documentation URL** | A link to your API's documentation (Swagger, Redoc, wiki page, etc.).                        | `https://docs.company.com/weather-api`       |

3. Click **Save**.

Your API is now in **draft** status. It is not visible to consumers and nothing has been provisioned in Kong. You can come back and edit it as many times as you like while it remains a draft.

---

## Step 3: Submit for Review

When your draft API is ready:

1. Go to `/api-registry` and find your API in the list.
2. Click the **"Submit"** button on the API row.
3. The status changes to **pending_review**.

A platform admin will review your submission. There are two possible outcomes:

- **Approved** -- The admin is satisfied with the configuration. Status moves to **approved** and the API is ready for activation.
- **Rejected** -- The admin leaves review notes explaining what needs to change. You will see these notes on the API detail page. To fix it:
  1. Edit the API (status returns to **draft**).
  2. Address the feedback.
  3. Re-submit.

There is no limit on how many times you can re-submit.

---

## Step 4: Activation

Activation is performed by a **platform admin**. Once your API is in the **approved** state:

1. An admin clicks **"Activate"** on the API.
2. The platform provisions the following in Kong:
   - A **service** pointing to your upstream URL.
   - A **route** mapped to your gateway path.
   - A **rate-limiting plugin** configured with the per-second, per-minute, and per-hour limits you specified.
   - An **auth plugin** matching your selected auth type (key-auth, oauth2, or jwt).
   - A **prometheus plugin** for per-consumer metrics collection.
3. Status changes to **active**.

Your API is now live and reachable at:

```
https://<gateway-host>/<gateway-path>
```

For example, if your gateway path is `/api/weather`, consumers will reach your service at `https://<gateway-host>/api/weather`.

---

## Step 5: Managing Your Active API

Navigate to `/api-registry/{id}` to view the detail page for any registered API.

### What you will see

- **Upstream config** -- The upstream URL, protocol, and health check path.
- **Gateway config** -- The gateway path, API type, and version.
- **Kong IDs** -- The provisioned Kong service ID and route ID (useful for debugging).
- **Active plugins** -- Which Kong plugins are attached (rate-limiting, auth, prometheus, etc.).
- **Timeline** -- A chronological log of status changes, reviews, and edits.
- **Review information** -- If the API was previously rejected or has review notes, they appear here.
- **Usage metrics** -- Service status, gateway path, protocols in use, and active plugins at a glance.

### Deprecation and retirement

If your API needs to be taken down, a platform admin can transition it through two stages:

- **Deprecate** -- The API remains accessible, but signals to consumers that they should migrate to a replacement. Use this when you have a new version ready but need to give consumers time to switch.
- **Retire** -- The API is removed from Kong entirely. Routes and services are deprovisioned. Traffic will no longer be routed.

A retired API can be **reactivated** if needed.

---

## API Lifecycle Diagram

The full lifecycle of an API registration looks like this:

```
draft -> pending_review -> approved -> active -> deprecated -> retired
              |                                      |
              v                                      v
          rejected -> draft (re-edit)             active (reactivate)
```

Every API starts as a **draft**. It moves forward through review and activation, and can be deprecated or retired at the end of its life. Rejected APIs return to draft for correction. Deprecated APIs can be reactivated if the decision is reversed.

---

## Managing Subscribers and API Keys

Navigate to `/subscribers` and `/api-keys` in the admin UI.

### Subscribers

Subscribers represent the external consumers of your APIs -- partner teams, third-party integrations, or client applications.

To create a subscriber:

1. Go to `/subscribers` and click **"+ Create Subscriber"**.
2. Fill in:
   - **Name** -- The subscriber's name or application name.
   - **Email** -- Contact email.
   - **Organization** -- The company or team the subscriber belongs to.
   - **Tier** -- The service tier: Free, Standard, Premium, or Enterprise.
3. Click **Save**.

### API keys

Each subscriber authenticates using API keys that you generate for them.

1. From the subscriber detail page, click **"+ Generate Key"**.
2. The key is displayed **once** on creation. Copy it and share it securely with the subscriber. The platform stores only a **SHA256 hash** of the key -- the original cannot be recovered.
3. Keys are automatically synced to Kong as consumer credentials.

Each key can optionally include:

- **Scopes** -- Restrict which APIs or endpoints the key grants access to.
- **Rate limits** -- Per-key overrides on top of the plan-level limits.
- **Expiration** -- An automatic expiry date after which the key stops working.

A subscriber can have **multiple keys** (for example, separate keys for staging and production).

### Rotating and revoking keys

- **Rotate** -- Creates a new key with the same configuration and immediately deactivates the old one. Use this for scheduled credential rotation.
- **Revoke** -- Deactivates a key immediately. Use this if a key is compromised or no longer needed.

---

## Viewing Plans and Subscriptions

Navigate to `/plans` in the admin UI.

### Plans

Plans define the rate limits and allowed endpoints for a given tier of service. They provide a standardized way to control what each subscriber can do.

### Subscriptions

A subscription links a subscriber to a plan. You can apply optional overrides at the subscription level if a particular subscriber needs different limits than what the plan defines.

### Default tier-based rate limits

| Tier         | Per Second | Per Minute | Per Hour   |
|--------------|------------|------------|------------|
| **Free**       | 1          | 30         | 500        |
| **Standard**   | 5          | 100        | 3,000      |
| **Premium**    | 20         | 500        | 15,000     |
| **Enterprise** | 100        | 3,000      | 100,000    |

These are starting points. Subscription-level overrides can adjust limits for individual subscribers when justified.

---

## Tips and Best Practices

- **Use descriptive slugs.** Pick slugs that match your team and service naming conventions. They show up in gateway paths and logs, so clarity matters.
- **Start with conservative rate limits.** It is much easier to increase limits than to deal with the fallout of an overloaded upstream. You can always raise them later.
- **Always provide a health check endpoint.** The platform uses it to monitor your service. If you do not have one, add a simple `/health` route that returns `200 OK`.
- **Document your API before submitting.** Reviewers will check for a documentation URL. Having thorough docs speeds up the approval process.
- **Choose the right auth type.** Use **API Key** (`key-auth`) for straightforward service-to-service integrations. Use **OAuth 2.0** for consumer-facing APIs that need delegated authorization. Use **JWT** when you already have a token issuer in your infrastructure. Use **None** only for truly public, unauthenticated endpoints.
- **Keep your team membership current.** Remove people who leave the team and assign appropriate roles. The principle of least privilege applies here too.
- **Check the timeline on your API detail page.** It is the single source of truth for what happened and when -- status changes, reviews, edits, and activations are all logged there.
