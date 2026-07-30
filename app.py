import streamlit as st
import sqlite3
import os

st.set_page_config(page_title="管制品追踪系统", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

# 检查数据库
db_exists = os.path.exists('guankong.db')
if not db_exists:
    st.error("❌ 数据库文件 guankong.db 不存在！")
    st.info("请确保已上传 guankong.db 文件")
else:
    # 初始化数据库表（如果不存在）
    conn = sqlite3.connect('guankong.db')
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
    
    # 测试查询
    cursor.execute('SELECT COUNT(*) FROM guankong_records')
    count = cursor.fetchone()[0]
    conn.close()
    
    # 侧边栏
    with st.sidebar:
        st.title('🧭 导航')
        page = st.radio("选择页面", ["📊 仪表盘", "📋 台账管理", "📈 报表分析", "⚙️ 系统管理"])
        st.markdown("---")
        st.markdown(f"**数据库**: {count} 条记录")
        st.markdown(f"**文件**: {'✅' if db_exists else '❌'} guankong.db")
    
    # 主内容
    if page == "📊 仪表盘":
        st.title('📊 管制品追踪数据看板')
        
        conn = sqlite3.connect('guankong.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT COALESCE(SUM(quantity),0) FROM guankong_records')
        total = cursor.fetchone()[0]
        
        cursor.execute('SELECT COALESCE(SUM(quantity),0) FROM guankong_records WHERE status!="已完成"')
        pending = cursor.fetchone()[0]
        
        cursor.execute('SELECT COALESCE(SUM(quantity),0) FROM guankong_records WHERE status="已完成"')
        done = cursor.fetchone()[0]
        
        conn.close()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("📦 总数量", f"{total:,}")
        c2.metric("📋 待处理", f"{pending:,}")
        c3.metric("✅ 已完成", f"{done:,}")
        
        st.info("仪表盘页面加载成功！")
        
    elif page == "📋 台账管理":
        st.title('📋 管制品台账')
        st.info("台账管理页面加载成功！")
        
        conn = sqlite3.connect('guankong.db')
        cursor = conn.cursor()
        cursor.execute('SELECT id, product_name, quantity, handler_name, status FROM guankong_records ORDER BY id DESC LIMIT 10')
        records = cursor.fetchall()
        conn.close()
        
        if records:
            st.dataframe(records, columns=['ID', '产品名称', '数量', '处理人', '状态'])
        else:
            st.warning("暂无记录")
            
    elif page == "📈 报表分析":
        st.title('📈 报表分析')
        st.info("报表分析页面加载成功！")
        
    elif page == "⚙️ 系统管理":
        st.title('⚙️ 系统管理')
        st.info("系统管理页面加载成功！")
        st.success(f"✅ 数据库连接正常，共 {count} 条记录")
