from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("practice", "0005_practice_question_progress"),
    ]

    operations = [
        # How the question body is composed: text only / image only / text + image
        migrations.AddField(
            model_name="practicequestion",
            name="question_content_type",
            field=models.CharField(
                max_length=10,
                choices=[
                    ("text",  "Text only"),
                    ("image", "Image only"),
                    ("both",  "Text and image"),
                ],
                default="text",
                help_text="Controls which elements are shown to students in the question body.",
            ),
        ),
        # R2 object key for an optional question-body image
        migrations.AddField(
            model_name="practicequestion",
            name="question_image_key",
            field=models.CharField(
                max_length=500,
                blank=True,
                default="",
                help_text="Cloudflare R2 object key for the question body image.",
            ),
        ),
    ]
