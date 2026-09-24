from functools import wraps
from datetime import date, timedelta
import os
import io
import json
import qrcode


from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, send_file, jsonify
from flask_login import login_required, current_user
import bcrypt

from app import db
from app.models import User, Student, Book, Transaction, Notification
from app.admin.forms import (AddBookForm, EditBookForm, AddStudentForm,
                              EditStudentForm, IssueBookForm)

admin_bp = Blueprint('admin', __name__, template_folder='../templates/admin')


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


# ──────────────────────── Dashboard ────────────────────────

@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    # Update overdue statuses
    overdue_txns = Transaction.query.filter(
        Transaction.status == 'issued',
        Transaction.due_date < date.today()
    ).all()
    for t in overdue_txns:
        t.status = 'overdue'
        # Create overdue notification
        existing = Notification.query.filter_by(
            user_id=t.student.user_id,
            message=f"OVERDUE: Book '{t.book.title}' was due on {t.due_date.strftime('%d %b %Y')}. Fine: ₹{t.calculated_fine:.0f}"
        ).first()
        if not existing:
            notif = Notification(
                user_id=t.student.user_id,
                message=f"OVERDUE: Book '{t.book.title}' was due on {t.due_date.strftime('%d %b %Y')}. Fine: ₹{t.calculated_fine:.0f}"
            )
            db.session.add(notif)
    db.session.commit()

    total_books = Book.query.filter_by(is_active=True).count()
    available_books = db.session.query(db.func.sum(Book.available_copies)).filter(Book.is_active == True).scalar() or 0
    issued_books = Transaction.query.filter(Transaction.status.in_(['issued', 'overdue'])).count()
    overdue_books = Transaction.query.filter_by(status='overdue').count()
    total_students = Student.query.count()
    recent_transactions = Transaction.query.order_by(Transaction.issue_date.desc()).limit(10).all()

    return render_template('dashboard.html',
                           total_books=total_books,
                           available_books=available_books,
                           issued_books=issued_books,
                           overdue_books=overdue_books,
                           total_students=total_students,
                           recent_transactions=recent_transactions)



# ──────────────────────── Book Management ────────────────────────

@admin_bp.route('/books')
@login_required
@admin_required
def books():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '', type=str)
    category = request.args.get('category', '', type=str)

    query = Book.query.filter_by(is_active=True)
    if search:
        query = query.filter(
            db.or_(
                Book.title.ilike(f'%{search}%'),
                Book.author.ilike(f'%{search}%'),
                Book.isbn.ilike(f'%{search}%')
            )
        )
    if category:
        query = query.filter_by(category=category)

    books = query.order_by(Book.title).paginate(page=page, per_page=10, error_out=False)
    categories = db.session.query(Book.category).filter_by(is_active=True).distinct().all()
    categories = [c[0] for c in categories]

    return render_template('books.html', books=books, search=search,
                           selected_category=category, categories=categories)


@admin_bp.route('/books/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_book():
    form = AddBookForm()
    if form.validate_on_submit():
        existing = Book.query.filter_by(isbn=form.isbn.data).first()
        if existing:
            flash('A book with this ISBN already exists.', 'danger')
            return render_template('add_book.html', form=form)

        book = Book(
            title=form.title.data,
            author=form.author.data,
            isbn=form.isbn.data,
            category=form.category.data,
            total_copies=form.total_copies.data,
            available_copies=form.total_copies.data,
            publisher=form.publisher.data or '',
            year=form.year.data,
            description=form.description.data or ''
        )
        db.session.add(book)
        db.session.commit()
        ensure_book_qr(book)
        flash(f'Book "{book.title}" added successfully! Unique QR code generated.', 'success')
        return redirect(url_for('admin.books'))


    return render_template('add_book.html', form=form)


@admin_bp.route('/books/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_book(id):
    book = Book.query.get_or_404(id)
    form = EditBookForm(obj=book)

    if form.validate_on_submit():
        dup = Book.query.filter(Book.isbn == form.isbn.data, Book.id != id).first()
        if dup:
            flash('Another book with this ISBN already exists.', 'danger')
            return render_template('edit_book.html', form=form, book=book)

        # Adjust available_copies if total changed
        diff = form.total_copies.data - book.total_copies
        book.title = form.title.data
        book.author = form.author.data
        book.isbn = form.isbn.data
        book.category = form.category.data
        book.total_copies = form.total_copies.data
        book.available_copies = max(0, book.available_copies + diff)
        book.publisher = form.publisher.data or ''
        book.year = form.year.data
        book.description = form.description.data or ''
        db.session.commit()
        flash(f'Book "{book.title}" updated successfully!', 'success')
        return redirect(url_for('admin.books'))

    return render_template('edit_book.html', form=form, book=book)


@admin_bp.route('/books/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_book(id):
    book = Book.query.get_or_404(id)
    book.is_active = False
    db.session.commit()
    flash(f'Book "{book.title}" has been removed.', 'warning')
    return redirect(url_for('admin.books'))


def ensure_book_qr(book):
    qr_dir = os.path.join(os.path.dirname(__file__), '..', 'static', 'generated_qr')
    os.makedirs(qr_dir, exist_ok=True)
    qr_path = os.path.join(qr_dir, f'book_{book.id}.png')

    # Payload explicitly encodes Book ID and ISBN as required
    payload = f"BOOK_ID={book.id}|ISBN={book.isbn}"

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(qr_path, 'PNG')
    return qr_path


@admin_bp.route('/books/<int:id>/qrcode')
@login_required
@admin_required
def book_qrcode(id):
    book = Book.query.get_or_404(id)
    qr_path = ensure_book_qr(book)
    download = request.args.get('download', 0, type=int)
    filename = f'book_{book.id}_qr.png'
    return send_file(qr_path, mimetype='image/png', as_attachment=bool(download), download_name=filename)


@admin_bp.route('/qr-generator')
@login_required
@admin_required
def qr_generator():
    search = request.args.get('search', '', type=str)
    category = request.args.get('category', '', type=str)

    query = Book.query.filter_by(is_active=True)
    if search:
        query = query.filter(
            db.or_(
                Book.title.ilike(f'%{search}%'),
                Book.author.ilike(f'%{search}%'),
                Book.isbn.ilike(f'%{search}%')
            )
        )
    if category:
        query = query.filter_by(category=category)

    books = query.order_by(Book.id.asc()).all()
    categories = db.session.query(Book.category).filter_by(is_active=True).distinct().all()
    categories = [c[0] for c in categories]

    # Ensure static QR PNG file exists for every active book
    for b in books:
        ensure_book_qr(b)

    return render_template('qr_generator.html', books=books, search=search,
                           selected_category=category, categories=categories)


@admin_bp.route('/generate-all-qrcodes', methods=['POST'])
@login_required
@admin_required
def generate_all_qrcodes():
    books = Book.query.filter_by(is_active=True).all()
    count = 0
    for b in books:
        ensure_book_qr(b)
        count += 1
    flash(f'Successfully generated unique QR codes for all {count} books!', 'success')
    return redirect(url_for('admin.qr_generator'))


@admin_bp.route('/books/<int:id>/generate-qr', methods=['POST'])
@login_required
@admin_required
def generate_single_qr(id):
    book = Book.query.get_or_404(id)
    ensure_book_qr(book)
    flash(f'Generated unique QR code for "{book.title}" (Book ID: {book.id}).', 'success')
    return redirect(url_for('admin.qr_generator'))


@admin_bp.route('/books/<int:id>/view-qr')
@login_required
@admin_required
def view_book_qr(id):
    book = Book.query.get_or_404(id)
    ensure_book_qr(book)
    return render_template('view_qr.html', book=book)


# ──────────────────────── Student Management ────────────────────────

@admin_bp.route('/students')
@login_required
@admin_required
def students():
    search = request.args.get('search', '', type=str)
    query = Student.query.join(User)
    if search:
        query = query.filter(
            db.or_(
                User.name.ilike(f'%{search}%'),
                Student.student_id.ilike(f'%{search}%'),
                Student.department.ilike(f'%{search}%')
            )
        )
    students = query.all()
    return render_template('students.html', students=students, search=search)


@admin_bp.route('/students/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_student():
    form = AddStudentForm()
    if form.validate_on_submit():
        if User.query.filter_by(email=form.email.data).first():
            flash('A user with this email already exists.', 'danger')
            return render_template('add_student.html', form=form)
        if Student.query.filter_by(student_id=form.student_id.data).first():
            flash('A student with this roll number already exists.', 'danger')
            return render_template('add_student.html', form=form)

        pw_hash = bcrypt.hashpw(form.password.data.encode('utf-8'),
                                bcrypt.gensalt()).decode('utf-8')
        user = User(
            name=form.name.data,
            email=form.email.data,
            password_hash=pw_hash,
            role='student'
        )
        db.session.add(user)
        db.session.flush()

        student = Student(
            user_id=user.id,
            student_id=form.student_id.data,
            department=form.department.data,
            year=form.year.data,
            phone=form.phone.data
        )
        db.session.add(student)
        db.session.commit()
        flash(f'Student "{user.name}" registered successfully!', 'success')
        return redirect(url_for('admin.students'))

    return render_template('add_student.html', form=form)


@admin_bp.route('/students/<int:id>')
@login_required
@admin_required
def view_student(id):
    student = Student.query.get_or_404(id)
    return render_template('view_student.html', student=student)


@admin_bp.route('/students/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_student(id):
    student = Student.query.get_or_404(id)
    form = EditStudentForm(obj=student)

    if request.method == 'GET':
        form.name.data = student.user.name
        form.email.data = student.user.email

    if form.validate_on_submit():
        dup_email = User.query.filter(User.email == form.email.data,
                                      User.id != student.user_id).first()
        if dup_email:
            flash('Another user with this email exists.', 'danger')
            return render_template('edit_student.html', form=form, student=student)

        dup_roll = Student.query.filter(Student.student_id == form.student_id.data,
                                        Student.id != id).first()
        if dup_roll:
            flash('Another student with this roll number exists.', 'danger')
            return render_template('edit_student.html', form=form, student=student)

        student.user.name = form.name.data
        student.user.email = form.email.data
        student.student_id = form.student_id.data
        student.department = form.department.data
        student.year = form.year.data
        student.phone = form.phone.data
        db.session.commit()
        flash('Student info updated successfully!', 'success')
        return redirect(url_for('admin.view_student', id=student.id))

    return render_template('edit_student.html', form=form, student=student)


@admin_bp.route('/scan-qr')
@login_required
@admin_required
def scan_qr():
    return render_template('scan_qr.html')


@admin_bp.route('/api/lookup-book', methods=['POST'])
@login_required
@admin_required
def lookup_book_api():
    data = request.get_json() or {}
    raw_code = (data.get('qr_code') or data.get('query') or '').strip()

    if not raw_code:
        return jsonify({'success': False, 'message': 'No code provided'}), 400

    book = None
    # 1. Parse BOOK_ID=<id>|ISBN=<isbn> format
    if 'BOOK_ID=' in raw_code:
        try:
            parts = raw_code.split('|')
            for part in parts:
                if part.startswith('BOOK_ID='):
                    bid_str = part.replace('BOOK_ID=', '').strip()
                    if bid_str.isdigit():
                        book = Book.query.filter_by(id=int(bid_str), is_active=True).first()
        except Exception:
            pass

    # 2. Parse BOOK_ID:<id> format
    if not book and 'BOOK_ID:' in raw_code:
        try:
            parts = raw_code.split('|')
            for part in parts:
                if part.startswith('BOOK_ID:'):
                    bid_str = part.replace('BOOK_ID:', '').strip()
                    if bid_str.isdigit():
                        book = Book.query.filter_by(id=int(bid_str), is_active=True).first()
        except Exception:
            pass

    # 3. Try parsing raw_code as JSON payload
    if not book:
        try:
            payload = json.loads(raw_code)
            if isinstance(payload, dict):
                if 'id' in payload:
                    book = Book.query.filter_by(id=payload['id'], is_active=True).first()
                elif 'isbn' in payload:
                    book = Book.query.filter_by(isbn=payload['isbn'], is_active=True).first()
        except (json.JSONDecodeError, TypeError):
            pass

    # 4. Fallback: query by exact ISBN, numeric ID, or title match
    if not book:
        if raw_code.isdigit():
            book = Book.query.filter_by(id=int(raw_code), is_active=True).first()
        if not book:
            book = Book.query.filter_by(isbn=raw_code, is_active=True).first()
        if not book:
            book = Book.query.filter(Book.is_active == True, Book.title.ilike(f'%{raw_code}%')).first()


    if not book:
        return jsonify({'success': False, 'message': f'No active book found matching "{raw_code}"'}), 404

    # Fetch active transactions for this book
    active_txns = Transaction.query.filter(
        Transaction.book_id == book.id,
        Transaction.status.in_(['issued', 'overdue'])
    ).all()

    issued_details = []
    for t in active_txns:
        issued_details.append({
            'transaction_id': t.id,
            'student_name': t.student.user.name,
            'student_id': t.student.student_id,
            'issue_date': t.issue_date.strftime('%d %b %Y'),
            'due_date': t.due_date.strftime('%d %b %Y'),
            'status': t.status,
            'fine': f"₹{t.calculated_fine:.0f}"
        })

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
            'year': book.year or 'N/A',
            'description': book.description or '',
            'is_available': book.is_available,
            'qrcode_url': url_for('admin.book_qrcode', id=book.id),
            'issue_url': url_for('admin.issue_book', isbn=book.isbn),
            'edit_url': url_for('admin.edit_book', id=book.id),
            'active_issues': issued_details
        }
    })


@admin_bp.route('/api/lookup-student', methods=['POST'])
@login_required
@admin_required
def lookup_student_api():
    data = request.get_json() or {}
    roll_number = (data.get('student_id') or data.get('roll_number') or '').strip()

    if not roll_number:
        return jsonify({'success': False, 'message': 'Please enter a Student Roll Number / ID.'}), 400

    student = Student.query.filter(Student.student_id.ilike(roll_number)).first()
    if not student:
        return jsonify({'success': False, 'message': f'Student with Roll Number "{roll_number}" not found.'}), 404

    active_issues_count = Transaction.query.filter(
        Transaction.student_id == student.id,
        Transaction.status.in_(['issued', 'overdue'])
    ).count()

    can_issue = active_issues_count < 3

    return jsonify({
        'success': True,
        'student': {
            'id': student.id,
            'student_id': student.student_id,
            'name': student.user.name,
            'email': student.user.email,
            'department': student.department,
            'year': student.year,
            'phone': student.phone or 'N/A',
            'active_issues_count': active_issues_count,
            'can_issue': can_issue,
            'message': 'Student already has 3 active borrowed books.' if not can_issue else ''
        }
    })


@admin_bp.route('/api/issue-book', methods=['POST'])
@login_required
@admin_required
def issue_book_api():
    data = request.get_json() or {}
    book_id = data.get('book_id')
    student_roll = (data.get('student_id') or data.get('roll_number') or '').strip()

    if not book_id:
        return jsonify({'success': False, 'message': 'Book ID is required.'}), 400
    if not student_roll:
        return jsonify({'success': False, 'message': 'Student Roll Number is required.'}), 400

    book = Book.query.filter_by(id=book_id, is_active=True).first()
    if not book:
        return jsonify({'success': False, 'message': 'Book not found or inactive.'}), 404

    if book.available_copies <= 0:
        return jsonify({'success': False, 'message': 'No copies available for this book.'}), 400

    student = Student.query.filter(Student.student_id.ilike(student_roll)).first()
    if not student:
        return jsonify({'success': False, 'message': f'Student with Roll Number "{student_roll}" not found.'}), 404

    # Prevent duplicate active issue of the SAME book to the SAME student
    existing_txn = Transaction.query.filter(
        Transaction.student_id == student.id,
        Transaction.book_id == book.id,
        Transaction.status.in_(['issued', 'overdue'])
    ).first()
    if existing_txn:
        return jsonify({
            'success': False,
            'message': f'Student {student.user.name} ({student.student_id}) already currently has this book issued.'
        }), 400

    # Validate active books limit (< 3)
    active_count = Transaction.query.filter(
        Transaction.student_id == student.id,
        Transaction.status.in_(['issued', 'overdue'])
    ).count()
    if active_count >= 3:
        return jsonify({
            'success': False,
            'message': f'Student {student.user.name} already has {active_count} active borrowed books (limit 3).'
        }), 400

    # Process issue transaction
    txn = Transaction(
        student_id=student.id,
        book_id=book.id,
        issue_date=date.today(),
        due_date=date.today() + timedelta(days=14),
        status='issued'
    )
    book.available_copies -= 1
    db.session.add(txn)

    # Create notification for student
    notif = Notification(
        user_id=student.user_id,
        message=f"Book '{book.title}' issued to you. Due by {txn.due_date.strftime('%d %b %Y')}."
    )
    db.session.add(notif)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Book "{book.title}" successfully issued to {student.user.name} ({student.student_id})! Due by {txn.due_date.strftime("%d %b %Y")}.',
        'transaction_id': txn.id,
        'new_available_copies': book.available_copies
    })



# ──────────────────────── Issue & Return ────────────────────────

@admin_bp.route('/issue', methods=['GET', 'POST'])
@login_required
@admin_required
def issue_book():
    form = IssueBookForm()
    if request.method == 'GET' and request.args.get('isbn'):
        form.book_isbn.data = request.args.get('isbn')
    if form.validate_on_submit():
        student = Student.query.filter_by(student_id=form.student_roll.data).first()
        if not student:
            flash('Student with this roll number not found.', 'danger')
            return render_template('issue_book.html', form=form)

        # Find book by ISBN or title
        book = Book.query.filter(
            db.and_(
                Book.is_active == True,
                db.or_(
                    Book.isbn == form.book_isbn.data,
                    Book.title.ilike(f'%{form.book_isbn.data}%')
                )
            )
        ).first()
        if not book:
            flash('Book not found.', 'danger')
            return render_template('issue_book.html', form=form)

        # Validate constraints
        active_issues = Transaction.query.filter(
            Transaction.student_id == student.id,
            Transaction.status.in_(['issued', 'overdue'])
        ).count()
        if active_issues >= 3:
            flash('Student already has 3 active issued books. Cannot issue more.', 'danger')
            return render_template('issue_book.html', form=form)

        if book.available_copies <= 0:
            flash('No available copies of this book.', 'danger')
            return render_template('issue_book.html', form=form)

        # Issue the book
        txn = Transaction(
            student_id=student.id,
            book_id=book.id,
            issue_date=date.today(),
            due_date=date.today() + timedelta(days=14),
            status='issued'
        )
        book.available_copies -= 1
        db.session.add(txn)

        # Create notification
        notif = Notification(
            user_id=student.user_id,
            message=f"Book '{book.title}' issued to you. Due by {txn.due_date.strftime('%d %b %Y')}."
        )
        db.session.add(notif)
        db.session.commit()
        flash(f'Book "{book.title}" issued to {student.user.name} successfully!', 'success')
        return redirect(url_for('admin.transactions'))

    return render_template('issue_book.html', form=form)


@admin_bp.route('/return/<int:transaction_id>', methods=['POST'])
@login_required
@admin_required
def return_book(transaction_id):
    txn = Transaction.query.get_or_404(transaction_id)
    if txn.status == 'returned':
        flash('This book has already been returned.', 'info')
        return redirect(url_for('admin.transactions'))

    txn.return_date = date.today()
    txn.status = 'returned'

    # Calculate fine
    if txn.return_date > txn.due_date:
        days = (txn.return_date - txn.due_date).days
        txn.fine_amount = days * 2.0
        notif = Notification(
            user_id=txn.student.user_id,
            message=f"Book '{txn.book.title}' returned with a fine of ₹{txn.fine_amount:.0f} ({days} days overdue)."
        )
        db.session.add(notif)
    else:
        txn.fine_amount = 0.0
        notif = Notification(
            user_id=txn.student.user_id,
            message=f"Book '{txn.book.title}' returned successfully. No fine."
        )
        db.session.add(notif)

    txn.book.available_copies += 1
    db.session.commit()
    flash(f'Book "{txn.book.title}" returned. Fine: ₹{txn.fine_amount:.0f}', 'success')
    return redirect(url_for('admin.transactions'))


@admin_bp.route('/transactions')
@login_required
@admin_required
def transactions():
    status_filter = request.args.get('status', 'all', type=str)
    search = request.args.get('search', '', type=str)

    query = Transaction.query.join(Student).join(Book)
    if status_filter and status_filter != 'all':
        query = query.filter(Transaction.status == status_filter)
    if search:
        query = query.filter(
            db.or_(
                Book.title.ilike(f'%{search}%'),
                Student.student_id.ilike(f'%{search}%')
            )
        )
    txns = query.order_by(Transaction.issue_date.desc()).all()
    return render_template('transactions.html', transactions=txns,
                           status_filter=status_filter, search=search)
