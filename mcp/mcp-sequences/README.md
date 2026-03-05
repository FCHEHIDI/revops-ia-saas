# mcp-sequences

MCP server for outreach sequence management in the RevOps IA SaaS platform.

## Overview

`mcp-sequences` exposes tools to create, manage, and analyze outreach sequences (email cadences, LinkedIn outreach, multi-channel sequences). It is a **stateless**, **isolated**, **multi-tenant** microservice backed by PostgreSQL with Row-Level Security.

## Architecture

- **Transport**: stdio (default) or SSE (`MCP_TRANSPORT=sse`)
- **Auth**: Tenant isolation via `validate_tenant()` + RLS (`app.current_tenant_id`)
- **Audit**: Every tool call writes a non-blocking audit event to `audit_events`
- **Port** (SSE): `0.0.0.0:3004` (override with `SSE_BIND_ADDR`)

## Environment Variables

| Variable        | Required | Default  | Description                        |
|-----------------|----------|----------|------------------------------------|
| `DATABASE_URL`  | Yes      | —        | PostgreSQL connection string        |
| `MCP_TRANSPORT` | No       | `stdio`  | `stdio` or `sse`                   |
| `SSE_BIND_ADDR` | No       | `0.0.0.0:3004` | Bind address for SSE transport |
| `LOG_LEVEL`     | No       | `info`   | Tracing filter                     |

## Tools

### Sequences CRUD

#### `create_sequence`
Creates a new outreach sequence.

- **Permission**: `sequences:write`
- **Input**:
  - `tenant_id` (uuid, required)
  - `user_id` (uuid, required)
  - `name` (string, required)
  - `description` (string, optional)
  - `steps` (array, required, min 1 item):
    - `step_type`: `email` | `linkedin_message` | `task` | `call` | `wait`
    - `delay_days`: integer >= 0
    - `delay_hours`: integer in [0, 23]
    - `template_id` (uuid, optional)
    - `subject` (string, optional)
    - `body_template` (string, optional)
  - `exit_conditions` (array, optional)
  - `tags` (string[], optional)
- **Output**: `{ sequence_id, steps_count, created_at }`
- **Errors**: `ValidationError` (empty steps, invalid delay, empty name)

#### `update_sequence`
Updates sequence metadata. Blocked by active enrollments unless `force=true`.

- **Permission**: `sequences:write`
- **Input**: `{ tenant_id, user_id, sequence_id, name?, description?, tags?, force }`
- **Output**: `{ updated_at, warning? }`
- **Errors**: `SequenceHasActiveEnrollments { count }`, `NotFound`, `ValidationError`

#### `delete_sequence`
Permanently deletes a sequence. With `force=true`, unenrolls active contacts first.

- **Permission**: `sequences:delete`
- **Input**: `{ tenant_id, user_id, sequence_id, force }`
- **Output**: `{ deleted_at, unenrolled_count }`
- **Errors**: `SequenceHasActiveEnrollments { count }`, `NotFound`

#### `get_sequence`
Retrieves a sequence with all its steps.

- **Permission**: `sequences:read`
- **Input**: `{ tenant_id, user_id?, sequence_id }`
- **Output**: `{ sequence: Sequence }` (includes full steps array)
- **Errors**: `NotFound`, `TenantForbidden`

#### `list_sequences`
Lists sequences with optional filters.

- **Permission**: `sequences:read`
- **Input**: `{ tenant_id, user_id?, status?, tags?, limit?, offset? }`
- **Output**: `{ sequences: SequenceSummary[], total }`

---

### Enrollment

#### `enroll_contact`
Enrolls a contact into an active sequence.

- **Permission**: `sequences:write`
- **Input**: `{ tenant_id, user_id, sequence_id, contact_id, start_at?, custom_variables?, override_if_enrolled }`
- **Checks** (sequential):
  1. Tenant validation
  2. Sequence must be `active` → `SequenceNotActive`
  3. Contact must exist → `ContactNotFound`
  4. If already enrolled and `override_if_enrolled=false` → `AlreadyEnrolled { enrollment_id }`
  5. If `override_if_enrolled=true` → previous enrollment is set to `unenrolled`
- **Output**: `{ enrollment_id, starts_at, first_step_at }`

#### `unenroll_contact`
Unenrolls a contact by enrollment ID.

- **Permission**: `sequences:write`
- **Input**: `{ tenant_id, user_id, enrollment_id, reason }` — reason: `replied` | `converted` | `manual` | `bounced`
- **Output**: `{ unenrolled_at, steps_completed, steps_remaining }`
- **Errors**: `NotFound`, `ValidationError` (invalid reason)

#### `list_enrollments`
Lists enrollments for a sequence.

- **Permission**: `sequences:read`
- **Input**: `{ tenant_id, user_id?, sequence_id, status?, limit?, offset? }`
- **Output**: `{ enrollments: EnrollmentSummary[], total }`

---

### Execution

#### `pause_sequence`
Pauses a sequence and all its active enrollments.

- **Permission**: `sequences:write`
- **Input**: `{ tenant_id, user_id, sequence_id, reason? }`
- **SQL**:
  1. `UPDATE sequences SET status='paused'`
  2. `UPDATE enrollments SET status='paused' WHERE status='active'`
- **Output**: `{ paused_at, active_enrollments_affected }`

#### `resume_sequence`
Resumes a paused sequence and reactivates paused enrollments.

- **Permission**: `sequences:write`
- **Input**: `{ tenant_id, user_id, sequence_id }`
- **SQL**:
  1. `UPDATE sequences SET status='active'`
  2. `UPDATE enrollments SET status='active' WHERE status='paused'`
- **Output**: `{ resumed_at, enrollments_reactivated }`

---

### Analytics

#### `get_sequence_performance`
Returns aggregated performance metrics for a sequence.

- **Permission**: `sequences:read`
- **Input**: `{ tenant_id, user_id?, sequence_id, period_start?, period_end? }`
- **Output**:
  - `total_enrolled`, `total_completed`, `total_unenrolled`, `total_active`
  - `open_rate`, `click_rate`, `reply_rate`, `conversion_rate`, `bounce_rate`, `unsubscribe_rate` (as % values)
  - `step_metrics[]`: per-step breakdown with `sent`, `opened`, `clicked`, `replied` and corresponding rates
- **Note**: Rates are computed as `(count / COALESCE(NULLIF(sent,0), 1)) * 100`

---

## Error Codes

| Code | HTTP | Description |
|------|------|-------------|
| `TENANT_FORBIDDEN` | 403 | Tenant does not exist or is inactive |
| `PERMISSION_DENIED` | 403 | Missing required permission |
| `NOT_FOUND` | 404 | Resource not found |
| `VALIDATION_ERROR` | 422 | Input validation failed |
| `SEQUENCE_HAS_ACTIVE_ENROLLMENTS` | 409 | Cannot modify/delete, active enrollments exist |
| `ALREADY_ENROLLED` | 409 | Contact already enrolled in this sequence |
| `SEQUENCE_NOT_ACTIVE` | 422 | Sequence must be active for enrollment |
| `CONTACT_NOT_FOUND` | 404 | Contact not found in tenant |
| `DATABASE_ERROR` | 500 | PostgreSQL error |
| `INTERNAL_ERROR` | 500 | Unexpected internal error |

## Database Tables Required

- `organizations` — tenant validation (`id`, `active`)
- `sequences` — sequences (`id`, `tenant_id`, `name`, `description`, `status`, `exit_conditions`, `tags`, `created_by`, `created_at`, `updated_at`)
- `sequence_steps` — steps (`id`, `sequence_id`, `tenant_id`, `position`, `step_type`, `delay_days`, `delay_hours`, `template_id`, `subject`, `body_template`)
- `enrollments` — enrollment tracking (`id`, `tenant_id`, `sequence_id`, `contact_id`, `status`, `current_step`, `custom_variables`, `enrolled_at`, `next_step_at`, `completed_at`, `unenroll_reason`)
- `contacts` — contact existence check (`id`, `tenant_id`)
- `email_events` — email event tracking (`id`, `enrollment_id`, `step_id`, `event_type`, `occurred_at`)
- `audit_events` — audit log (shared across MCP servers)
