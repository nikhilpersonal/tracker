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

    prompt = "Analyze the image and provide the results in a table with columns 'Amount Wagered' and 'Amount Won'. DO NOT INCLUDE ANYTHING ELSE IN THE RESPONSE EXCEPT THE TABLE"

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

# Function to save bet results to CSV
def save_results_to_csv(df):
    if not os.path.isfile(csv_file_path):
        # Create a new DataFrame and CSV file if it doesn't exist
        df.to_csv(csv_file_path, index=False)
    else:
        # Otherwise, append to the existing CSV file
        df.to_csv(csv_file_path, mode='a', header=False, index=False)

# Function to read and summarize the CSV data
def summarize_csv_data():
    if os.path.isfile(csv_file_path):
        df = pd.read_csv(csv_file_path)
        df['Amount Wagered'] = df['Amount Wagered'].str.replace('$', '').astype(float).astype(int)
        df['Amount Won'] = df['Amount Won'].str.replace('$', '').astype(float).astype(int)
        df['result'] = np.where(df['Amount Won']>df['Amount Wagered'], 1, 0)
        total_wagered = df["Amount Wagered"].sum()
        total_won = df["Amount Won"].sum()
        record = df['result'].sum()
        count = df['Amount Wagered'].count()
        return total_wagered, total_won, record, count
    else:
        return 0, 0, 0, 0  # Return 0 if the CSV file does not exist

 


def rename(option):
    global csv_file_path
    csv_file_path = option + "_betting_results.csv"


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

def save_to_github(df, filename):
    # Save DataFrame to CSV in the local git repository
    df.to_csv(filename, index=False)

    # Git commands to commit and push the changes
    try:
        subprocess.run(['git', 'add', filename], check=True)
        subprocess.run(['git', 'commit', '-m', f'Update {filename}'], check=True)
        subprocess.run(['git', 'push'], check=True)
        return True
    except subprocess.CalledProcessError as e:
        print("Error with git operation:", e)
        return False


def main():
    st.title("Nikh's Bet Tracker")

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

    
            

    rename(selected_user)
    
    # Upload image section
    uploaded_image = st.file_uploader("Upload an image", type=["jpg", "jpeg", "png"])
    if uploaded_image is not None:
        st.image(uploaded_image, width = 250)
    # When the user uploads an image and clicks the 'Analyze' button
    if uploaded_image is not None and st.button("Analyze Image"):
        # Call the analyze_image function
        
        content = analyze_image_and_get_wager_results(uploaded_image)
        st.write(content)
        # Create a DataFrame
        df = parse_content_to_df(content)

        # Save the DataFrame to CSV
        save_results_to_csv(df)

        # Show the analysis results
        st.write("Analysis Results:")
        
        #st.dataframe(wager_results_df)

    # Display the cumulative summary table
    
    total_wagered, total_won, record, count = summarize_csv_data()

    col1, col2= st.columns(2)
    with col1:
        st.metric(label = "Total Amount Wagered", value = "$" + str(total_wagered))
    with col2:
        st.metric(label = "Total Won", value = "$" + str(total_won))
    
    st.metric(label = "Lifetime Record",  value =str(record)+ "-" +str(count))

    with st.expander("Full Results"):
        if os.path.isfile(csv_file_path):
            results = pd.read_csv(csv_file_path)
            st.write(results)  
        else: 
            st.write("No Data")    
    
if __name__ == "__main__":
    main()
