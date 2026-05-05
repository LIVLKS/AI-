import gradio as gr
import sqlite3
import random

DB = "homework.db"

#数据相关
def _conn():
    return sqlite3.connect(DB)

def _once_init():
    """第一次跑建表并塞默认数据，后面保证有配置就好"""
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
    c.execute('''CREATE TABLE IF NOT EXISTS config
                 (key text primary key, value text)''')
    if not c.execute("select count(*) from users").fetchone()[0]:
        c.execute("insert into users values ('t1','王老师','123','teacher',null)")
        c.execute("insert into classes values ('c1','三年级一班','t1')")
        for uid, uname in [('s1','张三'),('s2','李四'),('s3','王五')]:
            c.execute("insert into users values (?,?,?,?,?)", (uid,uname,'123','student','c1'))
        c.execute("insert into assignments values ('a1','c1','t1','第一次语文填空练习','open')")
        qs = [
            ('q1','a1','填空','床前明月光，____。','疑是地上霜',10),
            ('q2','a1','填空','春眠不觉晓，____。','处处闻啼鸟',10),
            ('q3','a1','填空','____，粒粒皆辛苦。','谁知盘中餐',10)
        ]
        for q in qs:
            c.execute("insert into questions values (?,?,?,?,?,?)", q)
    # 无论如何补充 config 默认值（用insert or ignore防止重复）
    c.execute("insert or ignore into config values ('high','90')")
    c.execute("insert or ignore into config values ('mid','70')")
    db.commit()
    db.close()

def _get_cfg():
    db = _conn()
    c = db.cursor()
    # 查不到就返回默认 90/70
    row = c.execute("select value from config where key='high'").fetchone()
    high = int(row[0]) if row else 90
    row = c.execute("select value from config where key='mid'").fetchone()
    mid = int(row[0]) if row else 70
    db.close()
    return high, mid

def _set_cfg(high, mid):
    db = _conn()
    c = db.cursor()
    c.execute("update config set value=? where key='high'", (str(high),))
    c.execute("update config set value=? where key='mid'", (str(mid),))
    db.commit()
    db.close()

#教师校验
def check_teacher(name, pwd):
    db = _conn()
    row = db.execute("select * from users where role='teacher' and name=? and password=?", (name,pwd)).fetchone()
    db.close()
    if row:
        return dict(zip(['id','name','password','role','class_id'], row))
    return None

def cls_id_by_name(cname):
    db = _conn()
    rid = db.execute("select id from classes where name=?", (cname,)).fetchone()
    db.close()
    return rid[0] if rid else None

def get_assigns_by_cls(cid):
    db = _conn()
    rows = db.execute("select * from assignments where class_id=?", (cid,)).fetchall()
    db.close()
    return [{'id':r[0],'class_id':r[1],'teacher_id':r[2],'title':r[3],'status':r[4]} for r in rows]

def get_assign_detail(aid):
    db = _conn()
    row = db.execute("select * from assignments where id=?", (aid,)).fetchone()
    if not row:
        db.close()
        return None
    qrows = db.execute("select * from questions where assignment_id=?", (aid,)).fetchall()
    db.close()
    questions = [{'id':q[0],'type':q[2],'content':q[3],'correct':q[4],'score':q[5]} for q in qrows]
    return {'id':row[0],'class_id':row[1],'teacher_id':row[2],'title':row[3],'status':row[4],'questions':questions}

def get_submissions_for_assign(aid):
    db = _conn()
    rows = db.execute("select * from submissions where assignment_id=?", (aid,)).fetchall()
    db.close()
    subs = []
    for r in rows:
        answers = r[3].split('||') if r[3] else []
        grades = eval(r[4]) if r[4] else []
        subs.append({
            'id':r[0], 'assignment_id':r[1], 'student_id':r[2],
            'answers':answers, 'ai_grades':grades, 'avg_confidence':r[5],
            'status':r[6], 'teacher_comment':r[7]
        })
    return subs

def get_sub_by_id(sub_id):
    db = _conn()
    row = db.execute("select * from submissions where id=?", (sub_id,)).fetchone()
    db.close()
    if row:
        return {
            'id':row[0], 'assignment_id':row[1], 'student_id':row[2],
            'answers':row[3].split('||') if row[3] else [],
            'ai_grades':eval(row[4]) if row[4] else [],
            'avg_confidence':row[5], 'status':row[6], 'teacher_comment':row[7]
        }
    return None

def get_stu_name(uid):
    db = _conn()
    name = db.execute("select name from users where id=?", (uid,)).fetchone()[0]
    db.close()
    return name

def upd_sub_status(sub_id, status, comment=None, new_grades=None):
    db = _conn()
    c = db.cursor()
    if new_grades:
        c.execute("update submissions set ai_grades=?, status=?, teacher_comment=? where id=?",
                  (str(new_grades), status, comment or '', sub_id))
    else:
        c.execute("update submissions set status=?, teacher_comment=? where id=?",
                  (status, comment or '', sub_id))
    db.commit()
    db.close()

def next_id(prefix):
    db = _conn()
    c = db.cursor()
    tb = {'a':'assignments','q':'questions','sub':'submissions'}.get(prefix, 'assignments')
    rows = c.execute(f"select id from {tb} where id like '{prefix}%'").fetchall()
    db.close()
    nums = [int(r[0][len(prefix):]) for r in rows if r[0][len(prefix):].isdigit()]
    return f"{prefix}{max(nums)+1}" if nums else f"{prefix}1"

#AI 批改
def ai_score(stu_ans, correct):
    s = stu_ans.strip().replace(' ','')
    c = correct.strip().replace(' ','')
    if not s:
        return 0, 0, False
    if s == c:
        return 10, 95, True
    if c in s or s in c:
        ratio = len(c)/max(len(s),len(c))
        if ratio > 0.6:
            return 8, 85, True
        return 3, 60, False
    return 0, 20, False

def gen_comment_draft(name, title, avg, total):
    if avg >=9:
        lv, dt = "非常出色", "基础很扎实"
    elif avg >=7:
        lv, dt = "良好", "部分题目还需巩固"
    elif avg >=5:
        lv, dt = "继续加油", "建议多读多写"
    else:
        lv, dt = "要加把劲了", "建议重新温习课文"
    return f"{name}同学，《{title}》表现{lv}，{dt}。"

#教师界面
def build_teacher_ui():
    with gr.Blocks(title="教师端-作业批改系统") as demo:
        cur_teacher = gr.State(None)
        cur_cid = gr.State(None)
        cur_aid = gr.State(None)

        with gr.Group(visible=True) as login_block:
            gr.Markdown("## 教师登录")
            t_name = gr.Textbox(label="姓名")
            t_pwd = gr.Textbox(label="密码", type="password")
            login_btn = gr.Button("登录")
            login_msg = gr.Textbox(interactive=False)

        with gr.Column(visible=False) as main_block:
            gr.Markdown("## 工作台")
            with gr.Tabs():
                with gr.Tab("作业工作台"):
                    cls_dd = gr.Dropdown(label="班级")
                    prog_txt = gr.Textbox(label="批改进度", lines=5, interactive=False)
                    btn_refresh_prog = gr.Button("刷新进度")
                    btn_refresh_prog.click(
                        fn=lambda t,c: update_progress(t,c),
                        inputs=[cur_teacher, cls_dd],
                        outputs=prog_txt
                    )

                # 布置作业
                with gr.Tab("布置作业"):
                    a_title = gr.Textbox(label="作业标题")
                    q_txt = gr.Textbox(label="题目(每行: 题目||答案||分值)", lines=5,
                                       value="床前明月光，____。||疑是地上霜||10\n春眠不觉晓，____。||处处闻啼鸟||10\n____，粒粒皆辛苦。||谁知盘中餐||10")
                    cls_dd2 = gr.Dropdown(label="选择班级")
                    btn_create = gr.Button("发布作业")
                    create_msg = gr.Textbox(interactive=False)
                    btn_create.click(fn=create_assign, inputs=[cur_teacher, cls_dd2, a_title, q_txt], outputs=create_msg)

                # AI批改面板
                with gr.Tab("AI批改面板"):
                    assign_dd = gr.Dropdown(label="选择作业")
                    btn_refresh = gr.Button("刷新列表及分组")
                    summary = gr.Textbox(interactive=False)
                    with gr.Tab("高可信度组"):
                        high_df = gr.Dataframe(headers=["学生","平均可信度"], interactive=False)
                        btn_adopt = gr.Button("一键采纳全部")
                        adopt_msg = gr.Textbox(interactive=False)
                    with gr.Tab("中可信度组"):
                        mid_df = gr.Dataframe(headers=["学生","平均可信度"], interactive=False)
                        btn_spot = gr.Button("随机抽查两份（模拟）")
                        spot_msg = gr.Textbox(interactive=False)
                    with gr.Tab("低可信度组"):
                        low_df = gr.Dataframe(headers=["学生","平均可信度","状态"], interactive=False)
                        review_dd = gr.Dropdown(label="待复核提交", interactive=True)
                        btn_load_review = gr.Button("加载详情")
                        review_detail = gr.Textbox(label="AI评分详情", lines=8, interactive=False)
                        cmt_input = gr.Textbox(label="教师评语(可选)")
                        s1 = gr.Number(label="第1题分数", value=0)
                        s2 = gr.Number(label="第2题分数", value=0)
                        s3 = gr.Number(label="第3题分数", value=0)
                        btn_save_review = gr.Button("保存并发布")
                        review_save_msg = gr.Textbox(interactive=False)

                    # 刷新
                    def refresh_panel(aid):
                        if not aid: return "请选作业",[],[],[], gr.update(choices=[])
                        h,m = _get_cfg()
                        subs = get_submissions_for_assign(aid)
                        high,mid,low = [],[],[]
                        low_list = []
                        for s in subs:
                            nm = get_stu_name(s['student_id'])
                            cf = round(s['avg_confidence'],1)
                            if cf >= h:
                                high.append([nm,cf])
                            elif cf >= m:
                                mid.append([nm,cf])
                            else:
                                low.append([nm,cf,s['status']])
                                if s['status'] != 'published':
                                    low_list.append(s)
                        sum_text = f"共{len(subs)}份：高{len(high)}，中{len(mid)}，低{len(low)}"
                        dd_choices = [f"{get_stu_name(s['student_id'])} (ID:{s['id']})" for s in low_list]
                        return sum_text, high or [["无"]], mid or [["无"]], low or [["无"]], gr.update(choices=dd_choices, value=dd_choices[0] if dd_choices else None)

                    btn_refresh.click(fn=refresh_panel, inputs=[cur_aid],
                                      outputs=[summary,high_df,mid_df,low_df,review_dd])
                    assign_dd.change(fn=lambda t: get_assign_id_by_name(t), inputs=assign_dd, outputs=cur_aid).then(
                        fn=refresh_panel, inputs=[cur_aid], outputs=[summary,high_df,mid_df,low_df,review_dd]
                    )
                    btn_adopt.click(fn=do_adopt, inputs=[cur_aid], outputs=[adopt_msg,high_df,summary])
                    btn_spot.click(fn=do_spot, inputs=[cur_aid], outputs=[spot_msg])
                    btn_load_review.click(fn=load_review_detail, inputs=[review_dd], outputs=[review_detail,s1,s2,s3])
                    btn_save_review.click(fn=do_save_review, inputs=[review_dd,cmt_input,s1,s2,s3], outputs=review_save_msg)

                # 评语助手
                with gr.Tab("评语助手"):
                    sub_sel = gr.Dropdown(label="学生提交", interactive=True)
                    draft_box = gr.Textbox(label="AI草稿", lines=3)
                    btn_gen = gr.Button("生成草稿")
                    btn_save_cmt = gr.Button("发布评语")
                    help_txt = gr.Textbox(interactive=False)

                    def pop_sub(aid):
                        if not aid: return gr.update(choices=[])
                        subs = get_submissions_for_assign(aid)
                        choices = [f"{get_stu_name(s['student_id'])} (ID:{s['id']})" for s in subs]
                        return gr.update(choices=choices, value=choices[0] if choices else None)
                    assign_dd.change(fn=pop_sub, inputs=[cur_aid], outputs=sub_sel)

                    def gen_draft(sub_str):
                        if not sub_str: return ""
                        sid = sub_str.split("ID:")[-1].strip(')')
                        s = get_sub_by_id(sid)
                        if not s: return ""
                        a = get_assign_detail(s['assignment_id'])
                        stu = get_stu_name(s['student_id'])
                        avg = sum(g['score'] for g in s['ai_grades'])/len(s['ai_grades']) if s['ai_grades'] else 0
                        total = sum(q['score'] for q in a['questions'])
                        return gen_comment_draft(stu, a['title'], avg, total)
                    btn_gen.click(fn=gen_draft, inputs=[sub_sel], outputs=draft_box)

                    def save_cmt(sub_str, draft):
                        if not sub_str: return "选一下提交"
                        sid = sub_str.split("ID:")[-1].strip(')')
                        upd_sub_status(sid, 'published', comment=draft)
                        return "评语已发布"
                    btn_save_cmt.click(fn=save_cmt, inputs=[sub_sel,draft_box], outputs=help_txt)

                # 配置
                with gr.Tab("配置"):
                    h_val, m_val = _get_cfg()
                    h_slider = gr.Slider(50,99,value=h_val,label="高可信下限(%)")
                    m_slider = gr.Slider(30,90,value=m_val,label="中可信下限(%)")
                    btn_cfg = gr.Button("保存")
                    cfg_msg = gr.Textbox(interactive=False)
                    btn_cfg.click(fn=lambda h,m: (_set_cfg(int(h),int(m)), f"已改:高≥{int(h)}% 中≥{int(m)}%")[1],
                                  inputs=[h_slider,m_slider], outputs=cfg_msg)

        # 登录
        def do_login(name, pwd):
            t = check_teacher(name, pwd)
            if not t:
                return None, "用户名或密码错误", gr.update(visible=True), gr.update(visible=False), gr.update(), None, "", gr.update(), gr.update()
            cls_list = [c['name'] for c in get_teacher_classes(t['id'])]
            first_cls = cls_list[0] if cls_list else None
            cid = cls_id_by_name(first_cls) if first_cls else None
            assign_list = [a['title'] for a in get_assigns_by_cls(cid)] if cid else []
            return (t, f"欢迎 {t['name']} 老师",
                    gr.update(visible=False), gr.update(visible=True),
                    gr.update(choices=cls_list, value=first_cls), cid, "",
                    gr.update(choices=assign_list, value=assign_list[0] if assign_list else None),
                    gr.update(choices=cls_list, value=first_cls))

        login_btn.click(fn=do_login, inputs=[t_name,t_pwd],
                        outputs=[cur_teacher,login_msg,login_block,main_block,cls_dd,cur_cid,prog_txt,assign_dd,cls_dd2])

        def on_cls_change(teacher, cname):
            if not cname: return None, "", gr.update(choices=[]), gr.update(choices=[])
            cid = cls_id_by_name(cname)
            assigns = [a['title'] for a in get_assigns_by_cls(cid)] if cid else []
            prog = update_progress(teacher, cname)
            return cid, prog, gr.update(choices=assigns, value=assigns[0] if assigns else None), gr.update(choices=assigns, value=assigns[0] if assigns else None)

        cls_dd.change(fn=on_cls_change, inputs=[cur_teacher,cls_dd], outputs=[cur_cid,prog_txt,assign_dd,cls_dd2])

    return demo

def get_teacher_classes(tid):
    db = _conn()
    rows = db.execute("select * from classes where teacher_id=?", (tid,)).fetchall()
    db.close()
    return [{'id':r[0],'name':r[1],'teacher_id':r[2]} for r in rows]

def update_progress(teacher, cname):
    if not teacher or not cname: return "先选班级"
    cid = cls_id_by_name(cname)
    if not cid: return "班级不存在"
    assigns = get_assigns_by_cls(cid)
    lines = []
    for a in assigns:
        subs = get_submissions_for_assign(a['id'])
        ai = sum(1 for s in subs if s['status'] == 'ai_reviewed')
        wait = sum(1 for s in subs if s['status'] == 'pending_review')
        pub = sum(1 for s in subs if s['status'] == 'published')
        lines.append(f"{a['title']}：AI已批{ai}，待复核{wait}，已发布{pub}")
    return '\n'.join(lines) if lines else "暂无作业"

def create_assign(teacher, cname, title, qtext):
    if not teacher: return "请登录"
    cid = cls_id_by_name(cname)
    if not cid: return "班级不存在"
    qs = []
    for line in qtext.strip().split('\n'):
        parts = line.split('||')
        if len(parts)==3:
            qs.append({'id':next_id('q'), 'type':'填空', 'content':parts[0].strip(), 'correct':parts[1].strip(), 'score':int(parts[2].strip())})
    if not qs: return "格式错误"
    aid = next_id('a')
    db = _conn()
    c = db.cursor()
    c.execute("insert into assignments values (?,?,?,?,?)", (aid,cid,teacher['id'],title,'open'))
    for q in qs:
        c.execute("insert into questions values (?,?,?,?,?,?)", (q['id'],aid,q['type'],q['content'],q['correct'],q['score']))
    db.commit()
    db.close()
    return f"作业《{title}》发布成功"

def get_assign_id_by_name(title):
    db = _conn()
    row = db.execute("select id from assignments where title=?", (title,)).fetchone()
    db.close()
    return row[0] if row else None

def do_adopt(aid):
    if not aid: return "选作业",[],""
    h,_ = _get_cfg()
    subs = get_submissions_for_assign(aid)
    cnt=0
    for s in subs:
        if s['avg_confidence']>=h and s['status']!='published':
            upd_sub_status(s['id'],'published')
            cnt+=1
    high_after = [[get_stu_name(s['student_id']), round(s['avg_confidence'],1)] for s in get_submissions_for_assign(aid) if s['avg_confidence']>=h]
    return f"已一键发布{cnt}份", high_after or [["无"]], ""

def do_spot(aid):
    if not aid: return "先选作业"
    h,m = _get_cfg()
    mids = [s for s in get_submissions_for_assign(aid) if m <= s['avg_confidence'] < h]
    if not mids: return "中可信组无提交"
    sample = random.sample(mids, min(2,len(mids)))
    names = [get_stu_name(s['student_id']) for s in sample]
    return f"已抽取{', '.join(names)}复查（模拟）"

def load_review_detail(opt):
    if not opt: return "",0,0,0
    sid = opt.split("ID:")[-1].strip(')')
    s = get_sub_by_id(sid)
    if not s: return "",0,0,0
    a = get_assign_detail(s['assignment_id'])
    lines=[]
    gs = s['ai_grades']
    for i,q in enumerate(a['questions']):
        ans = s['answers'][i] if i<len(s['answers']) else '没答'
        sc = gs[i]['score'] if i<len(gs) else 0
        lines.append(f"第{i+1}题：{q['content']}  学生答：{ans}  AI分：{sc}")
    return '\n'.join(lines), gs[0]['score'] if len(gs)>0 else 0, gs[1]['score'] if len(gs)>1 else 0, gs[2]['score'] if len(gs)>2 else 0

def do_save_review(opt, cmt, s1,s2,s3):
    if not opt: return "先选提交"
    sid = opt.split("ID:")[-1].strip(')')
    s = get_sub_by_id(sid)
    if not s: return "提交不存在"
    gs = s['ai_grades']
    if len(gs)>0: gs[0]['score'] = s1
    if len(gs)>1: gs[1]['score'] = s2
    if len(gs)>2: gs[2]['score'] = s3
    upd_sub_status(sid, 'published', cmt, gs)
    return "复核已保存并发布"

if __name__ == "__main__":
    _once_init()
    build_teacher_ui().launch(server_port=7860)