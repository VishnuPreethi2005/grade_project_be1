from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.db.models import Sum
from .models import (
    AnswerUpload, QuestionFeedback, SampleQuestionPaper, PreviousYearQuestionPaper,
    GeneratedQuestionPaper, GradingResult, QuestionGrade, CriteriaGrade, AIMetrics,
    MentorStudent, Evaluator, Language, Subject, Board, Question, MainRequest,
    Notification, AnswerAssignment, MentorshipRequest, Feedback
)

# ========================================================
#  HELPER FUNCTIONS (For Grading Visuals)
# ========================================================

def resolve_url(path):
    if not path: return ""
    clean_path = str(path).replace("\\", "/").strip("/")
    if clean_path.startswith("http"): return clean_path
    if clean_path.startswith("media/"): return f"/{clean_path}"
    return f"/media/{clean_path}"

def format_json_content(data):
    """Helper to convert answer JSON into readable HTML."""
    if not data or not isinstance(data, dict): return str(data) if data else "-"
    html = []
    if "text" in data and data["text"]:
        html.append(f'<div style="margin-bottom: 8px; white-space: pre-wrap;">{data["text"]}</div>')
    if "bullets" in data and data["bullets"]:
        items = "".join([f"<li>{item}</li>" for item in data["bullets"]])
        html.append(f'<ul style="margin: 5px 0 10px 20px;">{items}</ul>')
    if "equations" in data and data["equations"]:
        for eq in data["equations"]:
            val = eq.get("equation", "") if isinstance(eq, dict) else eq
            html.append(f'<div style="background:#f0f8ff;padding:4px;margin:2px 0;border-left:3px solid #007bff;font-family:monospace;">{val}</div>')
    if "tables" in data and data["tables"]:
        for idx, tbl in enumerate(data["tables"]):
            rows = ""
            if isinstance(tbl, dict):
                for k, v in tbl.items():
                    rows += f"<tr><td style='border:1px solid #ddd;padding:4px;background:#f1f1f1;'><strong>{k}</strong></td><td style='border:1px solid #ddd;padding:4px;'>{v}</td></tr>"
            html.append(f'<table style="width:100%;border-collapse:collapse;margin-top:5px;font-size:13px;">{rows}</table>')
    return "".join(html)

# ========================================================
#  NEW GRADING RESULT ADMIN (The Dashboard)
# ========================================================

class QuestionGradeInline(admin.TabularInline):
    """The custom 'All-in-One' row for each question."""
    model = QuestionGrade
    extra = 0
    can_delete = False
    
    # Optimization settings
    per_page = 10 
    show_full_result_count = False
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('grading_result__answer_upload').prefetch_related('criteria_grades')

    fields = ('comprehensive_row_view',)
    readonly_fields = ('comprehensive_row_view',)
    
    verbose_name = "Question Detail"
    verbose_name_plural = "Graded Questions Overview"

    def formfield_for_dbfield(self, db_field, **kwargs):
        return super().formfield_for_dbfield(db_field, **kwargs)

    def comprehensive_row_view(self, obj):
        # 1. DATA PREP
        s_imgs = []
        if obj.student_answer and isinstance(obj.student_answer, dict):
            d = obj.student_answer.get("diagram")
            if isinstance(d, dict): s_imgs = [resolve_url(v) for v in d.values()]
            elif isinstance(d, list): s_imgs = [resolve_url(v) for v in d]
        
        r_imgs = []
        if obj.expected_answer and isinstance(obj.expected_answer, dict):
            d = obj.expected_answer.get("diagram")
            if isinstance(d, dict): r_imgs.extend([resolve_url(v) for v in d.values()])
            elif isinstance(d, list): r_imgs.extend([resolve_url(v) for v in d])
            l = obj.expected_answer.get("reference_diagram_paths")
            if isinstance(l, list): r_imgs.extend([resolve_url(v) for v in l])

        # No per-question metrics - summary is shown in GradingResultAdmin header

        # Criteria
        criteria_rows = ""
        for c in obj.criteria_grades.all():
            criteria_rows += f"""
            <tr style="border-bottom:1px solid var(--hairline-color, #ccc);">
                <td style="padding:6px; width:35%; vertical-align:top; font-weight:500;">{c.criterion_text}</td>
                <td style="padding:6px; text-align:center; width:10%; vertical-align:top;"><strong>{c.obtained_marks}</strong> / {c.allocated_marks}</td>
                <td style="padding:6px; font-size:0.95em; vertical-align:top;">{c.feedback}</td>
            </tr>
            """
        if not criteria_rows: criteria_rows = "<tr><td colspan='3' style='padding:10px;'>No criteria found.</td></tr>"

        # 3. Concept Analysis
        concept_rows = ""
        if obj.concept_analysis and isinstance(obj.concept_analysis, list):
            for c in obj.concept_analysis:
                mastery = c.get("mastery_class", "N/A")
                score = c.get("concept_accuracy_percentage", 0)
                reason = c.get("reasoning", "")
                name = c.get("concept_name", "Unknown Concept")
                
                # Color coding for mastery
                bg_color = "#f8f9fa"
                if mastery == "High": bg_color = "#d4edda"
                elif mastery == "Good": bg_color = "#e2e3e5"
                elif mastery == "Bad": bg_color = "#f8d7da"

                concept_rows += f"""
                <tr style="border-bottom:1px solid var(--hairline-color, #ccc); background:{bg_color};">
                    <td style="padding:6px; font-weight:bold;">{name}</td>
                    <td style="padding:6px; text-align:center;">{mastery} ({score}%)</td>
                    <td style="padding:6px; font-size:0.95em;">{reason}</td>
                </tr>
                """
        
        if not concept_rows:
            concept_rows = "<tr><td colspan='3' style='padding:10px; color:#666;'>No concept analysis available.</td></tr>"

        # 4. RENDER HTML (Adaptive - works with light/dark mode)
        html = f"""
        <div style="width: 100%; min-width: 800px; border: 1px solid var(--hairline-color, #ccc); border-radius: 4px; margin-bottom: 15px;">
            <div style="padding: 10px 15px; border-bottom: 1px solid var(--hairline-color, #ccc); display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <span style="font-size: 1.2em; font-weight: 900;">{obj.question_number}</span>
                    <span style="font-size: 1em; margin-left: 5px; font-weight: 600;">({obj.question_type})</span>
                </div>
                <div style="display: flex; gap: 10px; align-items: center;">
                    <span style="background: var(--primary, #417690); color: var(--primary-fg, #fff); padding: 4px 10px; border-radius: 4px; font-weight: bold;">
                        {obj.obtained_marks} / {obj.allocated_marks} Marks
                    </span>
                </div>
            </div>
            <div style="display: flex; flex-wrap: wrap; border-bottom: 1px solid var(--hairline-color, #ccc);">
                <div style="flex: 1; min-width: 300px; padding: 15px; border-right: 1px solid var(--hairline-color, #ccc);">
                    <div style="font-size: 0.9em; text-transform: uppercase; font-weight: 900; margin-bottom: 10px; letter-spacing: 0.5px; text-decoration: underline;">Student Answer</div>
                    <div style="font-size: 1em; line-height: 1.5;">{format_json_content(obj.student_answer)}</div>
                    <div style="margin-top:10px;">{''.join([f'<a href="{s}" target="_blank"><img src="{s}" style="max-height:100px; border:1px solid var(--hairline-color, #ccc); margin:4px;"></a>' for s in s_imgs])}</div>
                </div>
                <div style="flex: 1; min-width: 300px; padding: 15px;">
                    <div style="font-size: 0.9em; text-transform: uppercase; font-weight: 900; margin-bottom: 10px; letter-spacing: 0.5px; text-decoration: underline;">Expected Answer</div>
                    <div style="font-size: 1em; line-height: 1.5;">{format_json_content(obj.expected_answer)}</div>
                    <div style="margin-top:10px;">{''.join([f'<a href="{s}" target="_blank"><img src="{s}" style="max-height:100px; border:1px solid var(--hairline-color, #ccc); margin:4px;"></a>' for s in r_imgs])}</div>
                </div>
            </div>
            <div style="padding: 15px;">
                <div style="margin-bottom: 15px; font-size: 1em;">
                    <div style="margin-bottom:6px;"><strong style="font-weight: 900;">Summary:</strong> {obj.summary or "None"}</div>
                    <div><strong style="font-weight: 900;">Mistakes:</strong> <span style="color: var(--error-fg, #ba2121); font-weight: bold;">{', '.join(obj.mistakes_identified) if obj.mistakes_identified else "None"}</span></div>
                </div>
                
                <div style="display:flex; gap:15px; flex-wrap:wrap;">
                    <!-- Criteria Table -->
                    <div style="flex:1; min-width:350px; border: 1px solid var(--hairline-color, #ccc); border-radius: 4px; overflow: hidden;">
                        <div style="background:var(--header-bg, #eee); padding:8px; font-weight:bold; border-bottom:1px solid #ccc;">Evaluation Criteria</div>
                        <table style="width: 100%; border-collapse: collapse; font-size: 0.95em;">
                            <thead style="border-bottom: 1px solid var(--hairline-color, #ccc);">
                                <tr>
                                    <th style="padding: 8px; text-align: left; font-weight: 900;">Criterion</th>
                                    <th style="padding: 8px; text-align: center; font-weight: 900;">Score</th>
                                    <th style="padding: 8px; text-align: left; font-weight: 900;">Feedback</th>
                                </tr>
                            </thead>
                            <tbody>{criteria_rows}</tbody>
                        </table>
                    </div>

                    <!-- Concept Analysis Table -->
                    <div style="flex:1; min-width:350px; border: 1px solid var(--hairline-color, #ccc); border-radius: 4px; overflow: hidden;">
                        <div style="background:var(--header-bg, #eee); padding:8px; font-weight:bold; border-bottom:1px solid #ccc;">Concept Analysis (AI Confidence: {obj.confidence_percentage}% - {obj.confidence_level})</div>
                        <table style="width: 100%; border-collapse: collapse; font-size: 0.95em;">
                            <thead style="border-bottom: 1px solid var(--hairline-color, #ccc);">
                                <tr>
                                    <th style="padding: 8px; text-align: left; font-weight: 900;">Concept</th>
                                    <th style="padding: 8px; text-align: center; font-weight: 900;">Mastery</th>
                                    <th style="padding: 8px; text-align: left; font-weight: 900;">Reasoning</th>
                                </tr>
                            </thead>
                            <tbody>{concept_rows}</tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
        """
        return mark_safe(html)

@admin.register(GradingResult)
class GradingResultAdmin(admin.ModelAdmin):
    list_display = (
        "answer_upload", "attempt_number_display", "user_id", "total_score", "max_possible_score", 
        "percentage", "grading_processed", "questions_count", 
        "diagrams_count", "graded_at"
    )
    list_filter = ("grading_processed", "created_at", "graded_at")
    search_fields = ("user_id", "answer_upload__id")
    readonly_fields = ("created_at", "graded_at", "percentage", "token_summary_display")

    fieldsets = (
        ("Answer Information", {"fields": ("answer_upload", "user_id")}),
        ("💰 Token Usage & Cost Summary", {
            "fields": ("token_summary_display",),
            "description": "Total token usage and costs for OCR and Grading processes."
        }),
        ("Grading Results", {
            "fields": ("total_score", "max_possible_score", "percentage", "questions_count", "diagrams_count")
        }),
        ("Processing Status", {
            "fields": ("grading_processed", "grading_error", "result_json_path"),
            "classes": ("collapse",)
        }),
        ("Timestamps", {
            "fields": ("created_at", "graded_at"), "classes": ("collapse",)
        }),
    )

    inlines = [QuestionGradeInline]

    def attempt_number_display(self, obj):
        """Display the attempt number from the related answer_upload."""
        if obj.answer_upload:
            return obj.answer_upload.attempt_number
        return "-"
    attempt_number_display.short_description = "Attempt #"
    attempt_number_display.admin_order_field = "answer_upload__attempt_number"

    def token_summary_display(self, obj):
        """Display OCR, Grading, and Combined token summaries."""
        if not obj or not obj.answer_upload:
            return "No data available"
        
        try:
            au = obj.answer_upload
            
            # OCR Totals
            ocr_metrics = AIMetrics.objects.filter(answer_upload=au, process_type='OCR')
            ocr_agg = ocr_metrics.aggregate(
                total_input=Sum('input_tokens'),
                total_output=Sum('output_tokens'),
                total_tokens=Sum('total_tokens'),
                total_cost=Sum('total_cost_usd')
            )
            ocr_input = ocr_agg['total_input'] or 0
            ocr_output = ocr_agg['total_output'] or 0
            ocr_tokens = ocr_agg['total_tokens'] or 0
            ocr_cost = float(ocr_agg['total_cost'] or 0)
            
            # Grading Totals
            grading_metrics = AIMetrics.objects.filter(answer_upload=au, process_type='GRADING')
            grading_agg = grading_metrics.aggregate(
                total_input=Sum('input_tokens'),
                total_output=Sum('output_tokens'),
                total_tokens=Sum('total_tokens'),
                total_cost=Sum('total_cost_usd')
            )
            grading_input = grading_agg['total_input'] or 0
            grading_output = grading_agg['total_output'] or 0
            grading_tokens = grading_agg['total_tokens'] or 0
            grading_cost = float(grading_agg['total_cost'] or 0)
            
            # Combined Totals
            combined_input = ocr_input + grading_input
            combined_output = ocr_output + grading_output
            combined_tokens = ocr_tokens + grading_tokens
            combined_cost = ocr_cost + grading_cost
            
            html = f'''
            <table style="width:100%; max-width:800px; border-collapse:collapse; margin:10px 0; font-size:14px;">
                <thead>
                    <tr style="background:var(--header-bg, transparent); border-bottom:2px solid var(--hairline-color, #ccc);">
                        <th style="padding:12px; text-align:left; font-weight:bold;">Process</th>
                        <th style="padding:12px; text-align:right; font-weight:bold;">Input Tokens</th>
                        <th style="padding:12px; text-align:right; font-weight:bold;">Output Tokens</th>
                        <th style="padding:12px; text-align:right; font-weight:bold;">Total Tokens</th>
                        <th style="padding:12px; text-align:right; font-weight:bold;">Cost (USD)</th>
                    </tr>
                </thead>
                <tbody>
                    <tr style="border-bottom:1px solid var(--hairline-color, #ccc);">
                        <td style="padding:10px; font-weight:bold;">📝 OCR</td>
                        <td style="padding:10px; text-align:right;">{ocr_input:,}</td>
                        <td style="padding:10px; text-align:right;">{ocr_output:,}</td>
                        <td style="padding:10px; text-align:right;">{ocr_tokens:,}</td>
                        <td style="padding:10px; text-align:right;">${ocr_cost:.6f}</td>
                    </tr>
                    <tr style="border-bottom:1px solid var(--hairline-color, #ccc);">
                        <td style="padding:10px; font-weight:bold;">📊 Grading</td>
                        <td style="padding:10px; text-align:right;">{grading_input:,}</td>
                        <td style="padding:10px; text-align:right;">{grading_output:,}</td>
                        <td style="padding:10px; text-align:right;">{grading_tokens:,}</td>
                        <td style="padding:10px; text-align:right;">${grading_cost:.6f}</td>
                    </tr>
                    <tr style="font-weight:bold; border-top:2px solid var(--hairline-color, #ccc);">
                        <td style="padding:12px;">💰 COMBINED TOTAL</td>
                        <td style="padding:12px; text-align:right;">{combined_input:,}</td>
                        <td style="padding:12px; text-align:right;">{combined_output:,}</td>
                        <td style="padding:12px; text-align:right;">{combined_tokens:,}</td>
                        <td style="padding:12px; text-align:right;">${combined_cost:.6f}</td>
                    </tr>
                </tbody>
            </table>
            '''
            return mark_safe(html)
        except Exception as e:
            return f"Error loading metrics: {e}"
    
    token_summary_display.short_description = "Token Usage Summary"

    def get_readonly_fields(self, request, obj=None) -> list:
        readonly = list(self.readonly_fields)
        if obj: readonly.extend(["answer_upload", "user_id"])
        return readonly

# Hide plain QuestionGrade from sidebar (User should go via GradingResult)
@admin.register(QuestionGrade)
class QuestionGradeAdmin(admin.ModelAdmin):
    def has_module_permission(self, request): return False


# ========================================================
#  STANDARD MODELS (Restored exactly as requested)
# ========================================================

@admin.register(AnswerUpload)
class AnswerUploadAdmin(admin.ModelAdmin):
    list_display = (
        "user_id", "organization", "question_paper_type", 
        "question_paper_id", "attempt_number", "upload_date", "ocr_processed",
    )
    list_filter = ("question_paper_type", "upload_date", "ocr_processed", "organization")
    search_fields = ("user_id", "question_paper_id", "organization__name")
    readonly_fields = ("upload_date", "ocr_processed_at")

    fieldsets = (
        ("User Information", {"fields": ("user_id", "organization", "file", "upload_date")}),
        ("Question Paper Details", {
            "fields": ("question_paper_type", "question_paper_id", "sample_question_paper", "previous_year_question_paper", "generated_question_paper", "questions")
        }),
        ("OCR Processing", {
            "fields": ("ocr_processed", "ocr_json_path", "ocr_images_dir", "ocr_error", "ocr_processed_at"),
            "classes": ("collapse",),
        }),
    )
    raw_id_fields = ["organization"]


@admin.register(QuestionFeedback)
class QuestionFeedbackAdmin(admin.ModelAdmin):
    list_display = ("answer_upload", "marks_obtained", "created_date")
    list_filter = ("created_date",)
    search_fields = ("answer_upload__user_id",)
    readonly_fields = ("created_date",)


class BaseQuestionPaperAdmin(admin.ModelAdmin):
    list_display = (
        "test_title", "subject", "board", "organization", 
        "total_marks", "total_questions", "upload_date"
    )
    list_filter = ("board", "subject", "upload_date", "organization")
    search_fields = ("test_title", "subject", "board", "organization__name")
    readonly_fields = ("upload_date",)
    fieldsets = (
        ("Paper Information", {
            "fields": ("organization", "test_title", "subject", "board", "updated_by", "upload_date")
        }),
        ("Questions and Marks", {"fields": ("questions", "total_marks", "total_questions")}),
    )
    raw_id_fields = ["organization"]


# @admin.register(SampleQuestionPaper)
# class SampleQuestionPaperAdmin(BaseQuestionPaperAdmin):
#     list_display = BaseQuestionPaperAdmin.list_display + ("file",)


@admin.register(PreviousYearQuestionPaper)
class PreviousYearQuestionPaperAdmin(BaseQuestionPaperAdmin):
    # NOTE: 'file' field removed from model - QP files not uploaded due to copyright
    list_display = BaseQuestionPaperAdmin.list_display + ("year", "set_number", "qp_code")
    list_filter = BaseQuestionPaperAdmin.list_filter + ("year", "set_number", "qp_code")
    search_fields = BaseQuestionPaperAdmin.search_fields + ("year", "set_number", "qp_code")
    fieldsets = (
        (
            "Paper Information",
            {
                "fields": (
                    "test_title",
                    "subject",
                    "board",
                    "year",
                    "set_number",
                    "qp_code",
                    "updated_by",
                    "upload_date",
                )
            },
        ),
        (
            "Questions and Marks",
            {"fields": ("questions", "total_marks", "total_questions")},
        ),
        ("Answer Key", {"fields": ("answer_key", "answer_key_uploaded_at")}),
        ("Asset Management", {
            "fields": ("assets", "new_asset_file", "new_asset_label"),
            "description": "Upload a single asset file (e.g. image) and assign it a label (e.g. 'Q4') to add it to the Assets list."
        }),
    )


@admin.register(GeneratedQuestionPaper)
class GeneratedQuestionPaperAdmin(BaseQuestionPaperAdmin):
    list_display = BaseQuestionPaperAdmin.list_display + ("user_id", "file")
    search_fields = BaseQuestionPaperAdmin.search_fields + ("user_id",)
    fieldsets = (
        ("Paper Information", {
            "fields": ("test_title", "subject", "board", "updated_by", "upload_date")
        }),
        ("User Information", {"fields": ("user_id",)}),
        ("Questions and Marks", {"fields": ("total_marks", "total_questions")}),
        ("Files", {"fields": ("file",)}),
    )


class FeedbackAdmin(admin.ModelAdmin):
    list_display = ("answer_upload", "question_number", "marks_obtained", "complexity", "feedback", "marks_out_of", "created_at", "updated_at")
    search_fields = ("answer_upload__answer_id", "question_number")
    list_filter = ("complexity",)
    ordering = ("-updated_at",)
admin.site.register(Feedback, FeedbackAdmin)


@admin.register(MentorshipRequest)
class MentorStudentRequestAdmin(admin.ModelAdmin):
    list_display = ("mentor", "student", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("mentor__email", "student__email")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("sender", "sender_role", "recipient", "recipient_role", "message", "created_at", "is_read", "mentor_request")
    list_filter = ("is_read", "created_at", "sender_role", "recipient_role")
    search_fields = ("sender__username", "recipient__username", "message")
    ordering = ("-created_at",)


@admin.register(MentorStudent)
class MentorStudentAdmin(admin.ModelAdmin):
    list_display = ("mentor", "student", "created_at")
    search_fields = ("mentor__user__username", "student__user__username")
    list_filter = ("mentor", "created_at")


@admin.register(MainRequest)
class MainRequestAdmin(admin.ModelAdmin):
    list_display = ("user", "resume", "role", "board", "subject", "submitted_at")


class QuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "subject", "topic", "exam_type", "is_submitted", "complexity", "question_type", "marks", "question_text", "question_image", "options", "correct_answer", "explanation", "explanation_image", "created_at")
    list_filter = ("subject", "exam_type", "complexity", "question_type", "created_at", "is_submitted")
    search_fields = ("subject", "topic", "question_text")
    fieldsets = (
        ("General Information", {
            "fields": ("subject", "topic", "exam_type", "complexity", "question_type", "marks", "is_submitted")
        }),
        ("Question Content", {"fields": ("question_text", "question_image")}),
        ("Options (For MCQ)", {
            "fields": ("options", "correct_answer"),
            "classes": ("collapse",),
        }),
        ("Explanation & Solution", {"fields": ("explanation", "explanation_image")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )
    readonly_fields = ("created_at", "updated_at")
admin.site.register(Question, QuestionAdmin)


@admin.register(AnswerAssignment)
class AnswerAssignmentAdmin(admin.ModelAdmin):
    list_display = ("answer_upload", "evaluator", "assigned_date", "completed", "is_expired_display")
    list_filter = ("completed", "assigned_date")
    search_fields = ("evaluator__email", "answer_upload__id")
    def is_expired_display(self, obj) -> bool:
        return obj.is_expired()
    is_expired_display.boolean = True
    is_expired_display.short_description = "Expired"


@admin.register(Evaluator)
class EvaluatorAdmin(admin.ModelAdmin):
    list_display = ("user", "rating")
    search_fields = ("user__username",)
    filter_horizontal = ("languages", "subjects", "boards")


@admin.register(Language)
class LanguageAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Board)
class BoardAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)