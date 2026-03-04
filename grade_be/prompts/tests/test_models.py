# your_app/tests/test_models.py

from django.test import TestCase
from prompts.models import Translation, Transliteration, Entity, EmailWriter
from django.contrib.auth import get_user_model


class TranslationModelTest(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="testuser@example.com", password="password123"
        )
        self.translation = Translation.objects.create(
            user=self.user,
            input_text="Hello",
            input_source="en",
            input_destination="es",
            output_response="Hola",
            cost="0.01",
        )

    def test_translation_creation(self):
        self.assertEqual(self.translation.input_text, "Hello")
        self.assertEqual(self.translation.output_response, "Hola")
        self.assertEqual(str(self.translation.cost), "0.01")


class TransliterationModelTest(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="testuser@example.com", password="password123"
        )
        self.transliteration = Transliteration.objects.create(
            user=self.user,
            input_text="Hello",
            input_source="en",
            input_destination="hi",
            output_response="हैलो",
            cost="0.01",
        )

    def test_transliteration_creation(self):
        self.assertEqual(self.transliteration.input_text, "Hello")
        self.assertEqual(self.transliteration.output_response, "हैलो")
        self.assertEqual(str(self.transliteration.cost), "0.01")


class EntityModelTest(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="testuser@example.com", password="password123"
        )
        self.entity = Entity.objects.create(
            user=self.user,
            input_text="Barack Obama was the 44th President of the United States.",
            entity="PERSON",
            custom_entity="President",
            output_response="Barack Obama",
            cost="0.01",
        )

    def test_entity_creation(self):
        self.assertEqual(
            self.entity.input_text,
            "Barack Obama was the 44th President of the United States.",
        )
        self.assertEqual(self.entity.output_response, "Barack Obama")
        self.assertEqual(str(self.entity.cost), "0.01")


class EmailWriterModelTest(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="testuser@example.com", password="password123"
        )
        self.email_writer = EmailWriter.objects.create(
            user=self.user,
            selectedType="formal",
            tone="polite",
            recipient="John Doe",
            purpose="Business Meeting",
            personalized="We need to discuss the quarterly report.",
            generated_email="Dear John, we need to discuss the quarterly report.",
            cost="0.01",
        )

    def test_email_writer_creation(self):
        self.assertEqual(
            self.email_writer.personalized,
            "We need to discuss the quarterly report.",
        )
        self.assertEqual(
            self.email_writer.generated_email,
            "Dear John, we need to discuss the quarterly report.",
        )
        self.assertEqual(str(self.email_writer.cost), "0.01")
