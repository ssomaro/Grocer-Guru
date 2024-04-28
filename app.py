# Importing required functions 
from distutils.log import debug 
from fileinput import filename 
from flask import *  
from pdf2image import convert_from_path
import json
import base64
import requests
import os
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.server_api import ServerApi
import pandas as pd
import plotly.express as px
import plotly.io as pio
from flask_cors import CORS



load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MONGO_URI = os.getenv("MONGO_URI")

app = Flask(__name__)
CORS(app)

def encode_image(image_path):
  with open(image_path, "rb") as image_file:
    return base64.b64encode(image_file.read()).decode('utf-8')
  
def get_data_from_image(filename):
    base64_image = encode_image(filename)
    headers = {  "Content-Type": "application/json","Authorization": f"Bearer {OPENAI_API_KEY}"}
    payload = {
    "model": "gpt-4-turbo",
    "messages": [
        {
        "role": "user",
        "content": [
            {
            "type": "text",
            "text": ''' Please extract the following information from the receipt: the item bought, its upc and a link ( the method to geneate the is link is given below) 
            and output the information in a structured json format. The receipt is attached below.the link can be generate by using this example if the item name is 'Kroger Grade A Large White Eggs' and upc is UPC: 0001111060933 
            the link is 'https://www.kroger.com/p/kroger-grade-a-large-white-eggs/0001111060933?searchType=suggestions'. give proper json dont give any '\n' in the json
            the json format is 
            {
    "items": [
        {
        "name": "name1",
        "upc": "upc1",
        "link": "https://www.kroger.com/p/ make appropriate link"
        },
        {
        "name": "name2",
        "upc": "upc2",
        "link": "https://www.kroger.com/p/ make appropriate link"
        }
        ]
        }
        dont give any other text just the json no other text and close the json properly
            '''
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
    "max_tokens": 2000
    }
    print('jj')
    response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
    items_json = response.json()['choices'][0]['message']['content']
    items = json.loads(items_json)
    upc_list = [item["upc"] for item in items["items"]]
    name_list = [item["name"] for item in items["items"]]
    print(upc_list)
    data = []
      # Create a new client and connect to the server
    client = MongoClient(MONGO_URI, server_api=ServerApi('1'))
    print('jj')
    # Specify the database and collection
    db = client["nutritionalValue"]
    collection = db["scrapedData_v2"]
    
    for upc in upc_list:
        query_result = collection.find_one({"UPC": upc})
        if query_result:
            data.append(query_result)
    df = pd.DataFrame(data)
    print(df)
    df.to_csv('data_final1.csv')
    
    print('ss')
    return items

@app.route('/get_summary_text')
def get_summary():
    ddf =pd.read_csv('data_final1.csv')
    text_table = ddf.to_string(index=False)
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI_API_KEY}"
    }
    payload = {
        "model": "gpt-3.5-turbo",
        "messages": [
            {
            "role": "user",
            "content":f''' The following is a content of nutritional values for various food items:\n\n{text_table}\n\nPlease provide a summary of items. be specific and mention items.
              an example summay gives an one line overview on how health the items are and then commention on few nutriients that are in excessive or are lacking and make few specific recommendations"
              keep in mind that this is an executive summary of an app that analyses the grocery items of a person and provides a summary of the nutritional values of the items in the grocery list.
              dont be generic. it is a executive summary keep it professional and it is the start of the webpage so it should be engaging and informative. give one whole paragraph of summary, dont mention "product name not found"
            '''
            }
        ],
        "max_tokens": 2000
    }

    # API request
    response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)

    # Extract and print the JSON response
    items_json = response.json()
    summary = items_json['choices'][0]['message']['content']
    return jsonify(summary)


@app.route('/plots')
def index():
    return render_template('plots.html')

@app.route('/nutritional_summary')
def nutritional_summary():
    ddf =pd.read_csv('data_final1.csv')
    # Get the aggregated data similar to the pie chart
    aggregated_values = ddf[['Calories', 'Total Fat (g)', 'Cholesterol (mg)','Total Carbohydrate (g)', 'Dietary Fiber (g)', 'Sugar (g)', 'Protein (g)','Sodium (mg)',]].sum()
    # Convert it into a list of dictionaries
    nutrients = [{'nutrient': nutrient, 'amount': float(amount)} for nutrient, amount in aggregated_values.items()]
    return jsonify(nutrients)

@app.route('/', methods=['GET', 'POST'])
def homepage():
    return render_template('home.html')
    

@app.route('/submit', methods=['GET', 'POST'])
def submit():
    if request.method == 'POST' :
        print('hi')
        f = request.files['file'] 
        f.save(f.filename)
        #get filename
        filename = f.filename
        images = convert_from_path(filename)
        images[0].save('page1' +'.jpg', 'JPEG')
        get_data_from_image('page1.jpg')
        render_template('plots.html')
        return render_template('plots.html')

def process_pdf(filepath):
    # Placeholder function for PDF processing logic
    print(f"Processing PDF at {filepath}")
    # Implement your PDF processing here using PyPDF2 or pdfplumber

@app.route('/macros_pie_chart')
def macros_pie_chart():
    ddf =pd.read_csv('data_final1.csv')
    macros = ddf[['Total Fat (g)', 'Saturated Fat (g)', 'Trans Fat (g)', 'Cholesterol (mg)',
                  'Total Carbohydrate (g)', 'Dietary Fiber (g)', 'Sugar (g)',
                 'Added Sugar (g)', 'Protein (g)']].sum().reset_index()
    macros.columns = ['Nutrient', 'Value']
    fig = px.pie(macros, values='Value', names='Nutrient')
    fig.update_layout(title="Macronutrient Composition of Food Items")
    return jsonify(pio.to_json(fig))


@app.route('/top_calories_bar')
def top_calories_bar():
    ddf =pd.read_csv('data_final1.csv')
    top_calories = ddf.nlargest(3, 'Calories')
    # Melt the DataFrame to long format for Plotly, excluding 'Sodium (mg)'
    top_calories_long = pd.melt(top_calories, id_vars=['product_name'], value_vars=[
        'Total Fat (g)',  'Cholesterol (mg)',
        'Total Carbohydrate (g)', 'Dietary Fiber (g)', 'Sugar (g)', 'Protein (g)'
    ], var_name='Nutrient', value_name='Amount')
    fig = px.bar(top_calories_long, x='Amount', y='product_name', color='Nutrient', orientation='h',
                 title="Top 3 Calorie-Rich Foods by Nutrient Composition")
    fig.update_layout(title="Top 3 Calorie-Rich Foods by Nutrient Composition", xaxis_title="Quantity", yaxis_title="Product Name")
    return jsonify(fig.to_json())

@app.route('/top_protein_bar')
def top_protein_bar():
    ddf =pd.read_csv('data_final1.csv')
    top_protein = ddf.nlargest(3, 'Protein (g)')
    # Melt the DataFrame to long format for Plotly, excluding 'Sodium (mg)'
    top_protein_long = pd.melt(top_protein, id_vars=['product_name'], value_vars=[
        'Total Fat (g)',  'Cholesterol (mg)',
        'Total Carbohydrate (g)', 'Dietary Fiber (g)', 'Sugar (g)', 'Protein (g)'
    ], var_name='Nutrient', value_name='Amount')
    fig = px.bar(top_protein_long, x='Amount', y='product_name', color='Nutrient', orientation='h',
                 title="Top 3 Protein-Rich Foods by Nutrient Composition")
    fig.update_layout(title="Top 3 Protein-Rich Foods by Nutrient Composition", xaxis_title="Quantity", yaxis_title="Product Name")
    return jsonify(fig.to_json())

# Main Driver Function 
if __name__ == '__main__':
    app.run(debug=True)
