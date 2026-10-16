'''
Flask application for the tank api project.
'''

import checks
import utils

import sqlite3
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

from contextlib import closing
from flask import Flask, jsonify, redirect, render_template, request, url_for
from pathlib import Path
from plotly.subplots import make_subplots

template_dir = './templates'
app = Flask(__name__, template_folder=template_dir)
database_path = Path(__file__).resolve().parent / 'tankapi.db'


# Home page route
@app.route('/')
def index():
    return render_template('home.html')

# Landing page route
@app.route('/landing')
def landing():
    return render_template('landing.html')

# About page route
@app.route('/about')
def about():
    return render_template('about.html')

# Home page route
@app.route('/home')
def home():
    return render_template('home.html')

@app.route('/log-test', methods=['GET', 'POST'])
def log_test():
    # Retrieve the log data from the request
    if request.method == 'POST':
        log_data = request.get_json()
        try:
            checks.validate_log_data(log_data)  # Call the function to check the log data
            with closing(sqlite3.connect(database_path)) as connection:
                with connection:
                    connection.execute(
                        '''
                        INSERT INTO tankdata (tank_id, temperature, ph, ammonia, nitrite, nitrate, alkalinity, shaky, note, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''',
                        (
                            log_data.get('tank_id'),
                            log_data.get('temp_f'),
                            log_data.get('ph'),
                            log_data.get('nh3'),
                            log_data.get('no2'),
                            log_data.get('no3'),
                            log_data.get('kh'),
                            log_data.get('shaky', False),
                            log_data.get('note', ''),
                            log_data.get('ts')
                        )
                    )
        except ValueError as e:
            return jsonify(error=str(e)), 400

        return jsonify(message='Log data received'), 200
    with closing(sqlite3.connect(database_path)) as connection:
        connection.row_factory = sqlite3.Row
        tank_rows = connection.execute(
            'SELECT id, name FROM tanks ORDER BY name'
        ).fetchall()
    return render_template('log_test.html', tanks=tank_rows)

@app.route('/log-event', methods=['GET', 'POST'])
def log_event():
    if request.method == "POST":
        log_event_data = request.get_json()
        with closing(sqlite3.connect(database_path)) as connection:
            with connection:
                connection.execute(
                    '''
                    INSERT INTO tankevents (tank_id, event_type, description, created_at)
                    VALUES (?, ?, ?, ?)
                    ''',
                    (
                        log_event_data.get('tank_id'),
                        log_event_data.get('kind'),
                        log_event_data.get('description', ''),
                        log_event_data.get('ts')
                    )
                )
        return jsonify(message='Event data received'), 200
    with closing(sqlite3.connect(database_path)) as connection:
        connection.row_factory = sqlite3.Row
        tank_rows = connection.execute(
            'SELECT id, name FROM tanks ORDER BY name'
        ).fetchall()
    return render_template('log_event.html', tanks=tank_rows)

@app.route('/tank-data/<int:tank_id>', methods=['GET'])
def tank_data(tank_id):
    data = pd.DataFrame({
        'Days': [],
        'Ammonia': [],
        'Nitrite': [],
        'Nitrate': [],
        'KH': [],
        'pH': [],
        'Temperature': []
    })
    with closing(sqlite3.connect(database_path)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            '''
            SELECT created_at, ammonia, nitrite, nitrate, alkalinity, ph, temperature
            FROM tankdata
            WHERE tank_id = ?
            ORDER BY created_at
            ''',
            (tank_id,)
        ).fetchall()
    for row in rows:
        data = pd.concat([data, pd.DataFrame({
            'Days': [row['created_at'].split(' ')[0]],  # Extract only the date part
            'Ammonia': [row['ammonia']],
            'Nitrite': [row['nitrite']],
            'Nitrate': [row['nitrate']],
            'KH': [row['alkalinity']],
            'pH': [row['ph']],
            'Temperature': [row['temperature']]
        })], ignore_index=True)
    ammonia_data = data[['Days', 'Ammonia', 'pH', 'Temperature']].to_dict(orient='records')
    toxic_ammonia_values = utils.calculate_toxic_ammonia(ammonia_data)  # Calculate toxic ammonia and add it to the data
    data['Toxic Ammonia'] = toxic_ammonia_values  # Add the calculated toxic ammonia values to the DataFrame
    fig_scatter = px.line(data, x='Days', y=['Ammonia', 'Nitrite', 'Nitrate', 'KH', 'pH', 'Temperature', 'Toxic Ammonia'], title=f'Tank {tank_id} Parameters Over Time')
    # combined_fig = go.Figure(data=fig_line.data + fig_scatter.data)
    
    ### Line Boundaries ###
    # Nitrite
    fig_scatter.add_hline(y=50, line_dash="dash", line_color="red", line_width=2, annotation_text="Max Nitrite", annotation_position="bottom right")

    # Temperature
    fig_scatter.add_hline(y=72, line_dash="dash", line_color="lightblue", line_width=2, annotation_text="Min Temp", annotation_position="bottom right")
    fig_scatter.add_hline(y=84, line_dash="dash", line_color="lightblue", line_width=2, annotation_text="Max Temp", annotation_position="bottom right")

    # pH
    fig_scatter.add_hline(y=6, line_dash="dash", line_color="orange", line_width=2, annotation_text="Min pH", annotation_position="bottom right")
    fig_scatter.add_hline(y=8, line_dash="dash", line_color="orange", line_width=2, annotation_text="Max pH", annotation_position="bottom right")
    ######
    
    fig_scatter.update_layout(title=f'Tank {tank_id} Data Over Time', xaxis_title='Days', yaxis_title='Values')

    return fig_scatter.to_html(full_html=True)

@app.route('/tanktrends/<int:tank_id>', methods=['GET'])
def tanktrends(tank_id):

    PARAMS = [  # column, label, is an increase bad?
        ('ammonia', 'Ammonia (ppm)', True),
        ('nitrite', 'Nitrite (ppm)', True),
        ('nitrate', 'Nitrate (ppm)', True),
        ('alkalinity', 'KH (dKH)', None),
        ('ph', 'pH', None),
        ('temperature', 'Temp (°F)', None),
    ]
    with closing(sqlite3.connect(database_path)) as connection:
        df = pd.read_sql_query(
            '''SELECT created_at, ammonia, nitrite, nitrate, alkalinity, ph, temperature
                FROM tankdata WHERE tank_id = ?
                ORDER BY created_at DESC LIMIT 2''',
            connection, params=(tank_id,))

    if len(df) < 2:
        return 'Log at least two tests to see a comparison.'

    latest, previous = df.iloc[0], df.iloc[1]
    fig = make_subplots(rows=2, cols=3, specs=[[{'type': 'indicator'}] * 3] * 2)

    for i, (col, label, up_is_bad) in enumerate(PARAMS):
        if pd.isna(latest[col]):
            continue  # skip anything you didn't test this time
        delta = {'reference': None if pd.isna(previous[col]) else previous[col]}
        if up_is_bad is True:
            delta['increasing'] = {'color': '#b3261e'}
            delta['decreasing'] = {'color': '#0b6e6a'}
        else:
            delta['increasing'] = {'color': '#3b6fb6'}
            delta['decreasing'] = {'color': '#3b6fb6'}
        fig.add_trace(go.Indicator(mode='number+delta', value=latest[col],
                                   title={'text': label}, delta=delta),
                      row=i // 3 + 1, col=i % 3 + 1)

    fig.update_layout(title=f"Latest test ({latest['created_at']}) vs previous ({previous['created_at']})",
                      height=420)
    return fig.to_html(full_html=True)

@app.route('/trends', methods=['GET'])
def trends():
    with closing(sqlite3.connect(database_path)) as connection:
        connection.row_factory = sqlite3.Row
        tank_rows = connection.execute(
            'SELECT id, name FROM tanks ORDER BY name'
        ).fetchall()
    return render_template('trends.html', tanks=tank_rows)

@app.route('/tanks', methods=['GET'])
def tanks():
    with closing(sqlite3.connect(database_path)) as connection:
        connection.row_factory = sqlite3.Row
        tank_rows = connection.execute(
            'SELECT id, name, description, created_at FROM tanks ORDER BY id'
        ).fetchall()
    return render_template('tanks.html', tanks=tank_rows)

@app.route('/history', methods=['GET', 'PUT', 'DELETE'])
def history():
    with closing(sqlite3.connect(database_path)) as connection:
        connection.row_factory = sqlite3.Row
        tank_rows = connection.execute('''SELECT * FROM tanks;''').fetchall()
        tank_data_rows = connection.execute('''SELECT * FROM tankdata;''').fetchall()
        tank_event_rows = connection.execute('''SELECT * FROM tankevents;''').fetchall()
    return render_template('history.html', tanks=tank_rows, logs=tank_data_rows, events=tank_event_rows)

EVENT_TYPES = {'water_change', 'filter_clean', 'dosing', 'livestock', 'incident', 'other'}
NUMBER_LIMITS = {'ammonia': (0, None), 'nitrite': (0, None), 'nitrate': (0, None),
                 'alkalinity': (0, None), 'ph': (0, 14), 'temperature': (None, None)}

def clean_number(value, low, high):
    """Return a float or None. Raises ValueError for a bad value."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError('Readings must be numbers')
    if low is not None and value < low or high is not None and value > high:
        raise ValueError('A reading is out of range')
    return float(value)

@app.route('/tankdata/<int:row_id>', methods=['PUT'])
def update_tankdata(row_id):
    data = request.get_json(silent=True) or {}
    created_at = (data.get('created_at') or '').strip()
    if not created_at:
        return jsonify(error='Date and time are required'), 400
    try:
        values = [clean_number(data.get(name), *limits) for name, limits in NUMBER_LIMITS.items()]
    except ValueError as e:
        return jsonify(error=str(e)), 400
    note = (data.get('note') or '').strip() or None
    shaky = 1 if data.get('shaky') else 0

    with closing(sqlite3.connect(database_path)) as connection:
        cur = connection.execute(
            '''UPDATE tankdata
               SET created_at=?, ammonia=?, nitrite=?, nitrate=?, alkalinity=?, ph=?,
                   temperature=?, shaky=?, note=?
               WHERE id=?''',
            (created_at, *values, shaky, note, row_id))
        connection.commit()
        changed = cur.rowcount
    if changed == 0:
        return jsonify(error='That test no longer exists'), 404
    return jsonify(ok=True)

@app.route('/tankdata/<int:row_id>', methods=['DELETE'])
def delete_tankdata(row_id):
    with closing(sqlite3.connect(database_path)) as connection:
        cur = connection.execute('DELETE FROM tankdata WHERE id=?', (row_id,))
        connection.commit()
        changed = cur.rowcount
    if changed == 0:
        return jsonify(error='That test no longer exists'), 404
    return jsonify(ok=True)

@app.route('/tankevents/<int:row_id>', methods=['PUT'])
def update_tankevent(row_id):
    data = request.get_json(silent=True) or {}
    created_at = (data.get('created_at') or '').strip()
    event_type = data.get('event_type')
    if not created_at:
        return jsonify(error='Date and time are required'), 400
    if event_type not in EVENT_TYPES:
        return jsonify(error='Unknown event type'), 400
    description = (data.get('description') or '').strip() or None

    with closing(sqlite3.connect(database_path)) as connection:
        cur = connection.execute(
            'UPDATE tankevents SET created_at=?, event_type=?, description=? WHERE id=?',
            (created_at, event_type, description, row_id))
        connection.commit()
        changed = cur.rowcount
    if changed == 0:
        return jsonify(error='That event no longer exists'), 404
    return jsonify(ok=True)

@app.route('/tankevents/<int:row_id>', methods=['DELETE'])
def delete_tankevent(row_id):
    with closing(sqlite3.connect(database_path)) as connection:
        cur = connection.execute('DELETE FROM tankevents WHERE id=?', (row_id,))
        connection.commit()
        changed = cur.rowcount
    if changed == 0:
        return jsonify(error='That event no longer exists'), 404
    return jsonify(ok=True)

@app.route('/add-tank', methods=['GET', 'POST'])
def add_tank():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip() or None
        if not name:
            return render_template(
                'addtank.html',
                error='Please enter a name.',
                name=name,
                description=request.form.get('description', ''),
            ), 400

        with closing(sqlite3.connect(database_path)) as connection:
            with connection:
                connection.execute(
                    'INSERT INTO tanks (name, description) VALUES (?, ?)',
                    (name, description),
                )
        return redirect(url_for('tanks'))

    return render_template('addtank.html', name='', description='')

def main():
    app.run(debug=True)

if __name__ == '__main__':
    main()