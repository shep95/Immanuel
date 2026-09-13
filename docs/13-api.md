# 30. API Architecture

**Purpose.** Expose the knowledge infrastructure through a **versioned** API, with clean
separation between public, internal, and administrative surfaces.

## 30.1 API surfaces (separated)

| Surface | Audience | Authn | Notes |
|---------|----------|-------|-------|
| Public API | Frontend, external consumers | API key / OAuth | Rate-limited, read-mostly, versioned. |
| Internal API | Inter-service calls | mTLS / service identity | Not internet-exposed. |
| Administrative API | Operators/admin console | MFA + admin identity | Config, policy, taxonomy governance, reprocessing. |

## 30.2 Public API endpoints (minimum)

- **Search API** — faceted search across all indexes.
- **Document API** — retrieve documents, versions, structure.
- **Source API** — source registry views (public-safe fields).
- **Domain API** — ontology tree navigation.
- **Entity API** — entity pages + mentions.
- **Claim API** — claims, support/contradiction, evidence.
- **Graph API** — bounded graph traversal.
- **Pattern API** — pattern library (approved patterns + provenance).
- **Version API** — temporal/version history & diffs.
- **Metadata API** — object/document metadata (privacy-filtered).
- **System status API** — health/coverage stats (public-safe subset).

Concrete request/response schemas: [`docs/28-schemas.md`](28-schemas.md).

## 30.3 Cross-cutting API concerns

- **Authentication** — API keys and/or OAuth2 client credentials; per-key identity.
- **Authorization** — scopes per endpoint; admin endpoints require admin scope + MFA.
- **Rate limiting** — token-bucket per key + global; separate budgets for expensive
  endpoints (graph, search).
- **Pagination** — cursor-based, bounded page size; no unbounded offset paging.
- **Filtering & sorting** — declarative, validated against allowlists.
- **Versioning** — URI-versioned (`/v1/…`) + deprecation policy; breaking changes → new
  major version, old version supported for a documented window.
- **Error handling** — consistent problem+json envelope with stable error codes.
- **Request validation** — strict schema validation; input size/complexity limits.
- **Response schemas** — versioned, documented (OpenAPI); every response includes
  provenance/epistemic tags where relevant.
- **Observability** — per-endpoint latency/error/rate metrics; request tracing.

## 30.4 Standard error envelope

```json
{
  "error": {
    "code": "RATE_LIMITED",
    "message": "Request rate exceeded for this API key.",
    "details": { "retry_after_s": 12 },
    "request_id": "req_01J9...",
    "api_version": "v1"
  }
}
```

Standard codes: `INVALID_REQUEST` · `UNAUTHENTICATED` · `FORBIDDEN` · `NOT_FOUND` ·
`RATE_LIMITED` · `QUERY_TOO_COMPLEX` · `PAYLOAD_TOO_LARGE` · `CONFLICT` ·
`UNAVAILABLE` · `INTERNAL`.

## 30.5 API security (see §62)

- Authentication + authorization on every endpoint (deny by default).
- Rate limiting, request validation, input size limits.
- **Query complexity limits** — pathological searches and deep graph traversals are
  rejected with `QUERY_TOO_COMPLEX` before they touch the stores.
- Pagination caps; abuse detection (per-key anomaly detection, deterministic thresholds).
- Full audit logging of admin API calls.

## 30.6 Design invariants

- API responses **preserve epistemic separation**: claims carry status/evidence/confidence;
  results carry the separated ranking sub-scores (§29); nothing is presented as adjudicated
  truth.
- The API is a **thin, stable contract** over internal services so the frontend and
  external consumers are insulated from internal changes (replaceability seam).

## 30.7 Failure modes, scaling, recovery

- **Failure:** downstream store slow/unavailable → endpoint returns `UNAVAILABLE` with
  `Retry-After`, and read endpoints serve from cache where safe.
- **Scaling:** stateless API nodes behind the gateway; scale horizontally; expensive
  endpoints isolated so they can't starve cheap ones.
- **Recovery:** API is stateless; recovery is redeploy + reconnect; no data lives here.
