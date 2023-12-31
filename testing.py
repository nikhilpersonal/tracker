import streamlit as st
import pandas as pd
import requests
import os
import base64
import re
from io import StringIO
import numpy as np
import subprocess
from streamlit_gsheets import GSheetsConnection
import matplotlib.pyplot as plt
import plotly.express as px


conn = st.connection("gsheets", type=GSheetsConnection)


# Function to encode the image
def encode_image(uploaded_image):
    return base64.b64encode(uploaded_image.read()).decode('utf-8')

# Helper function to parse the content string into a DataFrame
def parse_content_to_df(content):
    # Find the table inside the Markdown backticks
    
    lines = [line.strip() for line in content.strip().split('\n') if line.strip()]

    # Initialize an empty list to hold the data
    data = []

    # Process each line
    for line in lines:
        # Split the line by '|' and filter out empty strings
        columns = [col.strip() for col in line.split('|') if col.strip()]
        if columns:
            data.append(columns)

    # The first item in the list is the header
    header = data[0]

    # The rest are data rows
    rows = data[2:]  # We skip the second line as it is the separator

    # Create a DataFrame using the header and rows
    df = pd.DataFrame(rows, columns=header)
    
    return df

# Function to analyze the image using GPT-4 Vision API
def analyze_image_and_get_wager_results(uploaded_image):
    # Replace "YOUR_OPENAI_API_KEY" with your actual OpenAI API key
    
    api_key = st.secrets.OPENAI_API_KEY
    base64_image = encode_image(uploaded_image)
    org = st.secrets.ORG_ID

    headers = {
      "Content-Type": "application/json",
      "Authorization": f"Bearer {api_key}",
      "OpenAI-Organization": f"{org}"
    }

    prompt = "Analyze the image and provide the results in a table with columns 'Amount Wagered' and 'Amount Won' and 'Date'. DO NOT INCLUDE ANYTHING ELSE IN THE RESPONSE EXCEPT THE TABLE"

    payload = {
      "model": "gpt-4-vision-preview",
      "messages": [
        {
          "role": "user",
          "content": [
            {
              "type": "text",
              "text": prompt
            },
            {
              "type": "image_url",
              "image_url": {
                "url": f"data:image/jpeg;base64,{base64_image}"
              }
            }
          ]
        }
      ],
      "max_tokens": 300
    }

    response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)

    # Parse the response to extract the table content
    content = response.json()["choices"][0]["message"]["content"]
    wager_results_df = parse_content_to_df(content)
    
    return content

# Path to CSV file for persisting data
csv_file_path = "betting_results.csv"
active_user = "Example"

# Function to save bet results to CSV
def save_results_to_csv(df):
    try:
        df1 = conn.read(worksheet = active_user, usecols = [0,1])
        df1 = df1.dropna()
        df = pd.concat([df1, df], ignore_index=True)
        df = conn.update(worksheet = active_user, data = df)
        st.cache_data.clear()


    except:
        df = conn.create(worksheet = active_user, data = df)
        
    # if not os.path.isfile(csv_file_path):
    #     # Create a new DataFrame and CSV file if it doesn't exist
    #     df.to_csv(csv_file_path, index=False)
    # else:
    #     # Otherwise, append to the existing CSV file
    #     df.to_csv(csv_file_path, mode='a', header=False, index=False)

# Function to read and summarize the CSV data
def summarize_csv_data():
    try:
        df = conn.read(worksheet = active_user, usecols = [0,1])
        df = df.dropna()
        df['result'] = np.where(df['Amount Won']>df['Amount Wagered'], 1, 0)
        total_wagered = df["Amount Wagered"].sum()
        total_won = df["Amount Won"].sum()
        record = df['result'].sum()
        count = df['Amount Wagered'].count()
        return total_wagered, total_won, record, count
    except:
        return 0, 0, 0, 0  # Return 0 if the CSV file does not exist

def columns(total_wagered,total_won,record,count):
    col1, col2= st.columns(2)
    with col1:
        st.metric(label = "Total Amount Wagered", value = "$" + str(total_wagered))
    with col2:
        st.metric(label = "Total Won", value = "$" + str(total_won))

    col3, col4 = st.columns(2)
    with col3:
        st.metric(label = "Lifetime Record",  value =str(record)+ "-" +str(count))
    
    with col4:
        profit = total_won-total_wagered
        st.metric(label = "Profit", value =f"${profit}")
        
    col5, col6 = st.columns(2)
    
    with col5:
        t = st.number_input("Unit Size", value = 5)
      
    with col6: 
        try:
            s = total_won/t
            s = round(s,2)
            st.metric(label = "units up/down", value = (f" {s} u "))
        except:
            s= 0
            st.metric(label = "units up/down", value = str(s) + " u") 


def rename(option):
    global csv_file_path
    csv_file_path = option + "_betting_results.csv"
    
    global active_user
    active_user = option
    st.cache_data.clear()

def usernames():
    df = conn.read(worksheet = "usernames.csv", usecols=[0])
    df = df.dropna()
    new_user_df = pd.DataFrame([['New User']], columns=['Name'])
    df = pd.concat([df, new_user_df], ignore_index=True)
    return df
    
def add_new_user(username, options):
    df = options
    df = df[((df.Name != 'New User'))]
    new_user = pd.DataFrame([[username]], columns=['Name'])
    df = pd.concat([df, new_user]).drop_duplicates().reset_index(drop=True)
    df = conn.update(worksheet = "usernames.csv", data = df)
    st.cache_data.clear()
    st.experimental_rerun()

def plot_cumulative_score(df):
    # Data cleaning and preparation as before
    df['Amount Wagered'] = df['Amount Wagered'].replace('[\$,]', '', regex=True).astype(float)
    df['Amount Won'] = df['Amount Won'].replace('[\$,]', '', regex=True).astype(float)
    df['Date'] = pd.to_datetime(df['Date'], format='%m/%d/%Y', errors='coerce')
    df = df.dropna(subset=['Date'])
    df['Score Differential'] = df['Amount Won'] - df['Amount Wagered']
    df['Cumulative Score Differential'] = df['Score Differential'].cumsum()
    df = df.sort_values(by='Date')

    # Use Plotly for an interactive plot with hover functionality
    fig = px.line(df, x='Date', y='Cumulative Score Differential', 
                  title='Cumulative Score Differential by Date',
                  labels={'Cumulative Score Differential': 'Cumulative Score Differential', 'Date': 'Date'},
                  markers=True)

    # Add a horizontal line at 0
    fig.add_hline(y=0, line_color='green', line_width=1.5)

    # Improve layout
    fig.update_layout(
        xaxis_title='Date',
        yaxis_title='Cumulative Score Differential',
        hovermode='x'
    )

    # Display the plot in Streamlit
    st.plotly_chart(fig, use_container_width=True)

def main():
   

    # Load existing usernames
    options = usernames()

    # Sidebar dropdown for user selection
    with st.sidebar:
        selected_user = st.selectbox('Select User', options['Name'])

        if selected_user == "New User":
            new_username = st.text_input("Enter your username")
            if st.button("Add User") and new_username:
                add_new_user(new_username, options)
                st.cache_data.clear()
                st.experimental_rerun()

        if st.button("Refresh Data"):
            st.cache_data.clear()
            

    rename(selected_user)
    
    st.title("Nikhil's Bet Tracker")
    st.subheader("Current User = " + active_user)
    
    # Upload image section
    uploaded_images = st.file_uploader("Upload one or multiple slips:", accept_multiple_files=True)
    
    # When the user uploads an image and clicks the 'Analyze' button
    if uploaded_images is not None:
        # Call the analyze_image function
        if st.button("Analyze Image"):
            for uploaded_image in uploaded_images:
                try:
                    content = analyze_image_and_get_wager_results(uploaded_image)
                    df = parse_content_to_df(content)
                    save_results_to_csv(df)
                    
                    st.write("Bet Results:")
                    st.write(content)
                except:
                    st.write("no image")
        # Create a DataFrame
        

        # Save the DataFrame to CSV
        

        # Show the analysis results
        
    # Display the cumulative summary table
    
    total_wagered, total_won, record, count = summarize_csv_data()

    columns(total_wagered,total_won,record,count)

    i = 0
    with st.expander("Full Results"):
        try:
            results = conn.read(worksheet = active_user)
            results = results.dropna()
            st.write(results) 
            i = 1
        except: 
            st.write("No Data")    
    
    
    
    if i == 1:
        plot_cumulative_score(results)





if __name__ == "__main__":
    main()
