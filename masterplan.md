# Master Plan

## Vision

Build a modular Django learning platform with an immersive chatbot that personalizes academic content recommendations for students based on:

- Student profile data and self-declared challenges
- A baseline assessment configured by lecturers
- Student chat questions and interaction history
- Uploaded teaching materials and external academic resources
- Engagement analytics such as clicks, page visits, and material dwell time

The platform should support students, lecturers/admins, and teaching assistants, while keeping the implementation API-first, service-oriented, and well documented.

## Core Roles

- Admin/Lecturer
  - Manage users and course structures
  - Create baseline assessments and chatbot question flows
  - Upload files, links, and video resources
  - Review analytics and recommendation outcomes
- Teaching Assistant
  - Support lecturer workflows for content, questions, and student follow-up
  - Review engagement data and student progress
- Student
  - Maintain a personalized profile
  - Complete baseline assessments
  - Chat with the bot and answer lecturer-authored questions
  - Receive personalized learning resource recommendations

## Product Modules

### 1. Accounts and Profiles

- Custom user model with role support
- Student profile with:
  - identifiers
  - location
  - region
  - phone number
  - email
  - student number
  - free-text challenges
- Lecturer/TA profile support

### 2. Learning Domain

- Course
- Topic
- Material
- Baseline assessment
- Assessment question
- Student assessment attempt
- Lecturer-authored chatbot prompts/questions

### 3. Content Ingestion

- Upload local files such as PDF, DOCX, TXT, PPTX, CSV, and media references
- Save website resources and YouTube references
- Metadata capture:
  - title
  - authors
  - publication year
  - source type
  - tags
  - course/topic association
- Validation and ingestion services
- Text extraction hooks for future RAG indexing

### 4. Chatbot and Recommendations

- Chat sessions and messages
- Recommendation engine combining:
  - baseline performance
  - student challenges
  - recent questions
  - course/topic relevance
  - engagement patterns
- Response payloads that include:
  - chatbot answer
  - recommended materials
  - rationale
  - follow-up questions

### 5. External Discovery

- Service layer for free or low-friction academic discovery providers
- Initial abstraction for:
  - Crossref
  - OpenAlex
  - Semantic Scholar
  - YouTube metadata lookup
- Admin flow to review discovered resources before attaching them to the platform

### 6. Analytics

- Track:
  - page visits
  - clicks
  - material opens
  - dwell time
  - chatbot interactions
- Aggregate:
  - per-student engagement
  - material popularity
  - inferred interest signals

### 7. UI/UX

- Clean Django login flow
- Modular dashboard layouts
- Sidebar navigation by role
- Simple, neat, purpose-driven screens

## Architecture

### Backend Style

- Django project with Django REST Framework for API-first design
- App-per-domain structure
- Business logic in dedicated service modules
- Thin views and serializers
- Recommendation and ingestion designed behind interfaces for future AI/RAG expansion

### Proposed Django Apps

- `core`
- `accounts`
- `learning`
- `ingestion`
- `chatbot`
- `recommendations`
- `analytics_app`

### Data Notes

- Django `TextField` will be used for the student `challenges` field and other large free-text fields
- Materials should support uploaded files and external URLs
- Analytics events should be append-only

## Delivery Phases

### Phase 1. Foundation

- Initialize git
- Create `masterplan.md`
- Scaffold Django project
- Configure settings, templates, static files, and environment handling
- Implement custom user model and role support

### Phase 2. Learning and Profile Data

- Student profile model and forms
- Course/topic/material models
- Baseline assessment models
- Lecturer question authoring support

### Phase 3. Ingestion and Recommendation Core

- Admin upload workflows
- External resource link workflows
- Recommendation service based on rules and scoring
- Chat session and message persistence

### Phase 4. Analytics and Dashboards

- Event tracking endpoints
- Engagement summaries
- Student and lecturer dashboards

### Phase 5. Polish and Verification

- Documentation
- Automated tests
- Playwright UI verification where feasible
- Stage-by-stage git commits

## Git Stage Plan

- Stage 1: planning and repository bootstrap
- Stage 2: Django scaffold and auth foundation
- Stage 3: domain models and admin flows
- Stage 4: chatbot, recommendation, and analytics features
- Stage 5: tests, UI refinement, and final verification

## Implementation Checklist

- [ ] Initialize repository
- [x] Create `masterplan.md`
- [ ] Scaffold Django project
- [ ] Configure base settings and templates
- [ ] Add custom user model and roles
- [ ] Add student profile and challenges support
- [ ] Add courses, topics, and materials
- [ ] Add baseline assessment models
- [ ] Add lecturer-authored chatbot questions
- [ ] Add file and link ingestion flows
- [ ] Add external academic discovery service abstraction
- [ ] Add chatbot sessions and messages
- [ ] Add recommendation engine service
- [ ] Add analytics event tracking
- [ ] Add role-based dashboards and sidebar UI
- [ ] Add automated tests
- [ ] Run verification
- [ ] Commit each implementation stage

## Immediate Next Step

Scaffold the Django project and establish the modular app structure so feature work can proceed in isolated, testable slices.
