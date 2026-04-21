from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
import json, math

from .models import (
    ExamSession, MCQQuestion, OneWordQuestion,
    StudentAttempt, Test1Answer, Test2Answer, StudentAccessCode
)

# ── AUTH ──────────────────────────────────────────────────────────
def home(request):
    return render(request, 'home.html')

def teacher_login(request):
    if request.method == 'POST':
        user = authenticate(request, username=request.POST.get('username'),
                            password=request.POST.get('password'))
        if user:
            login(request, user)
            return redirect('teacher_dashboard')
        return render(request, 'teacher_login.html', {'error': 'Invalid credentials'})
    return render(request, 'teacher_login.html')

def teacher_logout(request):
    logout(request)
    return redirect('home')

# ── TEACHER ───────────────────────────────────────────────────────
@login_required
def teacher_dashboard(request):
    exams = ExamSession.objects.filter(created_by=request.user).order_by('-created_at')
    return render(request, 'teacher_dashboard.html', {'exams': exams})

@login_required
def delete_exam(request, exam_id):
    if request.method == 'POST':
        exam = get_object_or_404(ExamSession, id=exam_id, created_by=request.user)
        exam.delete()
        return JsonResponse({'status': 'ok'})
    return JsonResponse({'status': 'error', 'message': 'POST required'})

@login_required
def create_exam(request):
    if request.method == 'POST':
        exam = ExamSession.objects.create(
            title=request.POST.get('title'),
            created_by=request.user,
            test1_percentage=int(request.POST.get('percentage', 30)),
            duration_minutes=int(request.POST.get('duration_minutes', 30)),
            start_time=request.POST.get('start_time') or None,
            end_time=request.POST.get('end_time') or None,
            instructions=request.POST.get('instructions', ''),
            faculty_name=request.POST.get('faculty_name', ''),
            branch=request.POST.get('branch', ''),
            year=request.POST.get('year', ''),
            semester=request.POST.get('semester', ''),
        )
        return redirect('add_questions', exam_id=exam.id)
    return render(request, 'create_exam.html')

@login_required
def edit_exam_settings(request, exam_id):
    exam = get_object_or_404(ExamSession, id=exam_id, created_by=request.user)
    if request.method == 'POST':
        exam.title = request.POST.get('title', exam.title)
        exam.test1_percentage = int(request.POST.get('percentage', exam.test1_percentage))
        exam.duration_minutes = int(request.POST.get('duration_minutes', exam.duration_minutes))
        exam.start_time = request.POST.get('start_time') or None
        exam.end_time = request.POST.get('end_time') or None
        exam.instructions = request.POST.get('instructions', exam.instructions)
        exam.faculty_name = request.POST.get('faculty_name', exam.faculty_name)
        exam.branch = request.POST.get('branch', exam.branch)
        exam.year = request.POST.get('year', exam.year)
        exam.semester = request.POST.get('semester', exam.semester)
        exam.is_active = 'is_active' in request.POST
        exam.save()
        return redirect('add_questions', exam_id=exam.id)
    return render(request, 'edit_exam_settings.html', {'exam': exam})

@login_required
def add_questions(request, exam_id):
    exam = get_object_or_404(ExamSession, id=exam_id, created_by=request.user)
    return render(request, 'add_questions.html', {
        'exam': exam,
        'mcq_questions': exam.mcq_questions.all().order_by('order')
    })

@login_required
def save_mcq(request, exam_id):
    if request.method == 'POST':
        exam = get_object_or_404(ExamSession, id=exam_id, created_by=request.user)
        data = json.loads(request.body)
        count = exam.mcq_questions.count()
        mcq = MCQQuestion.objects.create(
            exam=exam,
            question_text=data['question_text'],
            option_a=data['option_a'], option_b=data['option_b'],
            option_c=data['option_c'], option_d=data['option_d'],
            correct_option=data['correct_option'].upper(),
            marks=int(data.get('marks', 1)),
            order=count + 1
        )
        OneWordQuestion.objects.create(
            exam=exam, corresponding_mcq=mcq,
            question_text=data['oneword_question'],
            correct_answer=data['oneword_answer'].strip().lower()
        )
        return JsonResponse({'status': 'ok', 'mcq_id': mcq.id, 'order': mcq.order})
    return JsonResponse({'status': 'error'}, status=400)

@login_required
def delete_question(request, question_id):
    mcq = get_object_or_404(MCQQuestion, id=question_id, exam__created_by=request.user)
    exam_id = mcq.exam.id
    mcq.delete()
    for i, q in enumerate(MCQQuestion.objects.filter(exam_id=exam_id).order_by('order'), 1):
        q.order = i
        q.save()
    return JsonResponse({'status': 'ok'})

@login_required
def manage_students(request, exam_id):
    exam = get_object_or_404(ExamSession, id=exam_id, created_by=request.user)
    
    if request.method == 'POST':
        from .student_parser import parse_excel, parse_word, parse_text
        students = []
        errors = []

        # --- Bulk file upload ---
        uploaded = request.FILES.get('student_file')
        if uploaded:
            name = uploaded.name.lower()
            try:
                if name.endswith('.xlsx') or name.endswith('.xls'):
                    students = parse_excel(uploaded)
                elif name.endswith('.docx'):
                    students = parse_word(uploaded)
                elif name.endswith('.txt'):
                    students = parse_text(uploaded.read().decode('utf-8'))
                else:
                    errors.append('Unsupported file. Use .xlsx, .docx, or .txt')
            except Exception as e:
                errors.append(f'File error: {str(e)}')

        # --- Manual text input ---
        manual_text = request.POST.get('student_names', '').strip()
        if manual_text:
            students += parse_text(manual_text)

        created = []
        for s in students:
            if s['name']:
                ac = StudentAccessCode.objects.create(
                    exam=exam,
                    student_name=s['name'],
                    enrollment_no=s.get('enrollment', ''),
                    student_email=s.get('email', '')
                )
                created.append(ac)

        return render(request, 'manage_students.html', {
            'exam': exam,
            'codes': exam.access_codes.all().order_by('created_at'),
            'new_codes': created,
            'errors': errors,
            'success': f'{len(created)} student(s) added!' if created else None
        })

    return render(request, 'manage_students.html', {
        'exam': exam,
        'codes': exam.access_codes.all().order_by('created_at'),
    })

@login_required
def delete_access_code(request, code_id):
    ac = get_object_or_404(StudentAccessCode, id=code_id, exam__created_by=request.user)
    exam_id = ac.exam.id
    ac.delete()
    return redirect('manage_students', exam_id=exam_id)

@login_required
def exam_results(request, exam_id):
    exam = get_object_or_404(ExamSession, id=exam_id, created_by=request.user)
    attempts = StudentAttempt.objects.filter(exam=exam, test2_completed=True).order_by('-total_marks')
    return render(request, 'exam_results.html', {'exam': exam, 'attempts': attempts})

@login_required
def attempt_detail(request, attempt_id):
    attempt = get_object_or_404(StudentAttempt, id=attempt_id, exam__created_by=request.user)
    t1 = attempt.test1_answers.all().select_related('question').order_by('question__order')
    t2 = attempt.test2_answers.all().select_related('oneword_question__corresponding_mcq')
    pct = round(attempt.total_marks / attempt.max_possible_marks * 100, 1) if attempt.max_possible_marks else 0

    # Test 1 stats
    t1_correct       = t1.filter(is_correct=True, promoted_to_test2=False).count()
    t1_promoted      = t1.filter(promoted_to_test2=True).count()
    t1_total_correct = t1_correct + t1_promoted  # all correct = direct correct + promoted
    t1_wrong         = t1.filter(is_correct=False, promoted_to_test2=False).exclude(selected_option='').count()
    t1_skipped       = t1.filter(selected_option='').count()

    # Test 2 stats
    t2_correct = t2.filter(is_correct=True).count()
    t2_wrong   = t2.filter(is_correct=False).count()

    return render(request, 'attempt_detail.html', {
        'attempt': attempt,
        't1_answers': t1,
        't2_answers': t2,
        'percentage': pct,
        't1_total': t1.count(),
        't1_correct': t1_correct,
        't1_wrong': t1_wrong,
        't1_skipped': t1_skipped,
        't1_promoted': t1_promoted,
        't1_total_correct': t1_total_correct,
        't2_correct': t2_correct,
        't2_wrong': t2_wrong,
    })

# ── STUDENT ───────────────────────────────────────────────────────
def student_register(request, exam_id):
    exam = get_object_or_404(ExamSession, id=exam_id, is_active=True)

    # Check exam window
    now = timezone.now()
    if exam.start_time and now < exam.start_time:
        return render(request, 'exam_closed.html', {
            'exam': exam, 'message': f'Exam has not started yet. It opens at {exam.start_time.strftime("%d %b %Y, %I:%M %p")}.'
        })
    if exam.end_time and now > exam.end_time:
        return render(request, 'exam_closed.html', {
            'exam': exam, 'message': 'Exam window has closed. You can no longer attempt this exam.'
        })

    if request.method == 'POST':
        enrollment_input = request.POST.get('enrollment_no', '').strip()
        code_input = request.POST.get('access_code', '').strip().upper()

        # Find code
        try:
            ac = StudentAccessCode.objects.get(code=code_input)
        except StudentAccessCode.DoesNotExist:
            return render(request, 'student_register.html', {
                'exam': exam, 'error': '❌ Invalid access code. Please check with your teacher.'
            })

        # Code must belong to THIS exam
        if ac.exam.id != exam.id:
            return render(request, 'student_register.html', {
                'exam': exam, 'error': '❌ This code is not valid for this exam.'
            })

        # Verify enrollment number if set
        if ac.enrollment_no and ac.enrollment_no.strip() != enrollment_input:
            return render(request, 'student_register.html', {
                'exam': exam, 'error': '❌ Enrollment number does not match. Please check with your teacher.'
            })

        if ac.is_completed:
            return render(request, 'student_register.html', {
                'exam': exam, 'error': '⚠️ This code has already been used and the exam is completed.'
            })

        if ac.is_used:
            try:
                attempt = ac.attempt
                request.session['attempt_id'] = attempt.id
                request.session['exam_id'] = exam.id
                if not attempt.test1_completed:
                    return redirect('exam_instructions', attempt_id=attempt.id)
                if not attempt.test2_completed:
                    return redirect('take_test2', attempt_id=attempt.id)
                return redirect('exam_submitted', attempt_id=attempt.id)
            except StudentAttempt.DoesNotExist:
                pass

        # First time — create attempt using teacher-entered name
        ac.is_used = True
        ac.save()
        attempt = StudentAttempt.objects.create(
            exam=exam,
            access_code=ac,
            student_name=ac.student_name,      # use teacher-entered name
            enrollment_no=ac.enrollment_no,    # use teacher-entered enrollment
            student_email=ac.student_email,
        )
        request.session['attempt_id'] = attempt.id
        request.session['exam_id'] = exam.id
        return redirect('exam_instructions', attempt_id=attempt.id)

    return render(request, 'student_register.html', {'exam': exam})


def exam_instructions(request, attempt_id):
    attempt = get_object_or_404(StudentAttempt, id=attempt_id)
    if attempt.test1_completed:
        return redirect('take_test2', attempt_id=attempt_id)
    exam = attempt.exam
    total_q = exam.mcq_questions.count()
    total_marks = sum(q.marks for q in exam.mcq_questions.all())
    return render(request, 'exam_instructions.html', {
        'attempt': attempt,
        'exam': exam,
        'total_q': total_q,
        'total_marks': total_marks,
    })


def _check_attempt_session(request, attempt):
    """Ensure student can only access their own attempt via session"""
    session_attempt = request.session.get('attempt_id')
    if session_attempt and session_attempt != attempt.id:
        return False
    return True

def _shuffle_options(question):
    """Shuffle options and return shuffled question dict + mapping"""
    import random
    opts = [('A', question.option_a), ('B', question.option_b),
            ('C', question.option_c), ('D', question.option_d)]
    shuffled = opts[:]
    random.shuffle(shuffled)
    
    # mapping: new_key -> original_key
    mapping = {}
    new_opts = {}
    keys = ['A', 'B', 'C', 'D']
    for i, (orig_key, text) in enumerate(shuffled):
        new_key = keys[i]
        mapping[new_key] = orig_key
        new_opts[f'option_{new_key.lower()}'] = text
    
    # Find new correct option key
    new_correct = [k for k, v in mapping.items() if v == question.correct_option][0]
    
    return new_opts, mapping, new_correct


def take_test1(request, attempt_id):
    attempt = get_object_or_404(StudentAttempt, id=attempt_id)
    if attempt.test1_completed:
        return redirect('test1_summary', attempt_id=attempt_id)

    if not attempt.test1_started_at:
        attempt.test1_started_at = timezone.now()
        attempt.save()

    import random
    questions = list(attempt.exam.mcq_questions.all().order_by('order'))
    
    # Shuffle question order per student (based on attempt id as seed)
    rng = random.Random(attempt.id)
    rng.shuffle(questions)
    
    # Shuffle options per question per student
    shuffled_questions = []
    for idx, q in enumerate(questions):
        rng2 = random.Random(attempt.id * 1000 + q.id)
        opts = [('A', q.option_a), ('B', q.option_b),
                ('C', q.option_c), ('D', q.option_d)]
        rng2.shuffle(opts)
        keys = ['A', 'B', 'C', 'D']
        mapping = {}
        new_q = {
            'id': q.id,
            'display_order': idx + 1,
            'question_text': q.question_text,
            'marks': q.marks,
            'correct_option': q.correct_option,
        }
        for i, (orig_key, text) in enumerate(opts):
            new_key = keys[i]
            mapping[new_key] = orig_key
            new_q[f'option_{new_key.lower()}'] = text
        # Store mapping string e.g. "A:C,B:A,C:D,D:B"
        new_q['shuffle_map'] = ','.join(f'{k}:{v}' for k,v in mapping.items())
        new_q['correct_display'] = [k for k,v in mapping.items() if v == q.correct_option][0]
        shuffled_questions.append(new_q)

    duration_seconds = attempt.exam.duration_minutes * 60
    elapsed = (timezone.now() - attempt.test1_started_at).total_seconds()
    remaining_seconds = max(0, int(duration_seconds - elapsed))

    # Pass Test 2 questions as locked preview
    # Show question text but hide answers
    test2_preview = []
    for mcq in attempt.exam.mcq_questions.all().order_by('order'):
        try:
            ow = mcq.oneword
            test2_preview.append({
                'mcq_order': mcq.order,
                'question': ow.question_text
            })
        except Exception:
            pass

    return render(request, 'test1.html', {
        'attempt': attempt,
        'questions': shuffled_questions,
        'remaining_seconds': remaining_seconds,
        'duration_minutes': attempt.exam.duration_minutes,
        'test2_preview': test2_preview,
        'test2_count': len(test2_preview),
    })


def submit_test1(request, attempt_id):
    if request.method != 'POST':
        return redirect('home')
    attempt = get_object_or_404(StudentAttempt, id=attempt_id)
    if attempt.test1_completed:
        return redirect('test1_summary', attempt_id=attempt_id)

    questions = attempt.exam.mcq_questions.all()
    correct_answers = []

    for q in questions:
        selected_display = request.POST.get(f'q_{q.id}', '').upper()
        shuffle_map_str = request.POST.get(f'shuffle_{q.id}', '')
        
        # Convert display option back to original option
        original_selected = selected_display
        if shuffle_map_str and selected_display:
            mapping = dict(pair.split(':') for pair in shuffle_map_str.split(',') if ':' in pair)
            original_selected = mapping.get(selected_display, selected_display)
        
        is_correct = (original_selected == q.correct_option) and bool(original_selected)
        t1a = Test1Answer.objects.create(
            attempt=attempt, question=q,
            selected_option=original_selected,
            is_correct=is_correct,
            option_shuffle_map=shuffle_map_str
        )
        if is_correct:
            correct_answers.append(t1a)

    if correct_answers:
        import random
        n_promote = max(1, math.ceil(len(correct_answers) * attempt.exam.test1_percentage / 100))
        # RANDOMLY select n_promote questions from correct answers
        promoted = random.sample(correct_answers, min(n_promote, len(correct_answers)))
        for t1a in promoted:
            t1a.promoted_to_test2 = True
            t1a.save()

    attempt.test1_completed = True
    attempt.save()

    # Save remaining timer for test2 continuation
    if attempt.test1_started_at:
        elapsed = (timezone.now() - attempt.test1_started_at).total_seconds()
        total = attempt.exam.duration_minutes * 60
        remaining = max(0, int(total - elapsed))
        request.session[f'remaining_{attempt.id}'] = remaining

    return redirect('test1_summary', attempt_id=attempt_id)


def test1_summary(request, attempt_id):
    """Show attempted/unattempted count + unlocked Test 2 questions"""
    attempt = get_object_or_404(StudentAttempt, id=attempt_id)
    t1_answers = attempt.test1_answers.all()
    attempted   = t1_answers.exclude(selected_option='').count()
    unattempted = t1_answers.filter(selected_option='').count()
    total       = t1_answers.count()

    # Get promoted questions with their one-word questions — now UNLOCKED
    promoted = attempt.test1_answers.filter(
        promoted_to_test2=True
    ).select_related('question__oneword').order_by('question__order')

    test2_unlocked = []
    for t1a in promoted:
        try:
            test2_unlocked.append({
                'mcq_order': t1a.question.order,
                'mcq_text': t1a.question.question_text,
                'ow_question': t1a.question.oneword.question_text,
            })
        except Exception:
            pass

    return render(request, 'test1_summary.html', {
        'attempt': attempt,
        'attempted': attempted,
        'unattempted': unattempted,
        'total': total,
        'test2_unlocked': test2_unlocked,
        'test2_count': len(test2_unlocked),
    })


def take_test2(request, attempt_id):
    attempt = get_object_or_404(StudentAttempt, id=attempt_id)
    if not attempt.test1_completed:
        return redirect('test1_summary', attempt_id=attempt_id)
    if attempt.test2_completed:
        return redirect('exam_submitted', attempt_id=attempt_id)

    promoted = attempt.test1_answers.filter(
        promoted_to_test2=True
    ).select_related('question__oneword').order_by('question__order')

    oneword_questions = []
    for idx, t1a in enumerate(promoted, 1):
        try:
            ow = t1a.question.oneword
            oneword_questions.append({
                'id': ow.id,
                'display_order': idx,
                'question_text': ow.question_text,
                'mcq_order': t1a.question.order,
                'mcq_text': t1a.question.question_text,
            })
        except Exception:
            pass

    if not oneword_questions:
        return _finalize_attempt(attempt, skip_test2=True)

    # Get remaining timer from session (continue from test1)
    remaining_seconds = request.session.get(f'remaining_{attempt.id}', 0)

    return render(request, 'test2.html', {
        'attempt': attempt,
        'oneword_questions': oneword_questions,
        'total': len(oneword_questions),
        'remaining_seconds': remaining_seconds,
        'duration_minutes': attempt.exam.duration_minutes,
    })


def submit_test2(request, attempt_id):
    if request.method != 'POST':
        return redirect('home')
    attempt = get_object_or_404(StudentAttempt, id=attempt_id)
    if attempt.test2_completed:
        return redirect('exam_submitted', attempt_id=attempt.id)

    promoted = attempt.test1_answers.filter(
        promoted_to_test2=True
    ).select_related('question__oneword')
    for t1a in promoted:
        try:
            ow_q = t1a.question.oneword
        except OneWordQuestion.DoesNotExist:
            continue
        student_ans = request.POST.get(f'ow_{ow_q.id}', '').strip()
        # Case-insensitive + whitespace-trimmed comparison
        is_correct = student_ans.lower().strip() == ow_q.correct_answer.lower().strip()
        Test2Answer.objects.create(
            attempt=attempt, oneword_question=ow_q,
            student_answer=student_ans,
            is_correct=is_correct
        )
    return _finalize_attempt(attempt)


def _finalize_attempt(attempt, skip_test2=False):
    all_t1 = attempt.test1_answers.all().select_related('question')
    max_marks = sum(a.question.marks for a in all_t1)
    direct_marks = bonus_marks = 0
    for t1a in all_t1:
        if not t1a.promoted_to_test2:
            if t1a.is_correct:
                direct_marks += t1a.question.marks
        elif not skip_test2:
            try:
                t2a = attempt.test2_answers.get(oneword_question=t1a.question.oneword)
                if t2a.is_correct:
                    bonus_marks += t1a.question.marks
            except Test2Answer.DoesNotExist:
                pass
    attempt.test1_direct_marks = direct_marks
    attempt.test2_bonus_marks = bonus_marks
    attempt.total_marks = direct_marks + bonus_marks
    attempt.max_possible_marks = max_marks
    attempt.test2_completed = True
    attempt.save()
    if attempt.access_code:
        attempt.access_code.is_completed = True
        attempt.access_code.save()
    return redirect('exam_submitted', attempt_id=attempt.id)


def result(request, attempt_id):
    attempt = get_object_or_404(StudentAttempt, id=attempt_id)
    if not attempt.test2_completed:
        return redirect('home')
    percentage = round(attempt.total_marks / attempt.max_possible_marks * 100, 1) if attempt.max_possible_marks else 0
    t1_answers = attempt.test1_answers.all().select_related('question')
    t2_answers = attempt.test2_answers.all().select_related('oneword_question__corresponding_mcq')
    t1_correct = t1_answers.filter(is_correct=True).count()
    t1_total   = t1_answers.count()
    t1_wrong   = t1_answers.filter(is_correct=False).exclude(selected_option='').count()
    t1_skipped = t1_answers.filter(selected_option='').count()
    return render(request, 'result.html', {
        'attempt': attempt,
        't1_answers': t1_answers,
        't2_answers': t2_answers,
        'percentage': percentage,
        't1_correct': t1_correct,
        't1_total': t1_total,
        't1_wrong': t1_wrong,
        't1_skipped': t1_skipped,
    })


def exam_submitted(request, attempt_id):
    attempt = get_object_or_404(StudentAttempt, id=attempt_id)
    return render(request, 'test2_submitted.html', {'attempt': attempt})


@login_required
def bulk_upload(request, exam_id):
    exam = get_object_or_404(ExamSession, id=exam_id, created_by=request.user)
    if request.method == 'POST':
        from .question_parser import parse_excel, parse_word, parse_text
        uploaded = request.FILES.get('question_file')
        errors = []
        parsed = []

        if uploaded:
            name = uploaded.name.lower()
            try:
                if name.endswith('.xlsx') or name.endswith('.xls'):
                    parsed = parse_excel(uploaded)
                elif name.endswith('.docx'):
                    parsed = parse_word(uploaded)
                elif name.endswith('.txt'):
                    parsed = parse_text(uploaded.read().decode('utf-8'))
                else:
                    errors.append('Unsupported file type. Use .xlsx, .docx, or .txt')
            except Exception as e:
                errors.append(f'Error parsing file: {str(e)}')

        count = exam.mcq_questions.count()
        saved = 0
        for q in parsed:
            try:
                mcq = MCQQuestion.objects.create(
                    exam=exam,
                    question_text=q['question_text'],
                    option_a=q['option_a'], option_b=q['option_b'],
                    option_c=q['option_c'], option_d=q['option_d'],
                    correct_option=q['correct_option'],
                    marks=q['marks'],
                    order=count + saved + 1
                )
                if q.get('oneword_question') and q.get('oneword_answer'):
                    OneWordQuestion.objects.create(
                        exam=exam, corresponding_mcq=mcq,
                        question_text=q['oneword_question'],
                        correct_answer=q['oneword_answer'].strip().lower()
                    )
                saved += 1
            except Exception as e:
                errors.append(f'Row error: {str(e)}')

        return render(request, 'bulk_upload.html', {
            'exam': exam, 'saved': saved, 'errors': errors, 'done': True
        })

    return render(request, 'bulk_upload.html', {'exam': exam})


# ── AI GENERATION ─────────────────────────────────────────────────
@login_required
def ai_generate_test2(request, exam_id):
    """AI generates Test 2 one-word questions from existing MCQs"""
    exam = get_object_or_404(ExamSession, id=exam_id, created_by=request.user)
    mcqs = exam.mcq_questions.all().order_by('order')

    if not mcqs.exists():
        return render(request, 'ai_generate.html', {
            'exam': exam,
            'error': 'Please add MCQ questions first before generating Test 2 questions.'
        })

    if request.method == 'POST':
        from .ai_generator import generate_oneword_questions

        # Build list for AI
        mcq_list = [{
            'question_text': q.question_text,
            'option_a': q.option_a, 'option_b': q.option_b,
            'option_c': q.option_c, 'option_d': q.option_d,
            'correct_option': q.correct_option,
        } for q in mcqs]

        results, error = generate_oneword_questions(mcq_list)

        if error:
            return render(request, 'ai_generate.html', {
                'exam': exam, 'mcqs': mcqs, 'error': error
            })

        # Save generated questions (overwrite existing oneword questions)
        saved = 0
        for item in results:
            idx = item.get('index', 0) - 1
            if 0 <= idx < len(list(mcqs)):
                mcq = list(mcqs)[idx]
                # Update or create OneWordQuestion
                from .models import OneWordQuestion
                OneWordQuestion.objects.update_or_create(
                    corresponding_mcq=mcq,
                    defaults={
                        'exam': exam,
                        'question_text': item.get('question', '').strip(),
                        'correct_answer': item.get('answer', '').strip().lower(),
                    }
                )
                saved += 1

        return render(request, 'ai_generate.html', {
            'exam': exam, 'mcqs': mcqs,
            'success': f'AI generated {saved} Test 2 questions successfully!',
            'generated': results,
        })

    return render(request, 'ai_generate.html', {'exam': exam, 'mcqs': mcqs})


@login_required
def save_api_key(request):
    """Save Claude API key to session (not permanent - for demo)"""
    if request.method == 'POST':
        import json
        data = json.loads(request.body)
        request.session['claude_api_key'] = data.get('api_key', '')
        return JsonResponse({'status': 'ok'})
    return JsonResponse({'status': 'error'}, status=400)


# ── AI VIEWS ─────────────────────────────────────────────────────

@login_required
def teacher_profile(request):
    """Teacher saves their Anthropic API key"""
    from .models import TeacherProfile
    profile, _ = TeacherProfile.objects.get_or_create(teacher=request.user)
    if request.method == 'POST':
        key = request.POST.get('api_key', '').strip()
        profile.anthropic_api_key = key
        profile.save()
        return render(request, 'teacher_profile.html', {
            'profile': profile, 'success': 'API key saved!'
        })
    return render(request, 'teacher_profile.html', {'profile': profile})



@login_required
def generate_ai_questions(request, exam_id):
    """Generate Test 2 one-word questions using Claude AI for ALL MCQs"""
    from .models import TeacherProfile, OneWordQuestion
    from .ai_generator import generate_all_questions

    exam = get_object_or_404(ExamSession, id=exam_id, created_by=request.user)

    # Get API key from teacher profile
    try:
        profile = request.user.profile
        api_key = profile.anthropic_api_key.strip()
    except Exception:
        return JsonResponse({'status': 'error',
                             'message': 'No API key found. Please add it in Profile settings first.'})

    if not api_key:
        return JsonResponse({'status': 'error',
                             'message': 'API key not set. Go to Profile page and add your Anthropic API key.'})

    mcq_questions = list(exam.mcq_questions.all().order_by('order'))
    if not mcq_questions:
        return JsonResponse({'status': 'error', 'message': 'No MCQ questions found. Add questions first.'})

    try:
        results = generate_all_questions(mcq_questions, api_key)
        saved = 0
        for mcq in mcq_questions:
            if mcq.id in results:
                data = results[mcq.id]
                try:
                    ow = mcq.oneword
                    ow.question_text = data['question']
                    ow.correct_answer = data['answer'].strip().lower()
                    ow.save()
                except OneWordQuestion.DoesNotExist:
                    OneWordQuestion.objects.create(
                        exam=exam, corresponding_mcq=mcq,
                        question_text=data['question'],
                        correct_answer=data['answer'].strip().lower()
                    )
                saved += 1

        return JsonResponse({
            'status': 'ok',
            'message': f'AI generated {saved} Test 2 questions successfully!',
            'saved': saved
        })

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'AI Error: {str(e)}'})


@login_required
def generate_ai_single(request, mcq_id):
    """Generate AI question for a single MCQ (called from add_questions page)"""
    from .models import TeacherProfile, OneWordQuestion
    from .ai_generator import generate_single_question

    mcq = get_object_or_404(MCQQuestion, id=mcq_id, exam__created_by=request.user)

    try:
        profile = request.user.profile
        api_key = profile.anthropic_api_key.strip()
    except Exception:
        return JsonResponse({'status': 'error', 'message': 'No API key found.'})

    if not api_key:
        return JsonResponse({'status': 'error', 'message': 'API key not set in Profile.'})

    correct_text = {
        'A': mcq.option_a, 'B': mcq.option_b,
        'C': mcq.option_c, 'D': mcq.option_d
    }.get(mcq.correct_option, '')

    try:
        result = generate_single_question(mcq.question_text, correct_text, api_key)
        return JsonResponse({'status': 'ok',
                             'question': result['question'],
                             'answer': result['answer']})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required
def download_seb_config(request, exam_id):
    """Generate and download .seb config file for an exam"""
    from .seb_generator import generate_seb_config
    from django.http import HttpResponse

    exam = get_object_or_404(ExamSession, id=exam_id, created_by=request.user)

    # Build the exam URL - teacher must set their server IP
    host = request.get_host()
    scheme = 'https' if request.is_secure() else 'http'
    exam_url = f"{scheme}://{host}/exam/{exam.id}/register/"

    quit_password = request.GET.get('quit_password', 'teacher123')

    seb_bytes = generate_seb_config(exam_url, exam.title, quit_password)

    # Clean filename
    safe_title = "".join(c for c in exam.title if c.isalnum() or c in (' ','-','_')).strip()
    filename = f"{safe_title}_exam.seb"

    response = HttpResponse(seb_bytes, content_type='application/seb')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def seb_setup(request, exam_id):
    exam = get_object_or_404(ExamSession, id=exam_id, created_by=request.user)
    steps = [
        "Install Safe Exam Browser on your computer (one time only): safeexambrowser.org",
        f"Get the .seb config file from your teacher for '{exam.title}'",
        "Double-click the .seb file — Safe Exam Browser will open automatically",
        "The screen will lock — only this exam website will be visible",
        "Enter your Enrollment Number and Access Code to begin",
        "After the exam is submitted, press Ctrl+Q and enter the quit password to exit SEB",
    ]
    return render(request, 'seb_setup.html', {'exam': exam, 'steps': steps})


@login_required
def download_sample_students(request):
    """Download sample student Excel file"""
    from django.http import FileResponse, HttpResponse
    import os
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                        'static', 'sample_students.xlsx')
    if os.path.exists(path):
        return FileResponse(open(path, 'rb'), 
                          content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                          as_attachment=True, filename='sample_students.xlsx')
    return HttpResponse("File not found", status=404)


# ── ANALYTICS & PDF ──────────────────────────────────────────────

@login_required
def download_result_pdf(request, attempt_id):
    """Download result as PDF"""
    from .pdf_generator import generate_result_pdf
    from django.http import HttpResponse
    attempt = get_object_or_404(StudentAttempt, id=attempt_id, exam__created_by=request.user)
    buf = generate_result_pdf(attempt)
    safe_name = "".join(c for c in attempt.student_name if c.isalnum() or c in ' _-').strip()
    filename = f"Result_{safe_name}_{attempt.exam.title}.pdf"
    resp = HttpResponse(buf.read(), content_type='application/pdf')
    resp['Content-Disposition'] = f'attachment; filename="{filename}"'
    return resp


@login_required
def download_class_pdf(request, exam_id):
    """Download all students result as PDF"""
    from .pdf_generator import generate_result_pdf
    from django.http import HttpResponse
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    import io

    exam = get_object_or_404(ExamSession, id=exam_id, created_by=request.user)
    attempts = StudentAttempt.objects.filter(exam=exam, test2_completed=True).order_by('-total_marks')

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=1.5*cm, rightMargin=1.5*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    story = []
    dark  = colors.HexColor('#0d0d14')
    muted = colors.HexColor('#6b7280')
    green = colors.HexColor('#16a34a')
    light = colors.HexColor('#f5f3ee')

    story.append(Paragraph(f"Class Results — {exam.title}",
        ParagraphStyle('t', fontSize=16, fontName='Helvetica-Bold', textColor=dark, spaceAfter=8)))
    story.append(Paragraph(f"Total Students: {attempts.count()}",
        ParagraphStyle('s', fontSize=10, textColor=muted, spaceAfter=12)))

    headers = ['#', 'Student Name', 'Enrollment', 'Marks', 'Max', '%', 'T2 Bonus']
    data = [headers]
    for i, a in enumerate(attempts, 1):
        pct = round(a.total_marks / a.max_possible_marks * 100, 1) if a.max_possible_marks else 0
        data.append([
            str(i), a.student_name, a.enrollment_no or '—',
            f"{a.total_marks:.1f}", f"{a.max_possible_marks:.0f}",
            f"{pct}%", f"{a.test2_bonus_marks:.1f}"
        ])

    t = Table(data, colWidths=[1*cm, 5*cm, 3.5*cm, 2*cm, 1.8*cm, 2*cm, 2.5*cm])
    t.setStyle(TableStyle([
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('BACKGROUND', (0,0), (-1,0), dark),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, light]),
        ('GRID', (0,0), (-1,-1), 0.3, colors.HexColor('#e0ddd8')),
        ('ALIGN', (3,0), (-1,-1), 'CENTER'),
        ('PADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t)
    doc.build(story)
    buf.seek(0)

    resp = HttpResponse(buf.read(), content_type='application/pdf')
    resp['Content-Disposition'] = f'attachment; filename="ClassResults_{exam.title}.pdf"'
    return resp


# ── ANALYTICS & PDF ──────────────────────────────────────────────

def student_analytics(request, attempt_id):
    """Per-student analytics with charts vs class average"""
    attempt = get_object_or_404(StudentAttempt, id=attempt_id, exam__created_by=request.user)
    exam    = attempt.exam

    # All completed attempts for this exam
    all_attempts = StudentAttempt.objects.filter(exam=exam, test2_completed=True)
    total_students = all_attempts.count()

    if total_students == 0:
        return render(request, 'student_analytics.html', {'attempt': attempt, 'no_data': True})

    # Class stats
    import statistics
    all_scores     = list(all_attempts.values_list('total_marks', flat=True))
    class_avg      = round(statistics.mean(all_scores), 1) if all_scores else 0
    class_max      = max(all_scores) if all_scores else 0
    class_min      = min(all_scores) if all_scores else 0
    max_possible   = attempt.max_possible_marks or 1

    student_pct    = round(attempt.total_marks / max_possible * 100, 1)
    class_avg_pct  = round(class_avg / max_possible * 100, 1)

    # Rank
    rank = sum(1 for s in all_scores if s > attempt.total_marks) + 1

    # Per-question analysis for this student
    t1_answers = attempt.test1_answers.all().select_related('question').order_by('question__order')
    t2_answers = attempt.test2_answers.all().select_related('oneword_question__corresponding_mcq')

    t1_correct  = t1_answers.filter(is_correct=True).count()
    t1_wrong    = t1_answers.filter(is_correct=False).exclude(selected_option='').count()
    t1_skipped  = t1_answers.filter(selected_option='').count()
    t1_promoted = t1_answers.filter(promoted_to_test2=True).count()
    t2_correct  = t2_answers.filter(is_correct=True).count()
    t2_wrong    = t2_answers.filter(is_correct=False).count()

    # Score distribution buckets for histogram
    buckets = {'0-25%': 0, '26-50%': 0, '51-75%': 0, '76-100%': 0}
    for s in all_scores:
        pct = (s / max_possible) * 100
        if pct <= 25:   buckets['0-25%'] += 1
        elif pct <= 50: buckets['26-50%'] += 1
        elif pct <= 75: buckets['51-75%'] += 1
        else:           buckets['76-100%'] += 1

    return render(request, 'student_analytics.html', {
        'attempt': attempt,
        'exam': exam,
        'total_students': total_students,
        'class_avg': class_avg,
        'class_avg_pct': class_avg_pct,
        'class_max': class_max,
        'class_min': class_min,
        'student_pct': student_pct,
        'rank': rank,
        'max_possible': max_possible,
        't1_correct': t1_correct, 't1_wrong': t1_wrong,
        't1_skipped': t1_skipped, 't1_promoted': t1_promoted,
        't2_correct': t2_correct, 't2_wrong': t2_wrong,
        't1_total': t1_answers.count(),
        't2_total': t2_answers.count(),
        't1_answers': t1_answers,
        't2_answers': t2_answers,
        'bucket_list': [buckets['0-25%'], buckets['26-50%'], buckets['51-75%'], buckets['76-100%']],
        'all_scores_json': list(all_scores),
    })


def exam_analytics(request, exam_id):
    """Full exam question-wise analysis with charts"""
    exam = get_object_or_404(ExamSession, id=exam_id, created_by=request.user)
    all_attempts = StudentAttempt.objects.filter(exam=exam, test2_completed=True)
    total_students = all_attempts.count()

    questions = exam.mcq_questions.all().order_by('order')
    q_analysis = []

    for q in questions:
        answers = Test1Answer.objects.filter(attempt__in=all_attempts, question=q)
        total_ans   = answers.count()
        correct     = answers.filter(is_correct=True).count()
        wrong       = answers.filter(is_correct=False).exclude(selected_option='').count()
        skipped     = answers.filter(selected_option='').count()
        correct_pct = round(correct / total_ans * 100) if total_ans else 0

        # Option distribution
        opt_dist = {}
        for opt in ['A', 'B', 'C', 'D']:
            opt_dist[opt] = answers.filter(selected_option=opt).count()

        q_analysis.append({
            'order': q.order,
            'text': q.question_text[:80],
            'correct_option': q.correct_option,
            'total': total_ans,
            'correct': correct,
            'wrong': wrong,
            'skipped': skipped,
            'correct_pct': correct_pct,
            'opt_dist': opt_dist,
            'difficulty': 'Easy' if correct_pct >= 70 else ('Medium' if correct_pct >= 40 else 'Hard'),
        })

    # Overall stats
    import statistics
    all_scores = list(all_attempts.values_list('total_marks', flat=True))
    avg_score   = round(statistics.mean(all_scores), 1) if all_scores else 0
    max_possible = questions.count()  # approximate

    # Sort by difficulty
    easy_qs   = [q for q in q_analysis if q['difficulty'] == 'Easy']
    medium_qs = [q for q in q_analysis if q['difficulty'] == 'Medium']
    hard_qs   = [q for q in q_analysis if q['difficulty'] == 'Hard']

    return render(request, 'exam_analytics.html', {
        'exam': exam,
        'total_students': total_students,
        'avg_score': avg_score,
        'q_analysis': q_analysis,
        'easy_count': len(easy_qs),
        'medium_count': len(medium_qs),
        'hard_count': len(hard_qs),
        'all_scores_json': list(all_scores),
        'q_correct_pcts': [q['correct_pct'] for q in q_analysis],
        'q_labels': [f"Q{q['order']}" for q in q_analysis],
    })


def generate_result_pdf(request, attempt_id):
    """Generate PDF result card for a student"""
    from django.http import HttpResponse
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    import io

    attempt = get_object_or_404(StudentAttempt, id=attempt_id, exam__created_by=request.user)
    pct = round(attempt.total_marks / attempt.max_possible_marks * 100, 1) if attempt.max_possible_marks else 0

    t1 = attempt.test1_answers.all().select_related('question')
    t2 = attempt.test2_answers.all().select_related('oneword_question__corresponding_mcq')
    t1_correct = t1.filter(is_correct=True).count()
    t1_total   = t1.count()
    t2_correct = t2.filter(is_correct=True).count()
    t2_total   = t2.count()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)

    styles = getSampleStyleSheet()
    title_style   = ParagraphStyle('title', fontSize=20, fontName='Helvetica-Bold',
                                    alignment=TA_CENTER, spaceAfter=6)
    sub_style     = ParagraphStyle('sub', fontSize=12, fontName='Helvetica',
                                    alignment=TA_CENTER, spaceAfter=4, textColor=colors.grey)
    heading_style = ParagraphStyle('h', fontSize=13, fontName='Helvetica-Bold', spaceBefore=14, spaceAfter=6)
    normal        = styles['Normal']

    story = []

    # Header
    story.append(Paragraph(attempt.exam.title, title_style))
    story.append(Paragraph("Result Card", sub_style))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#e84c1e')))
    story.append(Spacer(1, 0.4*cm))

    # Student info table
    info_data = [
        ['Student Name', attempt.student_name],
        ['Enrollment No.', attempt.enrollment_no or '—'],
        ['Exam Date', attempt.started_at.strftime('%d %B %Y')],
        ['Exam', attempt.exam.title],
    ]
    info_table = Table(info_data, colWidths=[5*cm, 12*cm])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
        ('FONTNAME', (1,0), (1,-1), 'Helvetica'),
        ('FONTSIZE', (0,0), (-1,-1), 11),
        ('ROWBACKGROUNDS', (0,0), (-1,-1), [colors.HexColor('#f9f8f6'), colors.white]),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e0ddd8')),
        ('PADDING', (0,0), (-1,-1), 7),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 0.5*cm))

    # Score summary
    story.append(Paragraph("Score Summary", heading_style))
    score_data = [
        ['', 'Value', 'Out of', 'Percentage'],
        ['Total Marks',      f"{attempt.total_marks:.1f}",       f"{attempt.max_possible_marks:.0f}", f"{pct}%"],
        ['Direct Marks (T1)', f"{attempt.test1_direct_marks:.1f}", '—', '—'],
        ['Bonus Marks (T2)', f"{attempt.test2_bonus_marks:.1f}",  '—', '—'],
        ['T1 Correct',       str(t1_correct), str(t1_total), f"{round(t1_correct/t1_total*100) if t1_total else 0}%"],
        ['T2 Correct',       str(t2_correct), str(t2_total), f"{round(t2_correct/t2_total*100) if t2_total else 0}%"],
    ]
    score_table = Table(score_data, colWidths=[6*cm, 3.5*cm, 3.5*cm, 4*cm])
    score_table.setStyle(TableStyle([
        ('BACKGROUND',  (0,0), (-1,0), colors.HexColor('#1a1a2e')),
        ('TEXTCOLOR',   (0,0), (-1,0), colors.white),
        ('FONTNAME',    (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTNAME',    (0,1), (-1,-1), 'Helvetica'),
        ('FONTSIZE',    (0,0), (-1,-1), 10),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor('#f0f0f0'), colors.white]),
        ('GRID',        (0,0), (-1,-1), 0.5, colors.HexColor('#e0ddd8')),
        ('PADDING',     (0,0), (-1,-1), 7),
        ('ALIGN',       (1,0), (-1,-1), 'CENTER'),
    ]))
    story.append(score_table)
    story.append(Spacer(1, 0.5*cm))

    # Result verdict
    verdict = "PASS ✓" if pct >= 40 else "FAIL ✗"
    v_color = colors.HexColor('#16a34a') if pct >= 40 else colors.HexColor('#dc2626')
    verdict_style = ParagraphStyle('v', fontSize=16, fontName='Helvetica-Bold',
                                    alignment=TA_CENTER, textColor=v_color, spaceBefore=8)
    story.append(Paragraph(f"Final Result: {verdict} ({pct}%)", verdict_style))
    story.append(Spacer(1, 0.3*cm))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#e0ddd8')))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph("Generated by ExamFlow", sub_style))

    doc.build(story)
    buffer.seek(0)

    safe_name = "".join(c for c in attempt.student_name if c.isalnum() or c == ' ').strip()
    filename  = f"{safe_name}_{attempt.exam.title}_result.pdf"
    response  = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def generate_all_results_pdf(request, exam_id):
    """Generate combined PDF with all students' results"""
    from django.http import HttpResponse
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    import io

    exam     = get_object_or_404(ExamSession, id=exam_id, created_by=request.user)
    attempts = StudentAttempt.objects.filter(exam=exam, test2_completed=True).order_by('-total_marks')

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=1.5*cm, leftMargin=1.5*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles  = getSampleStyleSheet()
    t_style = ParagraphStyle('t', fontSize=16, fontName='Helvetica-Bold', alignment=TA_CENTER, spaceAfter=4)
    s_style = ParagraphStyle('s', fontSize=10, fontName='Helvetica', alignment=TA_CENTER,
                              spaceAfter=12, textColor=colors.grey)
    story   = []

    story.append(Paragraph(exam.title, t_style))
    story.append(Paragraph(f"Class Results — {attempts.count()} Students", s_style))

    headers = ['Rank', 'Name', 'Enrollment', 'T1 Correct', 'T2 Correct', 'Total', 'Max', '%', 'Grade']
    data    = [headers]

    max_p = attempts.first().max_possible_marks if attempts.exists() else 1

    for rank, att in enumerate(attempts, 1):
        pct   = round(att.total_marks / max_p * 100, 1) if max_p else 0
        grade = 'A+' if pct>=90 else ('A' if pct>=80 else ('B' if pct>=70 else ('C' if pct>=60 else ('D' if pct>=40 else 'F'))))
        t1c   = att.test1_answers.filter(is_correct=True).count()
        t2c   = att.test2_answers.filter(is_correct=True).count()
        data.append([
            str(rank), att.student_name, att.enrollment_no or '—',
            str(t1c), str(t2c),
            f"{att.total_marks:.1f}", f"{att.max_possible_marks:.0f}",
            f"{pct}%", grade
        ])

    col_w = [1.2*cm, 4.5*cm, 3*cm, 2.2*cm, 2.2*cm, 1.8*cm, 1.8*cm, 1.8*cm, 1.5*cm]
    table = Table(data, colWidths=col_w, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND',  (0,0), (-1,0), colors.HexColor('#1a1a2e')),
        ('TEXTCOLOR',   (0,0), (-1,0), colors.white),
        ('FONTNAME',    (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE',    (0,0), (-1,-1), 9),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor('#f9f8f6'), colors.white]),
        ('GRID',        (0,0), (-1,-1), 0.4, colors.HexColor('#e0ddd8')),
        ('PADDING',     (0,0), (-1,-1), 5),
        ('ALIGN',       (0,0), (-1,-1), 'CENTER'),
        ('ALIGN',       (1,0), (1,-1), 'LEFT'),
        ('ALIGN',       (2,0), (2,-1), 'LEFT'),
    ]))
    story.append(table)
    doc.build(story)
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{exam.title}_all_results.pdf"'
    return response


@login_required  
def download_student_codes_pdf(request, exam_id):
    """Generate PDF with student names, enrollment, access codes and signature column"""
    from django.http import HttpResponse
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    import io

    exam = get_object_or_404(ExamSession, id=exam_id, created_by=request.user)
    codes = exam.access_codes.all().order_by('student_name')

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=1.5*cm, leftMargin=1.5*cm,
                            topMargin=2*cm, bottomMargin=2*cm)

    styles = getSampleStyleSheet()
    title_s = ParagraphStyle('t', fontSize=16, fontName='Helvetica-Bold', alignment=TA_CENTER, spaceAfter=4)
    sub_s   = ParagraphStyle('s', fontSize=10, fontName='Helvetica', alignment=TA_CENTER, spaceAfter=16, textColor=colors.grey)

    story = []
    story.append(Paragraph(exam.title, title_s))
    story.append(Paragraph(f"Student Access Codes — {codes.count()} Students", sub_s))

    # Table headers
    headers = ['#', 'Student Name', 'Enrollment No.', 'Access Code', 'Signature']
    data = [headers]

    for i, ac in enumerate(codes, 1):
        status = '✓ Used' if ac.is_used else 'Unused'
        data.append([
            str(i),
            ac.student_name,
            ac.enrollment_no or '—',
            ac.code,
            '',  # blank for signature
        ])

    col_w = [1*cm, 5.5*cm, 4*cm, 3.5*cm, 4*cm]
    table = Table(data, colWidths=col_w, repeatRows=1,
                  rowHeights=[0.8*cm] + [1.2*cm]*len(codes))
    table.setStyle(TableStyle([
        # Header
        ('BACKGROUND',   (0,0), (-1,0), colors.HexColor('#1a1a2e')),
        ('TEXTCOLOR',    (0,0), (-1,0), colors.white),
        ('FONTNAME',     (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE',     (0,0), (-1,0), 10),
        # Data rows
        ('FONTNAME',     (0,1), (-1,-1), 'Helvetica'),
        ('FONTSIZE',     (0,1), (-1,-1), 10),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor('#f9f8f6'), colors.white]),
        # Access code - monospace style
        ('FONTNAME',     (3,1), (3,-1), 'Courier-Bold'),
        ('FONTSIZE',     (3,1), (3,-1), 11),
        # Grid
        ('GRID',         (0,0), (-1,-1), 0.5, colors.HexColor('#e0ddd8')),
        ('PADDING',      (0,0), (-1,-1), 7),
        ('ALIGN',        (0,0), (0,-1), 'CENTER'),
        ('ALIGN',        (3,0), (3,-1), 'CENTER'),
        ('VALIGN',       (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(table)

    doc.build(story)
    buffer.seek(0)

    safe = "".join(c for c in exam.title if c.isalnum() or c == ' ').strip()
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{safe}_student_codes.pdf"'
    return response
