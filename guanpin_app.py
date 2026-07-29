import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import sqlite3
from datetime import datetime, timedelta

st.set_page_config(layout="wide", page_title="管制品追踪数据看板")

# 深色主题样式
st.markdown("""
<style>
    .stApp { background: #0f172a; }
    .stMetric { background: #1e293b; border-radius: 12px; padding: 20px; border: 1px solid #334155; }
    .stMetric label { color: #94a3b8; }
    .stMetric value { color: #f1f5f9; }
    h1, h2, h3 { color: #f1f5f9 !important; }
    .stMarkdown p { color: #94a3b8; }
    .stAlert { background: #1e293b; border: 1px solid #334155; }
    .stAlert p { color: #f1f5f9; }
    div[data-testid="stDataFrame"] { background: #1e293b; border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

@st.cache_data
def load_data():
    conn = sqlite3.connect('guankong.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    today = datetime.now().strftime('%Y-%m-%d')
    
    # Flask API 逻辑: pending_qty = total_qty_all (所有记录的总数量)
    cursor.execute('SELECT COALESCE(SUM(quantity), 0) FROM guankong_records')
    total_qty_all = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM guankong_records')
    pending_count = cursor.fetchone()[0]
    
    cursor.execute('SELECT COALESCE(SUM(quantity), 0) FROM guankong_records WHERE status != "已完成" AND deadline < ?', (today,))
    overdue_qty = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM guankong_records WHERE status != "已完成" AND deadline < ?', (today,))
    overdue_count = cursor.fetchone()[0]
    
    cursor.execute('SELECT COALESCE(SUM(quantity), 0) FROM guankong_records WHERE status = "已完成"')
    completed_qty = cursor.fetchone()[0]
    
    cursor.execute('SELECT COALESCE(SUM(quantity), 0) FROM guankong_records WHERE status != "已完成"')
    uncompleted_qty = cursor.fetchone()[0]
    
    completion_rate = round((completed_qty / total_qty_all) * 100) if total_qty_all > 0 else 0
    
    # 今日新增
    cursor.execute('SELECT COUNT(*) FROM guankong_records WHERE DATE(production_date) = ?', (today,))
    today_added = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM guankong_records WHERE DATE(production_date) = DATE("now", "-1 day")')
    yesterday_added = cursor.fetchone()[0]
    
    # 部门统计 - 与Flask完全一致
    cursor.execute('''
        SELECT COALESCE(handler_name, handle_dept) as dept,
               COUNT(*) as count,
               COALESCE(SUM(quantity), 0) as quantity,
               COALESCE(SUM(CASE WHEN (julianday('now') - julianday(deadline)) > 15 THEN quantity ELSE 0 END), 0) as critical_overdue,
               COALESCE(SUM(CASE WHEN (julianday('now') - julianday(deadline)) BETWEEN 7 AND 15 THEN quantity ELSE 0 END), 0) as normal_overdue,
               COALESCE(SUM(CASE WHEN (julianday('now') - julianday(deadline)) BETWEEN 5 AND 7 THEN quantity ELSE 0 END), 0) as upcoming_due,
               COALESCE(SUM(CASE WHEN (julianday('now') - julianday(deadline)) < 5 THEN quantity ELSE 0 END), 0) as normal
        FROM guankong_records
        WHERE status = "待处理"
          AND deadline IS NOT NULL
          AND COALESCE(handler_name, handle_dept) IS NOT NULL
          AND COALESCE(handler_name, handle_dept) != ""
          AND COALESCE(handler_name, handle_dept) != "未分配"
        GROUP BY COALESCE(handler_name, handle_dept)
        ORDER BY SUM(quantity) DESC
    ''')
    dept_stats = []
    for row in cursor.fetchall():
        dept_stats.append({
            'dept': row['dept'],
            'count': row['count'],
            'qty': row['quantity'],
            'quantity': row['quantity'],
            'critical_overdue': row['critical_overdue'],
            'normal_overdue': row['normal_overdue'],
            'upcoming_due': row['upcoming_due'],
            'normal': row['normal']
        })
    
    # 部门百分比
    dept_percentages = {}
    if uncompleted_qty > 0:
        cursor.execute('SELECT COALESCE(handler_name, handle_dept) as dept, COALESCE(SUM(quantity), 0) FROM guankong_records WHERE status = "待处理" GROUP BY COALESCE(handler_name, handle_dept)')
        pending_dept = {}
        for row in cursor.fetchall():
            pending_dept[row['dept']] = row[1]
        for dept in pending_dept:
            dept_percentages[dept] = round((pending_dept.get(dept, 0) / uncompleted_qty) * 100)
    
    # 管制原因分布
    cursor.execute('''
        SELECT control_reason, COUNT(*) as count, COALESCE(SUM(quantity), 0) as quantity
        FROM guankong_records
        WHERE status != "已完成"
        GROUP BY control_reason
        ORDER BY COUNT(*) DESC
    ''')
    reason_distribution = [dict(row) for row in cursor.fetchall()]
    
    # 近7天处理率趋势 - 与Flask完全一致
    last_7_days = []
    for i in range(6, -1, -1):
        date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
        
        cursor.execute('SELECT COALESCE(SUM(quantity), 0) FROM guankong_records WHERE DATE(production_date) = ?', (date,))
        created_qty = cursor.fetchone()[0]
        
        cursor.execute('SELECT COALESCE(SUM(quantity), 0) FROM guankong_records WHERE DATE(handle_time) = ?', (date,))
        completed_day = cursor.fetchone()[0]
        
        cursor.execute('''
            SELECT COALESCE(SUM(quantity), 0) FROM guankong_records 
            WHERE status = "待处理" AND (julianday(?) - julianday(deadline)) >= 7
        ''', (date,))
        pending_day = cursor.fetchone()[0]
        
        rate = round((completed_day / (created_qty + pending_day)) * 100) if (created_qty + pending_day) > 0 else 0
        
        last_7_days.append({
            'date': date,
            'count': created_qty,
            'completed': completed_day,
            'completed_qty': completed_day,
            'pending_qty': pending_day,
            'rate': rate
        })
    
    # 严重超期走马灯数据
    cursor.execute('''
        SELECT * FROM guankong_records 
        WHERE status != "已完成" 
        AND (julianday('now') - julianday(production_date)) > 30
        ORDER BY (julianday('now') - julianday(production_date)) DESC
    ''')
    critical_overdue_records = [dict(row) for row in cursor.fetchall()]
    
    # 待处理列表
    cursor.execute('''
        SELECT * FROM guankong_records 
        WHERE status != "已完成"
        ORDER BY (julianday('now') - julianday(production_date)) DESC
        LIMIT 20
    ''')
    product_records = [dict(row) for row in cursor.fetchall()]
    
    # 月度统计
    cursor.execute('''
        SELECT strftime('%Y-%m', production_date) as month,
               COALESCE(handler_name, handle_dept) as dept,
               COALESCE(SUM(quantity), 0) as quantity
        FROM guankong_records
        WHERE (handler_name IS NOT NULL AND TRIM(handler_name) != '' OR handle_dept IS NOT NULL AND TRIM(handle_dept) != '')
        GROUP BY month, COALESCE(handler_name, handle_dept)
        ORDER BY month, SUM(quantity) DESC
    ''')
    monthly_raw = [dict(row) for row in cursor.fetchall()]
    
    # 产品类别处理统计
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
    product_stats = []
    for row in cursor.fetchall():
        handled = row['handled_qty'] if row['handled_qty'] else 0
        total = row['total_qty'] if row['total_qty'] else 0
        product_stats.append({
            'name': row['product_category'],
            'pending_qty': row['pending_qty'],
            'handled_qty': handled,
            'total_qty': total,
            'handled_percent': round((handled / total) * 100) if total > 0 else 0
        })
    
    conn.close()
    
    return {
        'dept_stats': dept_stats,
        'pending_count': pending_count,
        'pending_qty': total_qty_all,  # 与Flask一致: 返回总数量
        'uncompleted_qty': uncompleted_qty,
        'overdue_qty': overdue_qty,
        'overdue_count': overdue_count,
        'total_qty': total_qty_all,
        'completed_qty': completed_qty,
        'completion_rate': completion_rate,
        'today_added': today_added,
        'yesterday_added': yesterday_added,
        'dept_percentages': dept_percentages,
        'reason_distribution': reason_distribution,
        'last_7_days': last_7_days,
        'critical_overdue_records': critical_overdue_records,
        'product_records': product_records,
        'monthly_raw': monthly_raw,
        'product_stats': product_stats
    }

data = load_data()

# 标题
st.title('📊 管制品追踪数据看板')
dept_labels = ' · '.join([f'{k} {v}%' for k, v in data['dept_percentages'].items() if v > 0]) or '无数据'
st.markdown(f'<p style="color: #64748b; font-size: 14px;">数据更新时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | 📦 共 {data["pending_count"]} 条记录 | {dept_labels}</p>', unsafe_allow_html=True)

# 4个指标卡片 - 与Flask一致
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("📦 待处理总数（箱）", f"{data['pending_qty']:,}", f"共 {data['pending_count']} 条记录")

with col2:
    overdue_rate = (data['overdue_qty'] / data['pending_qty'] * 100) if data['pending_qty'] > 0 else 0
    critical_qty = sum(d.get('critical_overdue', 0) for d in data['dept_stats'])
    st.metric("🔴 超期项目数（箱）", f"{data['overdue_qty']:,}", f"超期率 {overdue_rate:.1f}% | 超15天: {critical_qty:,}箱")

with col3:
    info_text = f"今日新增 {data['today_added']}条" if data['today_added'] > 0 else f"今日暂无，昨日 {data['yesterday_added']}条"
    st.metric("🆕 今日新增（条）", f"{data['today_added']}", info_text)

with col4:
    st.metric("✅ 处理率", f"{data['completion_rate']}%", "目标 ≥85%")

# 严重超期走马灯
if data['critical_overdue_records']:
    st.error(f"🔥 严重超期警示（超期30天以上未处理）：共 {len(data['critical_overdue_records'])} 项")
    marquee_items = []
    for item in data['critical_overdue_records'][:10]:
        days = (datetime.now() - datetime.strptime(item['production_date'], '%Y-%m-%d')).days
        handler = item.get('handler_name', item.get('handle_dept', '未分配'))
        marquee_items.append(f"【{item['product_name'][:20]}】超期{days}天 | {item['quantity']}箱 | 处理人: {handler}")
    st.markdown(
        f'<div style="background: #7f1d1d; padding: 10px; border-radius: 8px; overflow: hidden; white-space: nowrap;">'
        + ' ⚡ '.join(marquee_items) + 
        '</div>', unsafe_allow_html=True
    )

# 图表区域 - 第一行: 各部门待处理 + 近7天趋势
st.markdown("---")
col_chart1, col_chart2 = st.columns(2)

with col_chart1:
    st.subheader('📊 各部门待处理数量统计')
    dept_df = pd.DataFrame(data['dept_stats'])
    if not dept_df.empty:
        fig_dept = go.Figure()
        colors = {'critical_overdue': '#ef4444', 'normal_overdue': '#f59e0b', 
                  'upcoming_due': '#fbbf24', 'normal': '#10b981'}
        labels = {'critical_overdue': '严重超期(>15天)', 'normal_overdue': '一般超期(7-15天)', 
                 'upcoming_due': '即将到期(5-7天)', 'normal': '正常(<5天)'}
        
        for key in ['critical_overdue', 'normal_overdue', 'upcoming_due', 'normal']:
            fig_dept.add_trace(go.Bar(
                name=labels[key],
                x=dept_df['dept'],
                y=dept_df[key],
                marker_color=colors[key],
                hovertemplate='%{x}<br>' + labels[key] + ': %{y} 箱<extra></extra>'
            ))
        
        fig_dept.update_layout(
            barmode='stack',
            height=400,
            xaxis_title='处理人',
            yaxis_title='数量（箱）',
            legend=dict(orientation='h', yanchor='bottom', y=1.02),
            template='plotly_dark',
            paper_bgcolor='#1e293b',
            plot_bgcolor='#0f172a',
            font=dict(color='#94a3b8')
        )
        st.plotly_chart(fig_dept, use_container_width=True)

with col_chart2:
    st.subheader('📈 近7天处理率趋势')
    trend_df = pd.DataFrame(data['last_7_days'])
    if not trend_df.empty:
        fig_trend = go.Figure()
        fig_trend.add_trace(go.Bar(
            x=trend_df['date'].apply(lambda x: x[5:]),
            y=trend_df['completed_qty'],
            name='已处理箱数',
            marker_color='#3b82f6',
            yaxis='y2',
            opacity=0.5,
            hovertemplate='%{x}<br>已处理: %{y} 箱<extra></extra>'
        ))
        fig_trend.add_trace(go.Scatter(
            x=trend_df['date'].apply(lambda x: x[5:]),
            y=trend_df['rate'],
            mode='lines+markers',
            name='处理率',
            line=dict(color='#10b981', width=3),
            hovertemplate='%{x}<br>处理率: %{y}%<extra></extra>'
        ))
        fig_trend.add_hline(y=60, line_dash="dash", line_color="#10b981", 
                           annotation_text="达标线 60%")
        fig_trend.update_layout(
            height=400,
            xaxis_title='日期',
            yaxis=dict(title='处理率 (%)', range=[0, 100]),
            yaxis2=dict(title='已处理箱数', overlaying='y', side='right', showgrid=False),
            legend=dict(orientation='h', yanchor='bottom', y=1.02),
            template='plotly_dark',
            paper_bgcolor='#1e293b',
            plot_bgcolor='#0f172a',
            font=dict(color='#94a3b8')
        )
        st.plotly_chart(fig_trend, use_container_width=True)

# 第二行: 月度统计 + 管制原因占比
col_chart3, col_chart4 = st.columns(2)

with col_chart3:
    st.subheader('📦 月度管制品数量统计')
    monthly_raw = data['monthly_raw']
    if monthly_raw:
        monthly_df = pd.DataFrame(monthly_raw)
        pivot_df = monthly_df.pivot_table(index='month', columns='dept', values='quantity', fill_value=0)
        
        fig_monthly = px.bar(pivot_df, height=400, template='plotly_dark')
        fig_monthly.update_layout(
            barmode='stack',
            xaxis_title='月份',
            yaxis_title='数量（箱）',
            legend=dict(orientation='h', yanchor='bottom', y=1.02),
            paper_bgcolor='#1e293b',
            plot_bgcolor='#0f172a',
            font=dict(color='#94a3b8')
        )
        st.plotly_chart(fig_monthly, use_container_width=True)

with col_chart4:
    st.subheader('📋 管制原因分类占比')
    reason_df = pd.DataFrame(data['reason_distribution'])
    if not reason_df.empty:
        fig_reason = go.Figure(data=[go.Pie(
            labels=reason_df['control_reason'],
            values=reason_df['quantity'],
            hole=0.4
        )])
        fig_reason.update_layout(
            height=400, 
            template='plotly_dark',
            paper_bgcolor='#1e293b',
            font=dict(color='#94a3b8'),
            legend=dict(orientation='h', yanchor='bottom', y=-0.2)
        )
        st.plotly_chart(fig_reason, use_container_width=True)

# 第三行: 产品类别处理统计
st.subheader('🏭 产品类别处理统计')
product_stats_df = pd.DataFrame(data['product_stats'])
if not product_stats_df.empty:
    fig_product = go.Figure()
    fig_product.add_trace(go.Bar(
        name='待处理',
        x=product_stats_df['name'],
        y=product_stats_df['pending_qty'],
        marker_color='#ef4444'
    ))
    fig_product.add_trace(go.Bar(
        name='已处理',
        x=product_stats_df['name'],
        y=product_stats_df['handled_qty'],
        marker_color='#10b981'
    ))
    fig_product.update_layout(
        barmode='stack',
        height=400,
        xaxis_title='产品类别',
        yaxis_title='数量（箱）',
        legend=dict(orientation='h', yanchor='bottom', y=1.02),
        template='plotly_dark',
        paper_bgcolor='#1e293b',
        plot_bgcolor='#0f172a',
        font=dict(color='#94a3b8')
    )
    st.plotly_chart(fig_product, use_container_width=True)

# 待处理管制品列表
st.subheader('📦 待处理管制品列表')
product_df = pd.DataFrame(data['product_records'])
if not product_df.empty:
    display_cols = ['product_name', 'control_reason', 'quantity', 'handler_name', 'status', 'deadline']
    available_cols = [c for c in display_cols if c in product_df.columns]
    st.dataframe(product_df[available_cols].head(20), use_container_width=True, hide_index=True)

st.markdown("---")
st.markdown("💡 **提示**：数据实时从数据库读取，刷新页面即可获取最新数据")
