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
- Student communication

### Super Admin (Dean / Principal)
Institution leadership responsible for:
- Institutional oversight
- Faculty admin account management
- Enterprise-level analytics and platform engagement review

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
- Create and manage batches
- Manage student accounts
- Upload and manage resources
- Create and manage practice content
- Create, schedule, and manage assessments
- Create and manage contests
- View institutional analytics
- Manage announcements and scrolling updates
- View and respond to student inquiries

### 5.3 Super Admin (Dean / Principal)
- Full read access across all modules
- Create, manage, and deactivate admin accounts
- View all batches and students across departments
- Access full enterprise-level analytics and reports
- No content creation or operational management

---

## 6. Super Admin Portal — Navigation Tabs

| Tab | Purpose |
|-----|---------|
| **Overview** | Institution-wide KPIs — total students, batches, active admins, platform engagement |
| **Admin Management** | Create, deactivate, and manage faculty admin accounts |
| **Batches** | Read-only view of all batches and student counts |
| **Students** | Read-only view of all students across all departments and batches |
| **Analytics** | Full enterprise analytics — top performers, weak topic trends, resource utilization, assessment and contest participation, department-wise and batch-wise breakdowns |

---

## 7. Admin Portal — Navigation Tabs

| Tab | Purpose | Version |
|-----|---------|---------|
| **Batches** | Create and manage student batches | V1 |
| **Students** | Add, import, and manage student accounts | V1 |
| **Resources** | Manage company-wise preparation resources | V1 |
| **Practice** | Manage practice modules, sections, and questions | V1 |
| **Inquiries** | View and manage student inquiries | V1 |
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
| **Contact** | Submit inquiries to admin | V1 |
| **Assessments** | View and attempt assigned assessments | V2 |
| **Contests** | Join contests and view leaderboards | V2 |

---

## 9. Release Strategy

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

## 10. Functional Modules

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

## 11. Analytics & Reporting

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

## 12. Notifications

| Notification Type | Triggered By | Delivery | Version |
|------------------|-------------|---------|---------|
| New resources | Admin uploads new content | In-app | V1 |
| General announcements | Admin posts scrolling update | Scrolling banner (live, on-platform) | V1 |
| Assessment announcements | Admin schedules an assessment | In-app + PWA push | V2 |
| Contest reminders | Admin creates a contest | In-app + PWA push | V2 |
| Result publication | Admin publishes assessment results | In-app + PWA push | V2 |

---

## 13. Architecture

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

## 14. API Protocols

| Protocol | Used Where | Version |
|----------|-----------|---------|
| REST | All services — all standard operations | V1 |
| WebSocket | Contest leaderboard only — real-time push to 20,000+ clients | V2 |

---

## 15. Infrastructure

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

## 16. Technology Stack

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

## 17. Scale & Performance Requirements

| Requirement | Target |
|------------|--------|
| Concurrent users — Assessments | 20,000+ |
| Concurrent users — Contests | 20,000+ |
| Traffic — Resources | Low to Moderate |
| Traffic — Practice | Moderate |
| Uptime | 24/7, 365 days |
| Fault isolation | One service failure must not cause application-wide failure |

---

## 18. Non-Functional Requirements

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

## 19. Success Metrics

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

## 20. Future Expansion Scope

- Placement outcome tracking and success rate reporting
- AI-powered preparation recommendations
- Personalized preparation plans
- Interview simulation
- Resume analysis
- Placement prediction analytics
- Peer discussion forums
- Recruiter integration
- Certification systems
