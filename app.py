# pyright: reportMissingImports=false
import os
from flask import Flask, render_template, request, redirect, url_for, session, flash  # type: ignore[reportMissingImports]
import sqlite3
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'tajny_klucz_projektu_wypozyczalnia'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'car_rental.db')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
def odswiez_statusy(conn):
    dzis = datetime.now().strftime('%Y-%m-%d')
    przeterminowane = conn.execute('''
        SELECT id, car_id FROM reservations
        WHERE end_date < ? AND COALESCE(status, 'oczekująca') NOT IN ('zakończona', 'anulowana')
    ''', (dzis,)).fetchall()

    for rez in przeterminowane:
        conn.execute("UPDATE reservations SET status = 'zakończona' WHERE id = ?", (rez['id'],))
        conn.execute("UPDATE cars SET status = 'available' WHERE id = ?", (rez['car_id'],))

    if przeterminowane:
        conn.commit()

@app.route('/')
def strona_glowna():
    conn = get_db_connection()
    odswiez_statusy(conn)
    auta = conn.execute(
        "SELECT id, brand, model, year, price_per_day, image_url, status FROM cars WHERE status != 'service'"
    ).fetchall()
    conn.close()
    return render_template('index.html', auta=auta)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        conn = get_db_connection()
        user = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if user:
            flash('Użytkownik o takim adresie e-mail już istnieje!', 'danger')
            conn.close()
            return redirect(url_for('register'))
        conn.execute("INSERT INTO users (name, email, password) VALUES (?, ?, ?)", (name, email, password))
        conn.commit()
        conn.close()
        flash('Konto zostało pomyślnie utworzone! Możesz się zalogować.', 'success')
        return redirect(url_for('login_page'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE email = ? AND password = ?", (email, password)).fetchone()
        conn.close()
        if user:
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            session['user_role'] = user['role']
            session['role'] = user['role']
            if user['email'] == 'admin@gmail.com':
                 session['role'] = 'admin'
            flash(f"Zalogowano pomyślnie. Witaj {user['name']}!", 'success')
            return redirect(url_for('strona_glowna'))
        else:
            flash('Błędny e-mail lub hasło. Spróbuj ponownie.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Zostałeś pomyślnie wylogowany.', 'info')
    return redirect(url_for('strona_glowna'))

# NOWA FUNKCJA: Obsługa rezerwacji
@app.route('/rent/<int:car_id>', methods=['GET', 'POST'])
def rent_car(car_id):
    if 'user_id' not in session:
        flash('Musisz być zalogowany, aby wypożyczyć samochód.', 'warning')
        return redirect(url_for('login_page'))
        
    conn = get_db_connection()
    odswiez_statusy(conn)
    car = conn.execute("SELECT * FROM cars WHERE id = ?", (car_id,)).fetchone()
    if not car or car['status'] == 'service':
        conn.close()
        flash('Wybrany samochód jest obecnie niedostępny.', 'danger')
        return redirect(url_for('strona_glowna'))

    # Pobranie wszystkich aktywnych rezerwacji tego auta, żeby pokazać klientowi zajęte daty
    zajete_terminy = conn.execute('''
        SELECT start_date, end_date FROM reservations
        WHERE car_id = ?
          AND COALESCE(status, 'oczekująca') NOT IN ('anulowana', 'zakończona')
          AND end_date >= date('now')
        ORDER BY start_date ASC
    ''', (car_id,)).fetchall()
    
    if request.method == 'POST':
        start_date_str = request.form['start_date']
        end_date_str = request.form['end_date']
        
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
        dni = (end_date - start_date).days
        
        if start_date.date() < datetime.now().date():
            flash('Data wypożyczenia nie może być z przeszłości!', 'danger')
            conn.close()
            return redirect(url_for('rent_car', car_id=car_id))

        if dni <= 0:
            flash('Data zwrotu musi być późniejsza niż data wypożyczenia!', 'danger')
            conn.close()
            return redirect(url_for('rent_car', car_id=car_id))

        # Blokada nakładających się terminów
        kolizja = conn.execute('''
            SELECT id FROM reservations
            WHERE car_id = ?
              AND COALESCE(status, 'oczekująca') NOT IN ('anulowana', 'zakończona')
              AND start_date < ? AND end_date > ?
        ''', (car_id, end_date_str, start_date_str)).fetchone()

        if kolizja:
            flash('Ten samochód jest już zarezerwowany w wybranym terminie! Wybierz inne daty.', 'danger')
            conn.close()
            return redirect(url_for('rent_car', car_id=car_id))
            
        total_price = dni * car['price_per_day']
        conn.execute(
            "INSERT INTO reservations (user_id, car_id, start_date, end_date, total_price, status) VALUES (?, ?, ?, ?, ?, 'oczekująca')",
            (session['user_id'], car_id, start_date_str, end_date_str, total_price)
        )
        conn.commit()
        conn.close()
        
        flash(f'Pomyślnie zarezerwowano {car["brand"]} {car["model"]}! Całkowity koszt: {total_price:.2f} zł.', 'success')
        return redirect(url_for('strona_glowna'))
        
    conn.close()
    return render_template('rent.html', car=car, zajete_terminy=zajete_terminy)

# tydzien 7(panel uzytkownika)
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash('Musisz być zalogowany, aby zobaczyć swoje rezerwacje.', 'warning')
        return redirect(url_for('login_page'))

    conn = get_db_connection()
    # Automatyczne dodanie kolumny 'status' do rezerwacji, jeśli jeszcze jej nie ma
    try:
        conn.execute("ALTER TABLE reservations ADD COLUMN status TEXT DEFAULT 'oczekująca'")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    if session.get('role') == 'admin':
        wszystkie_auta = conn.execute('SELECT * FROM cars ORDER BY id DESC').fetchall()
        wszystkie_rezerwacje = conn.execute('''
            SELECT r.id, r.start_date, r.end_date, r.total_price, r.status,
                   u.email AS user_email, c.brand, c.model, c.year, c.id AS car_id
            FROM reservations r
            JOIN users u ON r.user_id = u.id
            JOIN cars c ON r.car_id = c.id
            ORDER BY r.id DESC
        ''').fetchall()
        conn.close()
        return render_template('dashboard.html', auta=wszystkie_auta, rezerwacje=wszystkie_rezerwacje, suma_wydatkow=0)

    rezerwacje = conn.execute('''
        SELECT r.id, r.start_date, r.end_date, r.total_price, r.status, c.brand, c.model, c.year
        FROM reservations r
        JOIN cars c ON r.car_id = c.id
        WHERE r.user_id = ?
        ORDER BY r.start_date DESC
    ''', (session['user_id'],)).fetchall()
    conn.close()

    # Obliczenie łącznej kwoty wszystkich rezerwacji użytkownika
    suma_wydatkow = sum(r['total_price'] for r in rezerwacje)

    return render_template('dashboard.html', rezerwacje=rezerwacje, suma_wydatkow=suma_wydatkow)

@app.route('/cancel/<int:res_id>', methods=['POST'])
def cancel_reservation(res_id):
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
        
    conn = get_db_connection()
    rez = conn.execute("SELECT car_id FROM reservations WHERE id = ? AND user_id = ?", (res_id, session['user_id'])).fetchone()
    if rez:
        conn.execute("DELETE FROM reservations WHERE id = ? AND user_id = ?", (res_id, session['user_id']))
        conn.execute("UPDATE cars SET status = 'available' WHERE id = ?", (rez['car_id'],))
        conn.commit()
    conn.close()
    
    flash('Rezerwacja została pomyślnie anulowana.', 'info')
    return redirect(url_for('dashboard'))
def zapisz_zdjecie(file):
    if file and file.filename != '':
        filename = secure_filename(file.filename)
        upload_folder = os.path.join(BASE_DIR, 'static', 'images')
        os.makedirs(upload_folder, exist_ok=True)
        file.save(os.path.join(upload_folder, filename))
        return url_for('static', filename='images/' + filename)
    return None

@app.route('/admin/dodaj-auto', methods=['POST'])
def admin_dodaj_auto():
    if session.get('role') != 'admin':
        return redirect(url_for('strona_glowna'))

    brand = request.form['brand']
    model = request.form['model']
    year = request.form['year']
    price_per_day = request.form['price_per_day']
    status = request.form.get('status', 'available')

    image_url = zapisz_zdjecie(request.files.get('image_file')) or request.form.get('image_url', '').strip()

    conn = get_db_connection()
    conn.execute(
        'INSERT INTO cars (brand, model, year, price_per_day, status, image_url) VALUES (?, ?, ?, ?, ?, ?)',
        (brand, model, year, price_per_day, status, image_url)
    )
    conn.commit()
    conn.close()
    flash('Dodano nowy samochód!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/admin/edytuj-auto/<int:car_id>', methods=['POST'])
def admin_edytuj_auto(car_id):
    if session.get('role') != 'admin':
        return redirect(url_for('strona_glowna'))

    brand = request.form['brand']
    model = request.form['model']
    year = request.form['year']
    price_per_day = request.form['price_per_day']
    status = request.form['status']

    nowe_zdjecie = zapisz_zdjecie(request.files.get('image_file')) or request.form.get('image_url', '').strip()

    conn = get_db_connection()
    if nowe_zdjecie:
        conn.execute(
            'UPDATE cars SET brand=?, model=?, year=?, price_per_day=?, status=?, image_url=? WHERE id=?',
            (brand, model, year, price_per_day, status, nowe_zdjecie, car_id)
        )
    else:
        conn.execute(
            'UPDATE cars SET brand=?, model=?, year=?, price_per_day=?, status=? WHERE id=?',
            (brand, model, year, price_per_day, status, car_id)
        )
    conn.commit()
    conn.close()
    flash('Zaktualizowano dane samochodu!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/admin/usun-auto/<int:car_id>', methods=['POST'])
def admin_usun_auto(car_id):
    if session.get('role') != 'admin':
        return redirect(url_for('strona_glowna'))

    conn = get_db_connection()
    conn.execute('DELETE FROM cars WHERE id = ?', (car_id,))
    conn.commit()
    conn.close()
    flash('Usunięto samochód z bazy.', 'info')
    return redirect(url_for('dashboard'))

@app.route('/admin/status-rezerwacji/<int:res_id>', methods=['POST'])
def admin_status_rezerwacji(res_id):
    if session.get('role') != 'admin':
        return redirect(url_for('strona_glowna'))

    nowy_status = request.form['status']
    car_id = request.form['car_id']

    conn = get_db_connection()
    conn.execute('UPDATE reservations SET status = ? WHERE id = ?', (nowy_status, res_id))

    if nowy_status in ['zatwierdzona', 'w trakcie']:
        conn.execute("UPDATE cars SET status = 'rented' WHERE id = ?", (car_id,))
    elif nowy_status in ['zakończona', 'anulowana']:
        conn.execute("UPDATE cars SET status = 'available' WHERE id = ?", (car_id,))

    conn.commit()
    conn.close()
    flash('Zmieniono status rezerwacji!', 'success')
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(debug=True)