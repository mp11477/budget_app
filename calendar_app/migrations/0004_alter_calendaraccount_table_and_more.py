from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('calendar_app', '0003_alter_calendaraccount_table_and_more'),
    ]

    operations = [
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
    ]