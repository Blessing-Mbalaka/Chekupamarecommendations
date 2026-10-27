# Institutions, departments and modules

The existing Course model is the academic module. Its database identity and all existing links are preserved. The hierarchy is Institution -> Department -> Module (Course) -> Topic -> Material. Existing data belongs to Johannesburg Business School (`jbs`); existing modules are assigned to its General department. Existing accounts keep their usernames and passwords and sign in using institution code `jbs`.

## Registration and administration

- `/institutions/register/`: register an institution and its first administrator. This never grants Django staff/superuser access.
- `/institutions/join/`: students register with the institution's invitation code. Students cannot select teaching or administrator roles. They may select modules offered by their own institution from Module settings.
- `/institutions/structure/`: institution administrators create/edit departments, modules and topics, and view/rotate the student invitation code.
- `/manage/users/`: administrators create users, assign departments, enrol students in modules, and assign lecturers/teaching assistants. Login identifiers (username and email) remain globally unique.
- `/login/`: institution code, username and password.

## Data boundaries

Business and learning models carry an indexed, required institution foreign key. Requests derive the boundary from the signed-in user, not submitted institution IDs. Institution-aware querysets scope cloned form choices, reads and writes. Foreign-key and many-to-many writes reject cross-institution links. Ordinary administrators see only their own institution, including analytics. Lecturers and teaching assistants see assigned modules; students see enrolled modules. Departments group modules; a student can be assigned modules across departments within their institution.

Profiles, quizzes, assessment attempts and chats retain their existing user ownership. Existing student result restrictions remain in place; teaching staff can review assigned module results. Recommendations explicitly restrict to the student's assigned modules, including when called outside HTTP requests. Retrieval and generated-answer caches use an institution/user namespace; streamed chat responses retain their request boundary.

Uploads are stored under `institutions/<id>/modules/<id>/materials/`. Existing upload names remain valid. All `/media/` requests go through an authenticated material lookup with institution/module checks. **Production web servers must route media through Django, not expose MEDIA_ROOT through a public alias.**

`all_institutions` and Django's base manager are trusted maintenance escape hatches; do not use them in user-facing code. Outside HTTP requests, use `institution_context(institution)` and, for student/lecturer retrieval, pass its `actor` argument. Existing application data commands default to Johannesburg Business School (database institution ID 1, code `jbs`). Data commands for another institution can be run with `python manage.py institution_command INSTITUTION_CODE COMMAND`. Database migrations remain global. Platform-maintenance scripts without a context are trusted and can inspect all institutions.

## Deployment and scaling

Back up the database and media, install requirements, run `python manage.py migrate`, then restart the app. SQLite remains the local default. PostgreSQL is supported through `DB_ENGINE=postgresql`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, and `DB_PORT`; the psycopg driver is listed in requirements. Changing database engines does not copy existing data automatically. Keep the protected media routing when deploying shared storage. Higher traffic will also require sizing the database, workers and AI provider capacity; this feature does not claim unlimited load capacity.

## Verification

Run `python manage.py test --settings=config.test_settings`. These test settings use a fast password hasher and disable live AI calls only inside the test process; production settings retain their normal password hashing and provider configuration.
