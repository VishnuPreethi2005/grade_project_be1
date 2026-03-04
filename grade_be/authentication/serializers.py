from rest_framework import serializers
from .models import User, Organization
from django.contrib.auth.password_validation import validate_password
from .models import UserCredit
from .models import Organization
from .models import Product, UserPurchase


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password],
        style={"input_type": "password"},
    )
    password2 = serializers.CharField(
        write_only=True, required=True, style={"input_type": "password"}
    )
    is_student = serializers.BooleanField(default=False)
    is_evaluator = serializers.BooleanField(default=False)
    is_qp_uploader = serializers.BooleanField(default=False)
    is_mentor = serializers.BooleanField(default=False)

    class Meta:
        model = User
        fields = (
            "email",
            "username",
            "password",
            "password2",
            "is_student",
            "is_evaluator",
            "is_qp_uploader",
            "is_mentor",
        )

    def validate(self, attrs):
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError(
                {"password": "Password fields didn't match."}
            )

        email = attrs.get("email", "").lower()
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError(
                {"email": "A user with this email already exists."}
            )

        return attrs

    def create(self, validated_data):
        validated_data.pop("password2")
        user = User.objects.create(
            email=validated_data["email"],
            username=validated_data["username"],
            is_active=True,
            is_student=validated_data.get("is_student", False),
            is_evaluator=validated_data.get("is_evaluator", False),
            is_qp_uploader=validated_data.get("is_qp_uploader", False),
            is_mentor=validated_data.get("is_mentor", False),
            active_role=(
                "student"
                if validated_data.get("is_student")
                else "evaluator"
                if validated_data.get("is_evaluator")
                else "qp_uploader"
                if validated_data.get("is_qp_uploader")
                else "mentor"
                if validated_data.get("is_mentor")
                else None
            ),
        )
        user.set_password(validated_data["password"])
        user.generate_otp()
        user.save()
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True, write_only=True)
    role = serializers.CharField(required=False)  # Optional for role switching


class GoogleLoginSerializer(serializers.Serializer):
    id_token = serializers.CharField(required=True)
    role = serializers.CharField(required=False)  # Add this line


class VerifyOTPSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    otp = serializers.CharField(required=True, max_length=6)


class ResendOTPSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)


class ResetPasswordSerializer(serializers.Serializer):
    token = serializers.CharField(required=True)
    password = serializers.CharField(
        required=True,
        write_only=True,
        validators=[validate_password],
        style={"input_type": "password"},
    )
    password2 = serializers.CharField(
        required=True, write_only=True, style={"input_type": "password"}
    )

    def validate(self, attrs):
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError(
                {"password": "Password fields didn't match."}
            )
        return attrs


class UserCreditSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserCredit
        fields = ["free_credit", "paid_credit", "total_credit", "last_updated"]


class CreateRazorpayOrderSerializer(serializers.Serializer):
    amount = serializers.DecimalField(
        max_digits=10, decimal_places=7, min_value=1
    )
    currency = serializers.CharField(max_length=3, default="USD")


class VerifyPaymentSerializer(serializers.Serializer):
    razorpay_payment_id = serializers.CharField()
    razorpay_order_id = serializers.CharField()
    razorpay_signature = serializers.CharField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=7)
    currency = serializers.CharField(max_length=3)


class GoogleLoginSerializer(serializers.Serializer):
    """Serializer for Google login (shared between users and organizations)"""

    id_token = serializers.CharField(required=True)


class OrganizationRegistrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = [
            "name",
            "email",
            "address",
            "phone_number",
            "registration_date",
            "registration_proof",
            "description",
        ]
        extra_kwargs = {"registration_proof": {"required": True}}

    def create(self, validated_data):
        organization = Organization.objects.create(**validated_data)
        return organization


class OrganizationVerificationSerializer(serializers.ModelSerializer):
    verification_notes = serializers.CharField(required=True)

    class Meta:
        model = Organization
        fields = ["is_verified", "verification_notes"]
        read_only_fields = ["is_verified"]


class OrganizationRejectionSerializer(serializers.ModelSerializer):
    verification_notes = serializers.CharField(required=True)

    class Meta:
        model = Organization
        fields = ["verification_notes"]


class OrganizationListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = [
            "id",
            "name",
            "email",
            "status",
            "is_verified",
            "created_at",
            "verified_at",
            "verification_notes",
            "address",
            "phone_number",
            "registration_date",
            "registration_proof",
            "description",
        ]
        read_only_fields = fields


class UserSerializer(serializers.ModelSerializer):
    profile_picture_url = serializers.SerializerMethodField()
    roles = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = ['id', 'email', 'username', 'full_name', 'profile_picture_url', 'is_profile_completed', 'roles']
    
    def get_profile_picture_url(self, obj):
        if obj.profile_picture:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.profile_picture.url)
            return obj.profile_picture.url
        return None

    def get_roles(self, obj):
        from .views import get_user_roles
        return get_user_roles(obj)


class ProductSerializer(serializers.ModelSerializer):
    is_purchased = serializers.SerializerMethodField()
    cover_image_url = serializers.SerializerMethodField()
    
    class Meta:
        model = Product
        fields = [
            "id", 
            "title", 
            "description", 
            "price", 
            "cover_image_url",
            "total_chapters",
            "is_purchased", 
            "created_at"
        ]
        read_only_fields = ["id", "created_at"]
    
    def get_is_purchased(self, obj):
        """Check if current user has purchased this product"""
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return UserPurchase.objects.filter(
                user=request.user, 
                product=obj
            ).exists()
        return False
    
    def get_cover_image_url(self, obj):
        """Get full URL for cover image"""
        if obj.cover_image:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.cover_image.url)
        return None


class CreateBookOrderSerializer(serializers.Serializer):
    """Serializer for creating book purchase order"""
    product_id = serializers.IntegerField()
    
    def validate_product_id(self, value):
        """Validate that product exists and is active"""
        try:
            product = Product.objects.get(id=value, is_active=True)
        except Product.DoesNotExist:
            raise serializers.ValidationError("Product not found or inactive")
        return value
