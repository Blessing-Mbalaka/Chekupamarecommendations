from accounts.models import StudentProfile, User


def get_or_create_student_profile(user: User) -> StudentProfile:
    profile, _ = StudentProfile.objects.get_or_create(user=user)
    return profile
