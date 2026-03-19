from django.contrib import admin
from .models import Question, TestCase, Topic, Company


class TestCaseInline(admin.TabularInline):
    """
    Inline admin interface for managing TestCase objects related to a Question.

    Displays test case fields such as input, expected output, sample status, and type.
    """
    model = TestCase
    extra = 1
    fields = ('input_data', 'expected_output', 'is_sample', 'test_type')
    readonly_fields = ()
    show_change_link = True


class QuestionAdmin(admin.ModelAdmin):
    """
    Admin configuration for the Question model.

    Allows custom display of fields, inline editing of test cases, and structured layout.
    """
    list_display = ['custom_id', 'title', 'difficulty', 'year_asked', 'get_topics', 'get_companies']
    search_fields = ['title', 'description', 'difficulty']
    readonly_fields = ['custom_id']

    fieldsets = (
        ("Basic Info", {
            'fields': (
                'custom_id',
                'title',
                'description',
                'sample_input',
                'sample_output',
                'explanation',
            )
        }),
        ("Additional Metadata", {
            'fields': (
                'constraints',
                'testcase_description',
                'difficulty',
                'topics',
                'companies',
                'year_asked',
            )
        }),
    )

    inlines = [TestCaseInline]

    def get_topics(self, obj: Question) -> str:
        """
        Returns a comma-separated string of topic names related to the question.

        Args:
            obj (Question): The Question instance.

        Returns:
            str: Comma-separated topic names.
        """
        return ", ".join(t.name for t in obj.topics.all())

    get_topics.short_description = 'Topics'

    def get_companies(self, obj: Question) -> str:
        """
        Returns a comma-separated string of company names associated with the question.

        Args:
            obj (Question): The Question instance.

        Returns:
            str: Comma-separated company names.
        """
        return ", ".join(c.name for c in obj.companies.all())

    get_companies.short_description = 'Companies'


class TopicAdmin(admin.ModelAdmin):
    """
    Admin configuration for the Topic model.

    Provides list display, search, and ordering functionalities.
    """
    list_display = ['id', 'name', 'created_at', 'updated_at']
    search_fields = ['name']
    ordering = ['name']


class CompanyAdmin(admin.ModelAdmin):
    """
    Admin configuration for the Company model.

    Allows listing, searching, and ordering of companies.
    """
    list_display = ['id', 'name']
    search_fields = ['name']
    ordering = ['name']


admin.site.register(Question, QuestionAdmin)
admin.site.register(Topic, TopicAdmin)
admin.site.register(Company, CompanyAdmin)




from django.contrib import admin
from .models import SiteSettings

admin.site.register(SiteSettings)

from .models import CodeSubmission

@admin.register(CodeSubmission)
class CodeSubmissionAdmin(admin.ModelAdmin):
    list_display = ('user', 'question', 'status', 'submitted_at', 'language')
    list_filter = ('status', 'language', 'submitted_at')
    search_fields = ('user__username', 'user__email', 'question__title', 'code')
    readonly_fields = ('submitted_at',)
