from flask import Flask, render_template, request, jsonify, redirect, url_for
from datetime import datetime, timedelta
import pymssql
import json
import os
from functools import wraps

app = Flask(__name__, template_folder='app/templates', static_folder='app/static')
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'

# Получаем параметры подключения из переменных окружения
DB_SERVER = os.environ.get('DB_SERVER')
DB_NAME = os.environ.get('DB_NAME')
DB_USER = os.environ.get('DB_USER')
DB_PASSWORD = os.environ.get('DB_PASSWORD')


# Декоратор для работы с БД
def get_db():
    conn = pymssql.connect(
        server=DB_SERVER,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
    return conn


# Helper функция для конвертации результатов в словари
def row_to_dict(cursor, row):
    """Конвертирует строку результата в словарь"""
    if row is None:
        return None
    columns = [column[0] for column in cursor.description]
    return dict(zip(columns, row))


def rows_to_dict_list(cursor, rows):
    """Конвертирует список строк в список словарей"""
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in rows]


# Инициализация базы данных
def init_db():
    conn = get_db()
    cursor = conn.cursor()

    try:
        # Создание таблицы goals
        cursor.execute('''
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='goals' AND xtype='U')
            CREATE TABLE goals (
                id INT IDENTITY(1,1) PRIMARY KEY,
                title NVARCHAR(255) NOT NULL,
                description NVARCHAR(MAX),
                start_date DATE NOT NULL,
                end_date DATE NOT NULL,
                target_days INT NOT NULL,
                created_at DATETIME DEFAULT GETDATE(),
                status NVARCHAR(50) DEFAULT 'active'
            )
        ''')

        # Создание таблицы progress_updates
        cursor.execute('''
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='progress_updates' AND xtype='U')
            CREATE TABLE progress_updates (
                id INT IDENTITY(1,1) PRIMARY KEY,
                goal_id INT NOT NULL,
                update_date DATE NOT NULL,
                progress_percent INT NOT NULL,
                notes NVARCHAR(MAX),
                created_at DATETIME DEFAULT GETDATE(),
                FOREIGN KEY (goal_id) REFERENCES goals(id)
            )
        ''')

        # Создание таблицы diary_entries
        cursor.execute('''
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='diary_entries' AND xtype='U')
            CREATE TABLE diary_entries (
                id INT IDENTITY(1,1) PRIMARY KEY,
                entry_date DATE NOT NULL,
                title NVARCHAR(255),
                content NVARCHAR(MAX) NOT NULL,
                mood NVARCHAR(50),
                tags NVARCHAR(255),
                created_at DATETIME DEFAULT GETDATE()
            )
        ''')

        # Создание таблицы reminders
        cursor.execute('''
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='reminders' AND xtype='U')
            CREATE TABLE reminders (
                id INT IDENTITY(1,1) PRIMARY KEY,
                title NVARCHAR(255) NOT NULL,
                description NVARCHAR(MAX),
                reminder_date DATE NOT NULL,
                reminder_time TIME,
                is_completed BIT DEFAULT 0,
                created_at DATETIME DEFAULT GETDATE()
            )
        ''')

        conn.commit()
    except Exception as e:
        print(f"Error initializing database: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


# Главная страница
@app.route('/')
def index():
    conn = get_db()
    cursor = conn.cursor()

    try:
        # Активные цели
        cursor.execute('''
                       SELECT g.*,
                              (SELECT TOP 1 progress_percent
                               FROM progress_updates
                               WHERE goal_id = g.id
                               ORDER BY update_date DESC) as latest_progress
                       FROM goals g
                       WHERE status = 'active'
                       ORDER BY end_date ASC
                       ''')
        goals = rows_to_dict_list(cursor, cursor.fetchall())

        # Сегодняшние напоминания
        today = datetime.now().date()
        cursor.execute('''
                       SELECT *
                       FROM reminders
                       WHERE reminder_date = %s
                         AND is_completed = 0
                       ORDER BY reminder_time
                       ''', (today,))
        reminders = rows_to_dict_list(cursor, cursor.fetchall())

        # Последние записи дневника
        cursor.execute('''
                       SELECT TOP 5 *
                       FROM diary_entries
                       ORDER BY entry_date DESC
                       ''')
        recent_entries = rows_to_dict_list(cursor, cursor.fetchall())

        return render_template('index.html',
                               goals=goals,
                               reminders=reminders,
                               recent_entries=recent_entries,
                               today=datetime.now().strftime('%B %d, %Y'))
    finally:
        cursor.close()
        conn.close()


# Страница управления целями (HTML)
@app.route('/goals')
def goals_page():
    return render_template('goals.html')


# API для получения списка целей
@app.route('/api/goals', methods=['GET'])
def goals_api_get():
    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute('SELECT * FROM goals ORDER BY created_at DESC')
        goals = rows_to_dict_list(cursor, cursor.fetchall())
        return jsonify(goals)
    finally:
        cursor.close()
        conn.close()


# Создание новой цели
@app.route('/goals', methods=['POST'])
def goals_create():
    data = request.json
    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute('''
                       INSERT INTO goals (title, description, start_date, end_date, target_days)
                       VALUES (%s, %s, %s, %s, %s)
                       ''', (
                           data['title'],
                           data.get('description', ''),
                           data['start_date'],
                           data['end_date'],
                           data['target_days']
                       ))
        conn.commit()
        return jsonify({'success': True})
    finally:
        cursor.close()
        conn.close()


@app.route('/goals/<int:goal_id>')
def goal_detail(goal_id):
    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute('SELECT * FROM goals WHERE id = %s', (goal_id,))
        goal_row = cursor.fetchone()
        goal = row_to_dict(cursor, goal_row)

        cursor.execute('''
                       SELECT *
                       FROM progress_updates
                       WHERE goal_id = %s
                       ORDER BY update_date ASC
                       ''', (goal_id,))
        updates = rows_to_dict_list(cursor, cursor.fetchall())

        if goal:
            return render_template('goal_detail.html',
                                   goal=goal,
                                   updates=updates)
        return "Goal not found", 404
    finally:
        cursor.close()
        conn.close()


@app.route('/goals/<int:goal_id>/progress', methods=['POST'])
def add_progress(goal_id):
    data = request.json
    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute('''
                       INSERT INTO progress_updates (goal_id, update_date, progress_percent, notes)
                       VALUES (%s, %s, %s, %s)
                       ''', (
                           goal_id,
                           data.get('update_date', datetime.now().date()),
                           data['progress_percent'],
                           data.get('notes', '')
                       ))

        # Если прогресс 100%, помечаем цель как завершенную
        if data['progress_percent'] >= 100:
            cursor.execute('UPDATE goals SET status = %s WHERE id = %s', ('completed', goal_id))

        conn.commit()
        return jsonify({'success': True})
    finally:
        cursor.close()
        conn.close()


# Дневник
@app.route('/diary')
def diary():
    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute('''
                       SELECT *
                       FROM diary_entries
                       ORDER BY entry_date DESC
                       ''')
        entries = rows_to_dict_list(cursor, cursor.fetchall())
        return render_template('diary.html', entries=entries)
    finally:
        cursor.close()
        conn.close()


@app.route('/diary', methods=['POST'])
def add_diary_entry():
    data = request.json
    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute('''
                       INSERT INTO diary_entries (entry_date, title, content, mood, tags)
                       VALUES (%s, %s, %s, %s, %s)
                       ''', (
                           data.get('entry_date', datetime.now().date()),
                           data.get('title', ''),
                           data['content'],
                           data.get('mood', ''),
                           data.get('tags', '')
                       ))
        conn.commit()
        return jsonify({'success': True})
    finally:
        cursor.close()
        conn.close()


# Напоминания
@app.route('/reminders', methods=['GET', 'POST'])
def reminders():
    if request.method == 'POST':
        data = request.json
        conn = get_db()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                           INSERT INTO reminders (title, description, reminder_date, reminder_time)
                           VALUES (%s, %s, %s, %s)
                           ''', (
                               data['title'],
                               data.get('description', ''),
                               data['reminder_date'],
                               data.get('reminder_time', '')
                           ))
            conn.commit()
            return jsonify({'success': True})
        finally:
            cursor.close()
            conn.close()

    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute('''
                       SELECT *
                       FROM reminders
                       WHERE is_completed = 0
                       ORDER BY reminder_date, reminder_time
                       ''')
        reminders = rows_to_dict_list(cursor, cursor.fetchall())
        return render_template('reminders.html', reminders=reminders)
    finally:
        cursor.close()
        conn.close()


@app.route('/reminders/<int:reminder_id>/complete', methods=['POST'])
def complete_reminder(reminder_id):
    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute('UPDATE reminders SET is_completed = 1 WHERE id = %s', (reminder_id,))
        conn.commit()
        return jsonify({'success': True})
    finally:
        cursor.close()
        conn.close()


# Аналитика и отчеты
@app.route('/analytics')
def analytics():
    conn = get_db()
    cursor = conn.cursor()

    try:
        # Статистика по целям
        cursor.execute('SELECT COUNT(*) as count FROM goals')
        total_goals = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) as count FROM goals WHERE status = %s', ('completed',))
        completed_goals = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) as count FROM goals WHERE status = %s', ('active',))
        active_goals = cursor.fetchone()[0]

        # Прогресс за последние 30 дней
        thirty_days_ago = (datetime.now() - timedelta(days=30)).date()
        cursor.execute('''
                       SELECT CAST(update_date AS DATE) as date, 
                   AVG(CAST(progress_percent AS FLOAT)) as avg_progress, 
                   COUNT(*) as updates_count
                       FROM progress_updates
                       WHERE update_date >= %s
                       GROUP BY CAST (update_date AS DATE)
                       ORDER BY date
                       ''', (thirty_days_ago,))
        recent_progress = rows_to_dict_list(cursor, cursor.fetchall())

        # Записи в дневнике по месяцам
        cursor.execute('''
                       SELECT FORMAT(entry_date, 'yyyy-MM') as month,
                   COUNT(*) as entries_count
                       FROM diary_entries
                       GROUP BY FORMAT(entry_date, 'yyyy-MM')
                       ORDER BY month DESC
                       ''')
        diary_stats_rows = cursor.fetchall()
        diary_stats = []
        for row in diary_stats_rows[:12]:
            diary_stats.append({'month': row[0], 'entries_count': row[1]})

        stats = {
            'total_goals': total_goals,
            'completed_goals': completed_goals,
            'active_goals': active_goals,
            'completion_rate': round((completed_goals / total_goals * 100) if total_goals > 0 else 0, 1),
            'recent_progress': recent_progress,
            'diary_stats': diary_stats
        }

        return render_template('analytics.html', stats=stats)
    finally:
        cursor.close()
        conn.close()


# API endpoint для получения данных для графиков
@app.route('/api/progress-chart/<int:goal_id>')
def progress_chart_data(goal_id):
    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute('''
                       SELECT update_date, progress_percent
                       FROM progress_updates
                       WHERE goal_id = %s
                       ORDER BY update_date
                       ''', (goal_id,))
        updates = rows_to_dict_list(cursor, cursor.fetchall())

        return jsonify({
            'dates': [str(u['update_date']) for u in updates],
            'progress': [u['progress_percent'] for u in updates]
        })
    finally:
        cursor.close()
        conn.close()

@app.route('/goals/<int:goal_id>/delete', methods=['POST'])
def delete_goal(goal_id):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM progress_updates WHERE goal_id = %s', (goal_id,))
        cursor.execute('DELETE FROM goals WHERE id = %s', (goal_id,))
        conn.commit()
        return jsonify({'success': True})
    finally:
        cursor.close()
        conn.close()


@app.route('/diary/<int:entry_id>/delete', methods=['POST'])
def delete_diary_entry(entry_id):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM diary_entries WHERE id = %s', (entry_id,))
        conn.commit()
        return jsonify({'success': True})
    finally:
        cursor.close()
        conn.close()


@app.route('/reminders/<int:reminder_id>/delete', methods=['POST'])
def delete_reminder(reminder_id):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM reminders WHERE id = %s', (reminder_id,))
        conn.commit()
        return jsonify({'success': True})
    finally:
        cursor.close()
        conn.close()
# Инициализация БД при загрузке модуля
init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(debug=False, host='0.0.0.0', port=port)
