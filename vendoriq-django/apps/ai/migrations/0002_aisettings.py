from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='AISettings',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('provider', models.CharField(choices=[('groq', 'Groq'), ('openai', 'OpenAI'), ('custom', 'Custom (OpenAI-compatible endpoint)')], default='groq', max_length=20)),
                ('model_name', models.CharField(blank=True, help_text='e.g. openai/gpt-oss-120b (Groq), gpt-4o-mini (OpenAI). Leave blank to use the provider\'s default model.', max_length=200)),
                ('custom_base_url', models.CharField(blank=True, default='', help_text='Only used when provider = "Custom". Full chat-completions URL, e.g. https://openrouter.ai/api/v1/chat/completions', max_length=500)),
                ('api_key_override', models.CharField(blank=True, default='', help_text='Optional. Leave blank to use GROQ_API_KEY / OPENAI_API_KEY from the environment for the selected provider. Only set this for a quick test without changing environment variables - prefer the env var in production.', max_length=255)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'ai_settings',
                'verbose_name': 'AI settings',
                'verbose_name_plural': 'AI settings',
            },
        ),
    ]
