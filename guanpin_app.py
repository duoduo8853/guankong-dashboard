import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import sqlite3
from datetime import datetime, timedelta

st.set_page_config(layout="wide", page_title="管制品追踪系统")

@st.cache_data
def load_data():
    conn = sqlite3.connect('guankong.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    today = datetime.now().strftime('%Y-%m-%d')
    
    cursor.execute('SELECT COALESCE(SUM(quantity), 0) FROM guankong_records')
    total_qty = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM guankong_records')
    pending_count = cursor.fetchone()[0]
    
    cursor.execute('SELECT COALESCE(SUM(quantity), 0) FROM guankong_records WHERE status != "已完成" AND deadline < ?', (today,))
    overdue_qty = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM guankong_records WHERE status != "已完成" AND deadline < ?', (today,))
    overdue_count = cursor.fetchone()[0]
    
    cursor.execute('SELECT COALESCE(SUM(quantity), 0) FROM guankong_records')
    total_qty_all = cursor.fetchone()[0]
    
    cursor.execute('SELECT COALESCE(SUM(quantity), 0) FROM guankong_records WHERE status = "已完成"')
    completed_qty = cursor.fetchone()[0]
    
    cursor.execute('SELECT COALESCE(SUM(quantity), 0) FROM guankong_records WHERE status != "已完成"')
    uncompleted_qty = cursor.fetchone()[0]
    
    completion_rate = round((completed_qty / total_qty_all) * 100) if total_qty_all > 0 else 0
    
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
    
    cursor.execute('''
        SELECT control_reason, COUNT(*) as count, COALESCE(SUM(quantity), 0) as quantity
        FROM guankong_records
        WHERE status != "已完成"
        GROUP BY control_reason
        ORDER BY COUNT(*) DESC
    ''')
    reason_distribution = [dict(row) for row in cursor.fetchall()]
    
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
    
    cursor.execute('''
        SELECT * FROM guankong_records 
        WHERE status != "已完成"
        ORDER BY (julianday('now') - julianday(production_date)) DESC
        LIMIT 20
    ''')
    product_records = [dict(row) for row in cursor.fetchall()]
    
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
    
    conn.close()
    
    return {
        'dept_stats': dept_stats,
        'pending_count': pending_count,
        'pending_qty': uncompleted_qty,
        'overdue_qty': overdue_qty,
        'overdue_count': overdue_count,
        'total_qty': total_qty_all,
        'completed_qty': completed_qty,
        'completion_rate': completion_rate,
        'reason_distribution': reason_distribution,
        'last_7_days': last_7_days,
        'product_records': product_records,
        'monthly_raw': monthly_raw
    }

st.title('📊 管制品追踪系统')
st.markdown('<p style="color: #666; font-size: 14px;">数据更新时间：' + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + '</p>', unsafe_allow_html=True)

data = load_data()

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("待处理数量", f"{data['pending_qty']:,}", f"{data['pending_count']} 条记录")

with col2:
    overdue_rate = (data['overdue_qty'] / data['pending_qty'] * 100) if data['pending_qty'] > 0 else 0
    st.metric("超期数量", f"{data['overdue_qty']:,}", f"超期率 {overdue_rate:.1f}%")

with col3:
    st.metric("总记录数", f"{data['total_qty']:,}", f"已完成 {data['completed_qty']:,}")

with col4:
    st.metric("处理率", f"{data['completion_rate']}%", delta="目标 ≥85%")

critical_data = [p for p in data['product_records'] 
                 if (datetime.now() - datetime.strptime(p['production_date'], '%Y-%m-%d')).days > 30 
                 and p['status'] != '已完成']

if critical_data:
    st.warning(f"🔥 严重超期警示（超期30天以上）：共 {len(critical_data)} 项")
    with st.expander("查看严重超期明细"):
        for item in critical_data[:5]:
            days = (datetime.now() - datetime.strptime(item['production_date'], '%Y-%m-%d')).days
            st.write(f"**{item['product_name'][:30]}** | 超期 {days} 天 | 数量: {item['quantity']} 箱 | 处理人: {item.get('handler_name', item.get('handle_dept', '未分配'))}")

col_chart1, col_chart2 = st.columns(2)

with col_chart1:
    st.subheader('📊 各处理人待处理数量统计')
    dept_df = pd.DataFrame(data['dept_stats'])
    if not dept_df.empty:
        fig_dept = go.Figure()
        colors = {'critical_overdue': '#ef4444', 'normal_overdue': '#f59e0b', 
                  'upcoming_due': '#fbbf24', 'normal': '#10b981'}
        labels = {'critical_overdue': '严重超期', 'normal_overdue': '一般超期', 
                 'upcoming_due': '即将到期', 'normal': '正常'}
        
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
            template='plotly_white'
        )
        st.plotly_chart(fig_dept, use_container_width=True)

with col_chart2:
    st.subheader('📈 近7天处理率趋势')
    trend_df = pd.DataFrame(data['last_7_days'])
    if not trend_df.empty:
        fig_trend = go.Figure()
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
            yaxis_title='处理率 (%)',
            yaxis=dict(range=[0, 100]),
            template='plotly_white'
        )
        st.plotly_chart(fig_trend, use_container_width=True)

st.subheader('📅 月度管制品数量统计')
monthly_raw = data['monthly_raw']
if monthly_raw:
    monthly_df = pd.DataFrame(monthly_raw)
    pivot_df = monthly_df.pivot_table(index='month', columns='dept', values='quantity', fill_value=0)
    
    fig_monthly = px.bar(
        pivot_df,
        height=400,
        xaxis_title='月份',
        yaxis_title='数量（箱）',
        template='plotly_white'
    )
    fig_monthly.update_layout(
        barmode='stack',
        legend=dict(orientation='h', yanchor='bottom', y=1.02)
    )
    st.plotly_chart(fig_monthly, use_container_width=True)

st.subheader('📋 管制原因分布')
reason_df = pd.DataFrame(data['reason_distribution'])
if not reason_df.empty:
    fig_reason = go.Figure(data=[go.Pie(
        labels=reason_df['control_reason'],
        values=reason_df['quantity'],
        hole=0.4
    )])
    fig_reason.update_layout(height=400, template='plotly_white')
    st.plotly_chart(fig_reason, use_container_width=True)

st.subheader('📦 待处理管制品列表')
product_df = pd.DataFrame(data['product_records'])
if not product_df.empty:
    display_cols = ['product_name', 'control_reason', 'quantity', 'handler_name', 'status', 'deadline']
    st.dataframe(product_df[display_cols].head(20), use_container_width=True, hide_index=True)

st.markdown("---")
st.markdown("💡 **提示**：数据实时从数据库读取，刷新页面即可获取最新数据")
