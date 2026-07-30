import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import sqlite3
from datetime import datetime, timedelta
import json
import base64

# 页面配置
st.set_page_config(
    page_title="管制品追踪系统",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 深色主题样式
st.markdown("""
<style>
    .stApp { background: #0f172a; }
    .stMetric { background: #1e293b; border-radius: 12px; padding: 15px; border: 1px solid #334155; }
    .stMetric label { color: #94a3b8 !important; }
    .stMetric > div > div:nth-child(1) { color: #94a3b8 !important; }
    .stMetric > div > div:nth-child(2) { color: #f1f5f9 !important; }
    h1, h2, h3, h4, h5 { color: #f1f5f9 !important; }
    .stMarkdown p, .stMarkdown li { color: #94a3b8; }
    .stAlert { background: #1e293b; border: 1px solid #334155; }
    .stAlert p { color: #f1f5f9; }
    div[data-testid="stDataFrame"] { background: #1e293b; border-radius: 8px; }
    .stTextInput input, .stSelectbox select, .stNumberInput input, .stDateInput input {
        background: #1e293b; color: #f1f5f9; border: 1px solid #334155;
    }
    .stExpander { background: #1e293b; border: 1px solid #334155; }
    .stExpander summary { color: #f1f5f9; }
    .stTabs [data-baseweb="tab"] { color: #94a3b8; }
    .stTabs [aria-selected="true"] { color: #f1f5f9; background: #334155; }
    .stButton button { background: #3b82f6; color: white; }
    .stButton button:hover { background: #2563eb; }
    .stRadio > div { flex-direction: column; }
    .stRadio label { color: #f1f5f9 !important; }
    /* 侧边栏样式 */
    section[data-testid="stSidebar"] { background: #1e293b; }
    section[data-testid="stSidebar"] .stRadio > div { gap: 0.5rem; }
    section[data-testid="stSidebar"] label { font-size: 1rem; padding: 0.5rem 1rem; border-radius: 8px; }
    section[data-testid="stSidebar"] label:hover { background: #334155; }
</style>
""", unsafe_allow_html=True)

# 数据库连接
@st.cache_resource
def get_db():
    conn = sqlite3.connect('guankong.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# 初始化数据库
def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS guankong_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        production_date DATE,
        product_name TEXT,
        control_reason TEXT,
        quantity INTEGER,
        handle_opinion TEXT,
        handle_time DATE,
        handle_dept TEXT,
        status TEXT DEFAULT '待处理',
        deadline DATE,
        remark TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        handled_quantity INTEGER DEFAULT 0,
        creator_id INTEGER,
        handler_name TEXT
    )''')
    conn.commit()

init_db()

# 侧边栏导航
with st.sidebar:
    st.title('🧭 管制品追踪系统')
    st.markdown('---')
    page = st.radio(
        "导航菜单",
        ["📊 仪表盘", "📋 台账管理", "📈 报表分析", "⚙️ 系统管理"],
        label_visibility="collapsed"
    )
    st.markdown('---')
    st.markdown(f"📅 **当前时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    # 数据刷新按钮
    if st.button("🔄 刷新数据", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ==================== 页面1：仪表盘 ====================
if page == "📊 仪表盘":
    st.title('📊 管制品追踪数据看板')
    
    conn = get_db()
    cursor = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')
    
    # 核心指标
    cursor.execute('SELECT COALESCE(SUM(quantity), 0) FROM guankong_records')
    total_qty = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM guankong_records')
    total_count = cursor.fetchone()[0]
    
    cursor.execute('SELECT COALESCE(SUM(quantity), 0) FROM guankong_records WHERE status != "已完成"')
    pending_qty = cursor.fetchone()[0]
    
    cursor.execute('SELECT COALESCE(SUM(quantity), 0) FROM guankong_records WHERE status != "已完成" AND deadline < ?', (today,))
    overdue_qty = cursor.fetchone()[0]
    
    cursor.execute('SELECT COALESCE(SUM(quantity), 0) FROM guankong_records WHERE status = "已完成"')
    completed_qty = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM guankong_records WHERE DATE(production_date) = ?', (today,))
    today_added = cursor.fetchone()[0]
    
    completion_rate = round((completed_qty / total_qty) * 100, 1) if total_qty > 0 else 0
    
    # 指标卡片
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("📦 总数量", f"{total_qty:,}", f"{total_count} 条记录")
    with c2:
        st.metric("📋 待处理", f"{pending_qty:,}")
    with c3:
        st.metric("🔴 超期数量", f"{overdue_qty:,}")
    with c4:
        st.metric("✅ 已完成", f"{completed_qty:,}")
    with c5:
        st.metric("📈 处理率", f"{completion_rate}%")
    
    # 严重超期警示
    cursor.execute('''
        SELECT * FROM guankong_records 
        WHERE status != "已完成" 
        AND (julianday('now') - julianday(production_date)) > 30
        ORDER BY (julianday('now') - julianday(production_date)) DESC
        LIMIT 6
    ''')
    critical_records = [dict(row) for row in cursor.fetchall()]
    
    if critical_records:
        st.markdown("---")
        st.markdown("### 🔥 严重超期警示（超期30天以上）")
        cols = st.columns(3)
        for i, rec in enumerate(critical_records):
            days = (datetime.now() - datetime.strptime(rec['production_date'], '%Y-%m-%d')).days
            handler = rec.get('handler_name') or rec.get('handle_dept') or '未分配'
            with cols[i % 3]:
                st.error(f"**{rec['product_name'][:30]}**\n\n"
                        f"超期 **{days}** 天 | {rec['quantity']} 箱 | {handler}")
    
    st.markdown("---")
    
    # 图表区域
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader('📊 各处理人待处理统计')
        cursor.execute('''
            SELECT COALESCE(handler_name, handle_dept) as dept,
                   COALESCE(SUM(quantity), 0) as qty,
                   COALESCE(SUM(CASE WHEN (julianday('now') - julianday(deadline)) > 15 THEN quantity ELSE 0 END), 0) as critical,
                   COALESCE(SUM(CASE WHEN (julianday('now') - julianday(deadline)) BETWEEN 7 AND 15 THEN quantity ELSE 0 END), 0) as normal_overdue,
                   COALESCE(SUM(CASE WHEN (julianday('now') - julianday(deadline)) < 7 THEN quantity ELSE 0 END), 0) as normal
            FROM guankong_records
            WHERE status = "待处理" AND deadline IS NOT NULL
            AND COALESCE(handler_name, handle_dept) IS NOT NULL
            AND COALESCE(handler_name, handle_dept) NOT IN ("", "未分配")
            GROUP BY dept ORDER BY qty DESC
        ''')
        dept_stats = [dict(row) for row in cursor.fetchall()]
        
        if dept_stats:
            df = pd.DataFrame(dept_stats)
            fig = go.Figure()
            fig.add_trace(go.Bar(name='严重超期', x=df['dept'], y=df['critical'], marker_color='#ef4444'))
            fig.add_trace(go.Bar(name='一般超期', x=df['dept'], y=df['normal_overdue'], marker_color='#f59e0b'))
            fig.add_trace(go.Bar(name='正常', x=df['dept'], y=df['normal'], marker_color='#10b981'))
            fig.update_layout(
                barmode='stack', height=380,
                template='plotly_dark', paper_bgcolor='#1e293b', plot_bgcolor='#0f172a',
                font=dict(color='#94a3b8'), xaxis_title='处理人', yaxis_title='数量（箱）'
            )
            st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.subheader('📋 管制原因分布')
        cursor.execute('''
            SELECT control_reason, COALESCE(SUM(quantity), 0) as qty
            FROM guankong_records WHERE status != "已完成"
            GROUP BY control_reason ORDER BY qty DESC
        ''')
        reason_stats = [dict(row) for row in cursor.fetchall()]
        
        if reason_stats:
            df = pd.DataFrame(reason_stats)
            fig = go.Figure(data=[go.Pie(labels=df['control_reason'], values=df['qty'], hole=0.4)])
            fig.update_layout(height=380, template='plotly_dark', paper_bgcolor='#1e293b',
                            font=dict(color='#94a3b8'), showlegend=True)
            st.plotly_chart(fig, use_container_width=True)
    
    # 近7天处理趋势
    st.subheader('📈 近7天处理趋势')
    trend_data = []
    for i in range(6, -1, -1):
        date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
        cursor.execute('SELECT COALESCE(SUM(quantity), 0) FROM guankong_records WHERE DATE(handle_time) = ?', (date,))
        completed = cursor.fetchone()[0]
        cursor.execute('SELECT COALESCE(SUM(quantity), 0) FROM guankong_records WHERE DATE(production_date) = ?', (date,))
        added = cursor.fetchone()[0]
        trend_data.append({'date': date[5:], '新增': added, '已处理': completed})
    
    df = pd.DataFrame(trend_data)
    fig = go.Figure()
    fig.add_trace(go.Bar(name='新增', x=df['date'], y=df['新增'], marker_color='#3b82f6'))
    fig.add_trace(go.Bar(name='已处理', x=df['date'], y=df['已处理'], marker_color='#10b981'))
    fig.update_layout(barmode='group', height=350, template='plotly_dark',
                    paper_bgcolor='#1e293b', plot_bgcolor='#0f172a', font=dict(color='#94a3b8'))
    st.plotly_chart(fig, use_container_width=True)
    
    conn.close()

# ==================== 页面2：台账管理 ====================
elif page == "📋 台账管理":
    st.title('📋 管制品台账管理')
    
    conn = get_db()
    cursor = conn.cursor()
    
    tab1, tab2, tab3 = st.tabs(["📝 记录列表", "➕ 新增记录", "📥 批量导入"])
    
    with tab1:
        # 筛选器
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            search = st.text_input("🔍 搜索", placeholder="产品名称/管制原因...")
        with col2:
            status_filter = st.selectbox("状态", ["全部", "待处理", "处理中", "已完成"])
        with col3:
            cursor.execute('''SELECT DISTINCT COALESCE(handler_name, handle_dept) 
                            FROM guankong_records 
                            WHERE COALESCE(handler_name, handle_dept) IS NOT NULL 
                            AND COALESCE(handler_name, handle_dept) != ""''')
            handlers = ["全部"] + [row[0] for row in cursor.fetchall()]
            handler_filter = st.selectbox("处理人", handlers)
        
        # 查询记录
        query = 'SELECT * FROM guankong_records WHERE 1=1'
        params = []
        if search:
            query += ' AND (product_name LIKE ? OR control_reason LIKE ?)'
            params.extend([f'%{search}%', f'%{search}%'])
        if status_filter != "全部":
            query += ' AND status = ?'
            params.append(status_filter)
        if handler_filter != "全部":
            query += ' AND COALESCE(handler_name, handle_dept) = ?'
            params.append(handler_filter)
        query += ' ORDER BY id DESC'
        
        cursor.execute(query, params)
        records = [dict(row) for row in cursor.fetchall()]
        
        st.info(f"共查询到 **{len(records)}** 条记录")
        
        # 批量操作
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📊 导出Excel", use_container_width=True):
                df = pd.DataFrame(records)
                import io
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False)
                st.download_button(
                    "⬇️ 下载Excel",
                    data=output.getvalue(),
                    file_name=f"管制品台账_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        
        with col2:
            if st.button("🗑️ 清空全部", type="secondary", use_container_width=True):
                st.warning("⚠️ 此操作将删除所有记录！")
                if st.button("确认清空", type="primary"):
                    cursor.execute('DELETE FROM guankong_records')
                    conn.commit()
                    st.success("已清空！")
                    st.rerun()
        
        # 显示记录（分页）
        page_size = 15
        if len(records) > 0:
            total_pages = (len(records) - 1) // page_size + 1
            page_num = st.number_input("页码", 1, total_pages, 1)
            start = (page_num - 1) * page_size
            end = start + page_size
            
            for rec in records[start:end]:
                status_icon = {'待处理': '🔴', '处理中': '🟡', '已完成': '🟢'}.get(rec.get('status'), '⚪')
                handler = rec.get('handler_name') or rec.get('handle_dept') or '未分配'
                
                with st.expander(f"{status_icon} {rec.get('product_name', '')[:40]} | {rec.get('quantity', 0)}箱 | {handler}"):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"**生产日期**: {rec.get('production_date', '-')}")
                        st.write(f"**管制原因**: {rec.get('control_reason', '-')}")
                        st.write(f"**数量**: {rec.get('quantity', 0)} 箱")
                        st.write(f"**状态**: {rec.get('status', '-')}")
                    with col2:
                        st.write(f"**截止日期**: {rec.get('deadline', '-')}")
                        st.write(f"**处理意见**: {rec.get('handle_opinion', '-')}")
                        st.write(f"**创建时间**: {rec.get('created_at', '-')[:10]}")
                    
                    # 操作按钮
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        if rec.get('status') != '已完成' and st.button(f"✅ 标记完成", key=f"done_{rec['id']}"):
                            cursor.execute('''UPDATE guankong_records 
                                            SET status="已完成", handle_time=DATE("now"), handled_quantity=quantity 
                                            WHERE id=?''', (rec['id'],))
                            conn.commit()
                            st.success("已完成！")
                            st.rerun()
                    
                    with col2:
                        if st.button(f"📝 编辑", key=f"edit_{rec['id']}"):
                            st.session_state['edit_id'] = rec['id']
                            st.rerun()
                    
                    with col3:
                        if st.button(f"🗑️ 删除", key=f"del_{rec['id']}"):
                            cursor.execute('DELETE FROM guankong_records WHERE id=?', (rec['id'],))
                            conn.commit()
                            st.success("已删除！")
                            st.rerun()
    
    with tab2:
        st.subheader("➕ 新增管制品记录")
        with st.form("add_record"):
            col1, col2 = st.columns(2)
            with col1:
                product_name = st.text_input("产品名称 *", placeholder="例：成品-PET500ml入24")
                production_date = st.date_input("生产日期 *", value=datetime.now())
                quantity = st.number_input("数量（箱）*", min_value=1, value=1)
                control_reason = st.selectbox("管制原因 *", [
                    "调配液超时", "CIP超时", "品质确认追踪（减薄盖试车）", 
                    "品质追踪（空瓶）", "色素追踪", "结线色素析出留样",
                    "开线色素析出留样", "品质追踪（贴标视检机调试）",
                    "品质确认追踪（扭矩）", "其他"
                ])
            with col2:
                handler_name = st.text_input("处理人 *", placeholder="例：阚帅")
                deadline = st.date_input("截止日期 *", value=datetime.now() + timedelta(days=7))
                handle_opinion = st.text_area("处理意见", placeholder="填写处理意见...")
                remark = st.text_area("备注", placeholder="其他备注信息...")
            
            submitted = st.form_submit_button("提交", type="primary", use_container_width=True)
            if submitted:
                if product_name and handler_name:
                    cursor.execute('''INSERT INTO guankong_records 
                        (product_name, production_date, quantity, control_reason, 
                         handler_name, deadline, handle_opinion, remark, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, '待处理')''',
                        (product_name, production_date.strftime('%Y-%m-%d'), quantity,
                         control_reason, handler_name, deadline.strftime('%Y-%m-%d'), 
                         handle_opinion, remark))
                    conn.commit()
                    st.success("✅ 添加成功！")
                    st.rerun()
                else:
                    st.error("请填写必填项（带 * 号）")
    
    with tab3:
        st.subheader("📥 批量导入Excel")
        uploaded_file = st.file_uploader("上传Excel文件", type=['xlsx', 'xls'])
        
        if uploaded_file:
            try:
                df = pd.read_excel(uploaded_file)
                st.write("预览前5行：")
                st.dataframe(df.head(), use_container_width=True)
                
                if st.button("确认导入", type="primary"):
                    imported = 0
                    for _, row in df.iterrows():
                        try:
                            cursor.execute('''INSERT INTO guankong_records 
                                (product_name, production_date, quantity, control_reason,
                                 handler_name, deadline, status)
                                VALUES (?, ?, ?, ?, ?, ?, '待处理')''',
                                (str(row.get('产品名称', row.get('product_name', ''))),
                                 str(row.get('生产日期', row.get('production_date', ''))),
                                 int(row.get('数量', row.get('quantity', 0))),
                                 str(row.get('管制原因', row.get('control_reason', '其他'))),
                                 str(row.get('处理人', row.get('handler_name', ''))),
                                 str(row.get('截止日期', row.get('deadline', '')))))
                            imported += 1
                        except Exception as e:
                            st.warning(f"跳过一行: {e}")
                    conn.commit()
                    st.success(f"✅ 成功导入 {imported} 条记录！")
                    st.rerun()
            except Exception as e:
                st.error(f"导入失败: {e}")
        
        st.markdown("""
        **Excel格式要求：**
        - 列名：产品名称、生产日期、数量、管制原因、处理人、截止日期
        - 第一行为表头
        """)
    
    conn.close()

# ==================== 页面3：报表分析 ====================
elif page == "📈 报表分析":
    st.title('📈 报表分析')
    
    conn = get_db()
    cursor = conn.cursor()
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader('📊 各处理人汇总')
        cursor.execute('''
            SELECT COALESCE(handler_name, handle_dept) as dept,
                   COUNT(*) as 记录数,
                   COALESCE(SUM(quantity), 0) as 总数量,
                   SUM(CASE WHEN status="已完成" THEN quantity ELSE 0 END) as 已完成,
                   SUM(CASE WHEN status="待处理" THEN quantity ELSE 0 END) as 待处理
            FROM guankong_records
            WHERE COALESCE(handler_name, handle_dept) IS NOT NULL
            AND COALESCE(handler_name, handle_dept) NOT IN ("", "未分配")
            GROUP BY dept ORDER BY 总数量 DESC
        ''')
        dept_summary = [dict(row) for row in cursor.fetchall()]
        if dept_summary:
            st.dataframe(pd.DataFrame(dept_summary), use_container_width=True, hide_index=True)
    
    with col2:
        st.subheader('📋 管制原因汇总')
        cursor.execute('''
            SELECT control_reason as 管制原因,
                   COUNT(*) as 记录数,
                   COALESCE(SUM(quantity), 0) as 总数量
            FROM guankong_records
            GROUP BY control_reason ORDER BY 总数量 DESC
        ''')
        reason_summary = [dict(row) for row in cursor.fetchall()]
        if reason_summary:
            st.dataframe(pd.DataFrame(reason_summary), use_container_width=True, hide_index=True)
    
    st.markdown("---")
    
    # 月度趋势
    st.subheader('📅 月度统计趋势')
    cursor.execute('''
        SELECT strftime('%Y-%m', production_date) as month,
               COALESCE(SUM(quantity), 0) as qty,
               COUNT(*) as cnt
        FROM guankong_records 
        GROUP BY month ORDER BY month
    ''')
    monthly = [dict(row) for row in cursor.fetchall()]
    
    if monthly:
        df = pd.DataFrame(monthly)
        fig = go.Figure()
        fig.add_trace(go.Bar(name='数量', x=df['month'], y=df['qty'], marker_color='#3b82f6'))
        fig.add_trace(go.Scatter(name='条数', x=df['month'], y=df['cnt'], 
                                mode='lines+markers', yaxis='y2', marker_color='#f59e0b'))
        fig.update_layout(height=400, template='plotly_dark', paper_bgcolor='#1e293b',
                        xaxis_title='月份', yaxis_title='数量',
                        yaxis2=dict(title='条数', overlaying='y', side='right'))
        st.plotly_chart(fig, use_container_width=True)
    
    # 产品类别统计
    st.subheader('📦 产品类别处理统计（Top 10）')
    cursor.execute('''
        SELECT 
            CASE 
                WHEN product_name LIKE '成品-PET%' THEN SUBSTR(product_name, 5, INSTR(SUBSTR(product_name, 5), '入') + 4)
                ELSE product_name 
            END as product_category,
            COALESCE(SUM(CASE WHEN status = "待处理" THEN quantity ELSE 0 END), 0) as pending_qty,
            COALESCE(SUM(handled_quantity), 0) as handled_qty,
            COALESCE(SUM(quantity), 0) as total_qty,
            COUNT(*) as record_count
        FROM guankong_records
        GROUP BY product_category
        ORDER BY pending_qty DESC
        LIMIT 10
    ''')
    product_stats = [dict(row) for row in cursor.fetchall()]
    
    if product_stats:
        df = pd.DataFrame(product_stats)
        df['handled_percent'] = round((df['handled_qty'] / df['total_qty']) * 100, 1)
        df = df.rename(columns={
            'product_category': '产品类别',
            'pending_qty': '待处理',
            'handled_qty': '已处理',
            'total_qty': '总数',
            'record_count': '记录数',
            'handled_percent': '处理率(%)'
        })
        st.dataframe(df, use_container_width=True, hide_index=True)
    
    conn.close()

# ==================== 页面4：系统管理 ====================
elif page == "⚙️ 系统管理":
    st.title('⚙️ 系统管理')
    
    conn = get_db()
    cursor = conn.cursor()
    
    # 统计信息
    cursor.execute('SELECT COUNT(*) FROM guankong_records')
    total = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM guankong_records WHERE status="已完成"')
    done = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(DISTINCT COALESCE(handler_name, handle_dept)) FROM guankong_records WHERE COALESCE(handler_name, handle_dept) IS NOT NULL')
    handlers = cursor.fetchone()[0]
    
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("📊 总记录数", total)
    with c2:
        st.metric("✅ 已完成", done)
    with c3:
        st.metric("👥 处理人数", handlers)
    
    st.markdown("---")
    
    # 数据管理
    st.subheader("💾 数据管理")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**导出数据**")
        cursor.execute('SELECT * FROM guankong_records')
        df = pd.DataFrame([dict(row) for row in cursor.fetchall()])
        
        import io
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        
        st.download_button(
            "📤 导出全部数据",
            data=output.getvalue(),
            file_name=f"管制品数据库_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    
    with col2:
        st.markdown("**清空数据**")
        st.warning("⚠️ 此操作不可恢复！")
        if st.button("🗑️ 清空全部数据", type="secondary", use_container_width=True):
            if st.button("确认清空", type="primary"):
                cursor.execute('DELETE FROM guankong_records')
                conn.commit()
                st.success("已清空！")
                st.rerun()
    
    st.markdown("---")
    
    # 系统信息
    st.subheader("ℹ️ 系统信息")
    st.markdown(f"""
    - **系统名称**: 管制品追踪系统
    - **版本**: 2.0
    - **部署平台**: Streamlit Community Cloud
    - **数据库**: SQLite
    - **更新时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """)
    
    conn.close()