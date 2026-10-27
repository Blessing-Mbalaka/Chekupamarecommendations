"""Authenticated, course-scoped load scenario. Configure only through environment variables."""
import os
import re

from locust import HttpUser, between, task


class CourseChatUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        self.username = os.environ["LOAD_TEST_USERNAME"]
        self.password = os.environ["LOAD_TEST_PASSWORD"]
        self.course_id = os.environ["LOAD_TEST_COURSE_ID"]
        response = self.client.get("/login/")
        csrf = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', response.text)
        if not csrf:
            raise RuntimeError("Could not obtain the login CSRF token")
        self.client.post(
            "/login/",
            {"username": self.username, "password": self.password, "csrfmiddlewaretoken": csrf.group(1)},
        )

    @task(3)
    def open_course_chat(self):
        self.client.get("/chatbot/", params={"course": self.course_id}, name="course chat page")

    @task
    def ask_course_question(self):
        with self.client.post(
            "/chatbot/stream/",
            data={
                "course": self.course_id,
                "message": "Summarise the main indexed concept.",
                "csrfmiddlewaretoken": self.client.cookies.get("csrftoken", ""),
            },
            name="course chat stream",
            catch_response=True,
        ) as response:
            if response.status_code != 200 or '"type": "done"' not in response.text:
                response.failure(f"unexpected stream response: HTTP {response.status_code}")
