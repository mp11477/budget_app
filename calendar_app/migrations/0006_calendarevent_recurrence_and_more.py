from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('calendar_app', '0005_alter_calendaraccount_table_and_more'),
    ]

    operations = [
        # The physical database tables already use the budget_* names.
        # Earlier calendar_app migrations left Django's migration state
        # believing the tables were named calendar_app_*.
        #
        # Update Django's migration STATE only. Do not rename any
        # physical database tables.
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterModelTable(
                    name='calendaraccount',
                    table='budget_calendaraccount',
                ),
                migrations.AlterModelTable(
                    name='calendarevent',
                    table='budget_calendarevent',
                ),
                migrations.AlterModelTable(
                    name='calendarrulespecial',
                    table='budget_calendarrulespecial',
                ),
                migrations.AlterModelTable(
                    name='calendarsource',
                    table='budget_calendarsource',
                ),
                migrations.AlterModelTable(
                    name='calendarspecial',
                    table='budget_calendarspecial',
                ),
            ],
        ),

        migrations.AddField(
            model_name='calendarevent',
            name='recurrence',
            field=models.CharField(
                choices=[
                    ('none', 'Does not repeat'),
                    ('daily', 'Daily'),
                    ('weekly', 'Weekly'),
                    ('biweekly', 'Every 2 weeks'),
                    ('monthly', 'Monthly'),
                    ('bimonthly', 'Every 2 months'),
                    ('yearly', 'Yearly'),
                ],
                default='none',
                max_length=20,
            ),
        ),

        migrations.AddField(
            model_name='calendarevent',
            name='recurrence_end',
            field=models.DateField(
                blank=True,
                null=True,
            ),
        ),

        migrations.AlterField(
            model_name='calendarevent',
            name='person',
            field=models.CharField(
                choices=[
                    ('mike', 'Mike'),
                    ('wife', 'Stef'),
                    ('kid1', 'Max'),
                    ('kid2', 'Leo'),
                    ('both_kids', 'Both Kids'),
                    ('family', 'Family'),
                ],
                default='mike',
                max_length=20,
            ),
        ),
    ]