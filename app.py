import streamlit as st
import requests
import pandas as pd
import json
from datetime import datetime, timedelta
from streamlit_tags import st_tags
import plotly.graph_objects as go
import os


try:
    PROJECT_ID = st.secrets["PROJECT_ID"]
    AUTH_TOKEN = st.secrets["AUTH_TOKEN"]
except (KeyError, FileNotFoundError):
    st.error("❌ Missing credentials! Please add secrets.toml file")
    st.stop()

def export_mixpanel_event(event_name, start_date, end_date):
    url = (
        f"https://data-eu.mixpanel.com/api/2.0/export?"
        f"project_id={PROJECT_ID}&from_date={start_date}&to_date={end_date}&event={json.dumps([event_name])}"
    )
    headers = {"accept": "text/plain", "authorization": AUTH_TOKEN}
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        return pd.DataFrame()
    try:
        data_json = [json.loads(line) for line in response.text.strip().split("\n")]
    except:
        return pd.DataFrame()
    if not data_json:
        return pd.DataFrame()
    df = pd.DataFrame(data_json)
    if "properties" in df.columns:
        props = pd.json_normalize(df["properties"])
        df = pd.concat([df.drop(columns=["properties"]), props], axis=1)
    if "$insert_id" in df.columns:
        df = df.drop_duplicates("$insert_id")
    return df


st.set_page_config(page_title="Mixpanel Funnel Analysis", layout="wide")
today = datetime.now().date()
default_start = today - timedelta(days=7)
default_end = today

# 1️⃣ Event selection
st.title("📊 Mixpanel Funnel Analysis")
st.subheader("1️⃣ Event Selection")
col1, col2, col3 = st.columns(3)
with col1:
    page_view_option = st.radio("Page View Event", ["$mp_web_page_view", "Web App Page View", "Both"], index=2)
with col2:
    conversion_event = st.radio("Conversion Event", ["Entered Use Case", "New User Sign Up"], index=0)
with col3:
    include_payment_event = st.checkbox("New Payment Made", value=True)

# 2️⃣ UTM filters
st.subheader("2️⃣ UTM Filters")
col1, col2, col3 = st.columns(3)
with col1:
    utm_sources_list = st_tags(label="UTM Source", text="Type and press Enter", value=[], key="utm_sources_tags")
with col2:
    utm_campaigns_list = st_tags(label="UTM Campaign", text="Type and press Enter", value=[], key="utm_campaign_tags")
with col3:
    utm_mediums_list = st_tags(label="UTM Medium", text="Type and press Enter", value=[], key="utm_medium_tags")

# 3️⃣ Date mode
st.subheader("3️⃣ Date Range")
mode = st.radio("Date Mode:", ["Standard", "Custom"], horizontal=True)
date_config = {}
st.sidebar.header("📅 Date Range Selection")

if mode == "Standard":
    standard_start = st.sidebar.date_input("Start Date", value=default_start)
    standard_end = st.sidebar.date_input("End Date", value=default_end)
    pageview_events = ["$mp_web_page_view", "Web App Page View"] if page_view_option == "Both" else [page_view_option]
    for evt in pageview_events:
        date_config[evt] = (standard_start, standard_end)
    date_config[conversion_event] = (standard_start, standard_end)
    date_config["New Payment Made"] = (standard_start, standard_end)
else:
    pageview_events = ["$mp_web_page_view", "Web App Page View"] if page_view_option == "Both" else [page_view_option]
    for evt in pageview_events:
        st.sidebar.subheader(evt)
        start = st.sidebar.date_input(f"Start Date for {evt}", value=default_start, key=f"{evt}_start")
        end = st.sidebar.date_input(f"End Date for {evt}", value=default_end, key=f"{evt}_end")
        date_config[evt] = (start, end)
    st.sidebar.subheader(conversion_event)
    conv_start = st.sidebar.date_input(f"Start Date {conversion_event}", value=default_start, key="conv_start")
    conv_end = st.sidebar.date_input(f"End Date {conversion_event}", value=default_end, key="conv_end")
    date_config[conversion_event] = (conv_start, conv_end)
    st.sidebar.subheader("New Payment Made")
    pay_start = st.sidebar.date_input("Start Date New Payment Made", value=default_start, key="pay_start")
    pay_end = st.sidebar.date_input("End Date New Payment Made", value=default_end, key="pay_end")
    date_config["New Payment Made"] = (pay_start, pay_end)

run_export = st.button("🚀 Start Analysis", type="primary")

if run_export:
    with st.spinner("Processing, please wait..."):
        # Export events
        exported_frames = {}
        events_to_export = []
        if page_view_option == "Both":
            events_to_export.extend(["$mp_web_page_view", "Web App Page View"])
        else:
            events_to_export.append(page_view_option)
        events_to_export.append(conversion_event)
        if include_payment_event:
            events_to_export.append("New Payment Made")

        for event in events_to_export:
            start, end = date_config[event]
            df = export_mixpanel_event(event, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
            exported_frames[event] = df if df is not None else pd.DataFrame()

        # Merge pageviews
        if page_view_option == "$mp_web_page_view":
            pageviews = exported_frames.get("$mp_web_page_view", pd.DataFrame())
        elif page_view_option == "Web App Page View":
            pageviews = exported_frames.get("Web App Page View", pd.DataFrame())
        else:
            df1_ = exported_frames.get("$mp_web_page_view", pd.DataFrame())
            df4_ = exported_frames.get("Web App Page View", pd.DataFrame())
            pageviews = pd.concat([df1_, df4_], ignore_index=True)

        if not pageviews.empty and 'time' in pageviews.columns:
            pageviews['time'] = pd.to_datetime(pageviews['time'], errors='coerce')
            first_pageview = pageviews.groupby('distinct_id', as_index=False)['time'].min()
        else:
            first_pageview = pd.DataFrame(columns=['distinct_id','time'])

        # Merge UTM info with safe column selection
        utm_cols = ['distinct_id','time','utm_source','utm_campaign','utm_medium']
        if page_view_option == "$mp_web_page_view":
            df_temp = exported_frames.get("$mp_web_page_view", pd.DataFrame())
            df_all = df_temp[[col for col in utm_cols if col in df_temp.columns]] if not df_temp.empty else pd.DataFrame()
        elif page_view_option == "Web App Page View":
            df_temp = exported_frames.get("Web App Page View", pd.DataFrame())
            df_all = df_temp[[col for col in utm_cols if col in df_temp.columns]] if not df_temp.empty else pd.DataFrame()
        else:
            df1_temp = exported_frames.get("$mp_web_page_view", pd.DataFrame())
            df4_temp = exported_frames.get("Web App Page View", pd.DataFrame())
            df1_cols = df1_temp[[col for col in utm_cols if col in df1_temp.columns]] if not df1_temp.empty else pd.DataFrame()
            df4_cols = df4_temp[[col for col in utm_cols if col in df4_temp.columns]] if not df4_temp.empty else pd.DataFrame()
            df_all = pd.concat([df1_cols, df4_cols], ignore_index=True)

        # Safe sorting and deduplication
        if not df_all.empty and 'time' in df_all.columns and 'distinct_id' in df_all.columns:
            df_all = df_all.sort_values('time').drop_duplicates(subset=['distinct_id'], keep='first')
        else:
            df_all = pd.DataFrame(columns=utm_cols)
        
        merged_df = pd.merge(first_pageview[['distinct_id']], df_all, on='distinct_id', how='left') if not first_pageview.empty else pd.DataFrame()

        # Apply UTM filters
        filtered = merged_df.copy()
        for col in ['utm_source','utm_campaign','utm_medium']:
            if col in filtered.columns:
                filtered[col] = filtered[col].astype(str).str.strip().replace({'nan':'', 'None':''})

        if utm_sources_list:
            filtered = filtered[filtered['utm_source'].isin(utm_sources_list)]
        if utm_campaigns_list:
            filtered = filtered[filtered['utm_campaign'].isin(utm_campaigns_list)]
        if utm_mediums_list:
            filtered = filtered[filtered['utm_medium'].isin(utm_mediums_list)]

        # Merge email if exists
        payment_df = exported_frames.get("New Payment Made", pd.DataFrame()) if include_payment_event else pd.DataFrame()
        if not payment_df.empty and '$email' in payment_df.columns:
            filtered = filtered.merge(payment_df[['distinct_id','$email']].drop_duplicates(), on='distinct_id', how='left')

       
        use_case_df = exported_frames.get(conversion_event, pd.DataFrame())
        filtered['did_use_case'] = filtered['distinct_id'].isin(use_case_df.get('distinct_id', []))
        
        # Safe workspace payment filtering
        if not payment_df.empty and 'Amount Description' in payment_df.columns and 'distinct_id' in payment_df.columns:
            workspace_payment = payment_df[
                payment_df['distinct_id'].isin(filtered[filtered['did_use_case']]['distinct_id']) &
                (payment_df['Amount Description'].str.contains('Workspace Subscription', case=False, na=False))
            ]['distinct_id'].unique()
        else:
            workspace_payment = []
        
        filtered['did_payment'] = filtered['distinct_id'].isin(workspace_payment)
        filtered['did_use_case'] = filtered['did_use_case'].map({True:"Yes", False:"No"})
        filtered['did_payment'] = filtered['did_payment'].map({True:"Yes", False:"No"})

        # Payment aggregation
        payments_for_users = payment_df[payment_df['distinct_id'].isin(workspace_payment)].copy()
        if not payments_for_users.empty and 'Amount Description' in payments_for_users.columns and 'Amount' in payments_for_users.columns:
            payments_for_users['Amount'] = pd.to_numeric(payments_for_users['Amount'], errors='coerce').fillna(0)
            payments_for_users['Payment Detail'] = payments_for_users['Amount Description'] + " | $" + payments_for_users['Amount'].astype(str)
            payment_table = payments_for_users.groupby(['distinct_id','$email'], as_index=False).agg({
                'Amount':'sum',
                'Payment Detail': lambda x: list(x)
            }).rename(columns={'Amount':'Total_Payment'})
        else:
            payment_table = pd.DataFrame(columns=['distinct_id','$email','Total_Payment','Payment Detail'])

        # 3-step funnel chart
        funnel_counts = [
            (len(filtered), "Total Users"),
            ((filtered['did_use_case']=='Yes').sum(), conversion_event),
            ((filtered['did_payment']=='Yes').sum(), "Workspace Payment")
        ]
        fig = go.Figure(go.Bar(
            x=[label for _, label in funnel_counts],
            y=[count for count, _ in funnel_counts],
            text=[count for count, _ in funnel_counts],
            textposition='auto',
            marker_color='indianred'
        ))
        st.subheader("📊 3-Step Funnel")
        fig.update_layout(title='3-Step Funnel Visualization', xaxis_title='', yaxis_title='Number of Users')
        st.plotly_chart(fig, use_container_width=True)

        # 3-step funnel tables
        st.markdown("**User Table**")
        st.dataframe(filtered)
        st.markdown("**Payment Table**")
        st.dataframe(payment_table)
        total_revenue_3 = payment_table['Total_Payment'].sum() if not payment_table.empty else 0
        st.markdown(f"**Total Revenue:** ${total_revenue_3:,.2f}")

       
        if not payment_df.empty and 'Amount Description' in payment_df.columns:
            workspace_payment_2 = payment_df[
                payment_df['distinct_id'].isin(filtered['distinct_id']) &
                (payment_df['Amount Description'].str.contains('Workspace Subscription', case=False, na=False))
            ]['distinct_id'].unique()
        else:
            workspace_payment_2 = []
            
        filtered_2 = filtered.copy()
        filtered_2['payment_done'] = filtered_2['distinct_id'].isin(workspace_payment_2)
        filtered_2['payment_done'] = filtered_2['payment_done'].map({True:"Yes", False:"No"})
        if 'did_use_case' in filtered_2.columns:
            filtered_2.drop(columns=['did_use_case'], inplace=True)
        if 'did_payment' in filtered_2.columns:
            filtered_2.drop(columns=['did_payment'], inplace=True)

        payments_for_users_2 = payment_df[payment_df['distinct_id'].isin(workspace_payment_2)].copy()
        if not payments_for_users_2.empty and 'Amount Description' in payments_for_users_2.columns and 'Amount' in payments_for_users_2.columns:
            payments_for_users_2['Amount'] = pd.to_numeric(payments_for_users_2['Amount'], errors='coerce').fillna(0)
            payments_for_users_2['Payment Detail'] = payments_for_users_2['Amount Description'] + " | $" + payments_for_users_2['Amount'].astype(str)
            payment_table_2 = payments_for_users_2.groupby(['distinct_id','$email'], as_index=False).agg({
                'Amount':'sum',
                'Payment Detail': lambda x: list(x)
            }).rename(columns={'Amount':'Total_Payment'})
        else:
            payment_table_2 = pd.DataFrame(columns=['distinct_id','$email','Total_Payment','Payment Detail'])

        # 2-step funnel chart
        funnel_counts_2 = [
            (len(filtered_2), "Total Users"),
            ((filtered_2['payment_done']=='Yes').sum(), "Workspace Payment")
        ]
        fig2 = go.Figure(go.Bar(
            x=[label for _, label in funnel_counts_2],
            y=[count for count, _ in funnel_counts_2],
            text=[count for count, _ in funnel_counts_2],
            textposition='auto',
            marker_color='indianred'
        ))
        st.subheader("📊 2-Step Funnel")
        fig2.update_layout(title='2-Step Funnel Visualization', xaxis_title='', yaxis_title='Number of Users')
        st.plotly_chart(fig2, use_container_width=True)

        # 2-step funnel tables
        st.markdown("**User Table**")
        st.dataframe(filtered_2)
        st.markdown("**Payment Table**")
        st.dataframe(payment_table_2)
        total_revenue_2 = payment_table_2['Total_Payment'].sum() if not payment_table_2.empty else 0
        st.markdown(f"**Total Revenue:** ${total_revenue_2:,.2f}")