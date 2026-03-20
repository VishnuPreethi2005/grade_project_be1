from .models import AnonymousUsage
from django.contrib import admin
from .models import (
    Translation,
    IPhits,
    Subscription,
    Transliteration,
    Entity,
    EmailWriter,
    GeneratedQuestion,
    UserFeedback,
)


class TranslationAdmin(admin.ModelAdmin):
    """
    Admin class for Translation model.
    """

    list_display = [
        "id",
        "user",
        "input_text",
        "output_response",
        "input_source",
        "input_destination",
        "input_domain",
        "input_subdomain",
        "created",
        "modified",
        "cost",
    ]
    # Defines which fields to display in the list view of the admin interface.


class IPhitsAdmin(admin.ModelAdmin):
    list_display = ["id", "ip_address", "hits", "created", "modified"]


admin.site.register(Translation, TranslationAdmin)
admin.site.register(IPhits, IPhitsAdmin)


class SubscriptionAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "user",
        "orderID",
        "amount",
        "paymentStatus",
        "created",
    ]


admin.site.register(Subscription, SubscriptionAdmin)


class TransliterationAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "user",
        "input_text",
        "output_response",
        "input_source",
        "input_destination",
        "created",
        "modified",
        "cost",
    ]


admin.site.register(Transliteration, TransliterationAdmin)


class EntityAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "user",
        "input_text",
        "entity",
        "custom_entity",
        "output_response",
        "created",
        "modified",
        "cost",
    ]


admin.site.register(Entity, EntityAdmin)


class EmailWriterAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "user",
        "selectedType",
        "tone",
        "recipient",
        "purpose",
        "personalized",
        "generated_email",
        "created",
        "modified",
        "cost",
    ]
    # Defines which fields to display in the list view of the admin interface.


admin.site.register(EmailWriter, EmailWriterAdmin)


class GeneratedQuestionAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "user",
        "question_type",
        "num_questions",
        "bloom",
        "level",
        "num_options",
        "option_type",
        "num_missing_words",
        "representing_words",
        "num_items",
        "learning_obj",
        "provide_answer",
        "explanation",
        "format_value",
        "response",
        "created",
        "modified",
        "cost",
    ]
    # Defines which fields to display in the list view of the admin interface.


admin.site.register(GeneratedQuestion, GeneratedQuestionAdmin)


@admin.register(AnonymousUsage)
class AnonymousUsageAdmin(admin.ModelAdmin):
    list_display = (
        "ip_address",
        "hits_remaining",
        "first_hit_time",
        "last_hit_time",
    )
    list_filter = ("first_hit_time",)
    search_fields = ("ip_address",)
    readonly_fields = ("first_hit_time", "last_hit_time")
    ordering = ("-last_hit_time",)


@admin.register(UserFeedback)
class UserFeedbackAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "user",
        "emoji_rating",
        "comment",
        "created",
        "modified",
    ]
    list_filter = ["emoji_rating", "created"]
    search_fields = ["user__email", "comment"]
    readonly_fields = ["created", "modified"]
    ordering = ["-created"]
