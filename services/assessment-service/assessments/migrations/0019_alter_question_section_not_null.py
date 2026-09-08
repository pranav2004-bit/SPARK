import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('assessments', '0018_backfill_question_sections'),
    ]

    operations = [
        migrations.AlterField(
            model_name='question',
            name='section',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='questions',
                to='assessments.questionsection',
            ),
        ),
    ]
