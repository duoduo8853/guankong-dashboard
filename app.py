import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import sqlite3
from datetime import datetime, timedelta
import io
from openpyxl import Workbook

# 页面配置
st.set_page_config(
    page_title="管制品追踪系统",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自定义深色主题CSS
st.markdown("""
<style>
    .stApp { background: #0f172a; }
    .sidebar .sidebar-content { background: #1e293b; }
    .sidebar .stButton > button { width: 100%; margin: 5px 0; }
    .stMetric { background: #1e293b; border-radius: 12px; padding: 20px; border: 1px solid #334155; }
    h1, h2, h3 { color: #f1f5f9 !important; }
    .stMarkdown p, .stMarkdown li { color: #94a3b8; }
    .stAlert { background: #1e293b; border: 1px solid #334155; }
    .stAlert p, .stAlert div { color: #f1f5f9; }
    div[data-testid="stDataFrame"] { background: #1e293b; border-radius: 8px; }
    div[class*="stFileUploader"] { background: #1e293b; }
    .stTextInput input, .stSelectbox select, .stNumberInput input { background: #1e293b; color: #f1f5f9; }
    .stExpander summary { color: #f1f5f9; }
    .stTabs [data-baseweb="tab"] { color: #94a3b8; }
    .stTabs [aria-selected="true"] { color: #f1f5f9; background: #334155; }
</style>
""", unsafe_allow_html=True)

# 数据库连接
def get_db():
    conn = sqlite3.connect('guankong.db')
    conn.row_factory = sqlite3.Row
    return conn

# 初始化数据库
def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS guankong_records (
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
        )
    ''')
    conn.commit()
    conn.close()

# 数据缓存
@st.cache_data(ttl=30)
def load_dashboard_data():
    conn = get_db()
    cursor = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')
    
    cursor.execute('SELECT COALESCE(SUM(quantity), 0) FROM guankong_records')
    total_qty = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM guankong_records')
    total_count = cursor.fetchone()[0]
    
    cursor.execute('SELECT COALESCE(SUM(quantity), 0) FROM guankong_records WHERE status != "已完成" AND deadline < ?', (today,))
    overdue_qty = cursor.fetchone()[0]
    
    cursor.execute('SELECT COALESCE(SUM(quantity), 0) FROM guankong_records WHERE status = "已完成"')
    completed_qty = cursor.fetchone()[0]
    
    cursor.execute('SELECT COALESCE(SUM(quantity), 0) FROM guankong_records WHERE status != "已完成"')
    uncompleted_qty = cursor.fetchone()[0]
    
    completion_rate = round((completed_qty / total_qty) * 100) if total_qty > 0 else 0
    
    cursor.execute('''
        SELECT COALESCE(handler_name, handle_dept) as dept,
               COUNT(*) as count,
               COALESCE(SUM(quantity), 0) as quantity,
               COALESCE(SUM(CASE WHEN (julianday('now') - julianday(deadline)) > 15 THEN quantity ELSE 0 END), 0) as critical_overdue,
               COALESCE(SUM(CASE WHEN (julianday('now') - julianday(deadline)) BETWEEN 7 AND 15 THEN quantity ELSE 0 END), 0) as normal_overdue,
               COALESCE(SUM(CASE WHEN (julianday('now') - julianday(deadline)) < 7 THEN quantity ELSE 0 END), 0) as normal
        FROM guankong_records
        WHERE status = "待处理" AND deadline IS NOT NULL
          AND COALESCE(handler_name, handle_dept) IS NOT NULL
          AND COALESCE(handler_name, handle_dept) != ""
          AND COALESCE(handler_name, handle_dept) != "未分配"
        GROUP BY COALESCE(handler_name, handle_dept)
        ORDER BY SUM(quantity) DESC
    ''')
    dept_stats = [dict(row) for row in cursor.fetchall()]
    
    cursor.execute('''
        SELECT control_reason, COUNT(*) as count, COALESCE(SUM(quantity), 0) as quantity
        FROM guankong_records WHERE status != "已完成"
        GROUP BY control_reason ORDER BY COUNT(*) DESC
    ''')
    reason_dist = [dict(row) for row in cursor.fetchall()]
    
    cursor.execute('''
        SELECT * FROM guankong_records WHERE status != "已完成"
        AND (julianday('now') - julianday(production_date)) > 30
        ORDER BY (julianday('now') - julianday(production_date)) DESC
    ''')
    critical_records = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    return {
        'total_qty': total_qty, 'total_count': total_count,
        'overdue_qty': overdue_qty, 'completed_qty': completed_qty,
        'uncompleted_qty': uncompleted_qty, 'completion_rate': completion_rate,
        'dept_stats': dept_stats, 'reason_dist': reason_dist,
        'critical_records': critical_records
    }

@st.cache_data(ttl=10)
def load_records():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM guankong_records
        ORDER BY COALESCE(deadline, production_date) DESC
    ''')
    records = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return records

# 页面：仪表盘
def page_dashboard():
    st.title('📊 管制品追踪数据看板')
    data = load_dashboard_data()
    
    # 指标卡片
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("📦 总数量（箱）", f"{data['total_qty']:,}", f"{data['total_count']} 条记录")
    with c2:
        st.metric("🔴 超期项目数", f"{data['overdue_qty']:,}")
    with c3:
        st.metric("📋 待处理数量", f"{data['uncompleted_qty']:,}")
    with c4:
        st.metric("✅ 处理率", f"{data['completion_rate']}%")
    
    # 严重超期警示
    if data['critical_records']:
        with st.expander(f"🔥 严重超期警示（超期30天以上，共 {len(data['critical_records'])} 项）", expanded=False):
            cols = st.columns(3)
            for i, rec in enumerate(data['critical_records'][:9]):
                with cols[i % 3]:
                    days = (datetime.now() - datetime.strptime(rec['production_date'], '%Y-%m-%d')).days
                    handler = rec.get('handler_name') or rec.get('handle_dept') or '未分配'
                    st.error(f"**{rec['product_name'][:25]}**\n超期{days}天 | {rec['quantity']}箱 | {handler}")
    
    # 图表区域
    col1, col2 = st.columns(2)
    with col1:
        st.subheader('📊 各处理人待处理统计')
        if data['dept_stats']:
            df = pd.DataFrame(data['dept_stats'])
            fig = go.Figure()
            fig.add_trace(go.Bar(name='严重超期', x=df['dept'], y=df['critical_overdue'], marker_color='#ef4444'))
            fig.add_trace(go.Bar(name='一般超期', x=df['dept'], y=df['normal_overdue'], marker_color='#f59e0b'))
            fig.add_trace(go.Bar(name='正常', x=df['dept'], y=df['normal'], marker_color='#10b981'))
            fig.update_layout(barmode='stack', height=380, template='plotly_dark',
                            paper_bgcolor='#1e293b', plot_bgcolor='#0f172a',
                            font=dict(color='#94a3b8'), xaxis_title='处理人', yaxis_title='数量（箱）')
            st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.subheader('📋 管制原因分布')
        if data['reason_dist']:
            df = pd.DataFrame(data['reason_dist'])
            fig = go.Figure(data=[go.Pie(labels=df['control_reason'], values=df['quantity'], hole=0.4)])
            fig.update_layout(height=380, template='plotly_dark', paper_bgcolor='#1e293b',
                            font=dict(color='#94a3b8'), showlegend=True,
                            legend=dict(orientation='v', yanchor='middle', y=0.5, xanchor='left', x=1.05))
            st.plotly_chart(fig, use_container_width=True)
    
    st.subheader('📈 最近7天处理趋势')
    trend_data = []
    for i in range(6, -1, -1):
        date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT COALESCE(SUM(quantity),0) FROM guankong_records WHERE DATE(handle_time)=?', (date,))
        completed = cursor.fetchone()[0]
        cursor.execute('SELECT COALESCE(SUM(quantity),0) FROM guankong_records WHERE DATE(production_date)=?', (date,))
        added = cursor.fetchone()[0]
        conn.close()
        trend_data.append({'date': date[5:], '已处理': completed, '新增': added})
    if trend_data:
        df = pd.DataFrame(trend_data)
        fig = go.Figure()
        fig.add_trace(go.Bar(name='新增', x=df['date'], y=df['新增'], marker_color='#3b82f6'))
        fig.add_trace(go.Bar(name='已处理', x=df['date'], y=df['已处理'], marker_color='#10b981'))
        fig.update_layout(barmode='group', height=350, template='plotly_dark',
                        paper_bgcolor='#1e293b', plot_bgcolor='#0f172a',
                        font=dict(color='#94a3b8'))
        st.plotly_chart(fig, use_container_width=True)

# 页面：台账管理
def page_records():
    st.title('📋 管制品台账')
    
    tab1, tab2, tab3 = st.tabs(["📝 记录列表", "➕ 新增记录", "📥 批量导入"])
    
    with tab1:
        records = load_records()
        
        # 筛选
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            search = st.text_input("🔍 搜索产品名称/原因", placeholder="输入关键词...")
        with col2:
            status_filter = st.selectbox("状态", ["全部", "待处理", "处理中", "已完成"])
        with col3:
            handler_filter = st.selectbox("处理人", ["全部"] + list(set(r.get('handler_name') or r.get('handle_dept') or '' for r in records if r.get('handler_name') or r.get('handle_dept'))))
        
        filtered = records
        if search:
            filtered = [r for r in filtered if search.lower() in str(r.get('product_name', '')).lower() 
                       or search.lower() in str(r.get('control_reason', '')).lower()]
        if status_filter != "全部":
            filtered = [r for r in filtered if r.get('status') == status_filter]
        if handler_filter != "全部":
            filtered = [r for r in filtered if (r.get('handler_name') or r.get('handle_dept')) == handler_filter]
        
        st.info(f"共 {len(filtered)} 条记录")
        
        # 批量操作
        col_batch1, col_batch2 = st.columns(2)
        with col_batch1:
            if st.button("🗑️ 删除全部记录", type="primary"):
                conn = get_db()
                conn.execute('DELETE FROM guankong_records')
                conn.commit()
                conn.close()
                st.cache_data.clear()
                st.success("已删除全部记录！")
                st.rerun()
        with col_batch2:
            if st.button("📊 导出Excel"):
                df = pd.DataFrame(filtered)
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False)
                st.download_button("⬇️ 下载Excel", data=output.getvalue(), 
                                  file_name=f"管制品台账_{datetime.now().strftime('%Y%m%d')}.xlsx",
                                  mime="application/vnd.openpyxl-sheet")
        
        # 显示记录（分页）
        page_size = 10
        if len(filtered) > 0:
            page = st.number_input("页码", 1, max(1, len(filtered)//page_size + 1), 1)
            start = (page - 1) * page_size
            end = start + page_size
            page_data = filtered[start:end]
            
            for rec in page_data:
                status_color = {'待处理': '🔴', '处理中': '🟡', '已完成': '🟢'}.get(rec.get('status'), '⚪')
                with st.expander(f"{status_color} {rec.get('product_name', '未知')[:40]} | {rec.get('control_reason', '')} | {rec.get('quantity', 0)}箱"):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.write(f"**生产日期**: {rec.get('production_date', '-')}")
                        st.write(f"**数量**: {rec.get('quantity', 0)} 箱")
                        st.write(f"**状态**: {rec.get('status', '-')}")
                    with col2:
                        handler = rec.get('handler_name') or rec.get('handle_dept') or '未分配'
                        st.write(f"**处理人**: {handler}")
                        st.write(f"**截止日期**: {rec.get('deadline', '-')}")
                        st.write(f"**处理意见**: {rec.get('handle_opinion', '-')}")
                    with col3:
                        st.write(f"**已处理**: {rec.get('handled_quantity', 0)} 箱")
                        st.write(f"**创建时间**: {rec.get('created_at', '-')[:10]}")
                        
                        if rec.get('status') != '已完成':
                            if st.button(f"✅ 标记完成", key=f"complete_{rec['id']}"):
                                conn = get_db()
                                conn.execute('''UPDATE guankong_records SET status="已完成", 
                                              handle_time=DATE("now"), handled_quantity=quantity 
                                              WHERE id=?''', (rec['id'],))
                                conn.commit()
                                conn.close()
                                st.cache_data.clear()
                                st.success("已标记完成！")
                                st.rerun()
                        
                        if st.button(f"🗑️ 删除", key=f"del_{rec['id']}"):
                            conn = get_db()
                            conn.execute('DELETE FROM guankong_records WHERE id=?', (rec['id'],))
                            conn.commit()
                            conn.close()
                            st.cache_data.clear()
                            st.success("已删除！")
                            st.rerun()
    
    with tab2:
        st.subheader("➕ 新增管制品记录")
        with st.form("add_record"):
            col1, col2 = st.columns(2)
            with col1:
                product_name = st.text_input("产品名称", placeholder="例：成品-PET500ml入24")
                production_date = st.date_input("生产日期", value=datetime.now())
                quantity = st.number_input("数量（箱）", min_value=1)
                control_reason = st.selectbox("管制原因", 
                    ["调配液超时", "CIP超时", "品质确认追踪（减薄盖试车）", "品质追踪（空瓶）",
                     "色素追踪", "结线色素析出留样", "开线色素析出留样", "品质追踪（贴标视检机调试）",
                     "品质确认追踪（扭矩）", "其他"])
            with col2:
                handler_name = st.text_input("处理人", placeholder="例：阚帅")
                deadline = st.date_input("截止日期", value=datetime.now() + timedelta(days=7))
                handle_opinion = st.text_area("处理意见", placeholder="填写处理意见...")
            
            if st.form_submit_button("提交", type="primary"):
                if product_name and handler_name:
                    conn = get_db()
                    conn.execute('''INSERT INTO guankong_records 
                        (product_name, production_date, quantity, control_reason, 
                         handler_name, deadline, handle_opinion, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, '待处理')''',
                        (product_name, production_date.strftime('%Y-%m-%d'), quantity,
                         control_reason, handler_name, deadline.strftime('%Y-%m-%d'), handle_opinion))
                    conn.commit()
                    conn.close()
                    st.cache_data.clear()
                    st.success("✅ 添加成功！")
                    st.rerun()
                else:
                    st.error("请填写产品名称和处理人")
    
    with tab3:
        st.subheader("📥 批量导入Excel")
        uploaded_file = st.file_uploader("上传Excel文件", type=['xlsx', 'xls'])
        if uploaded_file:
            try:
                df = pd.read_excel(uploaded_file)
                st.write("预览前5行：")
                st.dataframe(df.head())
                
                if st.button("确认导入"):
                    conn = get_db()
                    imported = 0
                    for _, row in df.iterrows():
                        try:
                            conn.execute('''INSERT INTO guankong_records 
                                (product_name, production_date, quantity, control_reason,
                                 handler_name, deadline, status)
                                VALUES (?, ?, ?, ?, ?, ?, '待处理')''',
                                (row.get('产品名称', row.get('product_name', '')),
                                 str(row.get('生产日期', row.get('production_date', ''))),
                                 int(row.get('数量', row.get('quantity', 0))),
                                 row.get('管制原因', row.get('control_reason', '其他')),
                                 row.get('处理人', row.get('handler_name', '')),
                                 str(row.get('截止日期', row.get('deadline', '')))))
                            imported += 1
                        except Exception as e:
                            st.warning(f"跳过一行: {e}")
                    conn.commit()
                    conn.close()
                    st.cache_data.clear()
                    st.success(f"✅ 成功导入 {imported} 条记录！")
                    st.rerun()
            except Exception as e:
                st.error(f"导入失败: {e}")
        
        st.markdown("""
        **Excel格式要求：**
        - 列名：产品名称、生产日期、数量、管制原因、处理人、截止日期
        - 第一行为表头
        """)

# 页面：报表分析
def page_report():
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
            AND COALESCE(handler_name, handle_dept) != ""
            GROUP BY dept
            ORDER BY 总数量 DESC
        ''')
        dept_summary = [dict(row) for row in cursor.fetchall()]
        if dept_summary:
            df = pd.DataFrame(dept_summary)
            st.dataframe(df, use_container_width=True, hide_index=True)
    
    with col2:
        st.subheader('📋 管制原因汇总')
        cursor.execute('''
            SELECT control_reason, COUNT(*) as 记录数,
                   COALESCE(SUM(quantity), 0) as 总数量
            FROM guankong_records
            GROUP BY control_reason
            ORDER BY 总数量 DESC
        ''')
        reason_summary = [dict(row) for row in cursor.fetchall()]
        if reason_summary:
            df = pd.DataFrame(reason_summary)
            fig = go.Figure(data=[go.Pie(labels=df['control_reason'], values=df['总数量'], hole=0.4)])
            fig.update_layout(height=350, template='plotly_dark', paper_bgcolor='#1e293b')
            st.plotly_chart(fig, use_container_width=True)
    
    st.subheader('📅 月度趋势')
    cursor.execute('''
        SELECT strftime('%Y-%m', production_date) as 月份,
               COALESCE(SUM(quantity), 0) as 新增数量,
               COUNT(*) as 新增条数
        FROM guankong_records
        GROUP BY 月份
        ORDER BY 月份
    ''')
    monthly = [dict(row) for row in cursor.fetchall()]
    if monthly:
        df = pd.DataFrame(monthly)
        fig = go.Figure()
        fig.add_trace(go.Bar(name='新增数量', x=df['月份'], y=df['新增数量'], marker_color='#3b82f6'))
        fig.add_trace(go.Scatter(name='新增条数', x=df['月份'], y=df['新增条数'], 
                               mode='lines+markers', yaxis='y2', marker_color='#f59e0b'))
        fig.update_layout(height=350, template='plotly_dark',
                        paper_bgcolor='#1e293b', plot_bgcolor='#0f172a',
                        xaxis_title='月份', yaxis_title='数量', yaxis2=dict(title='条数', overlaying='y', side='right'))
        st.plotly_chart(fig, use_container_width=True)
    
    conn.close()

# 页面：系统管理
def page_admin():
    st.title('⚙️ 系统管理')
    
    st.subheader('💾 数据库管理')
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**导出数据库备份**")
        if st.button("📤 导出全部数据为Excel"):
            conn = get_db()
            df = pd.read_sql_query('SELECT * FROM guankong_records', conn)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False)
            st.download_button("⬇️ 下载", data=output.getvalue(),
                             file_name=f"管制品数据库_{datetime.now().strftime('%Y%m%d')}.xlsx",
                             mime="application/vnd.openpyxl-sheet")
            conn.close()
    
    with col2:
        st.markdown("**统计信息**")
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM guankong_records')
        total = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM guankong_records WHERE status="已完成"')
        done = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(DISTINCT COALESCE(handler_name, handle_dept)) FROM guankong_records WHERE COALESCE(handler_name, handle_dept) IS NOT NULL')
        handlers = cursor.fetchone()[0]
        conn.close()
        
        st.metric("总记录数", total)
        st.metric("已完成", done)
        st.metric("处理人数", handlers)
    
    st.divider()
    st.markdown("⚠️ **危险操作**")
    if st.button("🗑️ 清空全部数据", type="error"):
        conn = get_db()
        conn.execute('DELETE FROM guankong_records')
        conn.commit()
        conn.close()
        st.cache_data.clear()
        st.warning("已清空全部数据！")
        st.rerun()

# 侧边栏导航
st.sidebar.title('🧭 导航')
page = st.sidebar.radio("选择页面", ["📊 仪表盘", "📋 管制品台账", "📈 报表分析", "⚙️ 系统管理"])

st.sidebar.markdown("---")
st.sidebar.markdown(f"**数据更新**: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
if st.sidebar.button("🔄 刷新数据"):
    st.cache_data.clear()
    st.success("数据已刷新！")
    st.rerun()

# 路由
if page == "📊 仪表盘":
    page_dashboard()
elif page == "📋 管制品台账":
    page_records()
elif page == "📈 报表分析":
    page_report()
elif page == "⚙️ 系统管理":
    page_admin()
