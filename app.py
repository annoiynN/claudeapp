from flask import Flask, render_template, request, jsonify, redirect, url_for
from datetime import datetime, timedelta
import sqlite3
import json
import os
from functools import wraps

app = Flask(__name__, template_folder='app/templates', static_folder='app/static')
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'
DATABASE = 'progress_tracker.db'


# Декоратор для работы с БД
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


# Инициализация базы данных
def init_db():
    with get_db() as conn:
        conn.executescript('''
                           CREATE TABLE IF NOT EXISTS goals
                           (
                               id
                               INTEGER
                               PRIMARY
                               KEY
                               AUTOINCREMENT,
                               title
                               TEXT
                               NOT
                               NULL,
                               description
                               TEXT,
                               start_date
                               DATE
                               NOT
                               NULL,
                               end_date
                               DATE
                               NOT
                               NULL,
                               target_days
                               INTEGER
                               NOT
                               NULL,
                               created_at
                               TIMESTAMP
                               DEFAULT
                               CURRENT_TIMESTAMP,
                               status
                               TEXT
                               DEFAULT
                               'active'
                           );

                           CREATE TABLE IF NOT EXISTS progress_updates
                           (
                               id
                               INTEGER
                               PRIMARY
                               KEY
                               AUTOINCREMENT,
                               goal_id
                               INTEGER
                               NOT
                               NULL,
                               update_date
                               DATE
                               NOT
                               NULL,
                               progress_percent
                               INTEGER
                               NOT
                               NULL,
                               notes
                               TEXT,
                               created_at
                               TIMESTAMP
                               DEFAULT
                               CURRENT_TIMESTAMP,
                               FOREIGN
                               KEY
                           (
                               goal_id
                           ) REFERENCES goals
                           (
                               id
                           )
                               );

                           CREATE TABLE IF NOT EXISTS diary_entries
                           (
                               id
                               INTEGER
                               PRIMARY
                               KEY
                               AUTOINCREMENT,
                               entry_date
                               DATE
                               NOT
                               NULL,
                               title
                               TEXT,
                               content
                               TEXT
                               NOT
                               NULL,
                               mood
                               TEXT,
                               tags
                               TEXT,
                               created_at
                               TIMESTAMP
                               DEFAULT
                               CURRENT_TIMESTAMP
                           );

                           CREATE TABLE IF NOT EXISTS reminders
                           (
                               id
                               INTEGER
                               PRIMARY
                               KEY
                               AUTOINCREMENT,
                               title
                               TEXT
                               NOT
                               NULL,
                               description
                               TEXT,
                               reminder_date
                               DATE
                               NOT
                               NULL,
                               reminder_time
                               TIME,
                               is_completed
                               BOOLEAN
                               DEFAULT
                               0,
                               created_at
                               TIMESTAMP
                               DEFAULT
                               CURRENT_TIMESTAMP
                           );
                           ''')
        conn.commit()


# Главная страница
@app.route('/')
def index():
    with get_db() as conn:
        # Активные цели
        goals = conn.execute('''
                             SELECT g.*,
                                    (SELECT progress_percent
                                     FROM progress_updates
                                     WHERE goal_id = g.id
                                     ORDER BY update_date DESC LIMIT 1) as latest_progress
                             FROM goals g
                             WHERE status = 'active'
                             ORDER BY end_date ASC
                             ''').fetchall()

        # Сегодняшние напоминания
        today = datetime.now().date()
        reminders = conn.execute('''
                                 SELECT *
                                 FROM reminders
                                 WHERE reminder_date = ?
                                   AND is_completed = 0
                                 ORDER BY reminder_time
                                 ''', (today,)).fetchall()

        # Последние записи дневника
        recent_entries = conn.execute('''
                                      SELECT *
                                      FROM diary_entries
                                      ORDER BY entry_date DESC LIMIT 5
                                      ''').fetchall()

    return render_template('index.html',
                           goals=goals,
                           reminders=reminders,
                           recent_entries=recent_entries,
                           today=datetime.now().strftime('%B %d, %Y'))


# Страница управления целями (HTML)
@app.route('/goals')
def goals_page():
    return render_template('goals.html')


# API для получения списка целей
@app.route('/api/goals', methods=['GET'])
def goals_api_get():
    with get_db() as conn:
        goals = conn.execute('SELECT * FROM goals ORDER BY created_at DESC').fetchall()
    return jsonify([dict(g) for g in goals])


# Создание новой цели
@app.route('/goals', methods=['POST'])
def goals_create():
    data = request.json
    with get_db() as conn:
        conn.execute('''
                     INSERT INTO goals (title, description, start_date, end_date, target_days)
                     VALUES (?, ?, ?, ?, ?)
                     ''', (
                         data['title'],
                         data.get('description', ''),
                         data['start_date'],
                         data['end_date'],
                         data['target_days']
                     ))
        conn.commit()
    return jsonify({'success': True})


@app.route('/goals/<int:goal_id>')
def goal_detail(goal_id):
    with get_db() as conn:
        goal = conn.execute('SELECT * FROM goals WHERE id = ?', (goal_id,)).fetchone()
        updates = conn.execute('''
                               SELECT *
                               FROM progress_updates
                               WHERE goal_id = ?
                               ORDER BY update_date ASC
                               ''', (goal_id,)).fetchall()

    if goal:
        return render_template('goal_detail.html',
                               goal=dict(goal),
                               updates=[dict(u) for u in updates])
    return "Goal not found", 404


@app.route('/goals/<int:goal_id>/progress', methods=['POST'])
def add_progress(goal_id):
    data = request.json
    with get_db() as conn:
        conn.execute('''
                     INSERT INTO progress_updates (goal_id, update_date, progress_percent, notes)
                     VALUES (?, ?, ?, ?)
                     ''', (
                         goal_id,
                         data.get('update_date', datetime.now().date()),
                         data['progress_percent'],
                         data.get('notes', '')
                     ))

        # Если прогресс 100%, помечаем цель как завершенную
        if data['progress_percent'] >= 100:
            conn.execute('UPDATE goals SET status = ? WHERE id = ?', ('completed', goal_id))

        conn.commit()
    return jsonify({'success': True})


# Дневник
@app.route('/diary')
def diary():
    with get_db() as conn:
        entries = conn.execute('''
                               SELECT *
                               FROM diary_entries
                               ORDER BY entry_date DESC
                               ''').fetchall()
    return render_template('diary.html', entries=[dict(e) for e in entries])


@app.route('/diary', methods=['POST'])
def add_diary_entry():
    data = request.json
    with get_db() as conn:
        conn.execute('''
                     INSERT INTO diary_entries (entry_date, title, content, mood, tags)
                     VALUES (?, ?, ?, ?, ?)
                     ''', (
                         data.get('entry_date', datetime.now().date()),
                         data.get('title', ''),
                         data['content'],
                         data.get('mood', ''),
                         data.get('tags', '')
                     ))
        conn.commit()
    return jsonify({'success': True})


# Напоминания
@app.route('/reminders', methods=['GET', 'POST'])
def reminders():
    if request.method == 'POST':
        data = request.json
        with get_db() as conn:
            conn.execute('''
                         INSERT INTO reminders (title, description, reminder_date, reminder_time)
                         VALUES (?, ?, ?, ?)
                         ''', (
                             data['title'],
                             data.get('description', ''),
                             data['reminder_date'],
                             data.get('reminder_time', '')
                         ))
            conn.commit()
        return jsonify({'success': True})

    with get_db() as conn:
        reminders = conn.execute('''
                                 SELECT *
                                 FROM reminders
                                 WHERE is_completed = 0
                                 ORDER BY reminder_date, reminder_time
                                 ''').fetchall()
    return render_template('reminders.html', reminders=[dict(r) for r in reminders])


@app.route('/reminders/<int:reminder_id>/complete', methods=['POST'])
def complete_reminder(reminder_id):
    with get_db() as conn:
        conn.execute('UPDATE reminders SET is_completed = 1 WHERE id = ?', (reminder_id,))
        conn.commit()
    return jsonify({'success': True})


# Аналитика и отчеты
@app.route('/analytics')
def analytics():
    with get_db() as conn:
        # Статистика по целям
        total_goals = conn.execute('SELECT COUNT(*) as count FROM goals').fetchone()['count']
        completed_goals = conn.execute(
            'SELECT COUNT(*) as count FROM goals WHERE status = "completed"'
        ).fetchone()['count']
        active_goals = conn.execute(
            'SELECT COUNT(*) as count FROM goals WHERE status = "active"'
        ).fetchone()['count']

        # Прогресс за последние 30 дней
        thirty_days_ago = (datetime.now() - timedelta(days=30)).date()
        recent_progress = conn.execute('''
                                       SELECT DATE (update_date) as date, AVG (progress_percent) as avg_progress, COUNT (*) as updates_count
                                       FROM progress_updates
                                       WHERE update_date >= ?
                                       GROUP BY DATE (update_date)
                                       ORDER BY date
                                       ''', (thirty_days_ago,)).fetchall()

        # Записи в дневнике по месяцам
        diary_stats = conn.execute('''
                                   SELECT strftime('%Y-%m', entry_date) as month,
                   COUNT(*) as entries_count
                                   FROM diary_entries
                                   GROUP BY month
                                   ORDER BY month DESC
                                       LIMIT 12
                                   ''').fetchall()

    stats = {
        'total_goals': total_goals,
        'completed_goals': completed_goals,
        'active_goals': active_goals,
        'completion_rate': round((completed_goals / total_goals * 100) if total_goals > 0 else 0, 1),
        'recent_progress': [dict(r) for r in recent_progress],
        'diary_stats': [dict(d) for d in diary_stats]
    }

    return render_template('analytics.html', stats=stats)


# API endpoint для получения данных для графиков
@app.route('/api/progress-chart/<int:goal_id>')
def progress_chart_data(goal_id):
    with get_db() as conn:
        updates = conn.execute('''
                               SELECT update_date, progress_percent
                               FROM progress_updates
                               WHERE goal_id = ?
                               ORDER BY update_date
                               ''', (goal_id,)).fetchall()

    return jsonify({
        'dates': [u['update_date'] for u in updates],
        'progress': [u['progress_percent'] for u in updates]
    })


if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 8000))
    app.run(debug=False, host='0.0.0.0', port=port)