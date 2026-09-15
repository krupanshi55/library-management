from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from config import Config

from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'info'
csrf = CSRFProtect()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    from app.auth.routes import auth_bp
    from app.admin.routes import admin_bp
    from app.student.routes import student_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(student_bp, url_prefix='/student')

    # Root route redirects to login
    @app.route('/')
    def index():
        from flask import redirect, url_for
        return redirect(url_for('auth.login'))

    # JSON API Routes
    from flask import jsonify, request
    from datetime import date, timedelta
    from app.models import Book, Student, Transaction, User

    @app.route('/api/books/<isbn>', methods=['GET', 'POST'])
    @csrf.exempt
    def api_get_book(isbn):
        book = Book.query.filter_by(isbn=isbn, is_active=True).first()
        if not book and isbn.isdigit():
            book = Book.query.filter_by(id=int(isbn), is_active=True).first()
        if not book:
            return jsonify({'success': False, 'error': 'Book not found', 'message': f'Book with ISBN/ID "{isbn}" not found.'}), 404
        return jsonify({
            'success': True,
            'book': {
                'id': book.id,
                'title': book.title,
                'author': book.author,
                'isbn': book.isbn,
                'category': book.category,
                'total_copies': book.total_copies,
                'available_copies': book.available_copies,
                'publisher': book.publisher or 'N/A',
                'year': book.year or 'N/A'
            }
        })

    @app.route('/api/transactions/issue', methods=['POST'])
    @csrf.exempt
    def api_issue_transaction():
        data = request.get_json() or {}
        student_id = (data.get('student_id') or data.get('roll_number') or '').strip()
        isbn = (data.get('isbn') or data.get('book_id') or data.get('qr_code') or '').strip()

        student = Student.query.filter(Student.student_id.ilike(student_id)).first()
        if not student:
            return jsonify({'success': False, 'error': 'Student not found', 'message': f'Student with Roll Number "{student_id}" not found.'}), 404

        book = Book.query.filter_by(isbn=isbn, is_active=True).first()
        if not book and isbn.isdigit():
            book = Book.query.filter_by(id=int(isbn), is_active=True).first()

        if not book:
            return jsonify({'success': False, 'error': 'Book not found', 'message': f'Book matching "{isbn}" not found.'}), 404

        if book.available_copies <= 0:
            return jsonify({'success': False, 'error': 'No copies available', 'message': 'No copies available for this book.'}), 400

        existing_issue = Transaction.query.filter(
            Transaction.student_id == student.id,
            Transaction.book_id == book.id,
            Transaction.status.in_(['issued', 'overdue'])
        ).first()
        if existing_issue:
            return jsonify({'success': False, 'error': 'Already issued', 'message': f'Student already has an active issue for "{book.title}".'}), 400

        active_count = Transaction.query.filter(
            Transaction.student_id == student.id,
            Transaction.status.in_(['issued', 'overdue'])
        ).count()
        if active_count >= 3:
            return jsonify({'success': False, 'error': 'Limit reached', 'message': 'Student has reached the maximum 3 active borrowed books limit.'}), 400

        issue_date = date.today()
        due_date = issue_date + timedelta(days=14)

        txn = Transaction(
            student_id=student.id,
            book_id=book.id,
            issue_date=issue_date,
            due_date=due_date,
            status='issued'
        )
        book.available_copies -= 1
        db.session.add(txn)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Book "{book.title}" issued successfully to {student.user.name}!',
            'transaction_id': txn.id,
            'book': {
                'id': book.id,
                'title': book.title,
                'available_copies': book.available_copies,
                'total_copies': book.total_copies
            }
        })

    @app.route('/api/transactions/return', methods=['POST'])
    @csrf.exempt
    def api_return_transaction():
        data = request.get_json() or {}
        txn_id = data.get('transaction_id')
        isbn = data.get('isbn')
        student_id = data.get('student_id')

        txn = None
        if txn_id:
            txn = Transaction.query.get(txn_id)
        elif isbn and student_id:
            student = Student.query.filter(Student.student_id.ilike(student_id)).first()
            book = Book.query.filter_by(isbn=isbn).first()
            if student and book:
                txn = Transaction.query.filter(
                    Transaction.student_id == student.id,
                    Transaction.book_id == book.id,
                    Transaction.status.in_(['issued', 'overdue'])
                ).first()

        if not txn:
            return jsonify({'success': False, 'error': 'Transaction not found', 'message': 'Transaction not found or already returned.'}), 404

        if txn.status == 'returned':
            return jsonify({'success': True, 'message': 'This book has already been returned.'})

        txn.return_date = date.today()
        txn.status = 'returned'
        fine_amount = 0.0
        if txn.return_date > txn.due_date:
            days = (txn.return_date - txn.due_date).days
            fine_amount = days * 2.0
        txn.fine_amount = fine_amount

        txn.book.available_copies += 1
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Book "{txn.book.title}" returned successfully.',
            'fine_amount': fine_amount,
            'available_copies': txn.book.available_copies
        })

    # CSRF & HTTP Error Handlers
    from flask_wtf.csrf import CSRFError

    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        if request.path.startswith('/api/') or request.path.startswith('/admin/api/'):
            return jsonify({'success': False, 'error': 'CSRF token missing or invalid', 'message': e.description}), 400
        from flask import flash, redirect, url_for
        flash('Session expired or CSRF token missing. Please try again.', 'warning')
        return redirect(request.referrer or url_for('auth.login'))

    @app.errorhandler(404)
    def handle_404(e):
        if request.path.startswith('/api/') or request.path.startswith('/admin/api/'):
            return jsonify({'success': False, 'error': 'Endpoint or resource not found', 'message': 'Endpoint or resource not found'}), 404
        from flask import render_template
        try:
            return render_template('404.html'), 404
        except Exception:
            return "<h3>404 - Page Not Found</h3><p><a href='/'>Return to Home</a></p>", 404

    @app.errorhandler(400)
    def handle_400(e):
        if request.path.startswith('/api/') or request.path.startswith('/admin/api/'):
            return jsonify({'success': False, 'error': 'Bad request', 'message': str(e)}), 400
        from flask import render_template
        try:
            return render_template('400.html'), 400
        except Exception:
            return f"<h3>400 - Bad Request</h3><p>{e}</p><p><a href='/'>Return to Home</a></p>", 400

    @app.errorhandler(500)
    def handle_500(e):
        if request.path.startswith('/api/') or request.path.startswith('/admin/api/'):
            return jsonify({'success': False, 'error': 'Internal server error', 'message': str(e)}), 500
        from flask import render_template
        try:
            return render_template('500.html'), 500
        except Exception:
            return f"<h3>500 - Internal Server Error</h3><p>{e}</p><p><a href='/'>Return to Home</a></p>", 500

    with app.app_context():
        db.create_all()

    return app
