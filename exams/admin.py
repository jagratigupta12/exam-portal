from django.contrib import admin
from .models import (
    ExamSession, MCQQuestion, OneWordQuestion,
    StudentAttempt, Test1Answer, Test2Answer
)

admin.site.register(ExamSession)
admin.site.register(MCQQuestion)
admin.site.register(OneWordQuestion)
admin.site.register(StudentAttempt)
admin.site.register(Test1Answer)
admin.site.register(Test2Answer)