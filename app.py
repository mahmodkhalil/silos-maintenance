from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
import sqlite3
from datetime import datetime
from functools import wraps
import pandas as pd
import io

app = Flask(__name__)
app.secret_key = "silos_maintenance_secret_key_2026"
DB_NAME = "database.db"

# ============ قاعدة البيانات ============
def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # جدول الأعمال
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS works (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, phase TEXT NOT NULL, start_date TEXT, end_date TEXT, 
            duration INTEGER, responsible TEXT, status TEXT DEFAULT 'لم يبدأ', 
            progress INTEGER DEFAULT 0, notes TEXT
        )
    """)

    # جدول العمال
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS workers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, role TEXT, phone TEXT, daily_wage REAL, active INTEGER DEFAULT 1
        )
    """)

    # جدول دوام العمال
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS worker_attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            worker_id INTEGER,
            date TEXT,
            status TEXT,
            overtime_hours REAL DEFAULT 0,
            notes TEXT,
            FOREIGN KEY (worker_id) REFERENCES workers(id)
        )
    """)

    # جدول المواد (مع material_code)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, unit TEXT, current_balance REAL DEFAULT 0,
            material_type TEXT DEFAULT 'مستهلكة',
            notes TEXT,
            material_code TEXT
        )
    """)

    # جدول الاستلام
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS material_receipts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id INTEGER, quantity REAL, date TEXT, time TEXT, 
            received_by TEXT, sender_name TEXT, vehicle_no TEXT, notes TEXT,
            FOREIGN KEY (material_id) REFERENCES materials(id)
        )
    """)

    # جدول الصرف
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS material_issues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id INTEGER, work_id INTEGER, quantity REAL, date TEXT, time TEXT, 
            issued_to TEXT, notes TEXT,
            FOREIGN KEY (material_id) REFERENCES materials(id),
            FOREIGN KEY (work_id) REFERENCES works(id)
        )
    """)

    # جدول العهدة
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tools_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_name TEXT NOT NULL, worker_name TEXT, quantity INTEGER DEFAULT 1, 
            date_out TEXT, time_out TEXT, date_in TEXT, time_in TEXT, status TEXT DEFAULT 'مع العامل'
        )
    """)

    # جدول الطلبات
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS material_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_name TEXT NOT NULL, quantity REAL, unit TEXT, 
            requested_by TEXT, date TEXT, status TEXT DEFAULT 'قيد الانتظار', notes TEXT
        )
    """)

    # جدول إعدادات المشروع
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS project_settings (
            id INTEGER PRIMARY KEY,
            project_name TEXT,
            location TEXT,
            coordinates TEXT,
            scope TEXT,
            manager TEXT
        )
    """)

    # السجل اليومي وربط العمال
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL, work_id INTEGER, workers_count INTEGER, notes TEXT,
            FOREIGN KEY (work_id) REFERENCES works(id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS work_workers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            work_id INTEGER, worker_id INTEGER, assigned_date TEXT,
            FOREIGN KEY (work_id) REFERENCES works(id),
            FOREIGN KEY (worker_id) REFERENCES workers(id)
        )
    """)

    conn.commit()
    conn.close()

# إنشاء قاعدة البيانات عند التشغيل (حتى مع gunicorn)
init_db()

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
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as total FROM works")
    total_works = cursor.fetchone()["total"]
    cursor.execute("SELECT COUNT(*) as done FROM works WHERE status='منجز'")
    done_works = cursor.fetchone()["done"]
    cursor.execute("SELECT COUNT(*) as active FROM works WHERE status='جاري'")
    active_works = cursor.fetchone()["active"]
    cursor.execute("SELECT COUNT(*) as workers FROM workers WHERE active=1")
    total_workers = cursor.fetchone()["workers"]
    cursor.execute("SELECT AVG(progress) as avg_progress FROM works")
    avg_progress = cursor.fetchone()["avg_progress"] or 0
    
    cursor.execute("SELECT * FROM project_settings WHERE id=1")
    project_settings = cursor.fetchone()
    
    conn.close()
    return render_template("index.html", 
        total_works=total_works, done_works=done_works, active_works=active_works, 
        total_workers=total_workers, avg_progress=round(avg_progress, 1),
        project_settings=project_settings)

# ============ إعدادات المشروع ============
@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    conn = get_connection()
    cursor = conn.cursor()
    
    if request.method == "POST":
        project_name = request.form.get("project_name")
        location = request.form.get("location")
        coordinates = request.form.get("coordinates")
        scope = request.form.get("scope")
        manager = request.form.get("manager")
        
        cursor.execute("""
            INSERT OR REPLACE INTO project_settings (id, project_name, location, coordinates, scope, manager)
            VALUES (1, ?, ?, ?, ?, ?)
        """, (project_name, location, coordinates, scope, manager))
        conn.commit()
        conn.close()
        flash("تم تحديث إعدادات المشروع بنجاح", "success")
        return redirect(url_for("settings"))
    
    cursor.execute("SELECT * FROM project_settings WHERE id = 1")
    settings_data = cursor.fetchone()
    conn.close()
    return render_template("settings.html", settings=settings_data)

@app.route("/export/settings")
@login_required
def export_settings():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM project_settings WHERE id=1")
    rows = cursor.fetchall()
    conn.close()
    data = [{"اسم المشروع": r["project_name"], "الموقع": r["location"], "الإحداثيات": r["coordinates"], "نطاق العمل": r["scope"], "مدير التنفيذ": r["manager"]} for r in rows]
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
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM works ORDER BY id")
    works_list = cursor.fetchall()
    cursor.execute("SELECT ww.*, w.name as worker_name, w.role as worker_role FROM work_workers ww JOIN workers w ON ww.worker_id = w.id ORDER BY ww.assigned_date DESC")
    all_assignments = cursor.fetchall()
    workers_by_work = {}
    for a in all_assignments:
        wid = a["work_id"]
        if wid not in workers_by_work: workers_by_work[wid] = []
        workers_by_work[wid].append(dict(a))
    cursor.execute("SELECT * FROM daily_log ORDER BY date DESC")
    logs = cursor.fetchall()
    logs_by_work = {}
    for l in logs:
        wid = l["work_id"]
        if wid not in logs_by_work: logs_by_work[wid] = []
        logs_by_work[wid].append(dict(l))
    conn.close()
    return render_template("works.html", works=works_list, workers_by_work=workers_by_work, logs_by_work=logs_by_work)

@app.route("/works/add", methods=["POST"])
@login_required
def add_work():
    name, phase = request.form.get("name"), request.form.get("phase")
    start_date, end_date = request.form.get("start_date"), request.form.get("end_date")
    responsible, status = request.form.get("responsible"), request.form.get("status", "لم يبدأ")
    duration = 0
    if start_date and end_date:
        d1 = datetime.strptime(start_date, "%Y-%m-%d")
        d2 = datetime.strptime(end_date, "%Y-%m-%d")
        duration = (d2 - d1).days
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO works (name, phase, start_date, end_date, duration, responsible, status) VALUES (?, ?, ?, ?, ?, ?, ?)", (name, phase, start_date, end_date, duration, responsible, status))
    conn.commit()
    conn.close()
    flash("تمت إضافة العمل بنجاح", "success")
    return redirect(url_for("works"))

@app.route("/works/edit/<int:work_id>", methods=["POST"])
@login_required
def edit_work(work_id):
    name, phase = request.form.get("name"), request.form.get("phase")
    start_date, end_date = request.form.get("start_date"), request.form.get("end_date")
    responsible, status = request.form.get("responsible"), request.form.get("status")
    duration = 0
    if start_date and end_date:
        d1 = datetime.strptime(start_date, "%Y-%m-%d")
        d2 = datetime.strptime(end_date, "%Y-%m-%d")
        duration = (d2 - d1).days
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE works SET name=?, phase=?, start_date=?, end_date=?, duration=?, responsible=?, status=? WHERE id=?", (name, phase, start_date, end_date, duration, responsible, status, work_id))
    conn.commit()
    conn.close()
    flash("تم تعديل العمل بنجاح", "success")
    return redirect(url_for("works"))

@app.route("/works/delete/<int:work_id>", methods=["POST"])
@login_required
def delete_work(work_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM works WHERE id=?", (work_id,))
    conn.commit()
    conn.close()
    flash("تم حذف العمل بنجاح", "danger")
    return redirect(url_for("works"))

@app.route("/works/update_progress/<int:work_id>", methods=["POST"])
@login_required
def update_progress(work_id):
    progress = int(request.form.get("progress", 0))
    status = "منجز" if progress >= 100 else ("جاري" if progress > 0 else "لم يبدأ")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE works SET progress=?, status=? WHERE id=?", (progress, status, work_id))
    conn.commit()
    conn.close()
    flash("تم تحديث نسبة الإنجاز", "success")
    return redirect(url_for("works"))

@app.route("/export/works")
@login_required
def export_works():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, phase, responsible, start_date, end_date, duration, status, progress FROM works ORDER BY id")
    rows = cursor.fetchall()
    conn.close()
    data = [{"الرقم": r["id"], "اسم العمل": r["name"], "المرحلة": r["phase"], "المسؤول": r["responsible"], "تاريخ البداية": r["start_date"], "تاريخ النهاية": r["end_date"], "المدة (يوم)": r["duration"], "الحالة": r["status"], "نسبة الإنجاز %": r["progress"]} for r in rows]
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
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM workers ORDER BY id")
    workers_list = cursor.fetchall()
    
    cursor.execute("""
        SELECT wa.*, w.name as worker_name 
        FROM worker_attendance wa 
        JOIN workers w ON wa.worker_id = w.id 
        ORDER BY wa.date DESC
    """)
    all_attendance = cursor.fetchall()
    
    attendance_by_worker = {}
    for a in all_attendance:
        wid = a["worker_id"]
        if wid not in attendance_by_worker:
            attendance_by_worker[wid] = []
        attendance_by_worker[wid].append(dict(a))
        
    conn.close()
    return render_template("workers.html", workers=workers_list, attendance_by_worker=attendance_by_worker)

@app.route("/workers/add", methods=["POST"])
@login_required
def add_worker():
    name, role = request.form.get("name"), request.form.get("role")
    phone, daily_wage = request.form.get("phone"), request.form.get("daily_wage") or 0
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO workers (name, role, phone, daily_wage) VALUES (?, ?, ?, ?)", (name, role, phone, daily_wage))
    conn.commit()
    conn.close()
    flash("تمت إضافة العامل", "success")
    return redirect(url_for("workers"))

@app.route("/workers/edit/<int:worker_id>", methods=["POST"])
@login_required
def edit_worker(worker_id):
    name, role = request.form.get("name"), request.form.get("role")
    phone, daily_wage = request.form.get("phone"), request.form.get("daily_wage") or 0
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE workers SET name=?, role=?, phone=?, daily_wage=? WHERE id=?", (name, role, phone, daily_wage, worker_id))
    conn.commit()
    conn.close()
    flash("تم تعديل بيانات العامل بنجاح", "success")
    return redirect(url_for("workers"))

@app.route("/workers/delete/<int:worker_id>", methods=["POST"])
@login_required
def delete_worker(worker_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM workers WHERE id=?", (worker_id,))
    conn.commit()
    conn.close()
    flash("تم حذف العامل بنجاح", "danger")
    return redirect(url_for("workers"))

# ============ سجل دوام وإضافي العمال ============
@app.route("/workers/attendance", methods=["GET", "POST"])
@login_required
def worker_attendance():
    conn = get_connection()
    cursor = conn.cursor()
    
    if request.method == "POST":
        worker_id = request.form.get("worker_id")
        date = request.form.get("date")
        status = request.form.get("status")
        overtime_hours = float(request.form.get("overtime_hours") or 0)
        notes = request.form.get("notes")
        
        cursor.execute("""
            INSERT INTO worker_attendance (worker_id, date, status, overtime_hours, notes)
            VALUES (?, ?, ?, ?, ?)
        """, (worker_id, date, status, overtime_hours, notes))
        conn.commit()
        flash("تم تسجيل الدوام بنجاح", "success")
        return redirect(url_for("worker_attendance"))
    
    cursor.execute("""
        SELECT wa.*, w.name as worker_name, w.role as worker_role 
        FROM worker_attendance wa 
        JOIN workers w ON wa.worker_id = w.id 
        ORDER BY wa.date DESC
    """)
    attendance_logs = cursor.fetchall()
    
    cursor.execute("SELECT * FROM workers WHERE active=1 ORDER BY name")
    workers_list = cursor.fetchall()
    conn.close()
    return render_template("worker_attendance.html", logs=attendance_logs, workers=workers_list)

@app.route("/export/attendance")
@login_required
def export_attendance():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT wa.date, w.name as worker_name, w.role, wa.status, wa.overtime_hours, wa.notes 
        FROM worker_attendance wa 
        JOIN workers w ON wa.worker_id = w.id 
        ORDER BY wa.date DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    data = [{"التاريخ": r["date"], "اسم العامل": r["worker_name"], "المهنة": r["role"], "الحالة": r["status"], "ساعات الإضافي": r["overtime_hours"], "ملاحظات": r["notes"]} for r in rows]
    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='سجل الدوام')
    output.seek(0)
    return send_file(output, download_name="سجل_الدوام_والإضافي.xlsx", as_attachment=True)

@app.route("/export/workers")
@login_required
def export_workers():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, role, phone, daily_wage, active FROM workers ORDER BY id")
    rows = cursor.fetchall()
    conn.close()
    data = [{"الرقم": r["id"], "الاسم": r["name"], "المهنة": r["role"], "الهاتف": r["phone"], "الأجر اليومي": r["daily_wage"], "الحالة": "نشط" if r["active"] == 1 else "غير نشط"} for r in rows]
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
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM materials ORDER BY material_type, id")
    materials_list = cursor.fetchall()
    cursor.execute("SELECT * FROM works ORDER BY name")
    works_list = cursor.fetchall()
    cursor.execute("SELECT mr.*, m.name as material_name FROM material_receipts mr JOIN materials m ON mr.material_id = m.id ORDER BY mr.date DESC, mr.time DESC")
    receipts = cursor.fetchall()
    cursor.execute("SELECT mi.*, m.name as material_name, w.name as work_name FROM material_issues mi JOIN materials m ON mi.material_id = m.id LEFT JOIN works w ON mi.work_id = w.id ORDER BY mi.date DESC, mi.time DESC")
    issues = cursor.fetchall()
    cursor.execute("SELECT * FROM tools_ledger ORDER BY status DESC, date_out DESC")
    tools = cursor.fetchall()
    cursor.execute("SELECT * FROM material_requests ORDER BY date DESC")
    requests_list = cursor.fetchall()
    conn.close()
    return render_template("materials.html", materials=materials_list, works=works_list, receipts=receipts, issues=issues, tools=tools, requests_list=requests_list)

@app.route("/materials/add", methods=["POST"])
@login_required
def add_material():
    name, unit = request.form.get("name"), request.form.get("unit")
    material_type = request.form.get("material_type", "مستهلكة")
    notes = request.form.get("notes")
    material_code = request.form.get("material_code")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO materials (name, unit, material_type, notes, material_code) VALUES (?, ?, ?, ?, ?)", (name, unit, material_type, notes, material_code))
    conn.commit()
    conn.close()
    flash("تمت إضافة المادة إلى الدليل", "success")
    return redirect(url_for("materials"))

# ============ تعديل وحذف المواد ============
@app.route("/materials/edit/<int:material_id>", methods=["POST"])
@login_required
def edit_material(material_id):
    name = request.form.get("name")
    unit = request.form.get("unit")
    material_type = request.form.get("material_type")
    current_balance = float(request.form.get("current_balance") or 0)
    notes = request.form.get("notes")
    material_code = request.form.get("material_code")
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE materials 
        SET name=?, unit=?, material_type=?, current_balance=?, notes=?, material_code=?
        WHERE id=?
    """, (name, unit, material_type, current_balance, notes, material_code, material_id))
    conn.commit()
    conn.close()
    flash("تم تعديل بيانات المادة بنجاح", "success")
    return redirect(url_for("materials"))

@app.route("/materials/delete/<int:material_id>", methods=["POST"])
@login_required
def delete_material(material_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM materials WHERE id=?", (material_id,))
    conn.commit()
    conn.close()
    flash("تم حذف المادة بنجاح", "danger")
    return redirect(url_for("materials"))

# ============ حذف عدة مواد (جماعي) ============
@app.route("/materials/bulk_delete", methods=["POST"])
@login_required
def bulk_delete_materials():
    selected_ids = request.form.getlist("selected_materials")
    if not selected_ids:
        flash("لم يتم تحديد أي مادة للحذف", "danger")
        return redirect(url_for("materials"))
    
    conn = get_connection()
    cursor = conn.cursor()
    try:
        for mat_id in selected_ids:
            cursor.execute("DELETE FROM materials WHERE id=?", (mat_id,))
        conn.commit()
        flash(f"تم حذف {len(selected_ids)} مادة بنجاح", "danger")
    except Exception as e:
        flash(f"حدث خطأ أثناء الحذف: {str(e)}", "danger")
    finally:
        conn.close()
    return redirect(url_for("materials"))

# ============ استيراد المواد من إكسل (ذكي) ============
@app.route("/materials/import", methods=["POST"])
@login_required
def import_materials():
    file = request.files.get('file')
    if not file or file.filename == '':
        flash("الرجاء اختيار ملف إكسل أولاً", "danger")
        return redirect(url_for("materials"))
        
    try:
        df = pd.read_excel(file)
        
        name_col = None
        unit_col = None
        code_col = None
        
        for col in df.columns:
            col_str = str(col).strip()
            if 'اسم' in col_str or 'مادة' in col_str or 'Material' in col_str:
                name_col = col
            if 'وحدة' in col_str or 'Unit' in col_str:
                unit_col = col
            if 'رمز' in col_str or 'Code' in col_str:
                code_col = col
                
        if not name_col:
            name_col = df.columns[0]
        if not unit_col and len(df.columns) > 1:
            unit_col = df.columns[1]
            
        conn = get_connection()
        cursor = conn.cursor()
        
        count = 0
        for index, row in df.iterrows():
            name = row[name_col]
            unit = row[unit_col] if unit_col else ''
            code = str(row[code_col]).strip() if code_col and pd.notna(row[code_col]) else ''
            
            if pd.notna(name) and str(name).strip() != '':
                cursor.execute("INSERT INTO materials (name, unit, material_type, material_code) VALUES (?, ?, 'مستهلكة', ?)", (str(name).strip(), str(unit).strip() if pd.notna(unit) else '', code))
                count += 1
                
        conn.commit()
        conn.close()
        flash(f"تم استيراد {count} مادة بنجاح من ملف الإكسل", "success")
    except Exception as e:
        flash(f"حدث خطأ أثناء قراءة الملف: {str(e)}", "danger")
        
    return redirect(url_for("materials"))

# ============ استيراد الواردات من إكسل ============
@app.route("/materials/import_receipts", methods=["POST"])
@login_required
def import_receipts():
    file = request.files.get('file')
    if not file or file.filename == '':
        flash("الرجاء اختيار ملف إكسل أولاً", "danger")
        return redirect(url_for("materials"))
        
    try:
        df = pd.read_excel(file)
        
        name_col = None
        qty_col = None
        unit_col = None
        code_col = None
        
        for col in df.columns:
            col_str = str(col).strip()
            if 'اسم' in col_str or 'مادة' in col_str or 'Material' in col_str:
                name_col = col
            elif 'كمية' in col_str or 'Quantity' in col_str or 'اجمالي' in col_str or 'إجمالي' in col_str:
                qty_col = col
            elif 'وحدة' in col_str or 'Unit' in col_str or 'واحدة' in col_str:
                unit_col = col
            elif 'رمز' in col_str or 'Code' in col_str:
                code_col = col
                
        if not name_col or not qty_col:
            flash("تأكد من أن ملف الإكسل يحتوي على أعمدة: 'المادة' و 'الاجمالي'", "danger")
            return redirect(url_for("materials"))
            
        conn = get_connection()
        cursor = conn.cursor()
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
                cursor.execute("SELECT id FROM materials WHERE name = ?", (name,))
                mat = cursor.fetchone()
                if mat:
                    material_id = mat["id"]
                    if code:
                        cursor.execute("UPDATE materials SET material_code = ?, unit = ? WHERE id = ?", (code, unit, material_id))
                else:
                    cursor.execute("INSERT INTO materials (name, unit, material_type, material_code) VALUES (?, ?, 'مستهلكة', ?)", (name, unit, code))
                    material_id = cursor.lastrowid
                
                cursor.execute("UPDATE materials SET current_balance = current_balance + ? WHERE id = ?", (quantity, material_id))
                cursor.execute("""
                    INSERT INTO material_receipts (material_id, quantity, date, time, received_by, sender_name, vehicle_no, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (material_id, quantity, date, time, received_by, 'مستودع رئيسي', code, code))
                count += 1
                
        conn.commit()
        conn.close()
        flash(f"تم استيراد {count} مادة بنجاح وتحديث الرصيد", "success")
    except Exception as e:
        flash(f"حدث خطأ أثناء قراءة الملف: {str(e)}", "danger")
        
    return redirect(url_for("materials"))

@app.route("/materials/receive", methods=["POST"])
@login_required
def receive_material():
    material_id = request.form.get("material_id")
    quantity = float(request.form.get("quantity") or 0)
    received_by, sender_name = request.form.get("received_by"), request.form.get("sender_name")
    vehicle_no, notes = request.form.get("vehicle_no"), request.form.get("notes")
    now = datetime.now()
    date, time = now.strftime("%Y-%m-%d"), now.strftime("%H:%M")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE materials SET current_balance = current_balance + ? WHERE id = ?", (quantity, material_id))
    cursor.execute("INSERT INTO material_receipts (material_id, quantity, date, time, received_by, sender_name, vehicle_no, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (material_id, quantity, date, time, received_by, sender_name, vehicle_no, notes))
    conn.commit()
    conn.close()
    flash("تم تسجيل استلام المادة وتحديث الرصيد", "success")
    return redirect(url_for("materials"))

@app.route("/materials/issue", methods=["POST"])
@login_required
def issue_material():
    material_id, work_id = request.form.get("material_id"), request.form.get("work_id")
    quantity = float(request.form.get("quantity") or 0)
    issued_to, notes = request.form.get("issued_to"), request.form.get("notes")
    now = datetime.now()
    date, time = now.strftime("%Y-%m-%d"), now.strftime("%H:%M")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT current_balance FROM materials WHERE id=?", (material_id,))
    if cursor.fetchone()["current_balance"] < quantity:
        flash("الرصيد غير كافٍ في المستودع!", "danger")
        conn.close()
        return redirect(url_for("materials"))
    cursor.execute("UPDATE materials SET current_balance = current_balance - ? WHERE id = ?", (quantity, material_id))
    cursor.execute("INSERT INTO material_issues (material_id, work_id, quantity, date, time, issued_to, notes) VALUES (?, ?, ?, ?, ?, ?, ?)", (material_id, work_id, quantity, date, time, issued_to, notes))
    conn.commit()
    conn.close()
    flash("تم صرف المادة وخصمها من الرصيد", "success")
    return redirect(url_for("materials"))

@app.route("/tools/checkout", methods=["POST"])
@login_required
def checkout_tool():
    tool_name, worker_name = request.form.get("tool_name"), request.form.get("worker_name")
    quantity = request.form.get("quantity") or 1
    now = datetime.now()
    date, time = now.strftime("%Y-%m-%d"), now.strftime("%H:%M")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO tools_ledger (tool_name, worker_name, quantity, date_out, time_out, status) VALUES (?, ?, ?, ?, ?, 'مع العامل')", (tool_name, worker_name, quantity, date, time))
    conn.commit()
    conn.close()
    flash("تم تسليم العدة للعامل", "success")
    return redirect(url_for("materials"))

@app.route("/tools/checkin/<int:tool_id>", methods=["POST"])
@login_required
def checkin_tool(tool_id):
    now = datetime.now()
    date, time = now.strftime("%Y-%m-%d"), now.strftime("%H:%M")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE tools_ledger SET date_in=?, time_in=?, status='تم الإرجاع' WHERE id=?", (date, time, tool_id))
    conn.commit()
    conn.close()
    flash("تم استلام العدة من العامل", "success")
    return redirect(url_for("materials"))

@app.route("/materials/request", methods=["POST"])
@login_required
def request_material():
    material_name, quantity = request.form.get("material_name"), request.form.get("quantity")
    unit, requested_by = request.form.get("unit"), request.form.get("requested_by")
    notes = request.form.get("notes")
    date = datetime.now().strftime("%Y-%m-%d")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO material_requests (material_name, quantity, unit, requested_by, date, notes, status) VALUES (?, ?, ?, ?, ?, ?, ?)", (material_name, quantity, unit, requested_by, date, notes, "قيد الانتظار"))
    conn.commit()
    conn.close()
    flash("تم إرسال طلب التوريد للمستودع الرئيسي", "success")
    return redirect(url_for("materials"))

@app.route("/materials/request/approve/<int:req_id>", methods=["POST"])
@login_required
def approve_request(req_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE material_requests SET status='تم التوريد' WHERE id=?", (req_id,))
    conn.commit()
    conn.close()
    flash("تم تأكيد وصول المادة من المستودع الرئيسي", "success")
    return redirect(url_for("materials"))

@app.route("/export/receipts")
@login_required
def export_receipts():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT mr.date, mr.time, m.name as material_name, mr.quantity, mr.received_by, mr.sender_name, mr.vehicle_no, mr.notes FROM material_receipts mr JOIN materials m ON mr.material_id = m.id ORDER BY mr.date DESC")
    rows = cursor.fetchall()
    conn.close()
    data = [{"التاريخ": r["date"], "الوقت": r["time"], "المادة": r["material_name"], "الكمية": r["quantity"], "المستلم": r["received_by"], "المرسل": r["sender_name"], "السيارة": r["vehicle_no"], "ملاحظات": r["notes"]} for r in rows]
    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='الواردات')
    output.seek(0)
    return send_file(output, download_name="سجل_الواردات.xlsx", as_attachment=True)

@app.route("/export/issues")
@login_required
def export_issues():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT mi.date, mi.time, m.name as material_name, mi.quantity, w.name as work_name, mi.issued_to, mi.notes FROM material_issues mi JOIN materials m ON mi.material_id = m.id LEFT JOIN works w ON mi.work_id = w.id ORDER BY mi.date DESC")
    rows = cursor.fetchall()
    conn.close()
    data = [{"التاريخ": r["date"], "الوقت": r["time"], "المادة": r["material_name"], "الكمية": r["quantity"], "العمل": r["work_name"], "المستلم": r["issued_to"], "ملاحظات": r["notes"]} for r in rows]
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
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT dl.*, w.name as work_name FROM daily_log dl LEFT JOIN works w ON dl.work_id = w.id ORDER BY dl.date DESC")
    logs = cursor.fetchall()
    cursor.execute("SELECT * FROM works ORDER BY name")
    works_list = cursor.fetchall()
    conn.close()
    return render_template("daily_log.html", logs=logs, works=works_list)

@app.route("/daily_log/add", methods=["POST"])
@login_required
def add_daily_log():
    date, work_id = request.form.get("date"), request.form.get("work_id")
    workers_count = request.form.get("workers_count") or 0
    notes = request.form.get("notes")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO daily_log (date, work_id, workers_count, notes) VALUES (?, ?, ?, ?)", (date, work_id, workers_count, notes))
    conn.commit()
    conn.close()
    flash("تم تسجيل اليومية", "success")
    return redirect(url_for("daily_log"))

@app.route("/export/daily_log")
@login_required
def export_daily_log():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT dl.date, w.name as work_name, dl.workers_count, dl.notes FROM daily_log dl LEFT JOIN works w ON dl.work_id = w.id ORDER BY dl.date DESC")
    rows = cursor.fetchall()
    conn.close()
    data = [{"التاريخ": r["date"], "العمل": r["work_name"], "عدد العمال": r["workers_count"], "ملاحظات": r["notes"]} for r in rows]
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
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM works ORDER BY start_date")
    works_list = cursor.fetchall()
    conn.close()
    return render_template("schedule.html", works=works_list)

@app.route("/export/schedule")
@login_required
def export_schedule():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, phase, responsible, start_date, end_date, duration, progress, status FROM works ORDER BY start_date")
    rows = cursor.fetchall()
    conn.close()
    data = [{"اسم العمل": r["name"], "المرحلة": r["phase"], "المسؤول": r["responsible"], "تاريخ البداية": r["start_date"], "تاريخ النهاية": r["end_date"], "المدة (يوم)": r["duration"], "نسبة الإنجاز %": r["progress"], "الحالة": r["status"]} for r in rows]
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
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT status, COUNT(*) as count FROM works GROUP BY status")
    status_counts = cursor.fetchall()
    cursor.execute("SELECT phase, COUNT(*) as count FROM works GROUP BY phase")
    phase_counts = cursor.fetchall()
    cursor.execute("SELECT * FROM works WHERE progress < 100 ORDER BY progress DESC")
    pending_works = cursor.fetchall()
    conn.close()
    return render_template("reports.html", status_counts=status_counts, phase_counts=phase_counts, pending_works=pending_works)

@app.route("/export/reports")
@login_required
def export_reports():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM works ORDER BY id")
    rows = cursor.fetchall()
    conn.close()
    data = [{"اسم العمل": r["name"], "المرحلة": r["phase"], "المسؤول": r["responsible"], "تاريخ البداية": r["start_date"], "تاريخ النهاية": r["end_date"], "المدة (يوم)": r["duration"], "الحالة": r["status"], "نسبة الإنجاز %": r["progress"]} for r in rows]
    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='تقرير المشروع')
    output.seek(0)
    return send_file(output, download_name="تقرير_المشروع.xlsx", as_attachment=True)

# ============ تشغيل ============
if __name__ == "__main__":
    init_db()
    app.run(host='0.0.0.0', port=5000)
