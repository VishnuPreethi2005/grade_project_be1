import logging
from django.utils import timezone
from django.db import models
from model_utils.models import TimeStampedModel
from authentication.models import User
from django.utils.translation import gettext_lazy as _


class Translation(TimeStampedModel):
    user = models.ForeignKey(
        User,
        related_name="User",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )
    input_text = models.CharField(max_length=100, null=True, blank=True)
    input_source = models.CharField(max_length=100, null=True, blank=True)
    input_destination = models.CharField(max_length=100, null=True, blank=True)
    input_domain = models.CharField(max_length=100, null=True, blank=True)
    input_subdomain = models.CharField(max_length=100, null=True, blank=True)
    output_response = models.CharField(max_length=500, null=True, blank=True)
    cost = models.CharField(max_length=500, null=True, blank=True)

    def __str__(self):
        return self.input_text

    class Meta:
        verbose_name = "Translation"
        verbose_name_plural = "Translations"


class EmailWriter(TimeStampedModel):
    """
    Model representing an email writer entry.
    """

    user = models.ForeignKey(
        User,
        related_name="emails",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )
    selectedType = models.CharField(max_length=100, null=True, blank=True)
    tone = models.CharField(max_length=100, null=True, blank=True)
    recipient = models.CharField(max_length=100, null=True, blank=True)
    purpose = models.CharField(max_length=100, null=True, blank=True)
    personalized = models.TextField(null=True, blank=True)
    generated_email = models.TextField(null=True, blank=True)
    cost = models.CharField(max_length=500, null=True, blank=True)

    def _str_(self):
        return self.selectedType

    class Meta:
        verbose_name = "EmailWriter"
        verbose_name_plural = "EmailWriters"


class Transliteration(TimeStampedModel):
    user = models.ForeignKey(
        User,
        related_name="transliterations",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )
    input_text = models.CharField(max_length=100, null=True, blank=True)
    input_source = models.CharField(max_length=100, null=True, blank=True)
    input_destination = models.CharField(max_length=100, null=True, blank=True)
    output_response = models.CharField(max_length=500, null=True, blank=True)
    cost = models.CharField(max_length=500, null=True, blank=True)

    def __str__(self):
        return self.input_text

    class Meta:
        verbose_name = "Transliteration"
        verbose_name_plural = "Transliterations"


class IPhits(TimeStampedModel):
    ip_address = models.CharField(max_length=100, blank=True, null=True)
    hits = models.IntegerField(blank=True, null=True)


class Subscription(TimeStampedModel):
    PAYMENT_STATUS_CHOICES = (
        ("success", "success"),
        ("failed", "failed"),
        ("in-progress", "in-progress"),
    )

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, null=True, blank=True
    )
    orderID = models.CharField(
        _("Order ID"), max_length=250, null=True, blank=True
    )
    amount = models.CharField(
        _("Order Amount"), max_length=250, null=True, blank=True
    )
    paymentStatus = models.CharField(
        _("Payment Status"),
        choices=PAYMENT_STATUS_CHOICES,
        max_length=250,
        null=True,
        blank=True,
        default="in-progress",
    )

    class Meta:
        verbose_name = "Subscription"
        verbose_name_plural = "Subscriptions"


class Entity(TimeStampedModel):
    user = models.ForeignKey(
        User,
        related_name="entities",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )
    input_text = models.CharField(max_length=100, null=True, blank=True)
    entity = models.CharField(max_length=100, null=True, blank=True)
    custom_entity = models.CharField(max_length=100, null=True, blank=True)
    output_response = models.CharField(max_length=500, null=True, blank=True)
    cost = models.CharField(max_length=500, null=True, blank=True)

    def __str__(self):
        return self.input_text

    class Meta:
        verbose_name = "Entity"
        verbose_name_plural = "Entities"


class GeneratedQuestion(TimeStampedModel):
    user = models.ForeignKey(
        User,
        related_name="generated_questions",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )
    question_type = models.CharField(max_length=100, null=True, blank=True)
    num_questions = models.CharField(max_length=100, null=True, blank=True)
    bloom = models.CharField(max_length=100, null=True, blank=True)
    level = models.CharField(max_length=100, null=True, blank=True)
    num_options = models.CharField(max_length=100, null=True, blank=True)
    option_type = models.CharField(max_length=100, null=True, blank=True)
    num_missing_words = models.CharField(max_length=100, null=True, blank=True)
    representing_words = models.CharField(
        max_length=100, null=True, blank=True
    )
    num_items = models.CharField(max_length=100, null=True, blank=True)
    learning_obj = models.CharField(max_length=100, null=True, blank=True)
    provide_answer = models.CharField(max_length=100, null=True, blank=True)
    explanation = models.CharField(max_length=100, null=True, blank=True)
    format_value = models.CharField(max_length=100, null=True, blank=True)
    response = models.TextField(null=True, blank=True)
    cost = models.CharField(max_length=100, null=True, blank=True)

    def __str__(self):
        return self.question_type

    class Meta:
        verbose_name = "GeneratedQuestion"
        verbose_name_plural = "GeneratedQuestions"


# models.py (add this to your existing models)

logger = logging.getLogger(__name__)


class AnonymousUsage(models.Model):
    """
    Tracks anonymous user usage by IP address with 3 free hits per 24-hour period
    """

    ip_address = models.GenericIPAddressField(unique=True)
    hits_remaining = models.PositiveIntegerField(default=3)
    first_hit_time = models.DateTimeField(auto_now_add=True)
    last_hit_time = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Anonymous Usage"
        verbose_name_plural = "Anonymous Usages"
        indexes = [
            models.Index(fields=["ip_address"]),
            models.Index(fields=["first_hit_time"]),
        ]

    def __str__(self):
        return f"{self.ip_address} - {self.hits_remaining} hits remaining"

    @classmethod
    def get_for_ip(cls, ip_address):
        """
        Get or create usage record for IP, resetting if 24 hours have passed
        """
        try:
            obj, created = cls.objects.get_or_create(
                ip_address=ip_address, defaults={"hits_remaining": 3}
            )

            # Reset if 24 hours have passed since first hit
            if (
                not created
                and (timezone.now() - obj.first_hit_time).total_seconds()
                > 24 * 3600
            ):
                obj.hits_remaining = 3
                obj.first_hit_time = timezone.now()
                obj.save()

            return obj
        except Exception as e:
            logger.error(
                f"Error getting AnonymousUsage for IP {ip_address}: {str(e)}"
            )
            # Fallback - create a temporary object
            return cls(ip_address=ip_address, hits_remaining=3)

    def record_hit(self):
        """
        Record a hit and return remaining hits
        """
        if self.hits_remaining > 0:
            self.hits_remaining -= 1
            self.last_hit_time = timezone.now()
            try:
                self.save()
            except Exception as e:
                logger.error(
                    f"Error saving AnonymousUsage for IP {self.ip_address}: {str(e)}"
                )
        return self.hits_remaining

    def can_access(self):
        """
        Check if this IP can access the service (has hits remaining)
        """
        # First check if 24 hours have passed (which would reset the counter)
        if (timezone.now() - self.first_hit_time).total_seconds() > 24 * 3600:
            self.hits_remaining = 3
            self.first_hit_time = timezone.now()
            try:
                self.save()
            except Exception as e:
                logger.error(
                    f"Error resetting AnonymousUsage for IP {self.ip_address}: {str(e)}"
                )
            return True
        return self.hits_remaining > 0


class UserFeedback(TimeStampedModel):
    """
    Model for storing general user feedback from the frontend
    """

    user = models.ForeignKey(
        User,
        related_name="user_feedback",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )
    emoji_rating = models.CharField(
        max_length=10,
        choices=[("good", "Good"), ("neutral", "Neutral"), ("bad", "Bad")],
        null=True,
        blank=True,
    )
    comment = models.TextField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        verbose_name = "User Feedback"
        verbose_name_plural = "User Feedbacks"
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["emoji_rating"]),
            models.Index(fields=["created"]),
        ]

    def __str__(self):
        user_info = (
            self.user.email if self.user else f"Anonymous ({self.ip_address})"
        )
        return f"Feedback from {user_info} - {self.emoji_rating}"
