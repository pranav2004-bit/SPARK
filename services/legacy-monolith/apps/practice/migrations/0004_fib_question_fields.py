from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("practice", "0003_practicequestion_number"),
    ]

    operations = [
        # Promote title from CharField(500) → TextField so editors can store
        # arbitrary-length question preview text.
        migrations.AlterField(
            model_name="practicequestion",
            name="title",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Short display title / preview — auto-generated or set by editor",
            ),
        ),

        # ── FIB / shared question content ─────────────────────────────────────
        migrations.AddField(
            model_name="practicequestion",
            name="question_text",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Full question text. Use ___ for blanks in FIB questions.",
            ),
        ),
        migrations.AddField(
            model_name="practicequestion",
            name="fib_answer",
            field=models.CharField(
                max_length=500,
                blank=True,
                default="",
                help_text="FIB: the correct answer for the blank",
            ),
        ),

        # ── Explanation ───────────────────────────────────────────────────────
        migrations.AddField(
            model_name="practicequestion",
            name="explanation_type",
            field=models.CharField(
                max_length=10,
                choices=[
                    ("none",  "No explanation"),
                    ("text",  "Text only"),
                    ("image", "Image only"),
                    ("both",  "Text and image"),
                ],
                default="none",
            ),
        ),
        migrations.AddField(
            model_name="practicequestion",
            name="explanation_text",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="practicequestion",
            name="explanation_image_key",
            field=models.CharField(
                max_length=500,
                blank=True,
                default="",
                help_text="Cloudflare R2 object key for the explanation image",
            ),
        ),
    ]
