import asyncio
from quart import Quart, render_template, request, session, redirect, url_for, jsonify, Response
import aiomysql
import os
import json
from redis import Redis
from rq import Queue
from judge import judge_code

app = Quart(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "hoangvudangghetxautinh")
queue = Queue(connection=Redis())

DB_CONFIG = {
    "host": "172.23.160.1",
    "port": 3306,
    "user": "root",
    "password": "10012008",
    "db": "vudz",
    "autocommit": True
}

# ======================= DB INIT ========================
async def init_db():
    async with aiomysql.connect(**DB_CONFIG) as conn:
        async with conn.cursor() as cur:
            await cur.execute('''
                CREATE TABLE IF NOT EXISTS account ( 
                    username VARCHAR(255) UNIQUE PRIMARY KEY,
                    password TEXT,
                    avatar LONGBLOB,
                    full_name TEXT,
                    email TEXT,
                    phone TEXT,
                    interest TEXT,
                    address TEXT,
                    date TEXT,
                    target TEXT,
                    role TEXT
                );
            ''')
            await cur.execute('''
                CREATE TABLE IF NOT EXISTS meta (
                    code_exercise TEXT,
                    exercise TEXT,
                    testcase TEXT,
                    topic TEXT        
                );
            ''')

            await cur.execute('''
                CREATE TABLE IF NOT EXISTS post (
                    username VARCHAR(225),
                    content TEXT,
                    thoigian DATE,
                    FOREIGN KEY ( username ) REFERENCES account(username) ON DELETE CASCADE
                );
            ''')

            await cur.execute('''
                INSERT IGNORE INTO account (
                    username, password, full_name, email, phone,
                    interest, address, date, target, role
                ) VALUES (
                    'lehoangvuqa', '0905201010012008', 'Quản trị viên', 'admin@gmail.com', '0000000000',
                    'Công nghệ', 'Hà Nội', '2025-06-17', 'Quản lý hệ thống', 'admin'
                );
            ''')

            await cur.execute('''
                CREATE TABLE IF NOT EXISTS solved_exercise( 
                    username VARCHAR(225),
                    content TEXT,
                    code_exercise VARCHAR(100),
                    type TEXT,
                    PRIMARY KEY ( username , code_exercise ),
                    FOREIGN KEY ( username ) REFERENCES account(username) ON DELETE CASCADE 
                );
            ''')

            await cur.execute('''
                CREATE TABLE IF NOT EXISTS solved_exercise_pass( 
                    username VARCHAR(225) UNIQUE,
                    code_exercise TEXT,
                    FOREIGN KEY ( username ) REFERENCES account(username) ON DELETE CASCADE 
                );
            ''')

# ======================== DB UTILS =========================
async def execute(query, args=None, fetch=False, one=False):
    try:
        async with aiomysql.connect(**DB_CONFIG) as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, args or ())
                if fetch:
                    result = await cur.fetchall()
                    if not result:
                        return None
                    return result[0] if one else result
                else:
                    await conn.commit()
    except Exception as e:
        print(f"[DB ERROR] {e}")
        return None

# ========================== LOGIC ============================
async def create_account(username, password, avatar, full_name, email, phone):
    try:
        await execute("""
            INSERT INTO account 
            (username, password, avatar, full_name, email, phone,role) 
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (username, password, avatar, full_name, email, phone,"member"))
    except Exception as e:
        print("❌ Tài khoản đã tồn tại", e)

def get_profile_html(is_logged_in):
    if not is_logged_in:
        return '<div id="nav-profile"><a href="/login">Đăng nhập</a></div>'
    return '<div id="nav-profile"><a href="/profile">Tài khoản</a></div>'

async def push_exercise(exercise, testcase, code_exercise , topic ):
    await execute("""
        INSERT INTO meta (code_exercise, exercise, testcase , topic)
        VALUES (%s, %s, %s, %s )
    """, (code_exercise, exercise, testcase , topic ))

async def get_exercise(code):
    return await execute("SELECT * FROM meta WHERE code_exercise=%s", (code,), fetch=True)

# ============================ ROUTES ==============================
@app.route('/')
async def home():
    # Lấy danh sách bài tập từ bảng meta
    # session.clear()

    cnt_exercise = await execute ("""
        SELECT topic, COUNT(*) AS tan_so
        FROM meta
        GROUP BY topic
        ORDER BY tan_so DESC;
    """, fetch=True )

    topic_counts = {}

    for item in cnt_exercise :
        topic_counts[ item[0] ] = item [ 1 ]
    
    post=''
    postList = await execute("SELECT * FROM post" , fetch=True )

    if postList : 
        for row in reversed(postList) :
            ct = f'''
                <div class="vudzso1-post">
                    <div class="vudzso1-post-header">
                    <img src="/avatar/{row[0]}" alt="avatar">
                    <div class="vudzso1-info">
                        <div class="vudzso1-name"> { await get_fullname(row[0])} </div>
                        <div class="vudzso1-time">{ row[2] } </div>
                    </div>
                    </div>
                    <div class="vudzso1-post-content">
                       { row[1] }
                    </div>
                </div>
            '''
            post += ct 

    # Lấy thông tin cá nhân
    if "username" not in session:
        profile_html =  await render_template("profile_empty.html")
    else : 
        
        row = await execute("""
            SELECT full_name, email, interest, address, date, target 
            FROM account WHERE username=%s
        """, (session["username"],), fetch=True, one=True)
        profile_html = await render_template("profile_full.html",
                    full_name=row[0], email=row[1], interest=row[2],
                    address=row[3], date=row[4], target=row[5],
                    list_problem_submit= await get_problem_list_html( session["username"] )
                )

    return await render_template("home.html",
        username=session.get("username"),
        profile=profile_html,
        postList=post,
        role = await get_role(session["username"]) if session else "",
        topic_counts=topic_counts
    )


@app.route('/register')
async def register_page():
    return await render_template("register.html")

@app.route("/submit", methods=["POST"])
async def login_and_register():
    action = (await request.form).get("action")
    return await login() if action == "login" else await register() if action == "register" else redirect(url_for('home'))

@app.route('/login')
async def login_page():
    return await render_template("login.html", error=None, username="", password="", command="login")

@app.route('/logout')
async def logout():
    session.clear()
    return redirect(url_for("home"))

@app.route("/avatar")
async def get_avatar():
    if "username" not in session:
        return "Không có tài khoản", 404
    row = await execute("SELECT avatar FROM account WHERE username=%s", (session["username"],), fetch=True, one=True)
    if row and row[0]:
        return Response(row[0], mimetype="image/jpeg")
    return "Không có ảnh", 404

@app.route('/avatar/<username>')
async def get_avatars( username ) : 
    row = await execute("SELECT avatar FROM account WHERE username=%s" , ( username,) , fetch=True , one=True ) 
    if row and row[0] : 
        return Response(row[0] , mimetype="image/jpeg")
    return "không có ảnh",404


@app.route("/edit_profile", methods=["GET", "POST"])
async def edit_profile():
    if "username" not in session:
        return redirect(url_for("login_page"))

    if request.method == "POST":
        form = await request.form
        avatar = (await request.files).get("avatar")
        args = [form.get("full_name", ""), form.get("email", ""), form.get("phone", ""),
                form.get("interest", ""), form.get("address", ""), form.get("date", "00/00/0000"),
                form.get("target", "")]

        if avatar and avatar.filename:
            await execute("""
                UPDATE account SET
                    full_name=%s, email=%s, phone=%s, interest=%s,
                    address=%s, date=%s, target=%s, avatar=%s
                WHERE username=%s
            """, (*args, avatar.read(), session["username"]))
        else:
            await execute("""
                UPDATE account SET
                    full_name=%s, email=%s, phone=%s, interest=%s,
                    address=%s, date=%s, target=%s
                WHERE username=%s
            """, (*args, session["username"]))

        return redirect(url_for("home"))

    row = await execute("""
        SELECT full_name, email, phone, interest, address, date, target 
        FROM account WHERE username=%s
    """, (session["username"],), fetch=True, one=True)
    if row:
        return await render_template("edit_profile.html",
            full_name=row[0], email=row[1], phone=row[2],
            interest=row[3], address=row[4], date=row[5], target=row[6])
    return "Không tìm thấy tài khoản", 404

@app.route('/create-exercise')
async def create_exercise():
    return await render_template("create_exercise.html",command="create",id="")


@app.route('/render_exercise/<id>')
async def render_exercise(id):
    return await render_template("render_exercise.html", id=id)

@app.route('/api/render_exercise', methods=['POST'])
async def get_info_exercise():
    data = await request.get_json()
    row = await execute("SELECT exercise,topic FROM meta WHERE code_exercise=%s", (data.get("id"),), fetch=True, one=True)
    exercise = json.loads(row[0])
    exercise["topic"] = row[1]
    return jsonify( exercise )

@app.route('/api/post_exercise', methods=['POST'])
async def handle_submission():
    data = await request.get_json()
    code_exercise = data.get("new_id", "")
    exercise = {
        "titles": data.get("titles", []),
        "bodies": data.get("bodies", []),
        "examples": data.get("examples", []),
        "time_limit": data.get("timeLimit", ""),
        "point": data.get("point", ""),
        "author": session["username"]
    }
    testcase = {
        "time_limit": data.get("timeLimit", ""),
        "point": data.get("point", ""),
        "tests": data.get("tests", {})
    }
    await push_exercise(
        json.dumps(exercise, ensure_ascii=False),
        json.dumps(testcase, ensure_ascii=False),
        code_exercise,
        data.get("topic","")
    )
    return jsonify({"message": "Đã nhận bài tập!"})

@app.route('/api/post' , methods=['POST'])
async def post() : 
    data = await request.get_json()
    content = data.get("content","") 
    time = data.get("time_post","0000-00-00")
    await execute("INSERT INTO post ( username , content , thoigian ) VALUES ( %s , %s , %s )" , ( session["username"] , content , time ) )
    return jsonify({"message" : "đăng bài thành công"})

@app.route('/submit-exercise/<id>')
async def go_submit_exercise( id ):
    if not session :
        return redirect ( url_for ("login_page") )
    return await render_template ( "submit.html" , code_exercise=id , command="setting" )

@app.route('/api/submit_exercise',methods=["POST"])
async def submit_exercise() :
    data = await request.get_json()
    # print(json.dumps(data, indent=4, ensure_ascii=False))
    row = await execute ( "SELECT testcase,topic FROM meta WHERE code_exercise=%s", data.get("code_exercise","") , one=True , fetch=True )
    if row and row[0] and row[1] :
        data [ "topic" ] = row[1]
        data ["username"] = session.get("username","")
        job = queue.enqueue( judge_code , data , json.loads(row[0]) )
        # print ( json.dumps( json.loads(row[0]), indent=4 , ensure_ascii=False ) )
        return jsonify({"message": "nhận thành công", "job_id": job.get_id()})
    else : 
        return jsonify ( { "message" : "không có bài"})

@app.route("/result/<job_id>")
async def result(job_id):
    from rq.job import Job
    job = Job.fetch(job_id, connection=Redis())
    if job.is_finished:
        for item in json.loads(job.result) : 
            if "username" in item :
                await execute ("""
                        INSERT IGNORE INTO solved_exercise ( username , content , code_exercise , type )
                        VALUES ( %s , %s , %s , %s )
                    """, ( item["username"] , json.dumps(item["content"],ensure_ascii=False) , item["code_exercise"] , ( "O" if item["pass"] else "X" ) ) )
                if item["pass"] : 
                    await execute ("""
                        INSERT IGNORE INTO solved_exercise_pass ( username , code_exercise )
                        VALUES ( %s , %s )
                    """, ( item["username"] , item["code_exercise" ] ) )
                    await execute ("""
                        UPDATE solved_exercise SET `type`="O" WHERE code_exercise=%s ;
                    """ , ( item["code_exercise"], ) )
        
        return jsonify({"status": "done", "result": job.result})
    elif job.is_failed:
        return jsonify({"status": "failed"})
    else:
        return jsonify({"status": "waiting"})
    
@app.route("/topic/<topic_name>")
async def topic_detail(topic_name):
    List_exercise = await execute("SELECT * FROM meta WHERE topic=%s", (topic_name,) , fetch=True)
    html = ''
    if session :
        username_role = await get_role(session.get("username", "")) or "member"
        user = session.get("username", "")
    else :
        username_role = "member"
        user = ""
    
    if List_exercise:
        for i in List_exercise:
            try:
                if not i[1]:
                    raise ValueError("Nội dung JSON rỗng")

                data = json.loads(i[1])
                html += f"""
                    <tr id="exercise-{i[0]}">
                        <td>{data.get("titles", "")}</td>
                        <td>{i[0]}</td>
                        <td>{i[3]}</td>
                        <td>
                            <button class="vudzso3-button" onclick="window.location.href='/render_exercise/{i[0]}'">Xem</button>
                            {
                                f'''<button class="vudzso2-btn vudzso2-btn-save" onclick="editExercise('{i[0]}')">Sửa</button>'''
                                if  username_role == "admin" or (
                                    username_role == "teacher"and user == data.get("author","") 
                                ) else ""
                            }
                            {
                                f'''<button class='vudzso2-btn vudzso2-btn-delete' onclick="deleteExercise('{i[0]}')">🗑 Xóa</button>'''
                                if  username_role == "admin" or (
                                    username_role == "teacher"and user == data.get("author","") 
                                ) else ""
                            }
                        </td>
                    </tr>
                """
            except Exception as e:
                html += f"<tr><td colspan='4'>Lỗi khi xử lý bài: {str(e)}</td></tr>"
        return html
    return "Không tìm thấy bài nào."

@app.route('/get_member')
async def get_member() : 
    list_member = await execute("SELECT * FROM account" , fetch=True )
    html = ''
    username = session.get("username")
    if not username:
        username_role = "member"
    else:
        username_role = await get_role(username) or "member"

    for item in list_member :
        member_role = item[10] or "member" ; 
        html += f"""
        <tr>
            <td>{item[0]}</td>
            <td>{item[3]}</td>
            <td>{item[5]}</td>
            <td>
                <select class="vudzso2-select-role" {"disabled" if username_role == "member" else ""} id="{item[0]}">
                    <option value='admin'
                        {"selected" if member_role == "admin" else ""}
                        {"disabled" if username_role != "admin" else ""}
                    >Quản trị</option>
                    
                    <option value='teacher'
                        {"selected" if member_role == "teacher" else ""}
                        {"disabled" if username_role not in ["admin", "teacher"] else ""}
                    >Giáo viên</option>
                    
                    <option value='member'
                        {"selected" if member_role == "member" else ""}
                        {"disabled" if username_role == "member" else ""}
                    >Học sinh</option>
                </select>
            </td>
            <td>
                <button class="vudzso2-btn vudzso2-btn-save"
                    onclick="confirmSave('{item[0]}')"
                    {"disabled" if username_role == "member" else ""}
                >💾 Lưu</button>
                
                <button class="vudzso2-btn vudzso2-btn-delete"
                    onclick="confirmDelete('{item[0]}')"
                    {"disabled" if username_role == "member" else ""}
                >🗑 Xóa</button>
            </td>
        </tr>
        """


    # print ( username_role )
    return html

@app.route('/delete/<username>')
async def delete_user(username):
    try:
        affected = await execute("DELETE FROM account WHERE username = %s", (username,))
        if affected == 0:
            return "❌ Không tìm thấy người dùng", 404
        return "✅ Đã xoá thành công", 200
    except Exception as e:
        print("Lỗi khi xoá:", e)
        return "❌ Đã xảy ra lỗi khi xoá người dùng", 500
    
from quart import request

@app.route('/update_role_user/<username>', methods=['POST'])
async def update_role_user(username):
    from quart import request, session
    data = await request.get_json()
    new_role = data.get("role")

    # Kiểm tra người đang cập nhật
    current_user = session.get("username", "")
    current_role = await get_role(current_user) or "member"

    # Kiểm tra quyền cập nhật
    target = await execute ("SELECT role FROM account WHERE username = %s", (username,) , fetch=True , one=True )
    if not target:
        return "❌ Không tìm thấy người dùng", 404

    target_role = target[0]

    if current_role == "admin":
        pass  # admin có toàn quyền
    elif current_role == "teacher":
        if target_role == "admin" or new_role == "admin":
            return "❌ Bạn không có quyền gán hoặc chỉnh quyền admin", 403
    else:
        return "❌ Bạn không có quyền thực hiện thao tác này", 403

    try:
        affected = await execute("UPDATE account SET role = %s WHERE username = %s", (new_role, username))
        if affected == 0:
            return "❌ Không có bản ghi nào bị ảnh hưởng", 404
        return "✅ Đã cập nhật quyền thành công", 200
    except Exception as e:
        print("Lỗi cập nhật quyền:", e)
        return "❌ Đã xảy ra lỗi khi cập nhật", 500

@app.route("/delete-exercise/<code_exercise>", methods=["DELETE"])
async def delete_exercise(code_exercise):
    # print ( code_exercise )
    try:
        affected = await execute("DELETE FROM meta WHERE code_exercise = %s", (code_exercise,))
        if affected == 0:
            return "❌ Không tìm thấy bài tập", 404
        await execute("DELETE FROM solved_exercise WHERE code_exercise = %s", (code_exercise,))
        await execute("DELETE FROM solved_exercise_pass WHERE code_exercise = %s", (code_exercise,))
        return "✅ Đã xoá bài tập thành công", 200
    except Exception as e:
        print("Lỗi khi xoá bài tập:", e)
        return "❌ Đã xảy ra lỗi khi xoá bài tập", 500

@app.route("/edit-exercise/<code_exercise>")
async def edit_exercise(code_exercise):
    return await render_template("create_exercise.html", command="edit", id=code_exercise)

@app.route("/api/edit_exercise", methods=["POST"])
async def edit_exercise_api():
    data = await request.get_json()
    code_exercise = data.get("new_id", "")
    exercise = {
        "titles": data.get("titles", []),
        "bodies": data.get("bodies", []),
        "examples": data.get("examples", []),
        "time_limit": data.get("timeLimit", ""),
        "point": data.get("point", ""),
        "author": session["username"]
    }
    testcase = {
        "time_limit": data.get("timeLimit", ""),
        "point": data.get("point", ""),
        "tests": data.get("tests", {})
    }
    await execute("""
        UPDATE meta SET
            exercise=%s, testcase=%s, topic=%s
        WHERE code_exercise=%s
    """, (json.dumps(exercise, ensure_ascii=False), json.dumps(testcase, ensure_ascii=False), data.get("topic",""), code_exercise))
    return jsonify({"message": "Đã cập nhật bài tập!"})

# ======================== AUTH =============================
async def login():
    form = await request.form
    data = {"username": form.get("username"), "password": form.get("password"), "remember": form.get("remember")}
    user = await execute("SELECT * FROM account WHERE username=%s", (data["username"],), fetch=True, one=True)
    if user:
        if user[1] == data["password"]:
            session["username"] = data["username"]
            session.permanent = bool(data["remember"])
            return await render_template("login.html", **data, command="welcome")
        return await render_template("login.html", error="Sai mật khẩu", **data, command="login")
    return await render_template("login.html", error="Tài khoản chưa tồn tại", **data, command="login")

async def register():
    form = await request.form
    data = {
        "username": form.get("username"),
        "password": form.get("password"),
        "confirm_password": form.get("confirm_password"),
        "full_name": form.get("fullname", ""),
        "email": form.get("email", ""),
        "phone": form.get("phone", ""),
        "avatar": (await request.files).get("avatar")
    }
    if data["password"] != data["confirm_password"]:
        return await render_template("register.html", error="Mật khẩu không khớp!", **data)
    existing = await execute("SELECT * FROM account WHERE username=%s", (data["username"],), fetch=True)
    if existing:
        return await render_template("register.html", error="Người dùng này đã tồn tại!", **data)

    avatar_data = data["avatar"].read() if data["avatar"] else open("./access/avatar.jpg", "rb").read()
    await create_account(data["username"], data["password"], avatar_data, data["full_name"], data["email"], data["phone"])
    return await render_template("login.html", error="Tạo tài khoản thành công! Mời bạn đăng nhập", username=data["username"], password="", command="login")


async def get_fullname( username ) : 
    row = await execute ("SELECT full_name FROM account WHERE username=%s" , (username) , fetch=True , one=True )
    if row and row[0] : 
        return row[0]
    return "không có tên",404

async def get_role( username ) :
    row = await execute ("SELECT role FROM account WHERE username=%s",(username) , fetch=True , one=True ) 
    if row and row[0] : 
        return row[0]
    return None

async def get_problem_list_html( username ) : 
    problem = '' 
    problemList = await execute ("""
        SELECT meta.code_exercise AS code_exercise ,
            meta.exercise AS exercise,
            solved_exercise.username AS username,
            solved_exercise.`type` AS `type`,
            meta.topic AS topic
        FROM solved_exercise
        JOIN meta ON meta.code_exercise = solved_exercise.code_exercise ;
    """
    , fetch=True )
    if problemList :
        for item in problemList :
            if item[2] == username :
                data = json.loads(item[1])
                problem = f"""
                    <tr class="{item[4]} topic">
                        <td>{ data["titles"] }</td>
                        <td class="{ "correct" if item[3] == "O" else "not-correct"}">
                            <b >{ "đúng" if item[3]=="O" else "không đúng"}</b>
                        </td>
                        <td><button onclick="window.location.href='/render_exercise/{item[0]}'">xem</button></td>
                    </tr>
                """ + problem 
        return problem
    return "<tr><td>chưa chấm bài nào</td></tr>"



# ============================ MAIN ==============================
if __name__ == "__main__":
    async def start():
        await init_db()
        await app.run_task(debug=True, port=5000)
    asyncio.run(start())
