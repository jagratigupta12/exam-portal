from django.db import models
from django.contrib.auth.models import User
import random, string


def generate_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))


class ExamSession(models.Model):
    title = models.CharField(max_length=200)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    test1_percentage = models.IntegerField(default=30)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    # Timer settings
    duration_minutes = models.IntegerField(default=30, help_text="Test duration in minutes")
    start_time = models.DateTimeField(null=True, blank=True, help_text="Exam window opens at")
    end_time = models.DateTimeField(null=True, blank=True, help_text="Exam window closes at")

    # Instructions
    # AI Settings
    use_ai_for_test2 = models.BooleanField(default=False,
        help_text="Let AI generate Test 2 questions from MCQs")
    ai_questions_generated = models.BooleanField(default=False)

    # Additional exam info
    faculty_name = models.CharField(max_length=200, blank=True)
    branch       = models.CharField(max_length=200, blank=True)
    year         = models.CharField(max_length=50,  blank=True)
    semester     = models.CharField(max_length=50,  blank=True)

    instructions = models.TextField(blank=True,
        default="1. Read all questions carefully.\n2. Each MCQ has only one correct answer.\n3. Do not refresh the page during the exam.\n4. The exam will auto-submit when time runs out.\n5. You cannot go back once you submit.")

    def __str__(self):
        return self.title


class MCQQuestion(models.Model):
    exam = models.ForeignKey(ExamSession, on_delete=models.CASCADE, related_name='mcq_questions')
    question_text = models.TextField()
    option_a = models.CharField(max_length=300)
    option_b = models.CharField(max_length=300)
    option_c = models.CharField(max_length=300)
    option_d = models.CharField(max_length=300)
    correct_option = models.CharField(max_length=1, choices=[('A','A'),('B','B'),('C','C'),('D','D')])
    marks = models.IntegerField(default=1)
    order = models.IntegerField(default=0)

    def __str__(self):
        return f"Q{self.order}: {self.question_text[:50]}"


class OneWordQuestion(models.Model):
    exam = models.ForeignKey(ExamSession, on_delete=models.CASCADE, related_name='oneword_questions')
    corresponding_mcq = models.OneToOneField(MCQQuestion, on_delete=models.CASCADE, related_name='oneword')
    question_text = models.TextField()
    correct_answer = models.CharField(max_length=200)

    def __str__(self):
        return f"OW for MCQ#{self.corresponding_mcq.order}"


class StudentAccessCode(models.Model):
    exam = models.ForeignKey(ExamSession, on_delete=models.CASCADE, related_name='access_codes')
    student_name = models.CharField(max_length=200)
    enrollment_no = models.CharField(max_length=50, blank=True)
    student_email = models.EmailField(blank=True)
    code = models.CharField(max_length=20, unique=True, default=generate_code)
    is_used = models.BooleanField(default=False)
    is_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.student_name} | {self.code}"


class StudentAttempt(models.Model):
    exam = models.ForeignKey(ExamSession, on_delete=models.CASCADE)
    access_code = models.OneToOneField('StudentAccessCode', on_delete=models.SET_NULL,
                                        null=True, blank=True, related_name='attempt')
    student_name = models.CharField(max_length=200)
    enrollment_no = models.CharField(max_length=50, blank=True)
    student_email = models.EmailField(blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    test1_started_at = models.DateTimeField(null=True, blank=True)
    test1_completed = models.BooleanField(default=False)
    test2_completed = models.BooleanField(default=False)
    tab_switch_count = models.IntegerField(default=0)
    fullscreen_exit_count = models.IntegerField(default=0)
    test1_direct_marks = models.FloatField(default=0)
    test2_bonus_marks = models.FloatField(default=0)
    total_marks = models.FloatField(default=0)
    max_possible_marks = models.FloatField(default=0)

    def __str__(self):
        return f"{self.student_name} - {self.exam.title}"


class Test1Answer(models.Model):
    attempt = models.ForeignKey(StudentAttempt, on_delete=models.CASCADE, related_name='test1_answers')
    question = models.ForeignKey(MCQQuestion, on_delete=models.CASCADE)
    selected_option = models.CharField(max_length=1, blank=True)
    is_correct = models.BooleanField(default=False)
    promoted_to_test2 = models.BooleanField(default=False)
    # Stores shuffled option mapping e.g. "A:C,B:A,C:D,D:B" (display->original)
    option_shuffle_map = models.CharField(max_length=20, blank=True)


class Test2Answer(models.Model):
    attempt = models.ForeignKey(StudentAttempt, on_delete=models.CASCADE, related_name='test2_answers')
    oneword_question = models.ForeignKey(OneWordQuestion, on_delete=models.CASCADE)
    student_answer = models.CharField(max_length=200, blank=True)
    is_correct = models.BooleanField(default=False)


class TeacherProfile(models.Model):
    """Stores teacher's Anthropic API key securely"""
    teacher = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    anthropic_api_key = models.CharField(max_length=200, blank=True,
        help_text="Your Anthropic API key for AI question generation")

    def __str__(self):
        return f"Profile: {self.teacher.username}"

    def has_api_key(self):
        return bool(self.anthropic_api_key.strip())
