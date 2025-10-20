import streamlit as st
import sqlite3
import pandas as pd
import google.generativeai as genai
import os

genai.configure(api_key="AIzaSyCiFIl7N1gDKFbR8zK250wraed-Oyho_Dc")
st.set_page_config(page_title="Stock Watch List", page_icon="📈")

try:
    conn = sqlite3.connect("mystock.db")
    df = pd.read_sql_query(
        "SELECT stock_code, company_name_cn, company_name_en FROM watch_list", conn
    )
except sqlite3.Error as e:
    st.error(f"Database error: {e}")
    st.stop()
finally:
    if conn:
        conn.close()


df["display_text"] = (
    df["stock_code"] + " | " + df["company_name_en"] + " | " + df["company_name_cn"]
)


with st.form(key="watchlist_form"):
    selected_options = st.multiselect(
        label="Select stocks for your input:",
        options=df.to_dict("records"),
        format_func=lambda record: f'{record["display_text"]}',
    )

    submit_button = st.form_submit_button(label="Submit Selection")

if submit_button:
    if selected_options:
        st.success("Your selection has been submitted!")
        selected_display_texts = [record["display_text"] for record in selected_options]
        stocks_string = ", ".join(selected_display_texts)
        st.code(stocks_string)
        prompt = f"{stocks_string} 2025除權息日期"
        try:
            model = genai.GenerativeModel("gemini-2.5-flash")

            # Call the Gemini API with the combined prompt
            response = model.generate_content(prompt)

            # Display the combined response
            st.markdown(response.text)

        except Exception as e:
            st.error(f"Error calling Gemini API: {e}")
    else:
        st.info("Please select at least one stock.")
