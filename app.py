from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from datetime import datetime
from functools import wraps
from flask_sqlalchemy import SQLAlchemy
import pandas as pd
import io
import os

app = Flask(__name__)
app.secret_key = "silos_maintenance_secret_key_2026"

# ============ إعداد قاعدة البيانات (PostgreSQL) ============
db_url = os.environ.get('DATABASE_URL', 'sqlite:///database.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ============ نماذج قاعدة البيانات (Models) ============
class Work(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    phase = db.Column(db.String(100), nullable=False)
    start_date = db.Column(db.String(20))
    end_date = db.Column(db.String(20))
    duration = db.Column(db.Integer)
    responsible = db.Column(db.String(100))
    status = db.Column(db.String(50), default='لم يبدأ')
    progress = db.Column(db.Integer, default=0)
    notes = db.Column(db.Text)

class Worker(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(50))
    phone = db.Column(db.String(20))
    daily_wage = db.Column(db.Float, default=0)
    active = db.Column(db.Integer, default=1)

class WorkerAttendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('worker.id'))
    date = db.Column(db.String(20))
    status = db.Column(db.String(20))
    overtime_hours = db.Column(db.Float, default=0)
    notes = db.Column(db.Text)

class Material(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    unit = db.Column(db.String(50))
    current_balance = db.Column(db.Float, default=0)
    material_type = db.Column(db.String(50), default='مستهلكة')
    notes = db.Column(db.Text)
    material_code = db.Column(db.String(50))

class MaterialReceipt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    material_id = db.Column(db.Integer, db.ForeignKey('material.id'))
    quantity = db.Column(db.Float)
    date = db.Column(db.String(20))
    time = db.Column(db.String(10))
    received_by = db.Column(db.String(100))
    sender_name = db.Column(db.String(100))
    vehicle_no = db.Column(db.String(50))
    notes = db.Column(db.Text)

class MaterialIssue(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    material_id = db.Column(db.Integer, db.ForeignKey('material.id'))
    work_id = db.Column(db.Integer, db.ForeignKey('work.id'))
    quantity = db.Column(db.Float)
    date = db.Column(db.String(20))
    time = db.Column(db.String(10))
    issued_to = db.Column(db.String(100))
    notes = db.Column(db.Text)

class ToolLedger(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tool_name = db.Column(db.String(200), nullable=False)
    worker_name = db.Column(db.String(100))
    quantity = db.Column(db.Integer, default=1)
    date_out = db.Column(db.String(20))
    time_out = db.Column(db.String(10))
    date_in = db.Column(db.String(20))
    time_in = db.Column(db.String(10))
    status = db.Column(db.String(50), default='مع العامل')

class MaterialRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    material_name = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Float)
    unit = db.Column(db.String(50))
    requested_by = db.Column(db.String(100))
    date = db.Column(db.String(20))
    status = db.Column(db.String(50), default='قيد الانتظار')
    notes = db.Column(db.Text)

class ProjectSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_name = db.Column(db.String(200))
    location = db.Column(db.String(200))
    coordinates = db.Column(db.String(100))
    scope = db.Column(db.String(200))
    manager = db.Column(db.String(100))

class DailyLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(20), nullable=False)
    work_id = db.Column(db.Integer, db.ForeignKey('work.id'))
    workers_count = db.Column(db.Integer)
    notes = db.Column(db.Text)

class WorkWorker(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    work_id = db.Column(db.Integer, db.ForeignKey('work.id'))
    worker_id = db.Column(db.Integer, db.ForeignKey('worker.id'))
    assigned_date = db.Column(db.String(20))

# إنشاء الجداول
with app.app_context():
    db.create_all()

def row_to_dict(row):
    if row is None: return None
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}

def rows_to_dicts(rows):
    return [row_to_dict(r) for r in rows]

# ============ تسجيل الدخول ============
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if password == "admin":
            session["logged_in"] = True
            session["username"] = username
            return redirect(url_for("index"))
        flash("كلمة المرور خاطئة", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ============ الصفحة الرئيسية ============
@app.route("/")
@login_required
def index():
    total_works = Work.query.count()
    done_works = Work.query.filter_by(status='منجز').count()
    active_works = Work.query.filter_by(status='جاري').count()
    total_workers = Worker.query.filter_by(active=1).count()
    
    works = Work.query.all()
    avg_progress = sum([w.progress for w in works]) / len(works) if works else 0
    project_settings = row_to_dict(ProjectSetting.query.first())
    
    return render_template("index.html", 
        total_works=total_works, done_works=done_works, active_works=active_works, 
        total_workers=total_workers, avg_progress=round(avg_progress, 1),
        project_settings=project_settings)
# ============ إعدادات المشروع ============
@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        setting = ProjectSetting.query.first()
        if not setting:
            setting = ProjectSetting()
            db.session.add(setting)
        
        setting.project_name = request.form.get("project_name")
        setting.location = request.form.get("location")
        setting.coordinates = request.form.get("coordinates")
        setting.scope = request.form.get("scope")
        setting.manager = request.form.get("manager")
        db.session.commit()
        
        flash("تم تحديث إعدادات المشروع بنجاح", "success")
        return redirect(url_for("settings"))
    
    settings_data = row_to_dict(ProjectSetting.query.first())
    return render_template("settings.html", settings=settings_data)

@app.route("/export/settings")
@login_required
def export_settings():
    setting = ProjectSetting.query.first()
    data = [{"اسم المشروع": setting.project_name, "الموقع": setting.location, "الإحداثيات": setting.coordinates, "نطاق العمل": setting.scope, "مدير التنفيذ": setting.manager}] if setting else []
    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='إعدادات المشروع')
    output.seek(0)
    return send_file(output, download_name="إعدادات_المشروع.xlsx", as_attachment=True)

# ============ فهرس الأعمال ============
@app.route("/works")
@login_required
def works():
    works_list = rows_to_dicts(Work.query.order_by(Work.id).all())
    
    all_assignments = WorkWorker.query.order_by(WorkWorker.assigned_date.desc()).all()
    workers_by_work = {}
    for a in all_assignments:
        worker = Worker.query.get(a.worker_id)
        a_dict = row_to_dict(a)
        a_dict['worker_name'] = worker.name if worker else 'محذوف'
        a_dict['worker_role'] = worker.role if worker else ''
        if a.work_id not in workers_by_work: workers_by_work[a.work_id] = []
        workers_by_work[a.work_id].append(a_dict)
        
    logs = rows_to_dicts(DailyLog.query.order_by(DailyLog.date.desc()).all())
    logs_by_work = {}
    for l in logs:
        if l['work_id'] not in logs_by_work: logs_by_work[l['work_id']] = []
        logs_by_work[l['work_id']].append(l)
        
    return render_template("works.html", works=works_list, workers_by_work=workers_by_work, logs_by_work=logs_by_work)

@app.route("/works/add", methods=["POST"])
@login_required
def add_work():
    start_date, end_date = request.form.get("start_date"), request.form.get("end_date")
    duration = 0
    if start_date and end_date:
        d1 = datetime.strptime(start_date, "%Y-%m-%d")
        d2 = datetime.strptime(end_date, "%Y-%m-%d")
        duration = (d2 - d1).days
    
    new_work = Work(
        name=request.form.get("name"), phase=request.form.get("phase"),
        start_date=start_date, end_date=end_date, duration=duration,
        responsible=request.form.get("responsible"), status=request.form.get("status", "لم يبدأ")
    )
    db.session.add(new_work)
    db.session.commit()
    flash("تمت إضافة العمل بنجاح", "success")
    return redirect(url_for("works"))

@app.route("/works/edit/<int:work_id>", methods=["POST"])
@login_required
def edit_work(work_id):
    work = Work.query.get_or_404(work_id)
    start_date, end_date = request.form.get("start_date"), request.form.get("end_date")
    duration = 0
    if start_date and end_date:
        d1 = datetime.strptime(start_date, "%Y-%m-%d")
        d2 = datetime.strptime(end_date, "%Y-%m-%d")
        duration = (d2 - d1).days
    
    work.name = request.form.get("name")
    work.phase = request.form.get("phase")
    work.start_date = start_date
    work.end_date = end_date
    work.duration = duration
    work.responsible = request.form.get("responsible")
    work.status = request.form.get("status")
    db.session.commit()
    flash("تم تعديل العمل بنجاح", "success")
    return redirect(url_for("works"))

@app.route("/works/delete/<int:work_id>", methods=["POST"])
@login_required
def delete_work(work_id):
    work = Work.query.get_or_404(work_id)
    db.session.delete(work)
    db.session.commit()
    flash("تم حذف العمل بنجاح", "danger")
    return redirect(url_for("works"))

@app.route("/works/update_progress/<int:work_id>", methods=["POST"])
@login_required
def update_progress(work_id):
    work = Work.query.get_or_404(work_id)
    progress = int(request.form.get("progress", 0))
    work.progress = progress
    work.status = "منجز" if progress >= 100 else ("جاري" if progress > 0 else "لم يبدأ")
    db.session.commit()
    flash("تم تحديث نسبة الإنجاز", "success")
    return redirect(url_for("works"))

@app.route("/export/works")
@login_required
def export_works():
    works = Work.query.order_by(Work.id).all()
    data = [{"الرقم": w.id, "اسم العمل": w.name, "المرحلة": w.phase, "المسؤول": w.responsible, "تاريخ البداية": w.start_date, "تاريخ النهاية": w.end_date, "المدة (يوم)": w.duration, "الحالة": w.status, "نسبة الإنجاز %": w.progress} for w in works]
    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='الأعمال')
    output.seek(0)
    return send_file(output, download_name="فهرس_الأعمال.xlsx", as_attachment=True)

# ============ العمال ============
@app.route("/workers")
@login_required
def workers():
    workers_list = rows_to_dicts(Worker.query.order_by(Worker.id).all())
    all_attendance = WorkerAttendance.query.order_by(WorkerAttendance.date.desc()).all()
    attendance_by_worker = {}
    for a in all_attendance:
        if a.worker_id not in attendance_by_worker: attendance_by_worker[a.worker_id] = []
        attendance_by_worker[a.worker_id].append(row_to_dict(a))
    return render_template("workers.html", workers=workers_list, attendance_by_worker=attendance_by_worker)

@app.route("/workers/add", methods=["POST"])
@login_required
def add_worker():
    new_worker = Worker(
        name=request.form.get("name"), role=request.form.get("role"),
        phone=request.form.get("phone"), daily_wage=float(request.form.get("daily_wage") or 0)
    )
    db.session.add(new_worker)
    db.session.commit()
    flash("تمت إضافة العامل", "success")
    return redirect(url_for("workers"))

@app.route("/workers/edit/<int:worker_id>", methods=["POST"])
@login_required
def edit_worker(worker_id):
    worker = Worker.query.get_or_404(worker_id)
    worker.name = request.form.get("name")
    worker.role = request.form.get("role")
    worker.phone = request.form.get("phone")
    worker.daily_wage = float(request.form.get("daily_wage") or 0)
    db.session.commit()
    flash("تم تعديل بيانات العامل بنجاح", "success")
    return redirect(url_for("workers"))

@app.route("/workers/delete/<int:worker_id>", methods=["POST"])
@login_required
def delete_worker(worker_id):
    worker = Worker.query.get_or_404(worker_id)
    db.session.delete(worker)
    db.session.commit()
    flash("تم حذف العامل بنجاح", "danger")
    return redirect(url_for("workers"))

@app.route("/workers/attendance", methods=["GET", "POST"])
@login_required
def worker_attendance():
    if request.method == "POST":
        new_attendance = WorkerAttendance(
            worker_id=request.form.get("worker_id"), date=request.form.get("date"),
            status=request.form.get("status"), overtime_hours=float(request.form.get("overtime_hours") or 0),
            notes=request.form.get("notes")
        )
        db.session.add(new_attendance)
        db.session.commit()
        flash("تم تسجيل الدوام بنجاح", "success")
        return redirect(url_for("worker_attendance"))
    
    logs = WorkerAttendance.query.order_by(WorkerAttendance.date.desc()).all()
    logs_data = []
    for l in logs:
        w = Worker.query.get(l.worker_id)
        d = row_to_dict(l)
        d['worker_name'] = w.name if w else 'محذوف'
        d['worker_role'] = w.role if w else ''
        logs_data.append(d)
        
    workers_list = rows_to_dicts(Worker.query.filter_by(active=1).order_by(Worker.name).all())
    return render_template("worker_attendance.html", logs=logs_data, workers=workers_list)

@app.route("/export/attendance")
@login_required
def export_attendance():
    logs = WorkerAttendance.query.order_by(WorkerAttendance.date.desc()).all()
    data = []
    for l in logs:
        w = Worker.query.get(l.worker_id)
        data.append({"التاريخ": l.date, "اسم العامل": w.name if w else 'محذوف', "المهنة": w.role if w else '', "الحالة": l.status, "ساعات الإضافي": l.overtime_hours, "ملاحظات": l.notes})
    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='سجل الدوام')
    output.seek(0)
    return send_file(output, download_name="سجل_الدوام_والإضافي.xlsx", as_attachment=True)

@app.route("/export/workers")
@login_required
def export_workers():
    workers = Worker.query.order_by(Worker.id).all()
    data = [{"الرقم": w.id, "الاسم": w.name, "المهنة": w.role, "الهاتف": w.phone, "الأجر اليومي": w.daily_wage, "الحالة": "نشط" if w.active == 1 else "غير نشط"} for w in workers]
    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='العمال')
    output.seek(0)
    return send_file(output, download_name="كشف_العمال.xlsx", as_attachment=True)
# ============ المستودع الفرعي (المواد) ============
@app.route("/materials")
@login_required
def materials():
    materials_list = rows_to_dicts(Material.query.order_by(Material.material_type, Material.id).all())
    works_list = rows_to_dicts(Work.query.order_by(Work.name).all())
    
    receipts = MaterialReceipt.query.order_by(MaterialReceipt.date.desc(), MaterialReceipt.time.desc()).all()
    receipts_data = []
    for r in receipts:
        m = Material.query.get(r.material_id)
        d = row_to_dict(r)
        d['material_name'] = m.name if m else 'محذوف'
        d['material_code'] = m.material_code if m else ''
        d['unit'] = m.unit if m else ''
        receipts_data.append(d)
        
    issues = MaterialIssue.query.order_by(MaterialIssue.date.desc(), MaterialIssue.time.desc()).all()
    issues_data = []
    for i in issues:
        m = Material.query.get(i.material_id)
        w = Work.query.get(i.work_id)
        d = row_to_dict(i)
        d['material_name'] = m.name if m else 'محذوف'
        d['work_name'] = w.name if w else '—'
        issues_data.append(d)
        
    tools = rows_to_dicts(ToolLedger.query.order_by(ToolLedger.status.desc(), ToolLedger.date_out.desc()).all())
    requests_list = rows_to_dicts(MaterialRequest.query.order_by(MaterialRequest.date.desc()).all())
    
    return render_template("materials.html", materials=materials_list, works=works_list, receipts=receipts_data, issues=issues_data, tools=tools, requests_list=requests_list)

@app.route("/materials/add", methods=["POST"])
@login_required
def add_material():
    new_material = Material(
        name=request.form.get("name"), unit=request.form.get("unit"),
        material_type=request.form.get("material_type", "مستهلكة"),
        notes=request.form.get("notes"), material_code=request.form.get("material_code")
    )
    db.session.add(new_material)
    db.session.commit()
    flash("تمت إضافة المادة إلى الدليل", "success")
    return redirect(url_for("materials"))

@app.route("/materials/edit/<int:material_id>", methods=["POST"])
@login_required
def edit_material(material_id):
    material = Material.query.get_or_404(material_id)
    material.name = request.form.get("name")
    material.unit = request.form.get("unit")
    material.material_type = request.form.get("material_type")
    material.current_balance = float(request.form.get("current_balance") or 0)
    material.notes = request.form.get("notes")
    material.material_code = request.form.get("material_code")
    db.session.commit()
    flash("تم تعديل بيانات المادة بنجاح", "success")
    return redirect(url_for("materials"))

@app.route("/materials/delete/<int:material_id>", methods=["POST"])
@login_required
def delete_material(material_id):
    material = Material.query.get_or_404(material_id)
    db.session.delete(material)
    db.session.commit()
    flash("تم حذف المادة بنجاح", "danger")
    return redirect(url_for("materials"))

@app.route("/materials/bulk_delete", methods=["POST"])
@login_required
def bulk_delete_materials():
    selected_ids = request.form.getlist("selected_materials")
    if not selected_ids:
        flash("لم يتم تحديد أي مادة للحذف", "danger")
        return redirect(url_for("materials"))
    
    try:
        Material.query.filter(Material.id.in_(selected_ids)).delete(synchronize_session=False)
        db.session.commit()
        flash(f"تم حذف {len(selected_ids)} مادة بنجاح", "danger")
    except Exception as e:
        db.session.rollback()
        flash(f"حدث خطأ أثناء الحذف: {str(e)}", "danger")
    return redirect(url_for("materials"))

@app.route("/materials/import", methods=["POST"])
@login_required
def import_materials():
    file = request.files.get('file')
    if not file or file.filename == '':
        flash("الرجاء اختيار ملف إكسل أولاً", "danger")
        return redirect(url_for("materials"))
        
    try:
        df = pd.read_excel(file)
        name_col, unit_col, code_col = None, None, None
        
        for col in df.columns:
            col_str = str(col).strip()
            if 'اسم' in col_str or 'مادة' in col_str or 'Material' in col_str: name_col = col
            if 'وحدة' in col_str or 'Unit' in col_str: unit_col = col
            if 'رمز' in col_str or 'Code' in col_str: code_col = col
                
        if not name_col: name_col = df.columns[0]
        if not unit_col and len(df.columns) > 1: unit_col = df.columns[1]
            
        count = 0
        for index, row in df.iterrows():
            name = row[name_col]
            unit = row[unit_col] if unit_col else ''
            code = str(row[code_col]).strip() if code_col and pd.notna(row[code_col]) else ''
            
            if pd.notna(name) and str(name).strip() != '':
                new_mat = Material(name=str(name).strip(), unit=str(unit).strip() if pd.notna(unit) else '', material_type='مستهلكة', material_code=code)
                db.session.add(new_mat)
                count += 1
        db.session.commit()
        flash(f"تم استيراد {count} مادة بنجاح من ملف الإكسل", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"حدث خطأ أثناء قراءة الملف: {str(e)}", "danger")
    return redirect(url_for("materials"))

@app.route("/materials/import_receipts", methods=["POST"])
@login_required
def import_receipts():
    file = request.files.get('file')
    if not file or file.filename == '':
        flash("الرجاء اختيار ملف إكسل أولاً", "danger")
        return redirect(url_for("materials"))
        
    try:
        df = pd.read_excel(file)
        name_col, qty_col, unit_col, code_col = None, None, None, None
        
        for col in df.columns:
            col_str = str(col).strip()
            if 'اسم' in col_str or 'مادة' in col_str or 'Material' in col_str: name_col = col
            elif 'كمية' in col_str or 'Quantity' in col_str or 'اجمالي' in col_str or 'إجمالي' in col_str: qty_col = col
            elif 'وحدة' in col_str or 'Unit' in col_str or 'واحدة' in col_str: unit_col = col
            elif 'رمز' in col_str or 'Code' in col_str: code_col = col
                
        if not name_col or not qty_col:
            flash("تأكد من أن ملف الإكسل يحتوي على أعمدة: 'المادة' و 'الاجمالي'", "danger")
            return redirect(url_for("materials"))
            
        now = datetime.now()
        date, time = now.strftime("%Y-%m-%d"), now.strftime("%H:%M")
        received_by = session.get("username", "مدير التنفيذ")
        count = 0
        
        for index, row in df.iterrows():
            name = str(row[name_col]).strip() if pd.notna(row[name_col]) else ''
            quantity = float(row[qty_col]) if pd.notna(row[qty_col]) else 0
            unit = str(row[unit_col]).strip() if unit_col and pd.notna(row[unit_col]) else 'وحدة'
            code = str(row[code_col]).strip() if code_col and pd.notna(row[code_col]) else ''
            
            if name and quantity > 0:
                mat = Material.query.filter_by(name=name).first()
                if mat:
                    material_id = mat.id
                    mat.material_code = code
                    mat.unit = unit
                    mat.current_balance += quantity
                else:
                    new_mat = Material(name=name, unit=unit, material_type='مستهلكة', material_code=code, current_balance=quantity)
                    db.session.add(new_mat)
                    db.session.flush()
                    material_id = new_mat.id
                
                new_receipt = MaterialReceipt(material_id=material_id, quantity=quantity, date=date, time=time, received_by=received_by, sender_name='مستودع رئيسي', vehicle_no='', notes='')
                db.session.add(new_receipt)
                count += 1
        db.session.commit()
        flash(f"تم استيراد {count} مادة بنجاح وتحديث الرصيد", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"حدث خطأ أثناء قراءة الملف: {str(e)}", "danger")
    return redirect(url_for("materials"))

@app.route("/materials/update_receipt/<int:receipt_id>", methods=["POST"])
@login_required
def update_receipt_details(receipt_id):
    receipt = MaterialReceipt.query.get_or_404(receipt_id)
    receipt.vehicle_no = request.form.get("vehicle_no")
    receipt.notes = request.form.get("notes")
    db.session.commit()
    flash("تم تحديث بيانات الوارد بنجاح", "success")
    return redirect(url_for("materials"))

@app.route("/materials/delete_receipt/<int:receipt_id>", methods=["POST"])
@login_required
def delete_receipt(receipt_id):
    receipt = MaterialReceipt.query.get_or_404(receipt_id)
    db.session.delete(receipt)
    db.session.commit()
    flash("تم حذف سجل الوارد", "danger")
    return redirect(url_for("materials"))

@app.route("/materials/receipts_report", methods=["GET", "POST"])
@login_required
def receipts_report():
    query = MaterialReceipt.query
    if request.method == "POST":
        month = request.form.get("month")
        material_name = request.form.get("material_name")
        
        if month:
            query = query.filter(MaterialReceipt.date.like(f"{month}%"))
        if material_name:
            mats = Material.query.filter(Material.name.like(f"%{material_name}%")).all()
            mat_ids = [m.id for m in mats]
            query = query.filter(MaterialReceipt.material_id.in_(mat_ids))
    
    receipts = query.order_by(MaterialReceipt.date.desc(), MaterialReceipt.time.desc()).all()
    receipts_data = []
    for r in receipts:
        m = Material.query.get(r.material_id)
        d = row_to_dict(r)
        d['material_name'] = m.name if m else 'محذوف'
        d['material_code'] = m.material_code if m else ''
        d['unit'] = m.unit if m else ''
        receipts_data.append(d)
    
    return render_template("receipts_report.html", receipts=receipts_data)

@app.route("/materials/receive", methods=["POST"])
@login_required
def receive_material():
    material_id = request.form.get("material_id")
    quantity = float(request.form.get("quantity") or 0)
    
    material = Material.query.get_or_404(material_id)
    material.current_balance += quantity
    
    now = datetime.now()
    new_receipt = MaterialReceipt(
        material_id=material_id, quantity=quantity, date=now.strftime("%Y-%m-%d"), time=now.strftime("%H:%M"),
        received_by=request.form.get("received_by"), sender_name=request.form.get("sender_name"),
        vehicle_no=request.form.get("vehicle_no"), notes=request.form.get("notes")
    )
    db.session.add(new_receipt)
    db.session.commit()
    flash("تم تسجيل استلام المادة وتحديث الرصيد", "success")
    return redirect(url_for("materials"))

@app.route("/materials/issue", methods=["POST"])
@login_required
def issue_material():
    material_id = request.form.get("material_id")
    work_id = request.form.get("work_id")
    quantity = float(request.form.get("quantity") or 0)
    
    material = Material.query.get_or_404(material_id)
    if material.current_balance < quantity:
        flash("الرصيد غير كافٍ في المستودع!", "danger")
        return redirect(url_for("materials"))
        
    material.current_balance -= quantity
    now = datetime.now()
    new_issue = MaterialIssue(
        material_id=material_id, work_id=work_id, quantity=quantity,
        date=now.strftime("%Y-%m-%d"), time=now.strftime("%H:%M"),
        issued_to=request.form.get("issued_to"), notes=request.form.get("notes")
    )
    db.session.add(new_issue)
    db.session.commit()
    flash("تم صرف المادة وخصمها من الرصيد", "success")
    return redirect(url_for("materials"))

@app.route("/tools/checkout", methods=["POST"])
@login_required
def checkout_tool():
    now = datetime.now()
    new_tool = ToolLedger(
        tool_name=request.form.get("tool_name"), worker_name=request.form.get("worker_name"),
        quantity=request.form.get("quantity") or 1,
        date_out=now.strftime("%Y-%m-%d"), time_out=now.strftime("%H:%M"), status='مع العامل'
    )
    db.session.add(new_tool)
    db.session.commit()
    flash("تم تسليم العدة للعامل", "success")
    return redirect(url_for("materials"))

@app.route("/tools/checkin/<int:tool_id>", methods=["POST"])
@login_required
def checkin_tool(tool_id):
    tool = ToolLedger.query.get_or_404(tool_id)
    now = datetime.now()
    tool.date_in = now.strftime("%Y-%m-%d")
    tool.time_in = now.strftime("%H:%M")
    tool.status = 'تم الإرجاع'
    db.session.commit()
    flash("تم استلام العدة من العامل", "success")
    return redirect(url_for("materials"))

@app.route("/materials/request", methods=["POST"])
@login_required
def request_material():
    new_req = MaterialRequest(
        material_name=request.form.get("material_name"), quantity=request.form.get("quantity"),
        unit=request.form.get("unit"), requested_by=request.form.get("requested_by"),
        date=datetime.now().strftime("%Y-%m-%d"), notes=request.form.get("notes"), status="قيد الانتظار"
    )
    db.session.add(new_req)
    db.session.commit()
    flash("تم إرسال طلب التوريد للمستودع الرئيسي", "success")
    return redirect(url_for("materials"))

@app.route("/materials/request/approve/<int:req_id>", methods=["POST"])
@login_required
def approve_request(req_id):
    req = MaterialRequest.query.get_or_404(req_id)
    req.status = 'تم التوريد'
    db.session.commit()
    flash("تم تأكيد وصول المادة من المستودع الرئيسي", "success")
    return redirect(url_for("materials"))

@app.route("/export/receipts")
@login_required
def export_receipts():
    receipts = MaterialReceipt.query.order_by(MaterialReceipt.date.desc()).all()
    data = []
    for r in receipts:
        m = Material.query.get(r.material_id)
        data.append({"التاريخ": r.date, "الوقت": r.time, "المادة": m.name if m else 'محذوف', "الكمية": r.quantity, "المستلم": r.received_by, "المرسل": r.sender_name, "السيارة": r.vehicle_no, "ملاحظات": r.notes})
    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='الواردات')
    output.seek(0)
    return send_file(output, download_name="سجل_الواردات.xlsx", as_attachment=True)

@app.route("/export/issues")
@login_required
def export_issues():
    issues = MaterialIssue.query.order_by(MaterialIssue.date.desc()).all()
    data = []
    for i in issues:
        m = Material.query.get(i.material_id)
        w = Work.query.get(i.work_id)
        data.append({"التاريخ": i.date, "الوقت": i.time, "المادة": m.name if m else 'محذوف', "الكمية": i.quantity, "العمل": w.name if w else '—', "المستلم": i.issued_to, "ملاحظات": i.notes})
    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='المنصرفات')
    output.seek(0)
    return send_file(output, download_name="سجل_المنصرفات.xlsx", as_attachment=True)

# ============ السجل اليومي ============
@app.route("/daily_log")
@login_required
def daily_log():
    logs = DailyLog.query.order_by(DailyLog.date.desc()).all()
    logs_data = []
    for l in logs:
        w = Work.query.get(l.work_id)
        d = row_to_dict(l)
        d['work_name'] = w.name if w else '—'
        logs_data.append(d)
    works_list = rows_to_dicts(Work.query.order_by(Work.name).all())
    return render_template("daily_log.html", logs=logs_data, works=works_list)

@app.route("/daily_log/add", methods=["POST"])
@login_required
def add_daily_log():
    new_log = DailyLog(
        date=request.form.get("date"), work_id=request.form.get("work_id"),
        workers_count=request.form.get("workers_count") or 0, notes=request.form.get("notes")
    )
    db.session.add(new_log)
    db.session.commit()
    flash("تم تسجيل اليومية", "success")
    return redirect(url_for("daily_log"))

@app.route("/export/daily_log")
@login_required
def export_daily_log():
    logs = DailyLog.query.order_by(DailyLog.date.desc()).all()
    data = []
    for l in logs:
        w = Work.query.get(l.work_id)
        data.append({"التاريخ": l.date, "العمل": w.name if w else '—', "عدد العمال": l.workers_count, "ملاحظات": l.notes})
    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='السجل اليومي')
    output.seek(0)
    return send_file(output, download_name="السجل_اليومي.xlsx", as_attachment=True)

# ============ الجدول الزمني ============
@app.route("/schedule")
@login_required
def schedule():
    works_list = rows_to_dicts(Work.query.order_by(Work.start_date).all())
    return render_template("schedule.html", works=works_list)

@app.route("/export/schedule")
@login_required
def export_schedule():
    works = Work.query.order_by(Work.start_date).all()
    data = [{"اسم العمل": w.name, "المرحلة": w.phase, "المسؤول": w.responsible, "تاريخ البداية": w.start_date, "تاريخ النهاية": w.end_date, "المدة (يوم)": w.duration, "نسبة الإنجاز %": w.progress, "الحالة": w.status} for w in works]
    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='الجدول الزمني')
    output.seek(0)
    return send_file(output, download_name="الجدول_الزمني.xlsx", as_attachment=True)

# ============ التقارير ============
@app.route("/reports")
@login_required
def reports():
    status_counts = db.session.query(Work.status, db.func.count(Work.id)).group_by(Work.status).all()
    status_counts = [{"status": s[0], "count": s[1]} for s in status_counts]
    
    phase_counts = db.session.query(Work.phase, db.func.count(Work.id)).group_by(Work.phase).all()
    phase_counts = [{"phase": p[0], "count": p[1]} for p in phase_counts]
    
    pending_works = rows_to_dicts(Work.query.filter(Work.progress < 100).order_by(Work.progress.desc()).all())
    
    return render_template("reports.html", status_counts=status_counts, phase_counts=phase_counts, pending_works=pending_works)

@app.route("/export/reports")
@login_required
def export_reports():
    works = Work.query.order_by(Work.id).all()
    data = [{"اسم العمل": w.name, "المرحلة": w.phase, "المسؤول": w.responsible, "تاريخ البداية": w.start_date, "تاريخ النهاية": w.end_date, "المدة (يوم)": w.duration, "الحالة": w.status, "نسبة الإنجاز %": w.progress} for w in works]
    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='تقرير المشروع')
    output.seek(0)
    return send_file(output, download_name="تقرير_المشروع.xlsx", as_attachment=True)

# ============ تشغيل ============
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000)
