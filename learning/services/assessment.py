from decimal import Decimal

from learning.models import AssessmentAttempt, AssessmentQuestion, AttemptAnswer, BaselineAssessment


def grade_assessment(assessment: BaselineAssessment, student, cleaned_data: dict) -> AssessmentAttempt:
    questions = list(assessment.questions.select_related("topic"))
    attempt = AssessmentAttempt.objects.create(assessment=assessment, student=student)
    correct_answers = 0
    for question in questions:
        field_name = f"question_{question.pk}"
        response = cleaned_data.get(field_name, "")
        selected_option = response if question.question_type == AssessmentQuestion.QuestionType.MULTIPLE_CHOICE else ""
        answer_text = response if question.question_type == AssessmentQuestion.QuestionType.SHORT_TEXT else ""
        is_correct = False
        if question.question_type == AssessmentQuestion.QuestionType.MULTIPLE_CHOICE:
            is_correct = response == question.correct_option
        elif question.expected_keywords:
            expected = [keyword.strip().lower() for keyword in question.expected_keywords.split(",") if keyword.strip()]
            answer_lower = str(response).lower()
            is_correct = any(keyword in answer_lower for keyword in expected)

        AttemptAnswer.objects.create(
            attempt=attempt,
            question=question,
            answer_text=answer_text,
            selected_option=selected_option,
            is_correct=is_correct,
        )
        correct_answers += int(is_correct)

    total = len(questions) or 1
    attempt.score = Decimal(correct_answers * 100 / total).quantize(Decimal("0.01"))
    attempt.save(update_fields=["score"])
    return attempt
