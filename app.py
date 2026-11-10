from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'tajny_klucz_projektu_wypozyczalnia'
DB_PATH = r'C:\Users\Jasty\Documents\Uczelnia\Projekt TI\car_rental.db\car_rental.db'

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def strona_glowna():
    conn = get_db_connection()
    # Dodaliśmy pobieranie "id", aby wiedzieć, które auto kliknął użytkownik
    auta = conn.execute("SELECT id, brand, model, year, price_per_day FROM cars").fetchall()
    conn.close()
    return render_template('index.html', auta=auta)

@app.route('/register', methods=['GET', 'POST'])
def register():
    # ... (kod pozostaje bez zmian z Tygodnia 5) ...
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
    # ... (kod pozostaje bez zmian z Tygodnia 5) ...
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
    # Zabezpieczenie: tylko zalogowani mogą wypożyczać
    if 'user_id' not in session:
        flash('Musisz być zalogowany, aby wypożyczyć samochód.', 'warning')
        return redirect(url_for('login_page'))
        
    conn = get_db_connection()
    car = conn.execute("SELECT * FROM cars WHERE id = ?", (car_id,)).fetchone()
    
    if request.method == 'POST':
        start_date_str = request.form['start_date']
        end_date_str = request.form['end_date']
        
        # Przeliczanie dat i liczby dni
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
        dni = (end_date - start_date).days
        
        # Prosta walidacja czy daty mają sens
        if dni <= 0:
            flash('Data zwrotu musi być późniejsza niż data wypożyczenia!', 'danger')
            conn.close()
            return redirect(url_for('rent_car', car_id=car_id))
            
        # Obliczenie pełnej kwoty i zapis do bazy
        total_price = dni * car['price_per_day']
        conn.execute(
            "INSERT INTO reservations (user_id, car_id, start_date, end_date, total_price) VALUES (?, ?, ?, ?, ?)",
            (session['user_id'], car_id, start_date_str, end_date_str, total_price)
        )
        conn.commit()
        conn.close()
        
        flash(f'Pomyślnie zarezerwowano {car["brand"]} {car["model"]}! Całkowity koszt: {total_price} zł.', 'success')
        return redirect(url_for('strona_glowna'))
        
    conn.close()
    return render_template('rent.html', car=car)

if __name__ == '__main__':
    app.run(debug=True)