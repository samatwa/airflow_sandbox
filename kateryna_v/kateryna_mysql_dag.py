from airflow import DAG
from datetime import datetime
from airflow.sensors.sql import SqlSensor
from airflow.operators.mysql_operator import MySqlOperator
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.utils.trigger_rule import TriggerRule as tr
import random
import time

# Функція для випадкового вибору медалі
def pick_medal(ti):
    medal = random.choice(['Bronze', 'Silver', 'Gold'])
    ti.xcom_push(key='medal_type', value=medal)
    return medal

# Функція для обчислення кількості медалей
def calc_medal_count(medal_type):
    return f"""
    INSERT INTO olympic_medals (medal_type, count, created_at)
    SELECT '{medal_type}', COUNT(*) AS count, NOW()
    FROM olympic_dataset.athlete_event_results
    WHERE medal = '{medal_type}'
    """

# Функція для затримки
def generate_delay():
    time.sleep(35)

# Аргументи за замовчуванням для DAG
default_args = {
    'owner': 'airflow',
    'start_date': datetime(2024, 8, 4, 0, 0),
}

# Назва з'єднання з базою даних MySQL
connection_name = "goit_mysql_db_kv"

# Визначення DAG
with DAG(
        'working_with_mysql_db_v',
        default_args=default_args,
        schedule_interval=None,  # DAG не має запланованого інтервалу виконання
        catchup=False,  # Вимкнути запуск пропущених задач
        tags=["veronika_y"]  # Теги для класифікації DAG
) as dag:

    # 1. Створення таблиці
    create_table = MySqlOperator(
        task_id='create_table',
        mysql_conn_id=connection_name,
        sql="""
        CREATE TABLE IF NOT EXISTS olympic_medals (
            id INT AUTO_INCREMENT PRIMARY KEY,
            medal_type VARCHAR(10),
            count INT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    # 2. Випадковий вибір медалі
    pick_medal_task = PythonOperator(
        task_id='pick_medal',
        python_callable=pick_medal,
    )

    # 3. Розгалуження завдань
    branch_task = BranchPythonOperator(
        task_id='branch_task',
        python_callable=lambda ti: ti.xcom_pull(task_ids='pick_medal', key='medal_type'),
    )

    # 4. Завдання для кожного типу медалі
    calc_bronze = MySqlOperator(
        task_id='calc_bronze',
        mysql_conn_id=connection_name,
        sql=calc_medal_count('Bronze'),
        trigger_rule=tr.NONE_FAILED
    )

    calc_silver = MySqlOperator(
        task_id='calc_silver',
        mysql_conn_id=connection_name,
        sql=calc_medal_count('Silver'),
        trigger_rule=tr.NONE_FAILED
    )

    calc_gold = MySqlOperator(
        task_id='calc_gold',
        mysql_conn_id=connection_name,
        sql=calc_medal_count('Gold'),
        trigger_rule=tr.NONE_FAILED
    )

    # 5. Затримка
    delay_task = PythonOperator(
        task_id='generate_delay',
        python_callable=generate_delay,
        trigger_rule=tr.ONE_SUCCESS
    )

    # 6. Сенсор для перевірки запису
    check_for_correctness = SqlSensor(
        task_id='check_for_correctness',
        conn_id=connection_name,
        sql="SELECT COUNT(*) FROM olympic_medals WHERE created_at >= NOW() - INTERVAL 30 SECOND",
        timeout=60,
        poke_interval=5,
    )

    # Встановлення залежностей між завданнями
    create_table >> pick_medal_task >> branch_task
    branch_task >> [calc_bronze, calc_silver, calc_gold]
    [calc_bronze, calc_silver, calc_gold] >> delay_task >> check_for_correctness

    