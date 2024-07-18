from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, time
from apscheduler.schedulers.background import BackgroundScheduler
import pytz
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from cryptography.fernet import Fernet
from sqlalchemy.orm.exc import NoResultFound

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///schedule_system.db'
#app.config['ENCRYPTION_KEY'] = b'your_fixed_base64_encoded_key_here'
from cryptography.fernet import Fernet
import base64

# キーの生成
key = Fernet.generate_key()

# Base64エンコード
#encoded_key = base64.urlsafe_b64encode(key)

# Flaskアプリケーションの設定に設定する例
#app.config['ENCRYPTION_KEY'] = key
app.config['ENCRYPTION_KEY'] = b'3_kpRUDHoFyxdQr2s3hdT5Cg15kslxOUkojGxo90Hm8='

print(f"app.config['ENCRYPTION_KEY'] = {app.config['ENCRYPTION_KEY']}")



db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

cipher_suite = Fernet(app.config['ENCRYPTION_KEY'])

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    #email = db.Column(db.String(100), unique=True, nullable=False)
    gmail_address = db.Column(db.String(100), nullable=True)
    gmail_app_password = db.Column(db.String(200), nullable=True)
    schedules = db.relationship('Schedule', backref='user', lazy=True)
    notifications = db.relationship('Notification', backref='user', lazy=True)

class Schedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(100), nullable=False)
    day = db.Column(db.String(20), nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    room_number = db.Column(db.String(20), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.String(200), nullable=False)
    notification_time = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
@login_required
def index():
    schedules = Schedule.query.filter_by(user_id=current_user.id).all()
    notifications = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.notification_time.desc()).limit(5).all()
    return render_template('index.html', schedules=schedules, notifications=notifications)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        #email = request.form['email']
        gmail_address = request.form['gmail_address']
        gmail_app_password = request.form['gmail_app_password']

        user = User.query.filter_by(username=username).first()
        if user:
            flash('Username already exists.')
            return redirect(url_for('register'))

        encrypted_app_password = cipher_suite.encrypt(gmail_app_password.encode())

        new_user = User(
            username=username, 
            password_hash=generate_password_hash(password),
            #email=email,
            gmail_address=gmail_address,
            gmail_app_password=encrypted_app_password
        )
        db.session.add(new_user)
        db.session.commit()
        flash('Registration successful. Please log in.')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('index'))
        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/add_schedule', methods=['GET', 'POST'])
@login_required
def add_schedule():
    if request.method == 'POST':
        subject = request.form['subject']
        day = request.form['day']
        start_time = datetime.strptime(request.form['start_time'], '%H:%M').time()
        end_time = datetime.strptime(request.form['end_time'], '%H:%M').time()
        room_number = request.form['room_number']
        new_schedule = Schedule(subject=subject, day=day, start_time=start_time, end_time=end_time, room_number=room_number, user_id=current_user.id)
        db.session.add(new_schedule)
        db.session.commit()
        flash('Schedule added successfully.')
        return redirect(url_for('index'))
    return render_template('add_schedule.html')

@app.route('/delete_schedule/<int:schedule_id>', methods=['POST'])
@login_required
def delete_schedule(schedule_id):
    schedule = Schedule.query.get_or_404(schedule_id)
    if schedule.user_id != current_user.id:
        flash('You do not have permission to delete this schedule.')
        return redirect(url_for('index'))
    db.session.delete(schedule)
    db.session.commit()
    flash('Schedule deleted successfully.')
    return redirect(url_for('index'))

def send_email(user, subject, body):
    msg = MIMEMultipart()
    msg['From'] = user.gmail_address
    msg['To'] = user.gmail_address
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        decrypted_password = cipher_suite.decrypt(user.gmail_app_password).decode()
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(user.gmail_address, decrypted_password)
        server.send_message(msg)
        server.quit()
        #print(f"Email sent successfully to {user.email}")
    except Exception as e:
        print(f"Failed to send email: {e.args}")
        raise  # 例外を再度発生させてプログラムの実行を停止する



def send_notifications():
    with app.app_context():
        now = datetime.now(pytz.timezone('Asia/Tokyo'))
        current_day = now.strftime('%A')
        current_time = now.time()
        schedules = Schedule.query.filter_by(day=current_day).all()
        for schedule in schedules:
            time_difference = (schedule.start_time.hour - current_time.hour) * 60 + (schedule.start_time.minute - current_time.minute)
            if 14 < time_difference <= 15:
                message = f"Reminder: {schedule.subject} starts in {time_difference} minutes in room {schedule.room_number}"
                
                try:
                    existing_notification = Notification.query.filter(
                        Notification.user_id == schedule.user_id,
                        Notification.message == message,
                        Notification.notification_time == datetime(now.year, now.month, now.day, schedule.start_time.hour, schedule.start_time.minute)
                    ).one()
                except NoResultFound:
                    existing_notification = None
                
                if not existing_notification:
                    notification = Notification(
                        message=message,
                        user_id=schedule.user_id,
                        notification_time=datetime(now.year, now.month, now.day, schedule.start_time.hour, schedule.start_time.minute)
                    )
                    db.session.add(notification)
                    
                    user = db.session.query(User).get(schedule.user_id)  # Fix to use query correctly
                    send_email(user, "Schedule Reminder", message)
        
        db.session.commit()

scheduler = BackgroundScheduler()
scheduler.add_job(func=send_notifications, trigger="interval", seconds=30)  # Run every 30 seconds for testing purposes
scheduler.start()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
