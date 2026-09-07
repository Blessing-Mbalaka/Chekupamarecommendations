# Forthcoming Features

## Course-aware chatbot retrieval

The chatbot currently operates as a centralised assistant: it searches all validated, indexed material across every course. Materials and RAG chunks already retain their course association, so course-scoped retrieval can be introduced without rechunking existing documents.

### Proposed plan

1. Keep centralised retrieval as the default for administrators and users who deliberately choose the complete library.
2. Add a course context to each chat session, selected explicitly or inferred from the page where the chat was opened.
3. Offer students only courses in which they are enrolled; teaching staff may access courses they teach or support.
4. Pass the selected course into hybrid semantic and BM25 retrieval so only chunks belonging to that course are ranked.
5. Apply the same course restriction to external academic suggestions, recommendations, analytics, and previous-question matching.
6. Display the active course clearly in the chatbot and provide an explicit **All courses** option where the user's role permits it.
7. Preserve separate chat history per student and course instead of combining every course into one session.
8. Add tests proving that course-scoped chats cannot retrieve or recommend material from another course and that centralised mode still searches the full library.

### Acceptance criteria

- Existing indexed documents do not need to be uploaded, chunked, or embedded again.
- A course-scoped question uses only validated chunks from the active course.
- Student access respects course enrolment.
- Sources and recommended materials follow the same scope as the generated answer.
- Authorised users can intentionally switch back to centralised library search.
