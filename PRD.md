# SPARK — Product Requirements Document

**Product Name:** SPARK — Structured Preparation and Readiness Kit  
**Type:** Enterprise Institutional Placement Preparation Platform  
**Version:** 1.0  
**Date:** 2026-05-28

---

## 1. Executive Summary

SPARK is a centralized placement preparation and readiness platform designed for educational institutions to help students prepare for campus recruitment drives in a structured, scalable, and measurable manner.

The platform provides:
- Company-specific preparation resources
- Topic-wise practice environments
- Mock assessments simulating real placement drives
- Competitive contests and rankings
- Enterprise-level analytics and dashboards

The objective is to create a single institutional ecosystem where students can continuously prepare, practice, evaluate, and improve their placement readiness.

---

## 2. Product Vision

To become the institution's unified placement preparation ecosystem that:
- Improves placement outcomes
- Standardizes preparation quality
- Increases student participation
- Provides measurable readiness insights
- Reduces fragmented preparation workflows

---

## 3. Product Goals

### Primary Goals
- Centralize placement preparation activities
- Improve student placement readiness
- Enable structured learning progression
- Simulate real placement experiences
- Improve student preparation quality for placement drives

### Secondary Goals
- Encourage competitive learning culture
- Provide institution-controlled preparation workflows
- Create reusable preparation resources
- Improve student engagement consistency

---

## 4. Target Users

### Students
Students preparing for:
- Campus placements
- Internship drives
- Aptitude rounds
- Coding rounds
- HR rounds
- Technical interviews

### Admin (Faculty)
Institution training administrators responsible for:
- Resource management
- Drive preparation
- Student readiness monitoring
- Assessment creation and management
- Contest management

### Super Admin (Dean / Principal)
Institution leadership responsible for:
- Institutional oversight
- Enterprise-level analytics and platform engagement review
- Read-only visibility into faculty admin accounts (management moved to IT, 2026-08-19)
- Provisioned by IT (2026-08-20) — no longer bootstrapped, no IT account management authority (reversed the same day)

### IT (Platform Operations)
Platform operations staff — the platform's bootstrapped root account (2026-08-20; a single account seeded from `.env`, replacing Super Admin in that role), responsible for:
- Student communication (inquiries)
- Outbox delivery-failure monitoring (Dead Letter Queue)
- Batch and student account management (exclusive — Admin and Super Admin have read-only access)
- Faculty admin account management (exclusive — Super Admin has read-only access, moved 2026-08-19)
- Super Admin account management (exclusive — Super Admin has zero access to this, moved 2026-08-20)
- Department master-data management (exclusive to IT, added 2026-08-20) — the department list every create/assign form and filter across the platform reads from; Admin and Super Admin have read-only access

---

## 5. User Roles

### 5.1 Student
- Access and consume resources
- Attempt practice questions
- Participate in assessments
- Join contests and leaderboards
- View personal analytics

### 5.2 Admin (Faculty)
- Full access to all content modules
- View batches, including each batch's student roster (read-only — CRUD is IT-exclusive, revised 2026-08-19)
- No standalone Students module — removed entirely (2026-08-19); Batches is Admin's only student-facing module
- Read-only visibility into the department list (CRUD is IT-exclusive, added 2026-08-20) — consumed as dropdown/filter options in student creation, batch filters, and assessment assignment/results filters
- Upload and manage resources
- Create and manage practice content
- Create, schedule, and manage assessments
- Create and manage contests
- View institutional analytics
- Manage announcements and scrolling updates

### 5.3 Super Admin (Dean / Principal)
- Full read access across all modules
- View admin accounts (read-only — creation/management moved to IT, 2026-08-19)
- View all batches across departments, including each batch's roster (read-only) — no standalone Students module (removed 2026-08-19, same as Admin)
- Read-only visibility into the department list (CRUD is IT-exclusive, added 2026-08-20)
- Access full enterprise-level analytics and reports
- No content creation or operational management
- No longer bootstrapped and no longer manages IT accounts (2026-08-20) — Super Admin is now itself created and managed by IT, the same way Admin and Student accounts are; zero access to the IT roster or to other Super Admin accounts
- Self-service "My Profile" (view/edit own name, change own password) and Scrollbar (manage the student-facing announcement bar) — opened 2026-08-20, the same modules Admin already had

### 5.4 IT (Platform Operations)
- The platform's bootstrapped root account (2026-08-20) — a single account seeded from `IT_EMAIL`/`IT_PASSWORD` in `.env` on first container startup (`create_default_it`), replacing Super Admin in that role. No public sign-up; no UI creates additional IT accounts.
- View and respond to student inquiries
- Monitor and retry outbox dead-letter events (Dead Letter Queue)
- Exclusive owner of the Students module and all Batches/Students account management — create, edit, delete, toggle status, bulk import, and reset student passwords (Admin and Super Admin both have read-only access to Batches, including a batch's roster, but neither has a Students module at all — briefly had shared write access 2026-08-19, reversed the same day; Students then dropped from Admin, then from Super Admin, entirely the same day)
- Exclusive owner of Admin (faculty) account management — create, edit (name and department), deactivate/reactivate, delete, and reset password (Super Admin has read-only access to the account list/detail; moved from Super Admin 2026-08-19 — briefly shared full access to validate parity, then Super Admin restricted to read-only the same day, same treatment as Batches). Every Admin account is mapped to a department, chosen from the live Departments list at creation and editable afterward. Bulk CSV import (2026-08-20) — a single-column `email` file plus one Department picked in the UI, applied to every account created; per-row created/rejected results, same mechanism as Student bulk import.
- Exclusive owner of Super Admin account management — create, edit (name and department), deactivate/reactivate, delete, and reset password (2026-08-20; unlike Admin, Super Admin has zero access here at all, not even read — same as Admin has zero visibility into other Admin accounts). Same department mapping and bulk CSV import as Admin account management.
- Exclusive owner of Department master data — create, edit (name only — the code is immutable after creation), deactivate/reactivate, and permanently delete departments (2026-08-20; Admin and Super Admin have read-only access, same treatment as Batches). This is the canonical list every department dropdown/filter across all three portals reads from live — a CRUD change here updates every open tab without a rebuild or reload (same-tab via shared state, other tabs via a broadcast event). Renaming or deleting a department does not retroactively change student/admin records that already reference the old code — it only affects what's offered going forward.
- No access to other academic content (resources, practice, assessments)

---

## 6. Super Admin Portal — Navigation Tabs

| Tab | Purpose |
|-----|---------|
| **Overview** | Institution-wide KPIs — total students, batches, active admins, platform engagement |
| **Admins** | Read-only view of faculty admin accounts (managed by IT, revised 2026-08-19) |
| **Batches** | Read-only view of all batches, student counts, and each batch's roster |
| **Scrollbar** | Manage the live scrolling announcement bar shown to students — same module and endpoints as Admin's, added 2026-08-20 |
| **Analytics** | Full enterprise analytics — top performers, weak topic trends, resource utilization, assessment and contest participation, department-wise and batch-wise breakdowns |

Also available from the header dropdown (not a nav tab, same as Admin): **My Profile** — view/edit own name, change own password. Added 2026-08-20.

---

## 7. Admin Portal — Navigation Tabs

| Tab | Purpose | Version |
|-----|---------|---------|
| **Batches** | View student batches, including each batch's roster (read-only — managed by IT, revised 2026-08-19) | V1 |
| **Resources** | Manage company-wise preparation resources | V1 |
| **Practice** | Manage practice modules, sections, and questions | V1 |
| **Scrollbar** | Manage live scrolling announcements shown to students | V1 |
| **Assessments** | Create, schedule, assign, and monitor assessments | V2 |
| **Contests** | Create and manage contests and leaderboards | V2 |

---

## 8. Student Portal — Navigation Tabs

| Tab | Purpose | Version |
|-----|---------|---------|
| **Home** | Student dashboard — upcoming assessments, contests, recent resources | V1 |
| **Companies** | Browse company-wise preparation resources | V1 |
| **Practice** | Topic-wise practice questions | V1 |
| **My Profile** | View and update personal profile | V1 |
| **Contact** | Submit inquiries (reviewed by IT) | V1 |
| **Assessments** | View and attempt assigned assessments | V2 |
| **Contests** | Join contests and view leaderboards | V2 |

---

## 9. IT Portal — Navigation Tabs

Added 2026-08-18. As of 2026-08-20, IT is the platform's bootstrapped root account — a single
account seeded from `IT_EMAIL`/`IT_PASSWORD` in `.env` on first container startup
(`create_default_it`), replacing Super Admin in that role (see §5.4). No public sign-up, no
link from the marketing site, and no UI creates additional IT accounts. Every module below is
exclusive to IT — either moved wholesale from its previous owner, or reserved for IT-only CRUD
from the start. Further modules are added here as decided.

| Tab | Purpose | Relationship to Admin/Super Admin |
|-----|---------|------------|
| **Super Admins** | Create (with department), edit (name/department), deactivate/reactivate, delete, reset password, and bulk-import via CSV (email list + one shared department) super admin accounts | Exclusive to IT — Super Admin has **zero** access here, not even read (moved from Super Admin 2026-08-20, alongside IT becoming the bootstrapped root; no transitional shared-access phase — this is a new capability, not a restriction of an existing one) |
| **Admins** | Create (with department), edit (name/department), deactivate/reactivate, delete, reset password, and bulk-import via CSV (email list + one shared department) faculty admin accounts | Exclusive to IT — Super Admin has read-only access on `/super-admin/admins` (moved from Super Admin 2026-08-19; briefly shared full access to validate parity, then restricted the same day) |
| **Departments** | Create departments (code + optional name), edit name, deactivate/reactivate, and permanently delete (2026-08-20) | Exclusive to IT — Admin and Super Admin both have read-only access, same treatment as Batches. A separate module from Super Admins/Admins, not merged into either — it's reference data consumed by account creation, student creation, and batch/assessment filters across every portal. CRUD here propagates live to every dropdown app-wide, no rebuild needed. |
| **Batches** | Create, edit, and delete student batches | Exclusive to IT — Admin and Super Admin both have read-only access on `/admin/batch` / `/super-admin/batches`, including a batch's roster (briefly shared write access 2026-08-19, reversed the same day) |
| **Students** | Add, import, edit, delete, and manage student accounts (status toggle, password reset) | Exclusive to IT — neither Admin nor Super Admin has any access (briefly shared write access, then read-only, both on 2026-08-19; the standalone module was removed from Admin, then from Super Admin, entirely later the same day — `/admin/students` and `/super-admin/students` no longer exist, old links redirect to their portal's Batches page) |
| **Dead Letter Queue** | Monitor and retry outbox events that exhausted all delivery retries | Moved from Super Admin (2026-08-18) — Super Admin no longer has access |
| **Inquiries** | View and manage student inquiries | Moved from Admin (2026-08-18) — Admin no longer has access |

---

## 10. Release Strategy

The platform is delivered in two versions released within a short interval.

| | Version 1 | Version 2 |
|--|-----------|-----------|
| **Modules** | Resources, Practice | + Assessments, Contests |
| **Services deployed** | auth, user, resource, practice, notification, analytics | + assessment, contest |
| **Architecture** | Microservices | Microservices + EDA + WebSocket |
| **PostgreSQL** | Instance 2 only — 6 databases | + Instance 1 — assessment_db, contest_db |
| **Redis** | Cache only | Cache + EDA (Redis Streams) + Leaderboard |
| **Notifications** | New resources, General announcements | + Assessment announcements, Contest reminders, Result publication |
| **PWA push** | Not active | Active |

---

## 11. Functional Modules

### 10.1 Authentication — V1

**Objective:** Provide secure, role-based authentication for all three user roles across the platform.

**Functional Flows:**
- Login — role-specific entry points; JWT issued on success, stored client-side
- Logout — token cleared, session ended
- Password reset — self-service via registered institutional email
- Token refresh — silent background refresh to maintain active sessions

**Role-Based Routing on Login:**
- Student → Student portal
- Admin → Admin portal
- Super Admin → Super Admin portal

**Operational Controls:**
- Admin can manually reset a student's password
- Super Admin can manually reset an admin's password

---

### 10.2 Resources Module — V1

**Objective:** Provide centralized company-wise preparation resources.

**Supported Resource Types:**
PDFs, notes, interview experiences, previous questions, coding sheets, HR preparation materials, technical documentation, video links

**Student Experience:**
- Browse and search resources by company
- Filter by category and topic, sort by latest updates

**Admin Controls:**
- Organize resources by company, topic, drive type, department, and difficulty level
- Upload, replace, and manage resources
- Publish / unpublish control per company

---

### 10.3 Practice Module — V1

**Objective:** Enable students to practice topic-wise questions with continuous improvement workflows.

**Practice Categories:**
- Aptitude
- Logical reasoning
- Verbal ability
- Coding
- Technical MCQs

**Difficulty Levels:**
- Beginner
- Intermediate
- Advanced

**Student Experience:**
- Attempt questions (MCQ single, MCQ multiple, fill-in-the-blank)
- View explanations after attempting
- Retry incorrect answers
- Track progress, accuracy, completion percentage, weak and strong topics

**Admin Controls:**
- Create and manage practice modules, sections, and questions
- Publish / unpublish control per module, section, and question
- Upload question images and explanation images

---

### 10.4 Assessments Module — V2

**Objective:** Simulate real placement assessments in a controlled, enterprise-grade environment supporting 20,000+ concurrent participants.

**Student Experience:**
- Full-length assessments, section-wise tests, company-specific mocks, timed assessments
- Assessment structure: Aptitude, Coding, Verbal, Logical Reasoning, Technical MCQs
- Section timers, auto-submit, question navigation, save and continue
- Result analytics: scores, accuracy analysis, section-wise breakdown, time analysis, performance trends

**Admin Controls:**
- Create and configure assessments
- Schedule and assign assessments to specific batches, departments, or platform-wide
- Publish results
- Monitor participation in real time

---

### 10.5 Contests Module — V2

**Objective:** Drive engagement through competitive preparation workflows supporting 20,000+ concurrent participants with real-time leaderboards.

**Contest Types:**
- Coding contests
- Aptitude battles
- Mixed contests
- Batch-vs-batch competitions

**Student Experience:**
- Live real-time leaderboards (WebSocket)
- Rankings, scores, accuracy, completion speed
- Achievement system: badges, winning streaks, milestones, rank achievements
- Participation tracking: contest history, rankings, wins, performance growth

**Admin Controls:**
- Create and schedule contests (daily, occasional, regular)
- Assign contests to specific batches, departments, or platform-wide
- Push questions to live contests
- Monitor real-time participation

---

## 12. Analytics & Reporting

### Student-Level Analytics
- Practice completion and accuracy
- Assessment scores and performance trends
- Contest participation and rankings
- Improvement trends over time

### Admin-Level Analytics
- Student engagement metrics
- Assessment participation rates
- Top performers
- Weak topic trends across students
- Resource usage analytics

### Super Admin — Enterprise Analytics
- Student engagement levels by department and batch
- Contest participation growth
- Resource utilization
- Assessment participation rates
- Department-wise and batch-wise performance breakdowns

---

## 13. Notifications

| Notification Type | Triggered By | Delivery | Version |
|------------------|-------------|---------|---------|
| New resources | Admin uploads new content | In-app | V1 |
| General announcements | Admin posts scrolling update | Scrolling banner (live, on-platform) | V1 |
| Assessment announcements | Admin schedules an assessment | In-app + PWA push | V2 |
| Contest reminders | Admin creates a contest | In-app + PWA push | V2 |
| Result publication | Admin publishes assessment results | In-app + PWA push | V2 |

---

## 14. Architecture

### Pattern
| Scope | Pattern |
|-------|---------|
| Entire backend | Microservices Architecture |
| Assessments and Contests workflows | Event-Driven Architecture (EDA) |

### Microservices — 8 Services

| # | Service | EDA | Version |
|---|---------|-----|---------|
| 1 | auth-service | | V1 |
| 2 | user-service | | V1 |
| 3 | resource-service | | V1 |
| 4 | practice-service | | V1 |
| 5 | assessment-service | Yes | V2 |
| 6 | contest-service | Yes + WebSocket | V2 |
| 7 | notification-service | | V1 |
| 8 | analytics-service | | V1 |

**Principles:**
- Each service is independently deployable
- Each service has its own database — no shared databases between services
- Services communicate via REST APIs (synchronous) or Redis Streams (asynchronous via EDA)
- Failure of one service does not affect other services

---

## 15. API Protocols

| Protocol | Used Where | Version |
|----------|-----------|---------|
| REST | All services — all standard operations | V1 |
| WebSocket | Contest leaderboard only — real-time push to 20,000+ clients | V2 |

---

## 16. Infrastructure

| Component | Technology |
|-----------|-----------|
| Frontend | Next.js |
| API Gateway | Nginx |
| Backend (8 services) | Django (Python) |
| Databases — Standard instance | PostgreSQL instance 2 — auth_db, user_db, resource_db, practice_db, notification_db, analytics_db |
| Databases — High-load instance | PostgreSQL instance 1 — assessment_db, contest_db |
| Cache + Message Queue + Leaderboard | Redis (1 shared instance) |
| Media Storage | Object Storage — S3 / Cloudflare R2 / MinIO (1 shared) |
| Media Delivery | CDN |

---

## 17. Technology Stack

| Layer | Technology | Language |
|-------|-----------|----------|
| Frontend | Next.js, React, TypeScript, Tailwind CSS, Zustand, Axios, React Hook Form, Lucide React, Recharts | TypeScript |
| API Gateway | Nginx | Configuration only |
| Backend | Django, Django REST Framework | Python |
| ASGI Server | Uvicorn | — |
| ORM | Django ORM | Python |
| Auth | JWT (djangorestframework-simplejwt) | Python |

### Frontend Additional Capability
| Capability | Implementation |
|-----------|---------------|
| PWA (Progressive Web App) | Service Worker, Web App Manifest, Install Prompt |
| Real-time leaderboard | Native Browser WebSocket API (no package required) |

### Technology Dependencies
| Package | Purpose | Version |
|---------|---------|---------|
| `uvicorn` | ASGI server replacing Gunicorn | V1 |
| `redis-py` | Redis connection for cache and message queue | V1 |
| `django-redis` | Redis cache backend for Django | V1 |
| `django-storages` | Object storage integration | V1 |
| `boto3` | S3 / R2 / MinIO SDK | V1 |
| `django-channels` | WebSocket support for contest leaderboard | V2 |
| `pywebpush` | Web Push notifications for PWA push delivery | V2 |

---

## 18. Scale & Performance Requirements

| Requirement | Target |
|------------|--------|
| Concurrent users — Assessments | 20,000+ |
| Concurrent users — Contests | 20,000+ |
| Traffic — Resources | Low to Moderate |
| Traffic — Practice | Moderate |
| Uptime | 24/7, 365 days |
| Fault isolation | One service failure must not cause application-wide failure |

---

## 19. Non-Functional Requirements

### Performance
- Fast page loads across all modules
- Stable and responsive during 20,000+ concurrent assessment and contest sessions
- Scalable independently per service based on traffic

### Reliability
- High availability
- Data consistency per service
- Safe and idempotent submission handling for assessments and contests
- Auto-submit on timer expiry

### Security
- Role-based access control enforced via JWT at every service
- Secure authentication via auth-service
- Protected assessment and contest workflows
- Rate limiting at API Gateway level

### Scalability
- Independent horizontal scaling per service
- Supports multiple departments and large student batches
- High concurrent test and contest participation
- Object storage for unlimited media capacity

### Observability
- Centralized structured logging per service
- Health check endpoints per service
- Error monitoring and alerting for production incidents

---

## 20. Success Metrics

### Student Metrics
- Daily active users
- Practice completion rates
- Assessment participation
- Improvement trends over time

### Institutional Metrics
- Student engagement levels
- Contest participation growth
- Resource utilization rates
- Assessment participation rates

---

## 21. Future Expansion Scope

- Placement outcome tracking and success rate reporting
- AI-powered preparation recommendations
- Personalized preparation plans
- Interview simulation
- Resume analysis
- Placement prediction analytics
- Peer discussion forums
- Recruiter integration
- Certification systems
