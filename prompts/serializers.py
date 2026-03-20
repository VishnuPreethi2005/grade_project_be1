from rest_framework.serializers import ModelSerializer

from prompts.models import User, Subscription, UserFeedback


class UserSerializer(ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "first_name", "last_name", "email"]


class SubscriptionSerializer(ModelSerializer):
    user = UserSerializer()

    class Meta:
        model = Subscription
        fields = "__all__"


class UserFeedbackSerializer(ModelSerializer):
    class Meta:
        model = UserFeedback
        fields = ["emoji_rating", "comment"]
        extra_kwargs = {
            "emoji_rating": {"required": False},
            "comment": {"required": False},
        }
