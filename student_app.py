import gradio as gr
import sqlite3

DB = "homework.db"

def _conn():
    return sqlite3.connect(DB)

def _ensure_tables():
    db = _conn()
    c = db.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id text primary key, name text, password text, role text, class_id text)''')
    c.execute('''CREATE TABLE IF NOT EXISTS classes
                 (id text primary key, name text, teacher_id text)''')
    c.execute('''CREATE TABLE IF NOT EXISTS assignments
                 (id text primary key, class_id text, teacher_id text, title text, status text)''')
    c.execute('''CREATE TABLE IF NOT EXISTS questions
                 (id text primary key, assignment_id text, type text, content text, correct text, score integer)''')
    c.execute('''CREATE TABLE IF NOT EXISTS submissions
                 (id text primary key, assignment_id text, student_id text, answers text,
                  ai_grades text, avg_confidence real, status text, teacher_comment text)''')
    db.commit()
    db.close()

def get_student(name, pwd):
    db = _conn()
    row = db.execute("select * from users where role='student' and name=? and password=?", (name,pwd)).fetchone()
    db.close()
    if row:
        return {'id':row[0],'name':row[1],'class_id':row[4]}
    return None

def get_assigns_for_stu(class_id):
    db = _conn()
    rows = db.execute("select * from assignments where class_id=?", (class_id,)).fetchall()
    db.close()
    return [{'id':r[0],'title':r[3]} for r in rows]

def get_assign_detail(aid):
    db = _conn()
    row = db.execute("select * from assignments where id=?", (aid,)).fetchone()
    if not row:
        db.close(); return None
    qrows = db.execute("select * from questions where assignment_id=?", (aid,)).fetchall()
    db.close()
    qlist = [{'id':q[0],'type':q[2],'content':q[3],'correct':q[4],'score':q[5]} for q in qrows]
    return {'id':row[0], 'title':row[3], 'questions':qlist}

def get_latest_sub(assign_id, student_id):
    db = _conn()
    row = db.execute("select * from submissions where assignment_id=? and student_id=? order by id desc limit 1",
                     (assign_id, student_id)).fetchone()
    db.close()
    if row:
        return {
            'id':row[0], 'answers':row[3].split('||') if row[3] else [],
            'ai_grades':eval(row[4]) if row[4] else [],
            'avg_confidence':row[5], 'status':row[6], 'teacher_comment':row[7]
        }
    return None

def save_sub(sub):
    db = _conn()
    c = db.cursor()
    c.execute("insert into submissions values (?,?,?,?,?,?,?,?)",
              (sub['id'], sub['assignment_id'], sub['student_id'],
               '||'.join(sub['answers']), str(sub['ai_grades']),
               sub['avg_confidence'], sub['status'], sub.get('teacher_comment','')))
    db.commit()
    db.close()

def ai_score(ans, correct):
    s = ans.strip().replace(' ','')
    c = correct.strip().replace(' ','')
    if not s: return 0,0,False
    if s==c: return 10,95,True
    if c in s or s in c:
        r = len(c)/max(len(s),len(c))
        if r>0.6: return 8,85,True
        return 3,60,False
    return 0,20,False

def next_sub_id():
    db = _conn()
    rows = db.execute("select id from submissions where id like 'sub%'").fetchall()
    db.close()
    nums = [int(r[0][3:]) for r in rows if r[0][3:].isdigit()]
    return f"sub{max(nums)+1}" if nums else "sub1"

def get_assign_id(title):
    db = _conn()
    row = db.execute("select id from assignments where title=?", (title,)).fetchone()
    db.close()
    return row[0] if row else None

def build_student_ui():
    with gr.Blocks(title="学生端-作业与批改") as demo:
        cur_stu = gr.State(None)
        with gr.Group(visible=True) as login_block:
            gr.Markdown("## 学生登录")
            s_name = gr.Textbox(label="姓名")
            s_pwd = gr.Textbox(label="密码", type="password")
            login_btn = gr.Button("登录")
            login_msg = gr.Textbox(interactive=False)

        with gr.Column(visible=False) as main_block:
            gr.Markdown("## 我的学习空间")
            with gr.Tabs():
                with gr.Tab("我的作业"):
                    assign_dd = gr.Dropdown(label="选作业")
                    view_btn = gr.Button("加载")
                    status_text = gr.Textbox(label="状态", interactive=False)

                    q_mds = [gr.Markdown(visible=False) for _ in range(5)]
                    ans_inps = [gr.Textbox(label=f"第{i+1}题答案", visible=False) for i in range(5)]
                    submit_btn = gr.Button("提交答案", visible=False)
                    ai_result = gr.Textbox(label="AI批改结果", lines=5, interactive=False)
                    wrong_md = gr.Markdown("## 错题详情\n- 错因：暂无\n- 解析：暂无", visible=False)

                    with gr.Column(visible=False) as review_col:
                        gr.Markdown("## 温习订正")
                        rev_inps = [gr.Textbox(label=f"第{i+1}题订正", visible=False) for i in range(5)]
                        re_sub_btn = gr.Button("提交订正", visible=False)
                        re_result = gr.Textbox(interactive=False)

            # 登录
            def do_login(name,pwd):
                stu = get_student(name,pwd)
                if not stu:
                    return None,"姓名或密码错误",gr.update(visible=True),gr.update(visible=False),gr.update()
                assigns = get_assigns_for_stu(stu['class_id'])
                choices = [a['title'] for a in assigns]
                return stu, f"欢迎 {stu['name']}", gr.update(visible=False), gr.update(visible=True), gr.update(choices=choices, value=choices[0] if choices else None)
            login_btn.click(fn=do_login, inputs=[s_name,s_pwd], outputs=[cur_stu,login_msg,login_block,main_block,assign_dd])

            def load_homework(stu, title):
                if not stu or not title:
                    return ["请先登录或选作业"] + [gr.update(visible=False)]*12 + [gr.update(visible=False)] + [gr.update(visible=False)]*5 + [gr.update(visible=False),gr.update(visible=False)]
                aid = get_assign_id(title)
                if not aid:
                    return ["作业不存在"] + [gr.update(visible=False)]*12 + [gr.update(visible=False)] + [gr.update(visible=False)]*5 + [gr.update(visible=False),gr.update(visible=False)]
                a = get_assign_detail(aid)
                sub = get_latest_sub(aid, stu['id'])
                status = sub['status'] if sub else "未提交"
                out = [f"作业：{title} | 状态：{status}"]

                # 题目展示
                for i in range(5):
                    if i < len(a['questions']):
                        out.append(gr.update(value=f"**第{i+1}题**：{a['questions'][i]['content']}", visible=True))
                    else:
                        out.append(gr.update(visible=False))
                # 答案框
                for i in range(5):
                    if i < len(a['questions']):
                        if sub and i < len(sub['answers']):
                            out.append(gr.update(value=sub['answers'][i], visible=True, interactive=(status!='published')))
                        else:
                            out.append(gr.update(value="", visible=True, interactive=(status!='published')))
                    else:
                        out.append(gr.update(visible=False))

                # 提交按钮
                out.append(gr.update(visible=(status=="未提交")))

                # AI结果
                ai_txt = ""
                if sub and sub['ai_grades']:
                    lines=[]
                    for i,g in enumerate(sub['ai_grades']):
                        q = a['questions'][i]
                        lines.append(f"第{i+1}题：{'✓' if g['is_correct'] else '✗'} 得分{g['score']}/{q['score']} 可信度{g['confidence']}%")
                    ai_txt = "\n".join(lines)
                out.append(gr.update(value=ai_txt, visible=True))

                # 错题详情
                show_wrong = sub and any(not g['is_correct'] for g in sub['ai_grades']) if sub else False
                out.append(gr.update(visible=show_wrong))

                # 订正区域
                show_review = (status == 'published')
                out.append(gr.update(visible=show_review))
                for i in range(5):
                    out.append(gr.update(visible=show_review, value=""))
                out.append(gr.update(visible=show_review))
                out.append(gr.update(visible=show_review, value=""))
                return out

            view_btn.click(fn=load_homework, inputs=[cur_stu,assign_dd],
                           outputs=[status_text]+q_mds+ans_inps+[submit_btn,ai_result,wrong_md,review_col]+rev_inps+[re_sub_btn,re_result])

            def do_submit(stu, title, *answers):
                if not stu or not title: return ""
                aid = get_assign_id(title)
                a = get_assign_detail(aid)
                if not a: return "作业不存在"
                ans_list = list(answers)[:len(a['questions'])]
                grades = []
                for i,q in enumerate(a['questions']):
                    sc,cf,ok = ai_score(ans_list[i] if i<len(ans_list) else '', q['correct'])
                    grades.append({'score':sc,'confidence':cf,'is_correct':ok})
                avg_cf = sum(g['confidence'] for g in grades)/len(grades) if grades else 0
                sub = {
                    'id':next_sub_id(),
                    'assignment_id':aid,
                    'student_id':stu['id'],
                    'answers':ans_list,
                    'ai_grades':grades,
                    'avg_confidence':avg_cf,
                    'status':'ai_reviewed',
                    'teacher_comment':''
                }
                save_sub(sub)
                lines=[]
                for i,g in enumerate(grades):
                    q = a['questions'][i]
                    lines.append(f"第{i+1}题：{'✓' if g['is_correct'] else '✗'} 得分{g['score']}/{q['score']} 可信度{g['confidence']}%")
                return '\n'.join(lines) + "\n已提交，等老师复核。"
            submit_btn.click(fn=do_submit, inputs=[cur_stu,assign_dd]+ans_inps, outputs=ai_result)

            def do_re_submit(stu, title, *answers):
                aid = get_assign_id(title)
                a = get_assign_detail(aid)
                ans_list = list(answers)[:len(a['questions'])]
                grades = []
                for i,q in enumerate(a['questions']):
                    sc,cf,ok = ai_score(ans_list[i], q['correct'])
                    grades.append({'score':sc,'confidence':cf,'is_correct':ok})
                sub = {
                    'id':next_sub_id(),
                    'assignment_id':aid,
                    'student_id':stu['id'],
                    'answers':ans_list,
                    'ai_grades':grades,
                    'avg_confidence':sum(g['confidence'] for g in grades)/len(grades) if grades else 0,
                    'status':'ai_reviewed',
                    'teacher_comment':''
                }
                save_sub(sub)
                lines=[]
                for i,g in enumerate(grades):
                    lines.append(f"第{i+1}题：{'✓' if g['is_correct'] else '✗'} 得分{g['score']}/{a['questions'][i]['score']}")
                return '\n'.join(lines) + "\n订正已交。"
            re_sub_btn.click(fn=do_re_submit, inputs=[cur_stu,assign_dd]+rev_inps, outputs=re_result)

    return demo

if __name__ == "__main__":
    _ensure_tables()
    build_student_ui().launch(server_port=7861)