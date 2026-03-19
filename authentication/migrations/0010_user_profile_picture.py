from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0009_customuser'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='profile_picture',
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to='profile_pictures/',
                verbose_name='Profile Picture'
            ),
        ),
    ]